"""Processing steps. Thin wrappers over vendor/ctw_analysis.py so the rules in CLAUDE.md
are enforced in one place."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..vendor import ctw_analysis as ca
from . import tides

RHO_G = 1025.0 * 9.81          # Pa per m of water
PA_PER_CM = RHO_G / 100.0      # ~100.6 Pa per cm
NEAREST_BAROMETER_KM = 250.0   # subtidal air pressure is coherent over this distance


def despike(s: pd.Series, tide: pd.Series | None = None, nmad: float = 6.0,
            iters: int = 3) -> tuple[pd.Series, int]:
    """Drop points whose high-passed tidal residual exceeds nmad x MAD (iterated).

    With a frozen-constant prediction `tide`, the residual is s - tide. Without one, use the
    vendor's window harmonic fit (`despike_detide`). Returns (cleaned series, n removed)."""
    if tide is None:
        clean, _, _, nrem = ca.despike_detide(s, nmad=nmad, iters=iters)
        return clean, nrem
    s = s.copy()
    nrem = 0
    for _ in range(iters):
        r = s - tide
        hp = r - r.rolling(25, center=True, min_periods=6).median()
        mad = np.nanmedian(np.abs(hp - np.nanmedian(hp))) * 1.4826
        bad = (np.abs(hp) > nmad * mad).to_numpy()
        if not bad.any():
            break
        nrem += int(bad.sum())
        s[bad] = np.nan
    return s, nrem


def detide_frozen(s: pd.Series, constants: dict) -> pd.Series:
    """Subtract a tidal prediction from frozen constants (rule 5)."""
    return s - tides.predict(constants, s.index)


def ib_correct_gauge(sea_level_cm: pd.Series, p_hpa: pd.Series) -> pd.Series:
    """Rule 2: gauges only. Never call for bottom pressure."""
    return ca.ib_correct(sea_level_cm, p_hpa)


def fill_pressure(primary: pd.Series, fallbacks: list[pd.Series]) -> pd.Series:
    """Fill gaps in a barometer record from other barometers, each shifted by its median
    offset from the primary over their overlap (station elevations differ)."""
    p = primary.copy()
    for fb in fallbacks:
        fb = fb.reindex(p.index)
        both = p.notna() & fb.notna()
        offset = float((p[both] - fb[both]).median()) if both.any() else 0.0
        p = p.combine_first(fb + offset)
    return p


def pressure_for(station: dict, pressures: dict[str, pd.Series], coords: dict[str, tuple],
                 index: pd.DatetimeIndex) -> tuple[pd.Series | None, str]:
    """Air pressure (hPa) for one gauge and a label for meta.ib_source.

    Order (rule 2): the gauge's own barometer, else the nearest barometer within
    NEAREST_BAROMETER_KM. Gaps in the chosen record are filled from the next nearest ones.
    Gauges marked pressure: era5 get none until the weekly ERA5 job exists."""
    sid = station["id"]
    if station.get("pressure") == "era5":
        return None, "none"
    lat, lon = coords[sid]
    others = sorted(
        ((float(ca.haversine_km(lat, lon, *coords[k])), k) for k in pressures if k != sid),
        key=lambda x: x[0])
    others = [(d, k) for d, k in others if d <= NEAREST_BAROMETER_KM]
    if sid in pressures:
        chosen, label = pressures[sid], "station"
    elif others:
        d, k = others.pop(0)
        chosen, label = pressures[k], f"nearest:{k} ({d:.0f} km)"
    else:
        return None, "none"
    p = chosen.reindex(index).interpolate(limit=6, limit_area="inside")
    return fill_pressure(p, [pressures[k] for _, k in others]), label


def godin(s: pd.Series, maxgap_h: int = 12) -> pd.Series:
    return ca.godin_lowpass(s, maxgap_h=maxgap_h)


def basin_reference(pressure_pa: dict[str, pd.Series], ref_ids: list[str]) -> pd.Series:
    """Rule 4: mean of available basin gauges (after detiding and de-meaning each)."""
    refs = [pressure_pa[i] - pressure_pa[i].mean() for i in ref_ids if i in pressure_pa]
    if not refs:
        raise ValueError("no basin reference series available")
    return pd.concat(refs, axis=1).mean(axis=1, skipna=True)


def anomaly_doy(s: pd.Series, baseline: dict | None) -> pd.Series:
    """Minus day-of-year baseline (M4). Without a baseline: minus the window mean, and
    say so in the product's `processing` line."""
    if baseline is None:
        return s - s.mean()
    raise NotImplementedError


def gauge_chain(sea_level_cm: pd.Series, p_hpa: pd.Series | None,
                constants: dict | None) -> tuple[pd.Series, dict]:
    """Hourly sea level (cm, regular hourly index) -> hourly low-passed anomaly (cm) and meta.

    despike -> detide (frozen constants, else a window fit) -> IB (if pressure) -> Godin ->
    minus window mean."""
    meta = {}
    tide = tides.predict(constants, sea_level_cm.index) if constants else None
    clean, nrem = despike(sea_level_cm, tide)
    meta["despiked"] = nrem
    if tide is not None:
        resid = clean - tide
        meta["tide_source"] = f"frozen constants ({constants['start'][:10]} to {constants['end'][:10]})"
    else:
        resid = clean - ca.harmonic_fit(clean)[0]
        meta["tide_source"] = "window fit (no frozen constants)"
    if p_hpa is not None and p_hpa.notna().any():
        resid = ib_correct_gauge(resid, p_hpa)
    lp = godin(resid)
    return anomaly_doy(lp, None), meta
