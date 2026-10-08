"""Nightly build: fetch -> process -> write, failing soft per source (CLAUDE.md rule 8).

Sea level from the tide gauges (M1); NEPTUNE bottom pressure and slope temperature from
ONC (M2). A failed source keeps its last good product, marked stale.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

from . import SCHEMA_VERSION, __version__
from .config import alongshore_km, enabled, load_config
from .process.steps import bottom_pressure_chain, gauge_chain, pressure_for
from .products.events import events_product
from .products.sealevel import hovmoller_product, stations_product
from .products.validate import validate_dir
from .products.writer import iso, timeseries_product, write_json
from .sources import context, onc, tide_gauges
from .sources.cache import RawCache
from .sources.onc import scrub

DEFAULT_TIDES = Path(".cache/tidal_constants.json")

# sea-level sources: (source id, fetch callable, provider in config/stations.yaml)
SEALEVEL_SOURCES = [
    ("noaa_coops", tide_gauges.fetch_noaa, "noaa_coops"),
    ("chs_iwls", tide_gauges.fetch_chs, "chs_iwls"),
    ("ioc_slsmf", tide_gauges.fetch_ioc, "ioc"),
    ("uhslc_fast", tide_gauges.fetch_uhslc, "uhslc"),
]

def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def load_constants(path: Path | str | None) -> dict:
    """Station id -> frozen tidal constants record, or {} if the file is missing."""
    if not path or not Path(path).exists():
        return {}
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return d.get("stations", {})


def load_drift(path: Path | str | None) -> dict:
    """Station id -> frozen bottom-pressure drift model (tides-fit output), or {}."""
    if not path or not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8")).get("drift", {})


def _last_good_series(last_good_dir, product: str) -> tuple[dict[str, pd.Series], dict]:
    """6-hourly series and meta from a previously deployed timeseries product."""
    if not last_good_dir or not (Path(last_good_dir) / product).exists():
        return {}, {}
    d = json.loads((Path(last_good_dir) / product).read_text(encoding="utf-8"))
    idx = pd.date_range(pd.Timestamp(d["t0"]), periods=d["n"], freq=pd.Timedelta(seconds=d["dt_s"]))
    vals = {k: pd.Series(np.array(v, dtype=float), index=idx) for k, v in d["values"].items()}
    return vals, d.get("meta", {})


def fetch_source(sid, fn, stations, start, now, cache) -> tuple[object | None, dict]:
    """Run one fetcher; return (SourceResult or None, manifest status entry). Never raises
    for data problems (rule 8); messages are scrubbed of tokens before they reach the site."""
    t = time.time()
    try:
        r = fn(stations, start, now, cache=cache)
    except Exception as e:  # noqa: BLE001 -- fail soft per source (rule 8), record why
        if not isinstance(e, (NotImplementedError, RuntimeError)):
            traceback.print_exc()
        msg = scrub(f"{type(e).__name__}: {e}")[:300]
        log(f"{sid}: failed after {time.time() - t:.0f}s: {msg}")
        return None, {"id": sid, "status": "failed", "message": msg}
    log(f"{sid}: {len(r.series)}/{len(stations)} stations in {time.time() - t:.0f}s"
        + (f"; errors {r.errors}" if r.errors else ""))
    st = {"id": sid, "status": "ok", "last_success": iso(now)}
    if r.last_observation is not None:
        st["last_observation"] = iso(r.last_observation)
    if r.errors:
        st["message"] = scrub(f"{len(r.errors)} of {len(stations)} stations missing: "
                              + "; ".join(f"{k}: {v}" for k, v in r.errors.items()))[:300]
    return r, st


def _fallback(product: str, out: Path, last_good_dir, status: dict) -> None:
    """Rule 8: reuse the whole last good product and mark the source stale."""
    if last_good_dir and (Path(last_good_dir) / product).exists():
        shutil.copy2(Path(last_good_dir) / product, out / product)
        status["status"] = "stale"


def build_bottom_pressure(cfg, out: Path, start, now, cache, constants, last_good_dir=None,
                          drift_models=None) -> dict:
    sts = [b for b in enabled(cfg["bottom_pressure"]) if b.get("location_code")]
    r, status = fetch_source("onc_bpr", onc.fetch_bottom_pressure, sts, start, now, cache)
    product = "bottom_pressure.json"
    if r is None:
        _fallback(product, out, last_good_dir, status)
        return status
    hourly = pd.date_range(start.floor("h"), now.floor("h"), freq="1h")
    idx6 = pd.date_range(start.ceil("6h"), now.floor("6h"), freq="6h")
    section = [b["id"] for b in sts if b.get("role") == "section"]
    refs = [b["id"] for b in sts if b.get("role") == "basin_ref"]
    try:
        devices = {k: v["devices"][-1]["deviceCode"] for k, v in r.meta.items() if v.get("devices")}
        series, m = bottom_pressure_chain({k: s.reindex(hourly) for k, s in r.series.items()},
                                          constants, section, refs, drift_models, devices)
    except ValueError as e:                       # no basin reference: rule 4 forbids writing
        status.update(status="failed", message=f"no basin reference: {e}"[:300])
        _fallback(product, out, last_good_dir, status)
        return status
    if not series:
        status.update(status="failed", message="no section gauge has data")
        _fallback(product, out, last_good_dir, status)
        return status
    values, meta = {}, {}
    for k in section:
        if k in series:
            v = series[k].reindex(idx6)
            values[k] = v.to_numpy()
            meta[k] = {**r.meta.get(k, {}), **m[k],
                       "last_valid": iso(v.last_valid_index()) if v.notna().any() else None}
    codes = {b["id"]: b["location_code"] for b in sts}
    used = ", ".join(codes[k] for k in m[next(iter(values))]["basin_reference"])
    days = round((now - start) / pd.Timedelta(days=1))
    frozen = [k for k in values if str(meta[k].get("drift", "")).startswith("frozen")]
    drift_note = ("instrument drift removed (frozen per-deployment fit)" if len(frozen) == len(values)
                  else f"instrument drift removed (frozen fit at {len(frozen)} of {len(values)} "
                       f"gauges, linear over the window elsewhere)")
    proc = (f"Seafloor pressure, hourly, detided (frozen tidal constants), minus the Cascadia Basin "
            f"reference ({used}), {drift_note}, Godin low-pass, minus the {days}-day mean; "
            f"cm of water (100.6 Pa/cm); not IB-corrected; 6-hourly")
    write_json(timeseries_product("bottom_pressure_anomaly", "cm", proc, idx6, values, meta),
               out / product)
    return status


def build_temperature(cfg, out: Path, start, now, cache, last_good_dir=None) -> dict:
    sts = enabled(cfg["temperature"])
    r, status = fetch_source("onc_ctd", onc.fetch_temperature, sts, start, now, cache)
    product = "temperature.json"
    if r is None:
        _fallback(product, out, last_good_dir, status)
        return status
    didx = pd.date_range(start.ceil("D"), now.floor("D") - pd.Timedelta(days=1), freq="1D")
    values, meta = {}, {}
    for st in sts:
        k = st["id"]
        if k not in r.series:
            continue
        v = r.series[k].reindex(didx)
        v = v - v.mean()                           # TODO(M4): minus the day-of-year baseline
        values[k] = v.to_numpy()
        meta[k] = {**r.meta.get(k, {}), "depth_m": st["depth_m"],
                   "last_valid": iso(v.last_valid_index()) if v.notna().any() else None}
    days = round((now - start) / pd.Timedelta(days=1))
    proc = (f"CTD temperature, daily mean, minus the {days}-day mean "
            f"(no day-of-year baseline yet); degC")
    write_json(timeseries_product("temperature_anomaly", "degC", proc, didx, values, meta,
                                  ndigits=3), out / product)
    return status


def build_sealevel(cfg, out: Path, start, now, cache: RawCache, constants: dict,
                   last_good_dir=None) -> list[dict]:
    gauges = enabled(cfg["tide_gauges"])
    by_id = {g["id"]: g for g in gauges}
    statuses, results, missing = [], [], {}
    for sid, fn, prov in SEALEVEL_SOURCES:
        sts = [g for g in gauges if g["provider"] == prov]
        if not sts:
            continue
        r, st = fetch_source(sid, fn, sts, start, now, cache)
        statuses.append(st)
        if r is None:
            missing.update({g["id"]: sid for g in sts})
            continue
        results.append(r)
        missing.update({k: sid for k in r.errors})

    hourly = pd.date_range(start.floor("h"), now.floor("h"), freq="1h")
    idx6 = pd.date_range(start.ceil("6h"), now.floor("6h"), freq="6h")
    coords = {g["id"]: (g["lat"], g["lon"]) for g in gauges}
    pressures = {k: v.reindex(hourly) for r in results for k, v in r.air_pressure_hpa.items()}
    values, meta, hourly_lp = {}, {}, {}
    for r in results:
        for k, s in r.series.items():
            try:
                p, ib_src = pressure_for(by_id[k], pressures, coords, hourly)
                lp, m = gauge_chain(s.reindex(hourly), p, constants.get(k))
            except Exception as e:  # noqa: BLE001 -- one bad series must not sink the product
                traceback.print_exc()
                missing[k] = r.source_id
                log(f"{k}: processing failed: {e}")
                continue
            hourly_lp[k] = lp.reindex(hourly)
            v = lp.reindex(idx6)
            values[k] = v.to_numpy()
            meta[k] = {**r.meta.get(k, {}), **m, "ib_source": ib_src,
                       "last_valid": iso(v.last_valid_index()) if v.notna().any() else None}

    # rule 8: stations we could not refresh keep their last good values, marked stale
    lg_vals, lg_meta = _last_good_series(last_good_dir, "sealevel.json")
    stale_sources = set()
    for k, src in missing.items():
        if k in lg_vals:
            values[k] = lg_vals[k].reindex(idx6).to_numpy()
            meta[k] = {**lg_meta.get(k, {}), "stale": True}
            hourly_lp[k] = (lg_vals[k].reindex(lg_vals[k].index.union(hourly))
                            .interpolate(limit=5, limit_area="inside").reindex(hourly))
            stale_sources.add(src)
    for st in statuses:
        if st["status"] == "failed" and st["id"] in stale_sources:
            st["status"] = "stale"

    dist = alongshore_km(gauges, cfg)
    write_json(stations_product(cfg, dist), out / "stations.json")
    if len(values) < 2:
        log("sealevel: fewer than two gauges; product not written")
        return statuses
    order = sorted(values, key=lambda k: dist[k])
    values = {k: values[k] for k in order}
    meta = {k: {**meta[k], "alongshore_km": dist[k]} for k in order}
    n_frozen = sum(1 for k in order if str(meta[k].get("tide_source", "")).startswith("frozen"))
    tide_note = ("frozen tidal constants" if n_frozen == len(order) else
                 f"frozen tidal constants at {n_frozen} of {len(order)} gauges, window fit elsewhere")
    days = round((now - start) / pd.Timedelta(days=1))
    proc = (f"Hourly, despiked, detided ({tide_note}), IB-corrected with the gauge's or nearest "
            f"barometer (Mexico and Central America: not IB-corrected), Godin low-pass, minus the "
            f"{days}-day mean (no climatology baseline yet); 6-hourly")
    write_json(timeseries_product("sealevel_anomaly", "cm", proc, idx6, values, meta),
               out / "sealevel.json")
    write_json(hovmoller_product(values, idx6, dist, cfg["coastal_path"]["gap_mask_km"], proc),
               out / "hovmoller.json")
    ev = events_product({k: hourly_lp[k] for k in order if k in hourly_lp}, dist)
    write_json(ev, out / "events.json")
    log(f"events: {len(ev['events'])} ({sum(e['propagating'] for e in ev['events'])} "
        f"propagating, {sum(e['major'] for e in ev['events'])} major)")
    return statuses


def build_context(cfg, out: Path, now, last_good_dir=None) -> dict:
    """NOAA CPC ONI and RONI for the context panel. Context only; fails soft like any source.
    An index that fails keeps its last good value (marked stale) when there is one."""
    product = "context.json"
    lg_path = Path(last_good_dir) / product if last_good_dir else None
    last = json.loads(lg_path.read_text(encoding="utf-8")) if lg_path and lg_path.exists() else {}
    fetchers = {"oni": (context.fetch_oni, cfg["context"]["oni_url"]),
                "roni": (context.fetch_roni, cfg["context"]["roni_url"])}
    got, errors = {}, {}
    for key, (fn, url) in fetchers.items():
        try:
            got[key] = {**fn(url), "fetched": iso(now)}
            log(f"noaa_cpc {key}: {got[key]['season']} {got[key]['year']} "
                f"{got[key]['anomaly_c']:+.2f}")
        except Exception as e:  # noqa: BLE001 -- fail soft per source (rule 8)
            errors[key] = scrub(f"{type(e).__name__}: {e}")[:140]
            log(f"noaa_cpc {key}: failed: {errors[key]}")
            if key in last:
                got[key] = {**last[key], "stale": True}
    status = {"id": "noaa_oni", "status": "ok" if not errors else "stale",
              "last_success": iso(now)}
    if errors:
        status["message"] = "; ".join(f"{k.upper()}: {v}" for k, v in errors.items())[:300]
    if "oni" not in got:                    # the product needs ONI (context.schema.json)
        status.update(status="failed")
        status.pop("last_success")
        _fallback(product, out, last_good_dir, status)
        return status
    write_json({"schema_version": SCHEMA_VERSION, **got}, out / product)
    return status


def run_build(out_dir, cache_dir=".cache/raw", last_good_dir=None, full=False, days=400,
              tides_path=DEFAULT_TIDES):
    cfg = load_config()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    now = pd.Timestamp.now(tz="UTC").floor("h")
    start = now - pd.Timedelta(days=days)
    cache = RawCache(cache_dir, full=full)
    constants = load_constants(tides_path)
    drift_models = load_drift(tides_path)
    log(f"tidal constants: {len(constants)} stations from {tides_path}")
    statuses = build_sealevel(cfg, out, start, now, cache, constants, last_good_dir)
    statuses.append(build_bottom_pressure(cfg, out, start, now, cache, constants, last_good_dir,
                                          drift_models))
    statuses.append(build_temperature(cfg, out, start, now, cache, last_good_dir))
    statuses.append(build_context(cfg, out, now, last_good_dir))
    manifest = {
        "schema_version": SCHEMA_VERSION, "generated_at": iso(now), "synthetic": False,
        "pipeline": {"version": __version__, "git_sha": os.environ.get("GITHUB_SHA", "local")[:12]},
        "window": {"start": iso(start), "end": iso(now)},
        "sources": statuses,
        "products": sorted(p.name for p in out.glob("*.json") if p.name != "manifest.json"),
    }
    write_json(manifest, out / "manifest.json")
    problems = validate_dir(out)
    if problems:
        raise SystemExit("schema validation failed:\n" + "\n".join(problems))
    return manifest
