"""Tide-gauge fetchers (milestone M1). Wrap vendor/margin_data.py; return hourly cm.

Vendor functions (signatures as of 2026-10-07):
  fetch_noaa_coops(station, start, end, product='hourly_height', datum='MSL')
      product='air_pressure' for the IB correction (check which stations have one)
  fetch_chs_iwls(station_id, start, end, code='wlo', resolution='FIFTEEN_MINUTES', window_days=6)
      use resolution='SIXTY_MINUTES', window_days=30; code='ap1' for air pressure
  ioc_sea_level(code, start, end, chunk_days=10, ...) -> raw; ioc_hourly(raw, sensor, to_cm=True)
  uhslc_fast_hourly(uhslc_id, start, end)
Measured: CO-OPS 1 yr 5.6 s; CHS 90 d 1.5 s; IOC 30 d of 1-min data 18.9 s.
"""
from __future__ import annotations

from .base import SourceResult


def fetch_noaa(stations: list[dict], start, end) -> SourceResult:
    raise NotImplementedError("M1: loop stations, vendor.margin_data.fetch_noaa_coops; m -> cm")


def fetch_chs(stations: list[dict], start, end) -> SourceResult:
    raise NotImplementedError("M1: vendor.margin_data.fetch_chs_iwls at SIXTY_MINUTES, 30-day windows")


def fetch_ioc(stations: list[dict], start, end) -> SourceResult:
    raise NotImplementedError("M1: ioc_sea_level + ioc_hourly; real-time, not QC'd - flag in meta")


def fetch_uhslc(stations: list[dict], start, end) -> SourceResult:
    raise NotImplementedError("M1: vendor.margin_data.uhslc_fast_hourly")
