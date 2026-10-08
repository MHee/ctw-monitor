"""`ctw-monitor tides-fit`: refit frozen tidal constants for every enabled tide gauge (rule 5).

Run monthly or on demand, then upload the file as a Release asset:
    gh release upload tides-latest .cache/tidal_constants.json --clobber
Stations that fail in a refit keep their previous constants from the existing file.
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
from .process import tides
from .process.steps import despike
from .products.writer import iso, write_json
from .sources.cache import RawCache


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
    for sid, fn, prov in SEALEVEL_SOURCES:
        sts = [g for g in gauges if g["provider"] == prov]
        if not sts:
            continue
        t = time.time()
        try:
            r = fn(sts, start, end, cache=cache)
        except Exception as e:  # noqa: BLE001 -- keep going with the other sources
            failed.update({g["id"]: f"{type(e).__name__}: {e}"[:200] for g in sts})
            print(f"{sid}: failed: {e}", file=sys.stderr, flush=True)
            continue
        failed.update(r.errors)
        print(f"{sid}: fetched {len(r.series)}/{len(sts)} in {time.time() - t:.0f}s",
              file=sys.stderr, flush=True)
        for k, s in r.series.items():
            try:
                clean, nrem = despike(s.reindex(hourly))
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
    doc = {
        "format_version": tides.FORMAT_VERSION, "created": iso(end), "pipeline_version": __version__,
        "method": ("least squares, mean + trend + 21 constituents (no long-period), lunar nodal "
                   "corrections; phases relative to epoch, not Greenwich"),
        "epoch": iso(tides.EPOCH), "units": "cm", "window_years": years,
        "stations": dict(sorted(stations.items())),
        "failed_this_run": failed,
    }
    write_json(doc, out_path)
    return doc
