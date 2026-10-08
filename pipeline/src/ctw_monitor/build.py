"""Nightly build: fetch -> process -> write, failing soft per source (CLAUDE.md rule 8).

Sea level (M1) is built from the tide-gauge sources. Bottom pressure and temperature (M2)
are still stubs: they record each source as failed and reuse last-good products if present.
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
from .process.steps import gauge_chain, pressure_for
from .products.sealevel import hovmoller_product, stations_product
from .products.validate import validate_dir
from .products.writer import iso, timeseries_product, write_json
from .sources import onc, tide_gauges
from .sources.cache import RawCache

DEFAULT_TIDES = Path(".cache/tidal_constants.json")

# sea-level sources: (source id, fetch callable, provider in config/stations.yaml)
SEALEVEL_SOURCES = [
    ("noaa_coops", tide_gauges.fetch_noaa, "noaa_coops"),
    ("chs_iwls", tide_gauges.fetch_chs, "chs_iwls"),
    ("ioc_slsmf", tide_gauges.fetch_ioc, "ioc"),
    ("uhslc_fast", tide_gauges.fetch_uhslc, "uhslc"),
]

# product file -> list of (source id, fetch callable, config section, provider filter)
PLAN = {
    "bottom_pressure.json": [("onc_bpr", onc.fetch_bottom_pressure, "bottom_pressure", None)],
    "temperature.json": [("onc_ctd", onc.fetch_temperature, "temperature", None)],
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def load_constants(path: Path | str | None) -> dict:
    """Station id -> frozen tidal constants record, or {} if the file is missing."""
    if not path or not Path(path).exists():
        return {}
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return d.get("stations", {})


def _last_good_series(last_good_dir, product: str) -> tuple[dict[str, pd.Series], dict]:
    """6-hourly series and meta from a previously deployed timeseries product."""
    if not last_good_dir or not (Path(last_good_dir) / product).exists():
        return {}, {}
    d = json.loads((Path(last_good_dir) / product).read_text(encoding="utf-8"))
    idx = pd.date_range(pd.Timestamp(d["t0"]), periods=d["n"], freq=pd.Timedelta(seconds=d["dt_s"]))
    vals = {k: pd.Series(np.array(v, dtype=float), index=idx) for k, v in d["values"].items()}
    return vals, d.get("meta", {})


def build_sealevel(cfg, out: Path, start, now, cache: RawCache, constants: dict,
                   last_good_dir=None) -> list[dict]:
    gauges = enabled(cfg["tide_gauges"])
    by_id = {g["id"]: g for g in gauges}
    statuses, results, missing = [], [], {}
    for sid, fn, prov in SEALEVEL_SOURCES:
        sts = [g for g in gauges if g["provider"] == prov]
        if not sts:
            continue
        t = time.time()
        try:
            r = fn(sts, start, now, cache=cache)
        except Exception as e:  # noqa: BLE001 -- fail soft per source (rule 8), record why
            if not isinstance(e, (NotImplementedError, RuntimeError)):
                traceback.print_exc()
            statuses.append({"id": sid, "status": "failed", "message": f"{type(e).__name__}: {e}"[:300]})
            missing.update({g["id"]: sid for g in sts})
            log(f"{sid}: failed after {time.time() - t:.0f}s: {e}")
            continue
        log(f"{sid}: {len(r.series)}/{len(sts)} stations in {time.time() - t:.0f}s"
            + (f"; errors {r.errors}" if r.errors else ""))
        results.append(r)
        missing.update({k: sid for k in r.errors})
        st = {"id": sid, "status": "ok", "last_success": iso(now)}
        if r.last_observation is not None:
            st["last_observation"] = iso(r.last_observation)
        if r.errors:
            st["message"] = (f"{len(r.errors)} of {len(sts)} stations missing: "
                             + "; ".join(f"{k}: {v}" for k, v in r.errors.items()))[:300]
        statuses.append(st)

    hourly = pd.date_range(start.floor("h"), now.floor("h"), freq="1h")
    idx6 = pd.date_range(start.ceil("6h"), now.floor("6h"), freq="6h")
    coords = {g["id"]: (g["lat"], g["lon"]) for g in gauges}
    pressures = {k: v.reindex(hourly) for r in results for k, v in r.air_pressure_hpa.items()}
    values, meta = {}, {}
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
    return statuses


def run_build(out_dir, cache_dir=".cache/raw", last_good_dir=None, full=False, days=400,
              tides_path=DEFAULT_TIDES):
    cfg = load_config()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    now = pd.Timestamp.now(tz="UTC").floor("h")
    start = now - pd.Timedelta(days=days)
    cache = RawCache(cache_dir, full=full)
    constants = load_constants(tides_path)
    log(f"tidal constants: {len(constants)} stations from {tides_path}")
    statuses = build_sealevel(cfg, out, start, now, cache, constants, last_good_dir)
    for product, sources in PLAN.items():
        results, product_failed = [], False
        for sid, fn, section, prov in sources:
            sts = [s for s in enabled(cfg[section]) if prov is None or s.get("provider") == prov]
            if not sts:
                continue
            try:
                results.append(fn(sts, start, now))
                statuses.append({"id": sid, "status": "ok", "last_success": iso(now)})
            except Exception as e:  # noqa: BLE001 -- fail soft per source (rule 8), record why
                product_failed = True
                statuses.append({"id": sid, "status": "failed", "message": f"{type(e).__name__}: {e}"[:300]})
                if not isinstance(e, NotImplementedError):
                    traceback.print_exc()
        if product_failed or not results:
            if last_good_dir and (Path(last_good_dir) / product).exists():
                shutil.copy2(Path(last_good_dir) / product, out / product)
                for s in statuses:
                    if s["status"] == "failed" and s["id"] in {x[0] for x in sources}:
                        s["status"] = "stale"
            continue
        # TODO(M2-M3): process results (process/steps.py) and write the product
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
