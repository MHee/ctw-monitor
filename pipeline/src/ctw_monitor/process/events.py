"""Extrema detection and along-coast speed (M3). Rule 3: speed from the timing of extrema,
fitted against distance (vendor ca.propagation_fit), never from whole-window lag correlation."""
from __future__ import annotations


def detect_events(sealevel: dict, dist_km: dict, prominence_cm: float = 3.0,
                  min_separation_days: float = 5.0, window_days: float = 10.0) -> list[dict]:
    raise NotImplementedError("M3: scipy.signal.find_peaks per gauge, associate, fit")
