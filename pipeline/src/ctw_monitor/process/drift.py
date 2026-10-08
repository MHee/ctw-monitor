"""Bottom-pressure drift (method B, chosen 2026-10-08): a + b t + c exp(-t / tau) per deployment.

Fitted by `tides-fit` to the basin-referenced daily record of the whole deployment (or from
`drift_fit_from` in config, to start after a level step), leaving out the last 60 days, then
frozen like the tidal constants and extrapolated by the nightly build. In the comparison
(docs/METHODS.md) this revised recent values least (0.31 cm mean against 1.37 cm for a
linear fit over the window) and tracked coastal sea level best.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TAUS_DAYS = np.geomspace(5, 1500, 60)
EXCLUDE_RECENT = pd.Timedelta(days=60)     # never let the fit lean on the newest data
MIN_DAYS = 180                             # shorter records fall back to the window fit


def fit(daily_cm: pd.Series, t0: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Fit a + b t + c exp(-t/tau) (t in days since t0) to daily values in cm before
    end - EXCLUDE_RECENT. tau is chosen by a grid scan; a, b, c by least squares.
    Raises ValueError if fewer than MIN_DAYS valid days."""
    s = daily_cm[(daily_cm.index >= t0) & (daily_cm.index < end - EXCLUDE_RECENT)].dropna()
    if len(s) < MIN_DAYS:
        raise ValueError(f"only {len(s)} valid days (< {MIN_DAYS})")
    t = (s.index - t0).total_seconds().to_numpy() / 86400.0
    y = s.to_numpy()
    best = None
    for tau in TAUS_DAYS:
        A = np.column_stack([np.ones_like(t), t, np.exp(-t / tau)])
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        rss = float(np.sum((A @ coef - y) ** 2))
        if best is None or rss < best[0]:
            best = (rss, tau, coef)
    rss, tau, (a, b, c) = best
    return {"t0": t0.strftime("%Y-%m-%dT%H:%M:%SZ"), "a_cm": float(a), "b_cm_per_day": float(b),
            "c_cm": float(c), "tau_days": float(tau),
            "fit_from": s.index[0].strftime("%Y-%m-%d"), "fit_to": s.index[-1].strftime("%Y-%m-%d"),
            "n_days": len(s), "rms_cm": round(float(np.sqrt(rss / len(s))), 2),
            "slope_cm_per_yr": round(float(b * 365.25), 2)}


def evaluate(model: dict, index: pd.DatetimeIndex) -> pd.Series:
    """Drift (cm) of a fitted model at index."""
    t = (index - pd.Timestamp(model["t0"])).total_seconds().to_numpy() / 86400.0
    return pd.Series(model["a_cm"] + model["b_cm_per_day"] * t
                     + model["c_cm"] * np.exp(-t / model["tau_days"]), index=index)


def daily_means(hourly_cm: pd.Series, min_hours: int = 20) -> pd.Series:
    """Daily means of a detided hourly series; days with fewer than min_hours values are NaN
    (a partial day keeps tidal residue and biases the mean)."""
    g = hourly_cm.resample("1D")
    d = g.mean()
    d[g.count() < min_hours] = np.nan
    return d
