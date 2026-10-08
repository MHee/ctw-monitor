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

## Fixes

- 2026-10-08, `ctw_analysis.propagation_fit`: the fit regressed distance on time. Timing
  errors then sit in the predictor, which attenuates the slope and biases the speed low
  (Monte Carlo: true 3.0 m/s, 24 h timing scatter -> 2.7-2.8 m/s; 2026 minima: 3.2 vs
  3.8 m/s). It now regresses time on distance and also returns the slowness, its standard
  error and dof, for confidence limits inverted from the slowness. Same keys as before,
  plus `slowness_s_per_m`, `slowness_se` and `slowness_dof`. Approved by Martin;
  reported upstream in feedback/ (see CLAUDE.md).
