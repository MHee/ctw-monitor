"""Distance-time gridding for the propagation panel."""
from __future__ import annotations

import numpy as np


def hovmoller(values: dict[str, np.ndarray], dist_km: dict[str, float],
              grid_km: np.ndarray, gap_km: float = 150.0):
    """Linear interpolation in distance at each time step between the gauges that have data.
    Cells farther than gap_km from every gauge with data at that time are NaN.

    values: station id -> array (n_time,), all on the same time axis.
    Returns array (n_time, len(grid_km)).
    """
    ids = sorted(values, key=lambda k: dist_km[k])
    x = np.array([dist_km[k] for k in ids])
    Y = np.vstack([values[k] for k in ids]).T            # (n_time, n_sta)
    out = np.full((Y.shape[0], grid_km.size), np.nan)
    for t in range(Y.shape[0]):
        ok = np.isfinite(Y[t])
        if ok.sum() < 2:
            continue
        xi, yi = x[ok], Y[t, ok]
        row = np.interp(grid_km, xi, yi, left=np.nan, right=np.nan)
        near = np.min(np.abs(grid_km[:, None] - xi[None, :]), axis=1) <= gap_km
        row[~near] = np.nan
        out[t] = row
    return out
