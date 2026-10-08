"""Assemble stations.json and hovmoller.json (shared by the real and synthetic builds)."""
from __future__ import annotations

from itertools import pairwise

import numpy as np
import pandas as pd

from .. import SCHEMA_VERSION
from ..config import alongshore_km, enabled
from ..process.grid import hovmoller
from .writer import grid_product

GRID_KM = 50.0          # 3 m/s = 259 km/day; finer grids made hovmoller.json too large
GRID_STEP = 2           # every 2nd 6-hourly value -> 12 h


def coastal_path(cfg: dict) -> list[dict]:
    """Waypoints of the along-coast path with their distance (same zero as the gauges)."""
    wps = [{"id": f"wp{i}", "name": n, "lat": la, "lon": lo}
           for i, (n, la, lo) in enumerate(cfg["coastal_path"]["waypoints"])]
    km = alongshore_km(wps, cfg)
    return [{"name": w["name"], "lat": w["lat"], "lon": w["lon"], "alongshore_km": km[w["id"]]}
            for w in wps]


def stations_product(cfg: dict, dist: dict[str, float]) -> dict:
    """NEPTUNE sites get an along-coast distance too: their projection onto the coastal path,
    so the panels can mark when a coastal event passes them."""
    gauges = [g for g in enabled(cfg["tide_gauges"]) if g["id"] in dist]
    bprs, ctds = enabled(cfg["bottom_pressure"]), cfg["temperature"]
    onc_km = alongshore_km(bprs + ctds, cfg)
    return {"schema_version": SCHEMA_VERSION, "coastal_path": coastal_path(cfg), "stations": (
        [{"id": g["id"], "name": g["name"], "kind": "tide_gauge", "provider": g["provider"],
          "lat": g["lat"], "lon": g["lon"], "alongshore_km": dist[g["id"]]} for g in gauges]
        + [{"id": b["id"], "name": b["location_code"], "kind": "bottom_pressure",
            "provider": "onc", "lat": b["lat"], "lon": b["lon"], "depth_m": b["depth_m"],
            "alongshore_km": onc_km[b["id"]]} for b in bprs]
        + [{"id": c["id"], "name": c["location_code"], "kind": "ctd", "provider": "onc",
            "lat": c["lat"], "lon": c["lon"], "depth_m": c["depth_m"],
            "alongshore_km": onc_km[c["id"]]} for c in ctds])}


def hovmoller_product(values: dict[str, np.ndarray], index: pd.DatetimeIndex,
                      dist: dict[str, float], gap_km: float, processing: str) -> dict:
    """Distance-time grid at GRID_KM x 12 h from 6-hourly gauge anomalies.

    mask_km lists spans between neighbouring gauges wider than 2 x gap_km (no gauge within
    gap_km), which the panel hatches instead of interpolating across."""
    xs = np.array(sorted(dist[k] for k in values))
    grid_km = np.arange(round(xs[0], -1), xs[-1] + GRID_KM, GRID_KM)
    sub = slice(None, None, GRID_STEP)
    H = hovmoller({k: np.asarray(v)[sub] for k, v in values.items()}, dist, grid_km, gap_km=gap_km)
    mask = [[float(a), float(b)] for a, b in pairwise(xs) if b - a > 2 * gap_km]
    return grid_product(processing + f"; grid {GRID_KM:.0f} km x {6 * GRID_STEP} h",
                        index[sub], grid_km, H, mask)
