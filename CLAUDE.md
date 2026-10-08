# CLAUDE.md — coastal-trapped wave monitor

Read this first. Then read `docs/ARCHITECTURE.md`, `docs/DATA_CONTRACT.md` and
`docs/METHODS.md` before writing code. Owner: Martin Heesemann (ONC). He works in
Python, uses conda for environments, and builds frontends with Vue 3 + Vite + vitest.

## What we are building

A static dashboard on GitHub Pages, rebuilt daily by GitHub Actions, that shows:

1. **Propagation panel (the main one):** a distance–time diagram of IB-corrected,
   detided, Godin-filtered sea-level anomaly along the coast from Acajutla (El Salvador)
   to Prince Rupert, with distance measured along a coastal path (0 km at Neah Bay,
   positive poleward). Below it, offset line traces per gauge.
2. **NEPTUNE cross-margin section:** basin-referenced bottom-pressure anomaly at
   FGPD (95 m), NCBC (396 m) and NC89 (1257 m), in cm of equivalent water.
3. **Slope temperature:** daily temperature anomaly (vs the multi-year day-of-year
   mean) at the Barkley Canyon CTDs and NC89.
4. **Events table:** detected sea-level minima and maxima with along-coast speed
   (from the timing of the extrema; see rule 3).
5. **Status:** age of each data stream (LIVE / STALE / FAULT) from `manifest.json`.
6. **Context:** latest NOAA ONI / Niño 3.4 value with a link. Context only.

## Hard rules (do not relax without asking Martin)

1. **Terminology (Steve Mihaly's rule, adopted Oct 2026).** Say *coastal-trapped wave*
   for the signal off Oregon, Washington and BC. Reserve *Kelvin wave* for the
   equatorial Kelvin wave, and use it only when quoting media or forecasts. Do not
   call the page an "El Niño monitor".
2. **IB correction applies to tide gauges, never to BPRs.** A BPR already records
   only the departure from the inverse-barometer response. For gauges, use local air
   pressure from the station barometer when it exists, else the nearest met station,
   else ERA5. Record which one was used per station in the product metadata.
3. **Propagation speed comes from the timing of the minima/maxima**, fitted against
   along-coast distance. Do not use whole-window lag correlation: weather forces the
   whole coast at once and biases the speed fast (2026: 3.1 m/s from the minima,
   about 6 m/s from lag correlation). Regress time on distance, not distance on time:
   timing errors bias the latter low (2026 minima: 3.8 m/s time-on-distance; Martin,
   2026-10-08; docs/METHODS.md).
4. **Bottom pressure is basin-referenced.** Subtract the mean of the Cascadia Basin
   gauges (CNE20, CBC27 CORK-1027C and, if added, the CBC27 APT) before filtering.
   CORK and APT seafloor gauges are as good as BPRs. Exclude CQS64 (CORK-1364A):
   its "Seafloor Pressure" stream has been the 156 mbsf borehole screen since 2012.
5. **Detiding uses frozen tidal constants**, refitted monthly or on demand
   (`ctw-monitor tides-fit`) and stored as a versioned file. Nightly runs only
   predict. This keeps past values stable and keeps the nightly job fast.
6. **Data never goes into git.** No JSON, CSV or Parquet under version control.
   `web/public/data/` is gitignored. Products are deployed in the Pages artifact.
   Persistent inputs that must outlive a run (tidal constants, climatology baselines)
   are GitHub Release assets, uploaded with `--clobber` to a fixed tag.
7. **Tokens.** The ONC token is used only by the pipeline in Actions, as the
   repository secret `ONC_API_TOKEN`, and never reaches the built site. Use a
   dedicated ONC service account, not Martin's personal token. Never print tokens,
   never write them to files, and never put a token in `VITE_*` variables.
8. **Fail soft, per source.** One failed source must not fail the run or blank the
   page. Reuse its last good product, set `status: "stale"` with the error message,
   and exit 0. Exit non-zero only on programming errors (so CI shows real bugs).
9. **Branding.** Follow `docs/BRANDING.md`. The footer must carry "A University of
   Victoria initiative". ONC Blue `#129DC0` is an accent and highlight only. Anomaly
   fields use a diverging scientific colormap (cmocean *balance*), not brand colours.
10. **Say what the data are.** The fixed banner states that the page is a personal
    prototype (not an official ONC data product), that it is not a forecast, that IOC data are real-time and not quality-controlled, and when the
    page shows synthetic data. Every panel states units and processing in one line.

## Milestones (do them in order; each ends with green CI)

- **M0 – bootstrap.** `git init`, first commit from this skeleton, `npm install` to
  create `web/package-lock.json` (commit it), bump GitHub Action majors to current,
  `pytest` and `npm run build` pass on synthetic data. Enable Pages with source
  "GitHub Actions". Add secret `ONC_API_TOKEN`.
- **M1 – tide-gauge chain.** Implement `sources/tide_gauges.py` (NOAA CO-OPS, CHS
  IWLS, IOC, UHSLC) using `vendor/margin_data.py`; `process/` despike, detide,
  IB, Godin, anomaly; `products/` for `sealevel.json` and `hovmoller.json`.
  Panel 1 renders real data. Close the masked gaps in the chain: add CO-OPS gauges between
  La Jolla and San Francisco (760 km gap; for example Los Angeles, Port San Luis, Monterey)
  and a central BC coast gauge between Winter Harbour and Prince Rupert (530 km); look up
  the station ids. The Baja California gap (about 1870 km) has no 2026 data source.
- **M2 – NEPTUNE section and temperature.** `sources/onc.py` via `vendor/onc_api.py`;
  basin reference; `bottom_pressure.json`, `temperature.json`; panels 2 and 3.
- **M3 – events and status.** `process/propagation.py` (extrema timing, speed with
  CI), `events.json`; status panel; ONI context.
- **M4 – operations.** Raw-data cache, last-good fallback, `tides-fit` and
  `baseline` commands with Release-asset storage, keepalive decision, README badges.
- **M5 – polish.** Station map (Leaflet + GMRT basemap), accessibility pass
  (contrast, keyboard, alt text), Lighthouse ≥ 90, mobile layout, favicon (Martin,
  2026-10-08; follow docs/BRANDING.md). Explainer page in the
  style of 3Blue1Brown (Martin, 2026-10-08): the 17 May 2026 minimum moving up the coast,
  collapsed into the distance–time plot (slope = speed), set against a winter storm that
  hits the whole coast at once (r² ≈ 0).

## Commands

```powershell
conda activate ctw-monitor                       # environment.yml at repo root
pip install -e pipeline
python -m ctw_monitor.cli synthetic --out web/public/data
python -m ctw_monitor.cli build --out web/public/data --cache .cache/raw [--full]
python -m ctw_monitor.cli pull-last-good --site <url> --out .cache/last_good
python -m ctw_monitor.cli tides-fit --years 2 --out .cache/tidal_constants.json
python -m ctw_monitor.cli baseline --start 2013-01-01 --out .cache/baseline.json
pytest pipeline/tests
ruff check pipeline
cd web; npm run dev; npm run build; npx vitest run
```

## Code conventions

- Keep the nightly install to the core dependencies in `pipeline/pyproject.toml`. New
  heavy packages go into an optional extra used only by the job that needs them.

- Python ≥ 3.12, `pandas` time series with tz-aware UTC `DatetimeIndex` throughout.
  Sea level and equivalent water height in **cm**; pressure in **Pa** (never mdbar).
- Every product file validates against its schema in `schema/` (tested in CI).
- `vendor/` holds code copied from the Claude Science skills
  `ne-pacific-margin-data`, `coastal-trapped-wave-analysis` and `onc-oceans3-api`
  (Oct 2026). Treat it as a library: wrap it, do not edit it in place unless fixing a
  bug, and note any fix in `vendor/README.md`.
- Keep network calls in `sources/`, pure functions in `process/`, file writing in
  `products/`. `process/` functions get unit tests on synthetic series.
- Web: Vue 3 `<script setup>`, Chart.js for line panels (`applyChartDefaults` from
  `lib/onc-theme.js`), a plain canvas for the distance–time heatmap. Colours come from
  `onc-theme.js` and CSS variables, never hard-coded hex in components.

## Known data-access facts (tested Oct 2026)

- ONC `scalardata/device` with `deviceCode`, `resamplePeriod=3600` returns a year of
  hourly BPR data in about 2 s. `scalardata/location` with `locationCode=NCBC`,
  `deviceCategoryCode=BPR`, `propertyCode=seawaterpressure` returned HTTP 400
  (errorCode 127) on 2026-10-07; find the right codes with the discovery endpoints
  before relying on location-based stitching across device swaps.
- ONC errorCode 127 for a window before a device was deployed means "no data", not a
  failure. Chunk multi-year requests by year (they time out at 120 s otherwise).
- With `outputFormat=object` and a resample period, `sensorData[i].data` is a list of
  per-interval dicts; qaqcFlag 7 ("averaged value") is normal; treat {1, 2, 7} as good.
- CHS IWLS: 30-day windows at `SIXTY_MINUTES`, 6-day windows at 15 min. Online `wlo`
  holdings start around 2019–2020 for Tofino, Bamfield, Winter Harbour, Prince Rupert.
- NOAA CO-OPS `hourly_height` (verified) had no data for the last days at any gauge on
  2026-10-07; use 6-min `water_level` (31-day request limit) for nightly runs. Every
  configured CO-OPS gauge reports `air_pressure` (Los Angeles 9410660 only intermittently).
- Acajutla: IOC `acaj` (sensor `rad`) is live; UHSLC fast delivery (id 82) lagged five
  weeks. The IOC `atm` channel there is near-constant and not a barometer.
- Central BC gap filler: CHS Pruth Bay 08863 (Calvert Island), live, no `ap1`.
- IOC SLSMF: about 1-min raw data, 10-day chunks; an empty list with HTTP 200 means no
  data. No 2026 Baja California gauges on IOC or UHSLC (Ensenada, Cedros, Cabo San Lucas
  and Mazatlán are missing), so the chain has a gap between La Jolla and Puerto Vallarta.
- NC89 CTD salinity is bad in 2026 (temperature is fine). NC27 CORK-1026 seafloor
  gauge stopped 2026-07-14. CDFM has no 2026 data.
- The CBC27 APT is not in ONC scalardata; it is FDSN `NV.CBC27.Z1.MDD` at EarthScope
  (5 Hz, counts/50 = Pa). Optional; needs `obspy`.
- ERA5 via the CDS API: one year per request, results come from
  `object-store.os-api.cci2.ecmwf.int`; latency about 5 days. Do not put CDS in the
  nightly path. See `docs/ARCHITECTURE.md` for the IB fallback plan.

## Feedback to the Claude for Science skills

`feedback/` (gitignored) is a directory junction to `OneDrive\Claude_Exchange\feedback\`,
where Claude for Science instances read reports on the vendored skills and reply. One file
per item; protocol in `feedback/README.md`. File a report when you fix or work around
something in `vendor/`, and check at the start of a session for items whose status changed
(`answered`, `accepted`, `declined`) and act on the replies. On a fresh clone, recreate the
link with `cmd /c mklink /J feedback C:\Users\mheesema\OneDrive\Claude_Exchange\feedback`.

## Decisions (Oct 2026)

- Public prototype on Martin's personal GitHub account (`MHee/ctw-monitor`).
- Code licence MIT (`LICENSE`). Derived data CC BY 4.0, matching ONC.
- The ONC token as repository secret `ONC_API_TOKEN` is acceptable (public data, no
  write endpoints). Use a token from a regular, non-staff ONC account so the public
  page can only show what any public user can see.
- Bottom-pressure drift: method B, a frozen exponential + linear fit per deployment,
  refitted with the tidal constants (2026-10-08; docs/METHODS.md).

## Open decisions (ask Martin)

- Keepalive: accept one automated commit about every six weeks, or trigger externally.
- Baseline period for anomalies (proposal: 2013–2025 day-of-year mean, 31-day smoothing).

## Definition of done for any change

`pytest` and `ruff` clean; `npm run build` clean; all product files validate against
`schema/`; synthetic mode still works; no data files staged (`git status`); the
banner, footer and units are intact.
