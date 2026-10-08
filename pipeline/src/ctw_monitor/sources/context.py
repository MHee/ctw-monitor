"""NOAA CPC ENSO indices (context only, M3; CLAUDE.md panel 6).

oni.ascii.txt has one row per overlapping 3-month season: SEAS YR TOTAL ANOM, for
example "JAS 2026  29.12   2.16". ANOM is the ONI (Niño 3.4 SST anomaly, ERSST v6, degC).
RONI.ascii.txt has SEAS YR ANOM: the Relative ONI, which NOAA uses for official ENSO
monitoring since NWS Public Information Statement 26-05 (2026).
"""
from __future__ import annotations

import requests

ONI_PAGE = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/oni/v6/"  # ERSST v6
RONI_PAGE = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/"


def parse_cpc_index(text: str) -> list[dict]:
    """All seasons in file order: [{season, year, anomaly_c[, total_c]}, ...]. Reads both
    the 4-column ONI file (SEAS YR TOTAL ANOM) and the 3-column RONI file (SEAS YR ANOM)."""
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) not in (3, 4) or not parts[1].isdigit():
            continue                                  # header or blank line
        try:
            row = {"season": parts[0], "year": int(parts[1]), "anomaly_c": float(parts[-1])}
            if len(parts) == 4:
                row["total_c"] = float(parts[2])
        except ValueError:
            continue
        rows.append(row)
    return rows


parse_oni = parse_cpc_index


def fetch_cpc_index(url: str, info_url: str, timeout: float = 30, keep: int = 12) -> dict:
    """Latest value plus the last `keep` seasons. Raises on network or format errors;
    the caller fails soft (rule 8)."""
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    rows = parse_cpc_index(r.text)
    if not rows:
        raise ValueError(f"no index rows in {url}")
    return {**rows[-1], "recent": rows[-keep:], "source_url": url, "info_url": info_url}


def fetch_oni(url: str, **kw) -> dict:
    return fetch_cpc_index(url, ONI_PAGE, **kw)


def fetch_roni(url: str, **kw) -> dict:
    return fetch_cpc_index(url, RONI_PAGE, **kw)
