"""Synthetic products in the data contract, for front-end development and CI.

Everything here is invented. manifest.json carries "synthetic": true and the web app shows
a banner. Never deploy synthetic data to the public site.
"""
from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import numpy as np
import pandas as pd

from . import SCHEMA_VERSION, __version__
from .config import alongshore_km, enabled, load_config
from .process.grid import hovmoller
from .products.writer import grid_product, iso, timeseries_product, write_json

SPEED_M_S = 3.0


def _pulse(t_days, centre_days, width_days):
    return np.exp(-0.5 * ((t_days - centre_days) / width_days) ** 2)


def make_synthetic(out_dir: Path | str, end: str = "2026-10-01", days: int = 400, seed: int = 1):
    rng = np.random.default_rng(seed)
    cfg = load_config()
    out = Path(out_dir)
    idx = pd.date_range(end=pd.Timestamp(end, tz="UTC"), periods=days * 4, freq="6h")
    td = (idx - idx[0]).total_seconds().to_numpy() / 86400.0

    gauges = enabled(cfg["tide_gauges"])
    dist = alongshore_km(gauges, cfg)
    x0 = min(dist.values())
    km_per_day = SPEED_M_S * 86.4
    # two poleward events: a depression followed by a rise, plus a weaker second pulse
    sl = {}
    for g in gauges:
        lag = (dist[g["id"]] - x0) / km_per_day
        decay = np.exp(-(dist[g["id"]] - x0) / 9000.0)
        sig = (-6 * _pulse(td, 250 + lag, 4) + 12 * _pulse(td, 262 + lag, 6)
               + 7 * _pulse(td, 330 + lag, 5)) * decay
        weather = np.convolve(rng.normal(0, 2.0, td.size), np.ones(12) / 12, mode="same")
        seasonal = 4 * np.sin(2 * np.pi * (td - 30) / 365.25)
        y = sig + weather + seasonal + rng.normal(0, 0.4, td.size)
        if g["provider"] == "ioc":
            y[rng.random(td.size) < 0.05] = np.nan
        sl[g["id"]] = y
    order = sorted(sl, key=lambda k: dist[k])
    sl = {k: sl[k] for k in order}
    meta = {k: {"ib_source": "none (synthetic)", "alongshore_km": dist[k]} for k in order}
    proc = "SYNTHETIC: invented poleward pulses at 3.0 m/s plus noise; 6-hourly"
    write_json(timeseries_product("sealevel_anomaly", "cm", proc, idx, sl, meta), out / "sealevel.json")

    # Grid at 50 km and 12 h keeps hovmoller.json small (subtidal signal; 3 m/s = 259 km/day)
    grid_km = np.arange(round(x0, -1), max(dist.values()) + 50, 50.0)
    gap = cfg["coastal_path"]["gap_mask_km"]
    sub = slice(None, None, 2)
    H = hovmoller({k: v[sub] for k, v in sl.items()}, dist, grid_km, gap_km=gap)
    xs = np.array(sorted(dist.values()))
    mask = [[float(a), float(b)] for a, b in pairwise(xs) if b - a > 2 * gap]
    write_json(grid_product(proc + "; grid 50 km x 12 h", idx[sub], grid_km, H, mask), out / "hovmoller.json")

    # NEPTUNE section: rise decreasing with depth (2026 ratios), basin-referenced
    bp = {}
    lag_bc = (dist.get("tofino", 400) - x0) / km_per_day
    for sid, amp in [("fgpd", 13.0), ("ncbc", 10.0), ("nc89", 5.0)]:
        bp[sid] = (amp * _pulse(td, 262 + lag_bc, 6) - 0.4 * amp * _pulse(td, 250 + lag_bc, 4)
                   + rng.normal(0, 0.3, td.size))
    write_json(timeseries_product("bottom_pressure_anomaly", "cm", "SYNTHETIC: basin-referenced, "
               "Godin low-pass; 6-hourly", idx, bp, {k: {} for k in bp}), out / "bottom_pressure.json")

    didx = pd.date_range(end=pd.Timestamp(end, tz="UTC"), periods=days, freq="1D")
    dd = (didx - didx[0]).total_seconds().to_numpy() / 86400.0
    tt = {}
    for sid, amp in [("bacnd_ctd", 0.29), ("bachy_ctd", 0.30), ("bacax_ctd", 0.28),
                     ("nc89_ctd", 0.13)]:
        step = amp / (1 + np.exp(-(dd - (264 + lag_bc)) / 2.0))
        tt[sid] = step * np.exp(-np.clip(dd - 300, 0, None) / 60) + rng.normal(0, 0.02, dd.size)
    write_json(timeseries_product("temperature_anomaly", "degC", "SYNTHETIC: daily mean minus "
               "day-of-year mean", didx, tt, {k: {} for k in tt}, ndigits=3), out / "temperature.json")

    events = {"schema_version": SCHEMA_VERSION, "events": [
        {"id": "synthetic-1", "type": "maximum", "speed_m_s": SPEED_M_S, "speed_ci95": [2.7, 3.3],
         "r2": 0.97, "n_stations": len(order), "first": iso(idx[0] + pd.Timedelta(days=262)),
         "label": "SYNTHETIC test pulse", "propagating": True}]}
    write_json(events, out / "events.json")

    stations = {"schema_version": SCHEMA_VERSION, "stations": (
        [{"id": g["id"], "name": g["name"], "kind": "tide_gauge", "provider": g["provider"],
          "lat": g["lat"], "lon": g["lon"], "alongshore_km": dist[g["id"]]} for g in gauges]
        + [{"id": b["id"], "name": b["location_code"], "kind": "bottom_pressure",
            "provider": "onc", "lat": b["lat"], "lon": b["lon"], "depth_m": b["depth_m"]}
           for b in enabled(cfg["bottom_pressure"])]
        + [{"id": c["id"], "name": c["location_code"], "kind": "ctd", "provider": "onc",
            "lat": c["lat"], "lon": c["lon"], "depth_m": c["depth_m"]} for c in cfg["temperature"]])}
    write_json(stations, out / "stations.json")

    now = iso(idx[-1])
    manifest = {
        "schema_version": SCHEMA_VERSION, "generated_at": now, "synthetic": True,
        "pipeline": {"version": __version__, "git_sha": "synthetic"},
        "window": {"start": iso(idx[0]), "end": now},
        "sources": [
            {"id": "noaa_coops", "status": "ok", "last_success": now, "last_observation": now},
            {"id": "chs_iwls", "status": "ok", "last_success": now, "last_observation": now},
            {"id": "ioc_slsmf", "status": "stale", "last_success": iso(idx[-20]),
             "last_observation": iso(idx[-20]), "message": "SYNTHETIC example of a stale source"},
            {"id": "onc", "status": "ok", "last_success": now, "last_observation": now},
        ],
        "products": ["stations.json", "sealevel.json", "hovmoller.json", "bottom_pressure.json",
                     "temperature.json", "events.json"],
    }
    write_json(manifest, out / "manifest.json")
    return manifest
