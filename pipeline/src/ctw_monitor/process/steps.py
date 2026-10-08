"""Processing steps. Thin wrappers over vendor/ctw_analysis.py so the rules in CLAUDE.md
are enforced in one place."""
from __future__ import annotations

import pandas as pd

from ..vendor import ctw_analysis as ca

RHO_G = 1025.0 * 9.81          # Pa per m of water
PA_PER_CM = RHO_G / 100.0      # ~100.6 Pa per cm


def despike(s: pd.Series) -> pd.Series:
    raise NotImplementedError("M1: ca.despike_detide returns (clean, ...) - check its return shape")


def detide_frozen(s: pd.Series, constants: dict) -> pd.Series:
    """Subtract a tidal prediction from frozen constants (rule 5). M1."""
    raise NotImplementedError


def ib_correct_gauge(sea_level_cm: pd.Series, p_hpa: pd.Series) -> pd.Series:
    """Rule 2: gauges only. Never call for bottom pressure."""
    return ca.ib_correct(sea_level_cm, p_hpa)


def godin(s: pd.Series, maxgap_h: int = 12) -> pd.Series:
    return ca.godin_lowpass(s, maxgap_h=maxgap_h)


def basin_reference(pressure_pa: dict[str, pd.Series], ref_ids: list[str]) -> pd.Series:
    """Rule 4: mean of available basin gauges (after detiding and de-meaning each)."""
    refs = [pressure_pa[i] - pressure_pa[i].mean() for i in ref_ids if i in pressure_pa]
    if not refs:
        raise ValueError("no basin reference series available")
    return pd.concat(refs, axis=1).mean(axis=1, skipna=True)


def anomaly_doy(s: pd.Series, baseline: dict | None) -> pd.Series:
    """Minus day-of-year baseline (M1/M4). Without a baseline: minus the window mean, and
    say so in the product's `processing` line."""
    if baseline is None:
        return s - s.mean()
    raise NotImplementedError
