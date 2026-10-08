# Vendored code

| file | from skill | used for |
|---|---|---|
| `margin_data.py` | `ne-pacific-margin-data` (23 functions) | NOAA CO-OPS, CHS IWLS, IOC, UHSLC, ECCC, NDBC, ERDDAP, ERA5 fetchers |
| `ctw_analysis.py` | `coastal-trapped-wave-analysis` (22 functions) | despike/detide, Godin, IB, along-coast distance, propagation fit, CTW model |
| `onc_api.py` | `onc-oceans3-api` (3 of 13 functions) | `onc_get` with token from `ONC_API_TOKEN` |

Copied 2026-10-07 from `OneDrive\Claude_Exchange\skills_2026-10\` and the installed
`onc-oceans3-api` skill. All imports are function-local, so `utide`, `xarray` and
`netCDF4` are needed only if the functions that use them are called (`detide_utide`,
ERA5 readers). The nightly path must not call them.

Record any bug fix here with date and reason.
