# Operations

## One-time setup

1. Create the repository (owner per the open decision in CLAUDE.md) and push.
2. Settings → Pages → Source: **GitHub Actions**.
3. Settings → Secrets and variables → Actions → New secret `ONC_API_TOKEN`
   (ONC service account). Nothing else is secret: NOAA, CHS, IOC, UHSLC and the
   CIOOS ERDDAP need no keys. `CDS_API_TOKEN` only if ERA5 runs in Actions.
4. Create the Release tags `tides-latest` and `baseline-v1` (empty releases are fine);
   `tides-fit` and `baseline` upload to them.
5. Run **Build data and deploy** once by hand (Actions → workflow_dispatch, tick
   `full_rebuild`).

## Schedule

`build-deploy.yml` runs daily at 13:17 UTC (06:17 PDT / 05:17 PST), after the NOAA and
CHS overnight updates and off the top of the hour, where GitHub delays and drops
scheduled runs most. Scheduled runs are best-effort and can be late by tens of minutes;
subtidal products do not care.

## Keeping the schedule alive (public repositories)

GitHub disables scheduled workflows in a public repository after 60 days without
repository activity, silently. Pick one:

- **Keepalive commit** (`keepalive.yml`, disabled by default): runs weekly; if the last
  commit on `main` is older than 45 days it commits a date to `.github/keepalive`.
  About 8 tiny commits a year in one file.
- **External trigger:** a scheduled task on an ONC machine runs
  `gh workflow run build-deploy.yml` daily. Also removes GitHub's cron delay. Check
  whether `workflow_dispatch` runs count as repository activity before relying on this
  alone (not verified).
- **Private repository:** the 60-day rule is documented for public repositories only;
  Pages on a private repository needs a paid GitHub plan.

Whatever is chosen, the status panel shows the age of every stream, so a stopped
schedule is visible on the page within a day.

## Failure handling

- Per-source errors: product reused from last good, `status: "stale"`, message in
  `manifest.json`, run exits 0.
- A source stale for more than 3 days shows STALE; more than 14 days shows FAULT.
- A programming error fails the run; the previous deployment stays live.
- Optional: a step that opens or updates a GitHub issue when any source is FAULT.

## ONC token for local runs

Store it once in Windows Credential Manager (encrypted per user, never in a file); the
pipeline reads it when `ONC_API_TOKEN` is not set:

```powershell
conda activate ctw-monitor
python -m keyring set ctw-monitor ONC_API_TOKEN     # prompts without echo
python -m keyring del ctw-monitor ONC_API_TOKEN     # to remove it
```

Actions keeps using the repository secret. Do not use `conda env config vars` for the
token: it is stored in plain text in the environment folder.

## Local mode (if tokens cannot live on GitHub)

On an ONC Windows machine with the `ctw-monitor` conda env:

```powershell
# scripts/run_local.ps1, scheduled daily in Task Scheduler
conda activate ctw-monitor
python -m ctw_monitor.cli build --out build\data --cache $env:LOCALAPPDATA\ctw-monitor\raw
gh release upload products-latest build\data\*.json --clobber
gh workflow run build-deploy.yml -f source=release
```

The deploy workflow then skips the pipeline, downloads the `products-latest` assets
and deploys as usual. The browser never reads Release assets directly (no CORS).

## Monthly and one-off jobs

| job | how | output |
|---|---|---|
| tidal constants | `tides-fit` (manual dispatch or local), ≥ 1 year per station | `tides-latest/tidal_constants.json` |
| anomaly baselines | `baseline` (local, ONC multi-year by year) | `baseline-v1/baseline.json` |
| ERA5-forced CTW model | weekly, local or manual dispatch | `products-latest/ctw_model.json` (M5+) |
