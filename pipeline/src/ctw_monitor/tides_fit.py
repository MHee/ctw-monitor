"""`ctw-monitor tides-fit`: refit frozen tidal constants for every enabled gauge (rule 5).

Tide gauges in cm; ONC seafloor pressure converted from Pa to cm of water first.
Run monthly or on demand, then upload the file as a Release asset:
    gh release upload tides-latest .cache/tidal_constants.json --clobber
Stations that fail in a refit keep their previous constants from the existing file.

It also fits the frozen bottom-pressure drift models (method B, process/drift.py) for the
NEPTUNE section gauges and stores them under "drift" in the same file.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

from . import __version__
from .build import SEALEVEL_SOURCES
from .config import enabled, load_config
from .process import drift, tides
from .process.steps import PA_PER_CM, despike
from .products.writer import iso, write_json
from .sources import onc
from .sources.cache import RawCache


def fit_drift_models(cfg, constants: dict, end) -> tuple[dict, dict]:
    """Drift model per section gauge from the basin-referenced daily record of its current
    deployment (detided with the frozen constants). Returns (models, failures)."""
    bprs = [b for b in enabled(cfg["bottom_pressure"]) if b.get("location_code")]
    daily, info, failed = {}, {}, {}
    for b in bprs:
        k = b["id"]
        if k not in constants:
            failed[k] = "no tidal constants"
            continue
        try:
            pa, dev, begin = onc.deployment_history(b, end)
        except Exception as e:  # noqa: BLE001 -- record and continue
            failed[k] = onc.scrub(f"{type(e).__name__}: {e}")[:200]
            continue
        cm = (pa / PA_PER_CM).asfreq("1h")
        daily[k] = drift.daily_means(cm - tides.predict(constants[k], cm.index))
        info[k] = (dev, begin)
        print(f"  {k}: {dev} since {begin.date()}, {daily[k].notna().sum()} days",
              file=sys.stderr, flush=True)
    refs = [b["id"] for b in bprs if b.get("role") == "basin_ref" and b["id"] in daily]
    if not refs:
        return {}, {**failed, "basin": "no basin gauge"}
    basin = pd.concat([daily[k] - daily[k].mean() for k in refs], axis=1).mean(axis=1)
    models = {}
    for b in bprs:
        k = b["id"]
        if b.get("role") != "section" or k not in daily:
            continue
        dev, begin = info[k]
        t0 = max(begin.floor("D"), pd.Timestamp(b.get("drift_fit_from", "1900-01-01"), tz="UTC"))
        try:
            m = drift.fit(daily[k] - basin, t0, end)
        except ValueError as e:
            failed[k] = str(e)
            continue
        models[k] = {**m, "deviceCode": dev, "basin_reference": refs}
        print(f"  drift {k}: {m['slope_cm_per_yr']} cm/yr, c {m['c_cm']:.1f} cm, "
              f"tau {m['tau_days']:.0f} d, rms {m['rms_cm']} cm ({m['fit_from']} to {m['fit_to']})",
              file=sys.stderr, flush=True)
    return models, failed


def run_tides_fit(out_path, years: float = 2.0, cache_dir=".cache/raw", only=None) -> dict:
    cfg = load_config()
    gauges = [g for g in enabled(cfg["tide_gauges"]) if not only or g["id"] in only]
    end = pd.Timestamp.now(tz="UTC").floor("h")
    start = end - pd.Timedelta(days=round(365.25 * years))
    cache = RawCache(cache_dir)
    out_path = Path(out_path)
    old = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    stations, failed = dict(old.get("stations", {})), {}
    hourly = pd.date_range(start, end, freq="1h")
    # (source id, fetcher, stations, factor to cm): gauges are in cm, seafloor pressure in Pa
    bprs = [b for b in enabled(cfg["bottom_pressure"]) if b.get("location_code")
            and (not only or b["id"] in only)]
    plan = [(sid, fn, [g for g in gauges if g["provider"] == prov], 1.0)
            for sid, fn, prov in SEALEVEL_SOURCES]
    plan.append(("onc_bpr", onc.fetch_bottom_pressure, bprs, 1.0 / PA_PER_CM))
    for sid, fn, sts, to_cm in plan:
        if not sts:
            continue
        t = time.time()
        try:
            r = fn(sts, start, end, cache=cache)
        except Exception as e:  # noqa: BLE001 -- keep going with the other sources
            failed.update({g["id"]: onc.scrub(f"{type(e).__name__}: {e}")[:200] for g in sts})
            print(f"{sid}: failed: {onc.scrub(e)}", file=sys.stderr, flush=True)
            continue
        failed.update(r.errors)
        print(f"{sid}: fetched {len(r.series)}/{len(sts)} in {time.time() - t:.0f}s",
              file=sys.stderr, flush=True)
        for k, s in r.series.items():
            try:
                clean, nrem = despike(s.reindex(hourly) * to_cm)
                rec = tides.fit_constants(clean)
            except Exception as e:  # noqa: BLE001 -- e.g. too short a record
                failed[k] = f"{type(e).__name__}: {e}"[:200]
                continue
            rec.update({"provider": r.meta.get(k, {}).get("provider", sid), "despiked": nrem})
            stations[k] = rec
            print(f"  {k}: M2 {rec['constituents']['M2']['amp_cm']:.1f} cm, "
                  f"K1 {rec['constituents']['K1']['amp_cm']:.1f} cm, "
                  f"rms residual {rec['rms_residual_cm']:.1f} cm, {rec['n_hours']} h",
                  file=sys.stderr, flush=True)
    drift_models, drift_failed = dict(old.get("drift", {})), {}
    if not only or any(b["id"] in only for b in enabled(cfg["bottom_pressure"])):
        print("drift models:", file=sys.stderr, flush=True)
        new_models, drift_failed = fit_drift_models(cfg, stations, end)
        drift_models.update(new_models)
    doc = {
        "format_version": tides.FORMAT_VERSION, "created": iso(end), "pipeline_version": __version__,
        "method": ("least squares, mean + trend + 21 constituents (no long-period), lunar nodal "
                   "corrections; phases relative to epoch, not Greenwich"),
        "epoch": iso(tides.EPOCH), "units": "cm", "window_years": years,
        "stations": dict(sorted(stations.items())),
        "failed_this_run": failed,
        "drift_method": ("a + b t + c exp(-t/tau) per deployment on the basin-referenced daily "
                         "record, last 60 days excluded; cm of water"),
        "drift": dict(sorted(drift_models.items())),
        "drift_failed_this_run": drift_failed,
    }
    write_json(doc, out_path)
    return doc
