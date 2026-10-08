"""Air pressure for the IB correction when a gauge has no barometer (M1).
ECCC climate-hourly: vendor.margin_data.fetch_eccc_climate_hourly; ERA5: weekly job only."""
from __future__ import annotations


def fetch_air_pressure(cfg: dict, start, end):
    raise NotImplementedError("M1")
