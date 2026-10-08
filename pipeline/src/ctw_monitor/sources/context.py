"""NOAA CPC Oceanic Niño Index (context only, M3; CLAUDE.md panel 6).

oni.ascii.txt has one row per overlapping 3-month season: SEAS YR TOTAL ANOM, for
example "JAS 2026  29.12   2.16". ANOM is the ONI (Niño 3.4 SST anomaly, degC).
"""
from __future__ import annotations

import requests

ONI_PAGE = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/oni/v6/"  # ERSST v6


def parse_oni(text: str) -> list[dict]:
    """All seasons in file order: [{season, year, total_c, anomaly_c}, ...]."""
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 4 or not parts[1].isdigit():
            continue                                  # header or blank line
        try:
            rows.append({"season": parts[0], "year": int(parts[1]),
                         "total_c": float(parts[2]), "anomaly_c": float(parts[3])})
        except ValueError:
            continue
    return rows


def fetch_oni(url: str, timeout: float = 30, keep: int = 12) -> dict:
    """Latest ONI value plus the last `keep` seasons. Raises on network or format errors;
    the caller fails soft (rule 8)."""
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    rows = parse_oni(r.text)
    if not rows:
        raise ValueError("no ONI rows in the CPC file")
    return {**rows[-1], "recent": rows[-keep:], "source_url": url, "info_url": ONI_PAGE}
