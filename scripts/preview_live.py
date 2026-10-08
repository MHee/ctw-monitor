"""Put the live site's products into web/public/data for a local look at the web app.

    python scripts/preview_live.py [--recompute-events] [--restations] [--site URL]

Downloads every product listed in the live manifest (web/public/data is gitignored; it is
overwritten). When the local code is ahead of the deployed pipeline:
  --recompute-events  rebuild events.json from the live sea-level product with local code
                      (6-hourly input; the nightly build uses hourly, so numbers differ slightly)
  --restations        rebuild stations.json from local config (new station fields)
Either flag sets the manifest's schema_version to the local one. Products are validated.
Then: cd web; npm run build; npx vite preview --port 4173 --strictPort
(vite preview serves web/dist, which copies data/ at build time: always rebuild).
See .claude/skills/preview-live/SKILL.md.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from ctw_monitor import SCHEMA_VERSION
from ctw_monitor.config import load_config
from ctw_monitor.products.events import events_product
from ctw_monitor.products.sealevel import stations_product
from ctw_monitor.products.validate import validate_dir
from ctw_monitor.products.writer import write_json

SITE = "https://mhee.github.io/ctw-monitor"
OUT = Path(__file__).resolve().parents[1] / "web" / "public" / "data"


def series_from(product: dict) -> dict[str, pd.Series]:
    idx = pd.date_range(product["t0"], periods=product["n"], freq=f"{product['dt_s']}s")
    return {k: pd.Series(np.array(v, dtype=float), index=idx) for k, v in product["values"].items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--site", default=SITE)
    ap.add_argument("--recompute-events", action="store_true")
    ap.add_argument("--restations", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = requests.get(f"{a.site}/data/manifest.json", timeout=30).json()
    for name in ["manifest.json", *manifest["products"]]:
        r = requests.get(f"{a.site}/data/{name}", timeout=60)
        r.raise_for_status()
        (OUT / name).write_bytes(r.content)
    print(f"live products ({manifest['generated_at']}, pipeline {manifest['pipeline']['git_sha']}): "
          f"{len(manifest['products'])} files -> {OUT}")
    changed = []
    sl = json.loads((OUT / "sealevel.json").read_text(encoding="utf-8"))
    dist = {k: sl["meta"][k]["alongshore_km"] for k in sl["stations"]}
    if a.recompute_events:
        write_json(events_product(series_from(sl), dist), OUT / "events.json")
        changed.append("events.json")
    if a.restations:
        write_json(stations_product(load_config(), dist), OUT / "stations.json")
        changed.append("stations.json")
    if changed:
        manifest["schema_version"] = SCHEMA_VERSION
        write_json(manifest, OUT / "manifest.json")
        print(f"recomputed with local code: {', '.join(changed)}; schema_version -> {SCHEMA_VERSION}")
    problems = validate_dir(OUT)
    print("validate:", "ok" if not problems else problems)


if __name__ == "__main__":
    main()
