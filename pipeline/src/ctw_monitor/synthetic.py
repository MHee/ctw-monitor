"""Synthetic products in the data contract, for front-end development and CI.

Everything here is invented. manifest.json carries "synthetic": true and the web app shows
a banner. Never deploy synthetic data to the public site.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import SCHEMA_VERSION, __version__
from .config import alongshore_km, enabled, load_config
from .products.events import events_product
from .products.sealevel import hovmoller_product, stations_product
from .products.writer import iso, timeseries_product, write_json
from .sources.context import ONI_PAGE

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

    write_json(hovmoller_product(sl, idx, dist, cfg["coastal_path"]["gap_mask_km"], proc),
               out / "hovmoller.json")

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

    series = {k: pd.Series(v, index=idx) for k, v in sl.items()}
    events = events_product(series, dist)
    write_json(events, out / "events.json")

    write_json(stations_product(cfg, dist), out / "stations.json")

    write_json({"schema_version": SCHEMA_VERSION, "oni": {
        "season": "JAS", "year": 2026, "anomaly_c": 1.5, "total_c": 28.5,
        "source_url": cfg["context"]["oni_url"], "info_url": ONI_PAGE,
        "recent": [{"season": s_, "year": 2026, "anomaly_c": a_} for s_, a_ in
                   [("MAM", 0.2), ("AMJ", 0.5), ("MJJ", 0.9), ("JJA", 1.2), ("JAS", 1.5)]]}},
               out / "context.json")

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
            {"id": "noaa_oni", "status": "ok", "last_success": now},
        ],
        "products": ["stations.json", "sealevel.json", "hovmoller.json", "bottom_pressure.json",
                     "temperature.json", "events.json", "context.json"],
    }
    write_json(manifest, out / "manifest.json")
    return manifest
