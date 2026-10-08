# Architecture and decisions

## Decision 1: static JSON on GitHub Pages, no database

**Chosen:** the pipeline writes a handful of JSON files; the site is static.
**Rejected for now:** Supabase (the WaveGlider dashboard's pattern).

| question | this monitor | WaveGlider dashboard |
|---|---|---|
| how data arrive | one nightly batch, single writer | continuous telemetry from a live vehicle |
| update pattern | the recent window is **recomputed** each night (filter edges, detiding, anomalies change past values) | rows appended, rarely changed |
| reads | the whole current product, by every visitor | queries by mission, time range, waypoint |
| volume | under 1 MB of JSON in total (measured below) | grows without bound |
| user state | none | — |

A database pays off for appends, ad-hoc queries and multiple writers. None apply here.
It would add a schema, row-level security policies and a public anon key to maintain,
and the Supabase free plan pauses projects that see low database activity over 7 days
(supabase.com/docs/guides/platform/free-project-pausing), so a quiet spell between
events would take the page down unless something pings it.

**Size, measured on the synthetic set** (series written: 26 gauges, 3 bottom-pressure, 4 CTD; 400 days; 6-hourly
series, distance–time grid at 50 km × 12 h): 0.73 MB of JSON in total, 0.11 MB gzipped
(GitHub Pages serves gzip). `hovmoller.json` is the largest file (0.50 MB raw,
0.06 MB gzipped); a 25 km × 6 h grid made it 2.0 MB raw, which is why the grid is coarser
than the series. Real data will be of the same order.

**When to revisit.** Add a database (or Parquet + DuckDB-WASM in the browser) if the
page needs user annotations or event picks by colleagues, sub-hourly live updates, or
interactive queries into a multi-decade archive.

## Decision 2: no data history in git

Products are built in the workflow and published only in the Pages deployment
artifact (`actions/upload-pages-artifact` + `actions/deploy-pages`). Nothing is
committed, so the repository stays small and its history is code only.

State that must survive between runs lives outside git:

| state | where | why |
|---|---|---|
| last good products | the live site itself (`pull-last-good` downloads `data/*.json` at the start of each run) | per-source fallback with zero extra storage |
| raw-data cache (hourly series) | `actions/cache` (key per run, restore by prefix) | incremental fetches; a daily run keeps the cache from the 7-day eviction |
| tidal constants, climatology baselines | GitHub Release assets on fixed tags (`tides-latest`, `baseline-v1`), uploaded with `gh release upload --clobber` | versioned without commits; replaced in place |
| optional archive snapshots | Release assets, e.g. monthly `products-YYYY-MM.zip` | keeps event records without git history |

Alternatives considered: an orphan `data` branch force-pushed each night (works, but
force-pushes leave dangling objects until GitHub garbage-collects them, and it clutters
the branch list); Git LFS (quota-limited and still versioned). Both are worse than the
Pages artifact for a product that is fully regenerated each night.

**Side effect to manage:** in a public repository GitHub disables scheduled workflows
after 60 days without repository activity. With no data commits, a quiet repository
will hit this. Options are in `docs/OPERATIONS.md` (keepalive).

## Decision 3: run in GitHub Actions; a local machine is the fallback

Measured on 2026-10-07 from the analysis sandbox (4-core Windows VM, office network),
using the vendored functions:

| step | window | size | time |
|---|---|---|---|
| NOAA CO-OPS Neah Bay hourly height | 365 d | 8,640 values | 5.6 s |
| CHS IWLS Tofino, hourly (30-day requests) | 90 d | 2,161 values | 1.5 s |
| IOC SLSMF Acajutla, raw ~1 min (10-day chunks) | 30 d | 92,622 samples | 18.9 s |
| ONC NCBC BPR `scalardata/device`, hourly mean | 365 d | 8,760 values | 2.1 s |
| despike + harmonic detide (`despike_detide`) | 365 d hourly | 8,640 | 2.8 s |
| Godin low-pass | 365 d hourly | 8,640 | 0.1 s |
| UTide detide (`detide_utide`) | 365 d hourly | 8,640 | 47.8 s |

Extrapolated for about 35 series:

- **Nightly incremental run** (last 3–10 days of each source, cached history, frozen
  tidal constants): well under 5 minutes including `npm ci` and the Vite build.
- **Full rebuild** (cache lost, 400-day window): about 10–40 minutes, dominated by IOC
  1-minute data for the Mexican gauges (about 4 min per station-year). Use UHSLC
  fast-delivery hourly where it exists, or a shorter IOC window.
- **UTide on every series nightly** would cost about 30 minutes, which is why tidal
  constants are frozen (rule 5 in CLAUDE.md) and refitted monthly.

GitHub-hosted runners for public repositories have no minute limits and allow 6-hour
jobs, so compute is not the constraint. The reasons to run on a local machine instead
would be policy or data access, not speed:

1. ONC does not allow a service-account token to be stored as a GitHub secret.
2. ERA5 forcing for the wind-driven CTW model (`ctw_model` in the vendored analysis
   code): CDS queues are slow and unpredictable. Run this weekly on a local machine
   (or as a separate `workflow_dispatch` job), not in the nightly path.
3. Long baselines (2013–2025 ONC series chunked by year): a one-off job.

`docs/OPERATIONS.md` describes the local mode: a Windows Task Scheduler job that runs
the same CLI, uploads the products as Release assets, and triggers the deploy workflow
with `gh workflow run`, so there is still a single deploy path.

## Inverse-barometer pressure for the nightly run

Station barometers cover most US gauges (CO-OPS `air_pressure`) and CHS Tofino,
Winter Harbour and Prince Rupert (`ap1`); ECCC climate-hourly covers the rest of BC.
The Mexican and Central American gauges have no barometer. Options, to evaluate in M1:
(a) ERA5 msl at gauge points in a weekly job, with the latest ~5 days shown as
"IB pending"; (b) a point API serving reanalysis or analysis pressure without a key
(for example Open-Meteo; not tested here). Until then those traces are labelled
"not IB-corrected".

## Dependencies: lean by design

The nightly job installs only the core of `pipeline/pyproject.toml`: numpy, pandas, scipy,
requests, pyyaml and jsonschema. It does not need the analysis environment used for the
2026 report (`tides`: utide, pyfes, gsw, xarray, statsmodels, matplotlib). Heavier
packages are optional extras, installed only by the jobs that use them:

| extra | packages | used by |
|---|---|---|
| `tides` | utide | monthly `tides-fit` |
| `era5` | xarray, netCDF4 | weekly ERA5 IB / wind forcing |
| `apt` | obspy | optional CBC27 APT from EarthScope |
| `dev` | pytest, ruff | CI and local development |

The vendored modules import their dependencies inside each function, so importing them
costs nothing; only calling `detide_utide` or the ERA5 readers needs the extras. The cmocean
colormap is baked into `web/src/lib/colormap.js` as a 256-entry table, so cmocean is not a
dependency at all. Local development uses its own `ctw-monitor` conda env
(`environment.yml`), not the base env or `tides`.

## Front end

Vue 3 + Vite, Chart.js for line panels, a plain canvas for the distance–time heatmap
(about 100,000 cells; Chart.js is not suited to this), Leaflet for the optional map.
`VITE_BASE` sets the Pages sub-path. The app reads `data/manifest.json` first and
falls back to `data-sample/` (synthetic, flagged) when no real data are present.
