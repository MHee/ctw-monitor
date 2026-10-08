import numpy as np

from ctw_monitor.process.grid import hovmoller


def test_interpolates_between_and_masks_gaps():
    vals = {"a": np.array([0.0, 1.0]), "b": np.array([10.0, np.nan]), "c": np.array([20.0, 3.0])}
    dist = {"a": 0.0, "b": 100.0, "c": 1000.0}
    grid = np.array([0.0, 50.0, 100.0, 550.0, 1000.0])
    H = hovmoller(vals, dist, grid, gap_km=150)
    assert H[0, 1] == 5.0
    assert np.isnan(H[0, 3])            # 450 km from any gauge
    assert abs(H[1, 2] - 1.2) < 1e-9     # b missing at t=1: interpolate a..c, a is 100 km away
    assert H[1, 0] == 1.0 and np.isnan(H[1, 3])
