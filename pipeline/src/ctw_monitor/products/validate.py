"""Validate product files against schema/*.schema.json before deploying."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from ..config import REPO

SCHEMAS = {
    "manifest.json": "manifest", "stations.json": "stations", "sealevel.json": "timeseries",
    "bottom_pressure.json": "timeseries", "temperature.json": "timeseries",
    "hovmoller.json": "grid", "events.json": "events",
}


def validate_dir(data_dir: Path | str) -> list[str]:
    data_dir = Path(data_dir)
    problems = []
    for fname, sname in SCHEMAS.items():
        f = data_dir / fname
        if not f.exists():
            continue
        schema = json.loads((REPO / "schema" / f"{sname}.schema.json").read_text(encoding="utf-8"))
        try:
            jsonschema.validate(json.loads(f.read_text(encoding="utf-8")), schema)
        except jsonschema.ValidationError as e:
            problems.append(f"{fname}: {e.message} at {list(e.absolute_path)}")
    return problems
