"""Nightly build: fetch -> process -> write, failing soft per source (CLAUDE.md rule 8).

Skeleton: every fetcher raises NotImplementedError until milestones M1-M3, so a real build
currently records each source as failed and reuses last-good products if present.
"""
from __future__ import annotations

import os
import shutil
import traceback
from pathlib import Path

import pandas as pd

from . import SCHEMA_VERSION, __version__
from .config import enabled, load_config
from .products.validate import validate_dir
from .products.writer import iso, write_json
from .sources import onc, tide_gauges

# product file -> list of (source id, fetch callable, config section, provider filter)
PLAN = {
    "sealevel.json": [
        ("noaa_coops", tide_gauges.fetch_noaa, "tide_gauges", "noaa_coops"),
        ("chs_iwls", tide_gauges.fetch_chs, "tide_gauges", "chs_iwls"),
        ("ioc_slsmf", tide_gauges.fetch_ioc, "tide_gauges", "ioc"),
        ("uhslc_fast", tide_gauges.fetch_uhslc, "tide_gauges", "uhslc"),
    ],
    "bottom_pressure.json": [("onc_bpr", onc.fetch_bottom_pressure, "bottom_pressure", None)],
    "temperature.json": [("onc_ctd", onc.fetch_temperature, "temperature", None)],
}


def run_build(out_dir, cache_dir=".cache/raw", last_good_dir=None, full=False, days=400):
    cfg = load_config()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    now = pd.Timestamp.now(tz="UTC").floor("h")
    start = now - pd.Timedelta(days=days)
    statuses = []
    for product, sources in PLAN.items():
        results, product_failed = [], False
        for sid, fn, section, prov in sources:
            sts = [s for s in enabled(cfg[section]) if prov is None or s.get("provider") == prov]
            if not sts:
                continue
            try:
                results.append(fn(sts, start, now))
                statuses.append({"id": sid, "status": "ok", "last_success": iso(now)})
            except Exception as e:  # fail soft, record why
                product_failed = True
                statuses.append({"id": sid, "status": "failed", "message": f"{type(e).__name__}: {e}"[:300]})
                if not isinstance(e, NotImplementedError):
                    traceback.print_exc()
        if product_failed or not results:
            # TODO(M4): merge partial results with last-good per station instead of all-or-nothing
            if last_good_dir and (Path(last_good_dir) / product).exists():
                shutil.copy2(Path(last_good_dir) / product, out / product)
                for s in statuses:
                    if s["status"] == "failed":
                        s["status"] = "stale"
            continue
        # TODO(M1-M3): process results (process/steps.py) and write the product
    manifest = {
        "schema_version": SCHEMA_VERSION, "generated_at": iso(now), "synthetic": False,
        "pipeline": {"version": __version__, "git_sha": os.environ.get("GITHUB_SHA", "local")[:12]},
        "window": {"start": iso(start), "end": iso(now)},
        "sources": statuses,
        "products": sorted(p.name for p in out.glob("*.json") if p.name != "manifest.json"),
    }
    write_json(manifest, out / "manifest.json")
    problems = validate_dir(out)
    if problems:
        raise SystemExit("schema validation failed:\n" + "\n".join(problems))
    return manifest
