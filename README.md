# Coastal-trapped wave monitor

A static web dashboard that tracks subtidal sea-level and bottom-pressure anomalies
along the eastern Pacific margin, from Central America to British Columbia, and across
the NEPTUNE slope off Vancouver Island. Its main panel is a distance–time
(Hovmöller) diagram of the tide-gauge chain, the view in which a poleward-propagating
coastal-trapped wave can be seen.

**Status:** skeleton (October 2026). The pipeline runs end to end on synthetic sample
data only. Real data fetching, processing and the chart panels are stubs, to be finished
with Claude Code following [CLAUDE.md](CLAUDE.md).

**What it is not:** an El Niño forecast. A coastal anomaly off BC is not by itself
evidence that an equatorial signal has arrived. The page says so in a fixed banner.

## How it works

```
GitHub Actions (daily cron, 13:17 UTC)
  pipeline/  Python: fetch -> despike/detide -> IB-correct (gauges only)
             -> Godin low-pass -> anomaly -> grid -> JSON
  web/       Vue 3 + Vite: reads ./data/*.json, draws the panels
  -> upload-pages-artifact -> deploy-pages
```

- Data products are **never committed**. They are built in the workflow and published
  only inside the Pages deployment artifact, so the repository has no data history.
- If a source fails, the pipeline reuses that source's last good product (downloaded
  from the live site at the start of each run) and marks it stale in `manifest.json`.
- No database. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for why JSON on
  GitHub Pages was chosen over Supabase, and for measured fetch and processing times.

## Layout

| path | content |
|---|---|
| `CLAUDE.md` | instructions for Claude Code: rules, milestones, definition of done |
| `docs/` | architecture, data contract, methods, data sources, branding, operations |
| `config/stations.yaml` | station list with provider ids and coordinates |
| `schema/` | JSON Schemas for every published file |
| `pipeline/` | Python package `ctw_monitor` (CLI, sources, processing, writers) |
| `pipeline/src/ctw_monitor/vendor/` | tested fetch and analysis functions from the Oct 2026 skills |
| `web/` | Vue 3 + Vite single-page app with ONC branding |
| `.github/workflows/` | `build-deploy.yml` (daily), `ci.yml` (PRs), `keepalive.yml` (optional) |

## Quick start (local)

```powershell
conda env create -f environment.yml
conda activate ctw-monitor
pip install -e pipeline

# synthetic sample data -> web/public/data (gitignored)
python -m ctw_monitor.cli synthetic --out web/public/data

cd web
npm install
npm run dev        # http://127.0.0.1:5173
```

A real build needs an ONC API token in `ONC_API_TOKEN`:

```powershell
$env:ONC_API_TOKEN = "<token>"
python -m ctw_monitor.cli build --out web/public/data --cache .cache/raw
```

Work in a clone outside OneDrive (for example `C:\Users\mheesema\projects\ctw-monitor`).
OneDrive syncing `node_modules/` and `.git/` is slow and can corrupt the repository.
This OneDrive folder is the seed for the first commit.

## Data and attribution

Ocean Networks Canada (CC BY 4.0), Fisheries and Oceans Canada / Canadian Hydrographic
Service (Open Government Licence – Canada), NOAA CO-OPS and NDBC (public domain),
IOC Sea Level Station Monitoring Facility (real-time, not quality-controlled), University
of Hawaii Sea Level Center fast-delivery data, ECCC via CIOOS Pacific, and Copernicus
ERA5. Full list and credit lines: [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Credits

Concept and direction: Martin Heesemann (Ocean Networks Canada,
ORCID [0000-0002-6877-6062](https://orcid.org/0000-0002-6877-6062)).
Methods follow the ONC internal report on the May–June 2026 coastal-trapped event
(v015, October 2026), reviewed by Steve Mihaly (ONC).

This skeleton was generated with AI assistance (Claude) under M. Heesemann's direction
and spot checks. It is provided as is and has not had a detailed human review.

Licence: code under the [MIT licence](LICENSE). Derived data products under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); credit the original
sources listed above.
