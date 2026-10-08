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
5. Drift (decided 2026-10-08, method B): `a + b·t + c·exp(−t/τ)` per deployment, fitted by
   `tides-fit` to the basin-referenced daily record of the whole current deployment
   (detided hourly values, days with ≥ 20 h), τ by scan, **the last 60 days left out**,
   then frozen in `tidal_constants.json` and extrapolated nightly. A gauge's fit can start
   later (`drift_fit_from`; FGPD after its ~15 cm step in 2020–21). If the deployed device
   differs from the fitted one, or a deployment has under 180 days, the nightly falls back
   to a straight line over the window and says so in `meta`. Compared with a linear fit
   over the window, a 120-day high-pass and none, B revised recent values least (0.31 cm
   mean against 1.37 cm) and tracked Bamfield/Tofino sea level best (r = 0.88); the
   high-pass removed the real seasonal signal (r = 0.61).
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

Defaults accepted by Martin on 2026-10-08, from a test on 399 days of live data
(3 Sep 2025 to 8 Oct 2026, 26 gauges; write-up: https://claude.ai/artifact/Rj9djVHEYttEzzGbxUf1bd).

1. Find extrema of the **hourly** Godin-filtered anomaly at each gauge (inside the
   pipeline, not the 6-hourly product) with prominence ≥ 3 cm and separation ≥ 5 days.
   Extrema at the edge of a data run are dropped.
2. Associate extrema of the same type between **neighbouring gauges**, ordered by
   along-coast distance. Each link joins the mutually nearest extrema within ±5 days.
   A gauge without data around the time is skipped. If two chains share at least half
   of their gauges within 2 days, keep the longer one.
3. **Break the chain** at any gap of more than 1000 km between gauges. The Baja
   California gap (about 1870 km) therefore separates a Mexico/Central America segment
   from the US/Canada segment.
4. An **event** needs ≥ 6 gauges spanning ≥ 1000 km, with a median extremum
   prominence ≥ 5 cm.
5. Fit time against distance (`propagation_fit`). Report the speed with its 95 % CI
   (t distribution, n − 2 dof), n stations, span and r². Use the timing of extrema;
   do not use lag correlation.
6. **Propagating** means 1 ≤ speed ≤ 10 m/s, r² ≥ 0.7, and a lower 95 % bound > 0.
   Anything else is "not propagating". A negative speed is labelled "southward".
7. **Major** means a median prominence ≥ 15 cm (about 11 events a year, the top 15 %).

Evidence, 2025-09 to 2026-10: the 17 May 2026 minimum gives 3.1–3.2 m/s, r² 0.86, 17
gauges, under all 24 combinations of prominence 2–5 cm, separation 3–7 d and window
5–10 d. The rules give 67 events, 29 of them propagating (median 4.0 m/s,
interquartile range 3.2–5.2). Only 3 of the 11 major events propagate. The rest are
winter storms that force the whole coast at once (r² ≈ 0) or travel south. The
detector cannot tell them apart; the classification does. Sensitivity:
r² 0.6/0.7/0.8 gives 33/29/18 propagating events; an upper bound of 6 m/s instead of 10
changes 29 to 28; a ±5-day window gives the same events as ±10 days; a 7-day separation
merges the late-May and early-June minima.

The 2026 reference: minima-timing speed 3.1 m/s (San Francisco and Crescent City 3
days before Neah Bay); Mexican pulse 1.95 ± 0.20 m/s (Acajutla 3 May to Puerto Vallarta
13 May), not traceable north of Puerto Vallarta for lack of Baja gauges.

## Wording on the page

Say "coastal-trapped wave"; quote "Kelvin wave" only from media or forecasts. State
that a coastal anomaly is not by itself evidence of an equatorial origin, and that
wind forcing along the US West Coast explained most of the BC signal in 2026
(63–76 % in the ERA5-forced model).
