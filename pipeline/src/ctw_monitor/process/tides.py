"""Frozen tidal constants (rule 5): fit once from >= 1 year of hourly data, predict nightly.

Least squares on mean + linear trend + the constituents of vendor `tidal_constituents()`
(no long-period tides, so subtidal signals are not absorbed), with time measured from a fixed
epoch and lunar nodal corrections f(t), u(t) applied in both the fit and the prediction.
Without nodal factors, constants from one year would mispredict M2 by up to ~4 %, K1 by
~11 % and O1 by ~19 % some years later. numpy only: predicting needs no optional packages.

Nodal formulas: the usual Schureman (1958) approximations in the node longitude N, with
compound tides from their parents. Check against UTide when the refit moves to M4. Phases here are relative to EPOCH, not Greenwich phases;
they are self-consistent between fit and prediction but not comparable with published tables.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..vendor import ctw_analysis as ca

EPOCH = pd.Timestamp("2000-01-01T12:00:00Z")   # J2000
FORMAT_VERSION = 1


def constituents() -> dict[str, float]:
    """Constituent frequencies in cycles per hour."""
    return ca.tidal_constituents()


def _hours(index: pd.DatetimeIndex) -> np.ndarray:
    return (index - EPOCH).total_seconds().to_numpy() / 3600.0


def nodal(index: pd.DatetimeIndex, names) -> tuple[np.ndarray, np.ndarray]:
    """Nodal amplitude factors f and phase corrections u (radians), shape (len(index), len(names))."""
    d = _hours(index) / 24.0
    N = np.radians(125.0445 - 0.0529539 * d)   # longitude of the Moon's ascending node
    c1, c2, c3 = np.cos(N), np.cos(2 * N), np.cos(3 * N)
    s1, s2, s3 = np.sin(N), np.sin(2 * N), np.sin(3 * N)
    one, zero = np.ones_like(N), np.zeros_like(N)
    fm2, um2 = 1.0004 - 0.0373 * c1 + 0.0002 * c2, -2.14 * s1
    fk1 = 1.0060 + 0.1150 * c1 - 0.0088 * c2 + 0.0006 * c3
    uk1 = -8.86 * s1 + 0.68 * s2 - 0.07 * s3
    fo1 = 1.0089 + 0.1871 * c1 - 0.0147 * c2 + 0.0014 * c3
    uo1 = 10.80 * s1 - 1.34 * s2 + 0.19 * s3
    fk2 = 1.0241 + 0.2863 * c1 + 0.0083 * c2 - 0.0015 * c3
    uk2 = -17.74 * s1 + 0.68 * s2 - 0.04 * s3
    fj1 = 1.0129 + 0.1676 * c1 - 0.0170 * c2 + 0.0016 * c3
    uj1 = -12.94 * s1 + 1.34 * s2 - 0.19 * s3
    foo1 = 1.1027 + 0.6504 * c1 + 0.0317 * c2 - 0.0014 * c3
    uoo1 = -36.68 * s1 + 4.02 * s2 - 0.57 * s3
    table = {
        "M2": (fm2, um2), "N2": (fm2, um2), "2N2": (fm2, um2), "MU2": (fm2, um2),
        "NU2": (fm2, um2), "L2": (fm2, um2),
        "S2": (one, zero), "P1": (one, zero), "S4": (one, zero),
        "K1": (fk1, uk1), "O1": (fo1, uo1), "Q1": (fo1, uo1), "K2": (fk2, uk2),
        "J1": (fj1, uj1), "OO1": (foo1, uoo1),
        "M3": (fm2 ** 1.5, 1.5 * um2), "MK3": (fm2 * fk1, um2 + uk1),
        "M4": (fm2 ** 2, 2 * um2), "MN4": (fm2 ** 2, 2 * um2), "MS4": (fm2, um2),
        "M6": (fm2 ** 3, 3 * um2),
    }
    f = np.column_stack([table[k][0] for k in names])
    u = np.radians(np.column_stack([table[k][1] for k in names]))
    return f, u


def _design(index, freqs: dict[str, float]):
    names = list(freqs)
    t = _hours(index)
    f, u = nodal(index, names)
    w = 2 * np.pi * np.array([freqs[k] for k in names])
    arg = t[:, None] * w[None, :] + u
    return names, f * np.cos(arg), f * np.sin(arg), t


MIN_SPAN_DAYS = 183.0      # Rayleigh: K2/S2 and P1/K1 need a span of 1/df = 4383 h
MAX_CONDITION = 100.0      # design matrix condition number; well-separated fits are < 10


def fit_constants(s: pd.Series, min_hours: int = 4000, min_span_days: float = MIN_SPAN_DAYS,
                  max_condition: float = MAX_CONDITION) -> dict:
    """Fit constants to an hourly series (cm, gaps allowed). Returns the per-station record.

    Raises ValueError if there are fewer than min_hours valid values, if the valid record
    spans less than min_span_days (the count alone does not separate K2 from S2 or P1 from K1;
    Claude for Science review 2026-10-08, item 4), or if gaps leave the least-squares problem
    ill-conditioned."""
    ok = s.notna().to_numpy()
    if ok.sum() < min_hours:
        raise ValueError(f"only {int(ok.sum())} valid hours (< {min_hours})")
    span = (s.index[ok][-1] - s.index[ok][0]) / pd.Timedelta(days=1)
    if span < min_span_days:
        raise ValueError(f"record spans {span:.0f} days (< {min_span_days:.0f}; K2/S2, P1/K1 "
                         f"not separable)")
    freqs = constituents()
    names, C, S, t = _design(s.index, freqs)
    tc = (t - t[ok].mean()) / 8766.0                      # trend in cm per year
    A = np.column_stack([np.ones_like(t), tc, C, S])
    cond = float(np.linalg.cond(A[ok]))
    if cond > max_condition:
        raise ValueError(f"design matrix condition number {cond:.0f} (> {max_condition:.0f})")
    coef, *_ = np.linalg.lstsq(A[ok], s.to_numpy()[ok], rcond=None)
    k = len(names)
    a, b = coef[2:2 + k], coef[2 + k:]
    resid = s.to_numpy()[ok] - A[ok] @ coef
    return {
        "start": s.index[ok][0].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": s.index[ok][-1].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_hours": int(ok.sum()),
        "condition_number": round(cond, 1),
        "rms_residual_cm": round(float(np.sqrt(np.mean(resid ** 2))), 2),
        "constituents": {n: {"amp_cm": round(float(np.hypot(a[i], b[i])), 3),
                             "phase_deg": round(float(np.degrees(np.arctan2(b[i], a[i])) % 360), 2)}
                         for i, n in enumerate(names)},
    }


def predict(record: dict, index: pd.DatetimeIndex) -> pd.Series:
    """Tidal height (cm, zero mean) at index from a record made by fit_constants."""
    freqs = constituents()
    cons = {k: v for k, v in record["constituents"].items() if k in freqs}
    names, C, S, _ = _design(index, {k: freqs[k] for k in cons})
    amp = np.array([cons[k]["amp_cm"] for k in names])
    ph = np.radians([cons[k]["phase_deg"] for k in names])
    h = C @ (amp * np.cos(ph)) + S @ (amp * np.sin(ph))
    return pd.Series(h, index=index, name="tide_cm")
