"""ONC Oceans 3.0 fetchers (milestone M2). Token from ONC_API_TOKEN via vendor.onc_api.

Working call (2026-10-07, ~2 s per device-year):
  onc_get("scalardata/device", deviceCode="RBRQUARTZ3BPR202320", sensorCategoryCodes="pressure",
          dateFrom=..., dateTo=..., resamplePeriod=3600, resampleType="avg", rowLimit=100000)
Pressure in dbar from the API -> convert to Pa (x 1e4). Follow `next` for pagination.
Chunk multi-year requests by year. errorCode 127 before a deployment = no data.
"""
from __future__ import annotations

from .base import SourceResult


def fetch_bottom_pressure(stations: list[dict], start, end) -> SourceResult:
    raise NotImplementedError("M2")


def fetch_temperature(stations: list[dict], start, end) -> SourceResult:
    raise NotImplementedError("M2: daily means from CTD temperature by location + deviceCategoryCode=CTD")
