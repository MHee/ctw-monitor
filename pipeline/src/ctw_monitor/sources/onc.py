"""ONC Oceans 3.0 fetchers (M2). Token from ONC_API_TOKEN via vendor.onc_api; never logged.

Devices are found at run time from /deployments (location + device category), so swaps
are handled and config needs no device codes. Each deployment overlapping the window is
fetched with /scalardata/device at resamplePeriod=900 (ONC's precomputed 15-min table:
seconds per device-year), averaged to hourly values centred on hh:00 (bottom pressure) or
to daily means (CTD temperature). Channels are chosen by sensorName, never by
sensorCategoryCode (the codes are not a vocabulary; see the onc-oceans3-api skill).

Facts (tested Oct 2026): errorCode 127 for a window outside a deployment means "no data";
chunk by year (multi-year requests time out at 120 s); qaqcFlag {1, 2, 7} is good.
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

from ..vendor.onc_api import ONC_API, onc_token
from .base import SourceResult
from .cache import RawCache, empty_series
from .tide_gauges import hourly_centred

GOOD_FLAGS = {1, 2, 7}
DBAR_TO_PA = 1.0e4
CHUNK = pd.Timedelta(days=365)
# preferred seafloor-pressure channel names, in order; anything raw/reference/compromised is out
PRESSURE_NAMES = ["Seafloor Pressure", "AZA Seafloor Pressure", "Pressure"]
PRESSURE_EXCLUDE = re.compile(r"raw|reference|uncompensated|compromised|residual", re.IGNORECASE)
TEMPERATURE_NAMES = ["Temperature"]


class NoData(Exception):
    """ONC errorCode 127 for the requested window: no data, not a failure."""


def scrub(msg: str) -> str:
    """Remove the token from any text that may end up in logs or manifest.json (rule 7)."""
    msg = re.sub(r"(token=)[^&\s'\"]+", r"\1***", str(msg))
    try:
        tok = onc_token()
    except RuntimeError:
        return msg
    return msg.replace(tok, "***")


def api_get(path: str, timeout: int = 120, retries: int = 2, **params) -> dict | list:
    """GET /api/<path> with the token. Raises NoData on errorCode 127, RuntimeError (scrubbed)
    on other errors. Never lets a URL with the token escape in an exception message."""
    p = {**params, "token": onc_token()}
    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(f"{ONC_API}/{path}", params=p, timeout=timeout)
        except requests.RequestException as e:
            last = RuntimeError(f"ONC {path}: {type(e).__name__}")   # message may hold the URL
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 200:
            return r.json()
        try:
            errs = r.json().get("errors", [])
        except ValueError:
            errs = []
        if any(e.get("errorCode") == 127 for e in errs) and r.status_code == 400:
            raise NoData(path)
        detail = "; ".join(f"{e.get('errorCode')}: {e.get('errorMessage')}" for e in errs)
        last = RuntimeError(scrub(f"ONC {path} -> HTTP {r.status_code}: {detail or r.text[:200]}"))
        if r.status_code < 500:
            break
        time.sleep(5 * (attempt + 1))
    raise last


def deployments(location_code: str, device_category: str, start, end) -> list[dict]:
    """Deployments at a location overlapping [start, end], oldest first."""
    deps = api_get("deployments", locationCode=location_code, deviceCategoryCode=device_category)
    out = []
    for d in deps:
        a = pd.Timestamp(d["begin"])
        b = pd.Timestamp(d["end"]) if d.get("end") else pd.Timestamp(end)
        if a < pd.Timestamp(end) and b > pd.Timestamp(start):
            out.append({"deviceCode": d["deviceCode"], "begin": max(a, pd.Timestamp(start)),
                        "end": min(b, pd.Timestamp(end))})
    return sorted(out, key=lambda d: d["begin"])


def pick_sensor(sensor_data: list[dict], names: list[str], exclude=None) -> dict | None:
    by_name = {s.get("sensorName", ""): s for s in sensor_data}
    for n in names:
        s = by_name.get(n)
        if s is not None and not (exclude and exclude.search(n)):
            return s
    return None


def sensor_series(sensor: dict) -> pd.Series:
    """Per-interval records -> Series of good values (qaqcFlag in GOOD_FLAGS)."""
    rows = [(r["sampleTime"], r["value"]) for r in sensor.get("data", [])
            if r.get("value") is not None and r.get("qaqcFlag") in GOOD_FLAGS]
    if not rows:
        return empty_series()
    t, v = zip(*rows, strict=True)
    s = pd.Series(np.asarray(v, dtype=float), index=pd.DatetimeIndex(pd.to_datetime(t, utc=True)))
    s.index = s.index.as_unit("ns")
    return s[~s.index.duplicated()].sort_index()


def device_series(device_code: str, start, end, names, exclude=None, period=900) -> tuple[pd.Series, str]:
    """One channel of one device over [start, end], chunked by year, following `next` pages.
    Returns (series in the API's unit, sensorName used)."""
    parts, used = [], ""
    a = pd.Timestamp(start)
    while a < pd.Timestamp(end):
        b = min(a + CHUNK, pd.Timestamp(end))
        params = {"deviceCode": device_code, "dateFrom": a.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                  "dateTo": b.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "outputFormat": "object",
                  "resampleType": "avg", "resamplePeriod": period, "metadata": "Full",
                  "rowLimit": 100000}
        while params:
            try:
                j = api_get("scalardata/device", **params)
            except NoData:
                break
            s = pick_sensor(j.get("sensorData") or [], names, exclude)
            if s is not None:
                used = s.get("sensorName", "")
                parts.append(sensor_series(s))
            nxt = j.get("next")
            params = dict(nxt["parameters"]) if nxt and nxt.get("parameters") else None
            if params:
                params.pop("token", None)
        a = b
    parts = [p for p in parts if not p.empty]
    if not parts:
        return empty_series(), used
    s = pd.concat(parts).sort_index()
    return s[~s.index.duplicated()], used


def _location_series(st, category, start, end, names, exclude, to_series):
    """Stitch every deployment at a location over the window into one series."""
    deps = deployments(st["location_code"], category, start, end)
    if not deps:
        return empty_series(), {"devices": []}
    parts, used = [], []
    for d in deps:
        raw, name = device_series(d["deviceCode"], d["begin"], d["end"], names, exclude)
        if raw.empty:
            continue
        parts.append(to_series(raw))
        used.append({"deviceCode": d["deviceCode"], "sensorName": name,
                     "from": d["begin"].strftime("%Y-%m-%d")})
    if not parts:
        return empty_series(), {"devices": used}
    s = pd.concat(parts).sort_index()
    return s[~s.index.duplicated(keep="last")], {"devices": used}


def _run(source_id, stations, work, workers=3) -> SourceResult:
    onc_token()   # fail the whole source early (and softly) if there is no token
    res = SourceResult(source_id)

    def one(st):
        try:
            return st, work(st), None
        except Exception as e:  # noqa: BLE001 -- one bad station must not sink the source
            return st, None, scrub(f"{type(e).__name__}: {e}")[:200]

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for st, out, err in ex.map(one, stations):
            if err is None and out[0].dropna().empty:
                err = "no data in window"
            if err is not None:
                res.errors[st["id"]] = err
                continue
            res.series[st["id"]], res.meta[st["id"]] = out
    if not res.series:
        raise RuntimeError("no station returned data: "
                           + "; ".join(f"{k}: {v}" for k, v in res.errors.items())[:250])
    return res


def fetch_bottom_pressure(stations: list[dict], start, end, cache: RawCache | None = None) -> SourceResult:
    """Hourly seafloor pressure in Pa per station (BPRs and CORK seafloor gauges)."""
    cache = cache or RawCache(None)

    def work(st):
        meta = {}

        def fetch(a, b):
            s, m = _location_series(st, st.get("device_category", "BPR"), a, b,
                                    [st["sensor_name"]] if st.get("sensor_name") else PRESSURE_NAMES,
                                    PRESSURE_EXCLUDE,
                                    lambda raw: hourly_centred(raw, min_count=3) * DBAR_TO_PA)
            meta.update(m)
            return s
        s = cache.get("onc_bpr", st["id"], start, end, fetch)
        return s, {"provider": "ONC Oceans 3.0", **meta}

    return _run("onc_bpr", stations, work)


def fetch_temperature(stations: list[dict], start, end, cache: RawCache | None = None) -> SourceResult:
    """Daily mean seawater temperature (degC) per CTD location."""
    cache = cache or RawCache(None)

    def work(st):
        meta = {}

        def fetch(a, b):
            s, m = _location_series(st, st.get("device_category", "CTD"), a, b, TEMPERATURE_NAMES,
                                    None, lambda raw: raw.resample("1D").mean())
            meta.update(m)
            return s
        s = cache.get("onc_ctd", st["id"], start, end, fetch)
        return s, {"provider": "ONC Oceans 3.0", **meta}

    return _run("onc_ctd", stations, work)
