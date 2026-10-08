# Methods

The processing follows the ONC internal report on the May–June 2026 coastal-trapped
event (v015, October 2026) and the `coastal-trapped-wave-analysis` skill, whose
functions are in `pipeline/src/ctw_monitor/vendor/ctw_analysis.py`.

## Tide gauges

1. Hourly series, stamped at the centre of the averaging interval (hh:00): NOAA 6-min
   `water_level` averaged over ±30 min (`hourly_height` is the verified product and lags
   by weeks, so it cannot feed a nightly run); CHS `wlo` at `SIXTY_MINUTES`; IOC hourly
   median of the raw samples over ±30 min (at least half the station's usual count);
   UHSLC fast-delivery hourly.
2. Despike: high-pass the residual from the frozen-constant tide prediction with a 25-h
   running median and drop points beyond 6 × MAD (3 iterations). Without constants,
   `despike_detide` with its window fit.
3. Detide with frozen constants (`process/tides.py`): least squares on mean + trend +
   21 constituents (no long-period tides), lunar nodal corrections in fit and prediction,
   phases relative to J2000. Fitted from 2 years by `ctw-monitor tides-fit`, stored as the
   Release asset `tides-latest/tidal_constants.json`. numpy only, so the nightly job needs
   no extras. Gauges without constants fall back to a window fit (noted in `meta`).
   Planned for M4: cross-check against UTide and refit monthly in a workflow.
4. **IB correction** (`ib_correct`): add 0.9945 cm per hPa of (p − mean p). Pressure
   source per station: the gauge's own barometer (all CO-OPS gauges here; CHS `ap1` at
   Tofino, Winter Harbour, Prince Rupert) → the nearest gauge barometer within 250 km
   (Port Renfrew, Bamfield, Pruth Bay). Gaps in the chosen record are filled from the
   next-nearest barometers, offset by the median difference. Mexican and Central American
   gauges are "not IB-corrected" until the weekly ERA5 job exists.
5. Godin low-pass (24-24-25 h; `godin_lowpass`), gaps up to 12 h bridged.
6. Anomaly: minus the station's day-of-year mean over the baseline period (proposal
   2013–2025, 31-day smoothing). Where a baseline is shorter (CHS online holdings start
   about 2019), say so in `meta`. **Until the baselines exist (M4), minus the mean of the
   400-day window**, so the seasonal cycle is still in the traces; the panel says so.
7. Resample to 6-hourly for publication.

## Bottom pressure (NEPTUNE)

1. Devices from `/deployments` per location (BPR; CORK for CBC27), each deployment in the
   window fetched with `scalardata/device` at `resamplePeriod=900` (precomputed, fast),
   channel chosen by `sensorName`, qaqcFlag {1, 2, 7}, averaged to hourly values
   centred on hh:00; dbar × 10⁴ = Pa.
2. Pa to cm of water with ρg = 1025 × 9.81 (≈ 100.6 Pa/cm), then despike and detide with
   frozen constants (fitted by `tides-fit` like the gauges, in cm of water).
3. **No IB correction.**
4. Subtract the Cascadia Basin reference: mean of CNE20, CBC27 (CORK-1027C) and, if
   added, the CBC27 APT, each de-meaned. This removes basin-scale ocean mass and
   common-mode signals. Without any basin gauge the product is not written (last good
   is kept).
5. Drift: removed by the basin reference only to the extent that drifts are similar;
   they are not. **Interim (M2): a straight line fitted over the 400-day window is
   removed** from each basin-referenced series. Still open: an exponential + linear
   drift fit per deployment (the `onc-pressure-drift-tides` method), refitted with the
   tidal constants, versus a high-pass at 120 days. Never let a drift fit run over the
   most recent 60 days alone.
6. Godin low-pass, minus the window mean, 6-hourly.

Reference values from the 2026 event (22 May–1 Jun rise): FGPD 1334 Pa, NCBC 1000 Pa,
NC89 488 Pa, Cascadia Basin 216 Pa.

## Temperature

Daily means from the CTDs at FGPPN, NCBC, BACND, BACHY, BACME, BACAX, NC89 and NC27;
anomaly against the day-of-year mean (NC89 has 15 years); also report the anomaly in
standard deviations. The 2026 event warmed the 646–983 m Barkley CTDs by about
0.28–0.30 °C (isotherms about 90–130 m deeper).

## Along-coast distance and the distance–time grid

Distance is cumulative great-circle distance along a waypoint path that follows the
open coast (`config/stations.yaml`, `coastal_path`), not a straight line: from
Central America to Cabo Corrientes, across the Gulf of California mouth to Cabo San
Lucas, up Baja California, then San Diego, Point Conception, Point Reyes, Point Arena,
Cape Mendocino, Cape Blanco, Cape Flattery (0 km at Neah Bay), Vancouver Island and
Prince Rupert. Each gauge is projected onto the path. The grid interpolates linearly
in distance between neighbouring gauges and masks spans with no gauge within 150 km.

## Events and speed

1. Find extrema of the 6-hourly anomaly at each gauge with prominence ≥ 3 cm and
   separation ≥ 5 days.
2. Associate extrema across gauges within a moving ±10-day window.
3. Fit time against distance (`propagation_fit`); report speed with 95 % CI, n
   stations and r². Use the timing of extrema; do not use lag correlation.
4. Flag events whose fitted speed is outside 1–10 m/s or whose r² < 0.6 as
   "not propagating".

The 2026 reference: minima-timing speed 3.1 m/s (San Francisco and Crescent City 3
days before Neah Bay); Mexican pulse 1.95 ± 0.20 m/s (Acajutla 3 May to Puerto Vallarta
13 May), not traceable north of Puerto Vallarta for lack of Baja gauges.

## Wording on the page

Say "coastal-trapped wave"; quote "Kelvin wave" only from media or forecasts. State
that a coastal anomaly is not by itself evidence of an equatorial origin, and that
wind forcing along the US West Coast explained most of the BC signal in 2026
(63–76 % in the ERA5-forced model).
