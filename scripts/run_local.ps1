# Local mode (docs/OPERATIONS.md): run the pipeline on an ONC machine and hand the products
# to the deploy workflow as Release assets. Schedule daily in Windows Task Scheduler.
# Needs: conda env ctw-monitor, GitHub CLI (gh) logged in, ONC_API_TOKEN in the user env.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
conda activate ctw-monitor
$out = Join-Path $repo "build\data"
$cache = Join-Path $env:LOCALAPPDATA "ctw-monitor\raw"
python -m ctw_monitor.cli build --out $out --cache $cache
gh release upload products-latest (Get-ChildItem "$out\*.json").FullName --clobber
gh workflow run build-deploy.yml -f source=release
