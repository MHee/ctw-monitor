"""Tide-gauge fetchers. Wrap vendor/margin_data.py; return hourly sea level in cm and, where
the gauge has a barometer, hourly air pressure in hPa. All indexes are tz-aware UTC, hourly,
stamped at the centre of the averaging interval (hh:00).

Provider notes (checked 2026-10-07):
- NOAA CO-OPS: `hourly_height` is the verified product and lags by weeks, so use 6-min
  `water_level` (verified where available, else preliminary) in 30-day requests and average
  to hourly. All configured CO-OPS gauges have `air_pressure`.
- CHS IWLS: `wlo` at SIXTY_MINUTES in 30-day windows (chart datum, m); `ap1` where listed.
- IOC SLSMF: ~1-min raw data in 10-day chunks; real-time, not quality-controlled.
- UHSLC fast delivery: hourly, cm.
Measured: CO-OPS 1 yr 5.6 s; CHS 90 d 1.5 s; IOC 30 d of 1-min data 18.9 s.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from itertools import pairwise

import numpy as np
import pandas as pd
import requests

from ..vendor import margin_data as md
from .base import SourceResult
from .cache import RawCache

HALF_HOUR = pd.Timedelta(minutes=30)


def hourly_centred(s: pd.Series, min_count: int) -> pd.Series:
    """Mean of sub-hourly samples in [hh:00 - 30 min, hh:00 + 30 min), stamped hh:00.
    Hours with fewer than min_count samples are NaN."""
    if s.empty:
        return pd.Series(dtype=float)
    x = s.astype(float).copy()
    x.index = x.index + HALF_HOUR
    g = x.resample("1h")
    h, n = g.mean(), g.count()
    h[n < min_count] = np.nan
    return h


def _chunks(start, end, days):
    edges = list(pd.date_range(start, end, freq=f"{days}D"))
    if not edges or edges[-1] < end:
        edges.append(pd.Timestamp(end))
    return list(pairwise(edges))


def _run(source_id, stations, work, workers=4) -> SourceResult:
    """Call work(station) -> (series_cm, pressure_hpa | None, meta) for each station in a
    thread pool. Per-station failures are recorded; the source fails only if all fail."""
    res = SourceResult(source_id)

    def one(st):
        try:
            return st, work(st), None
        except Exception as e:  # noqa: BLE001 -- one bad station must not sink the source
            return st, None, f"{type(e).__name__}: {e}"[:200]

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for st, out, err in ex.map(one, stations):
            sid = st["id"]
            if err is None and (out[0] is None or out[0].dropna().empty):
                err = "no data in window"
            if err is not None:
                res.errors[sid] = err
                continue
            sl, p, meta = out
            res.series[sid] = sl
            if p is not None and not p.dropna().empty:
                res.air_pressure_hpa[sid] = p
            res.meta[sid] = meta
    if not res.series:
        raise RuntimeError("no station returned data: "
                           + "; ".join(f"{k}: {v}" for k, v in res.errors.items())[:250])
    return res


def _noaa_request(sid, a, b, product, waits=(10, 30, 90)):
    """One CO-OPS request, pausing briefly; CO-OPS answers bursts with HTTP 403 for a while
    (seen 2026-10-07 with 4 parallel workers), so back off and retry on 403."""
    for w in (*waits, None):
        try:
            time.sleep(0.3)
            return md.fetch_noaa_coops(sid, a, b, product=product)
        except requests.HTTPError as e:
            if w is None or e.response is None or e.response.status_code != 403:
                raise
            time.sleep(w)
    raise AssertionError("unreachable")


def fetch_noaa(stations: list[dict], start, end, cache: RawCache | None = None) -> SourceResult:
    cache = cache or RawCache(None)

    def get(sid, product, scale):
        def fetch(a, b):
            parts = [_noaa_request(sid, x, y, product) for x, y in _chunks(a, b, 30)]
            parts = [p for p in parts if not p.empty]
            if not parts:
                return pd.Series(dtype=float)
            raw = pd.concat(parts)
            raw = raw[~raw.index.duplicated()].sort_index()
            return hourly_centred(raw, min_count=5) * scale
        return fetch

    def work(st):
        sid = st["provider_id"]
        sl = cache.get("noaa_coops", st["id"], start, end, get(sid, "water_level", 100.0))
        p = None
        if st.get("pressure") == "station":
            p = cache.get("noaa_coops_ap", st["id"], start, end, get(sid, "air_pressure", 1.0))
        return sl, p, {"provider": "NOAA CO-OPS", "provider_id": sid,
                       "product": "6-min water_level averaged to hourly"}

    return _run("noaa_coops", stations, work, workers=2)


def fetch_chs(stations: list[dict], start, end, cache: RawCache | None = None) -> SourceResult:
    cache = cache or RawCache(None)

    def get(pid, code, scale):
        def fetch(a, b):
            s = md.fetch_chs_iwls(pid, a, b, code=code, resolution="SIXTY_MINUTES", window_days=30)
            if s.empty:
                return s
            return s.resample("1h").mean() * scale   # values already on the hour
        return fetch

    def work(st):
        pid = st["provider_id"]
        sl = cache.get("chs_iwls", st["id"], start, end, get(pid, "wlo", 100.0))
        p = None
        if st.get("pressure") == "station":
            p = cache.get("chs_iwls_ap", st["id"], start, end, get(pid, "ap1", 1.0))
        return sl, p, {"provider": "DFO-CHS IWLS", "provider_id": st.get("chs_code", pid)}

    return _run("chs_iwls", stations, work)


IOC_BUDGET_S = 20 * 60     # whole source, per run; the Actions job has 60 min for everything


def fetch_ioc(stations: list[dict], start, end, cache: RawCache | None = None,
              budget_s: float = IOC_BUDGET_S) -> SourceResult:
    """From GitHub runners IOC is slow and drops connections: a cold 400-day pull failed with
    4 workers and then ran past the 60-min job limit with 2 (2026-10-08). So: 10-day requests
    newest first with a short timeout, a time budget for the whole source, and the raw cache
    backfills older chunks on later nights. A chunk that still fails is skipped.

    Each station also gets an equal share of the budget (budget / stations): with one
    shared deadline the first stations in the config spent it all on backfill and the last
    four never started (2026-10-08). The newest chunk of each request ignores the share, so
    every station gets its recent data while the whole-source budget lasts."""
    cache = cache or RawCache(None)
    workers = 2
    deadline = time.monotonic() + budget_s
    share_s = budget_s / max(1, len(stations))      # conservative: ignores the parallel workers

    def work(st):
        code, sensor = st["provider_id"], st.get("sensor", "rad")
        failed_chunks, skipped = [], []
        st_deadline = min(deadline, time.monotonic() + share_s)

        def fetch(a, b):
            parts = []
            for i, (x, y) in enumerate(reversed(_chunks(a, b, 10))):
                if time.monotonic() > (deadline if i == 0 else st_deadline):
                    skipped.append(y.strftime("%Y-%m-%d"))
                    break
                time.sleep(1.0)
                try:
                    parts.append(md.ioc_sea_level(code, x, y, timeout=30, retries=2, pause_s=3))
                except (requests.RequestException, ValueError):   # network, or a non-JSON reply
                    failed_chunks.append(x.strftime("%Y-%m-%d"))
            parts = [p for p in parts if not p.empty]
            if not parts:
                return pd.Series(dtype=float)
            raw = pd.concat(parts)
            raw = raw[raw["sensor"] == sensor]
            if raw.empty:
                return pd.Series(dtype=float)
            # samples per hour vary by station (1-10 min); require half the typical count
            n = raw["slevel"].resample("1h").count()
            min_n = max(3, int(0.5 * np.median(n[n > 0])))
            raw = raw.copy()
            raw.index = raw.index + HALF_HOUR        # centre the hourly median on hh:00
            return md.ioc_hourly(raw, sensor, min_samples=min_n, to_cm=True)

        sl = cache.get("ioc", st["id"], start, end, fetch)
        meta = {"provider": "IOC SLSMF", "provider_id": code, "sensor": sensor, "not_qc": True}
        if failed_chunks:
            meta["failed_chunks"] = failed_chunks
        if skipped:
            meta["time_budget_reached_before"] = skipped[0]   # older data come on later nights
        return sl, None, meta

    return _run("ioc_slsmf", stations, work, workers=workers)


def fetch_uhslc(stations: list[dict], start, end, cache: RawCache | None = None) -> SourceResult:
    cache = cache or RawCache(None)

    def work(st):
        uid = st["provider_id"]

        def fetch(a, b):
            s = md.uhslc_fast_hourly(uid, a, b)
            if s.empty:
                return s
            s.index = s.index.as_unit("ns")
            return s.resample("1h").mean()

        sl = cache.get("uhslc", st["id"], start, end, fetch)
        return sl, None, {"provider": "UHSLC fast delivery", "provider_id": uid}

    return _run("uhslc_fast", stations, work)
