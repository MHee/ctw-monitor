"""ctw-monitor command line. `python -m ctw_monitor.cli <command> -h` for options."""
from __future__ import annotations

import argparse
import json
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ctw-monitor")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("synthetic", help="write synthetic sample products (flagged)")
    p.add_argument("--out", default="web/public/data")
    p.add_argument("--end", default="2026-10-01")

    p = sub.add_parser("build", help="nightly build")
    p.add_argument("--out", default="web/public/data")
    p.add_argument("--cache", default=".cache/raw")
    p.add_argument("--last-good", default=None)
    p.add_argument("--full", action="store_true", help="ignore the raw cache, refetch the window")
    p.add_argument("--days", type=int, default=400)
    p.add_argument("--tides", default=".cache/tidal_constants.json",
                   help="frozen tidal constants (tides-fit output; Release asset tides-latest)")

    p = sub.add_parser("pull-last-good", help="download products from the live site")
    p.add_argument("--site", required=True)
    p.add_argument("--out", default=".cache/last_good")

    p = sub.add_parser("validate", help="validate a product directory against schema/")
    p.add_argument("dir")

    p = sub.add_parser("tides-fit", help="refit frozen tidal constants for the tide gauges")
    p.add_argument("--years", type=float, default=2.0)
    p.add_argument("--out", default=".cache/tidal_constants.json")
    p.add_argument("--cache", default=".cache/raw")
    p.add_argument("--stations", default=None, help="comma-separated station ids (default: all)")

    p = sub.add_parser("baseline", help="day-of-year anomaly baselines (one-off, slow)")
    p.add_argument("--start", default="2013-01-01")
    p.add_argument("--out", default=".cache/baseline.json")

    a = ap.parse_args(argv)
    if a.cmd == "synthetic":
        from .synthetic import make_synthetic
        m = make_synthetic(a.out, end=a.end)
        print(json.dumps({"written": m["products"] + ["manifest.json"], "out": a.out}))
    elif a.cmd == "build":
        from .build import run_build
        m = run_build(a.out, a.cache, a.last_good, a.full, a.days, a.tides)
        print(json.dumps({s["id"]: s["status"] for s in m["sources"]}))
    elif a.cmd == "pull-last-good":
        from .products.last_good import pull_last_good
        print(json.dumps(pull_last_good(a.site, a.out)))
    elif a.cmd == "tides-fit":
        from .tides_fit import run_tides_fit
        only = set(a.stations.split(",")) if a.stations else None
        d = run_tides_fit(a.out, a.years, a.cache, only)
        print(json.dumps({"stations": len(d["stations"]), "failed": d["failed_this_run"]}))
    elif a.cmd == "validate":
        from .products.validate import validate_dir
        probs = validate_dir(a.dir)
        print("\n".join(probs) or "ok")
        return 1 if probs else 0
    else:
        raise SystemExit(f"{a.cmd}: not implemented yet (milestone M4)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
