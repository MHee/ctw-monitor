"""Load config/stations.yaml and compute along-coast distances."""
from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "config" / "stations.yaml"
R_EARTH_KM = 6371.0


def load_config(path: Path | str = DEFAULT_CONFIG) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _hav(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dlmb = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * R_EARTH_KM * np.arcsin(np.sqrt(a))


def densify_path(waypoints, step_km: float = 2.0):
    """Return (lat, lon, cumulative_km) arrays along the waypoint path (linear in lat/lon)."""
    lat, lon = [], []
    for (_, la1, lo1), (_, la2, lo2) in pairwise(waypoints):
        n = max(2, int(np.ceil(_hav(la1, lo1, la2, lo2) / step_km)))
        f = np.linspace(0, 1, n, endpoint=False)
        lat.extend(la1 + f * (la2 - la1)); lon.extend(lo1 + f * (lo2 - lo1))
    lat.append(waypoints[-1][1]); lon.append(waypoints[-1][2])
    lat, lon = np.asarray(lat), np.asarray(lon)
    seg = _hav(lat[:-1], lon[:-1], lat[1:], lon[1:])
    return lat, lon, np.concatenate([[0.0], np.cumsum(seg)])


def alongshore_km(stations: list[dict], cfg: dict) -> dict[str, float]:
    """Project each station onto the coastal path; 0 km at cfg['coastal_path']['zero_at'],
    poleward positive. Nearest densified path point (2 km resolution)."""
    cp = cfg["coastal_path"]
    plat, plon, s = densify_path(cp["waypoints"])
    out = {}
    for st in stations:
        i = int(np.argmin(_hav(st["lat"], st["lon"], plat, plon)))
        out[st["id"]] = float(s[i])
    zero_id = cp["zero_at"]
    z = out.get(zero_id)
    if z is None:
        ref = next(st for st in cfg["tide_gauges"] if st["id"] == zero_id)
        z = float(s[int(np.argmin(_hav(ref["lat"], ref["lon"], plat, plon)))])
    return {k: round(v - z, 1) for k, v in out.items()}


def enabled(items: list[dict]) -> list[dict]:
    return [x for x in items if x.get("enabled", True)]
