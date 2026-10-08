"""Write products in the data contract (docs/DATA_CONTRACT.md)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .. import SCHEMA_VERSION


def _clean(a, ndigits):
    out = []
    for v in np.asarray(a, dtype=float).ravel():
        out.append(None if not math.isfinite(v) else round(float(v), ndigits))
    return out


def iso(ts) -> str:
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def timeseries_product(product: str, units: str, processing: str, index: pd.DatetimeIndex,
                       values: dict[str, np.ndarray], meta: dict | None = None,
                       ndigits: int = 1) -> dict:
    dt = (index[1] - index[0]).total_seconds()
    # pandas 3 defaults to datetime64[us]; never assume ns from .asi8
    assert np.allclose(index.to_series().diff().dt.total_seconds().iloc[1:], dt), \
        "index must be regular"
    return {
        "schema_version": SCHEMA_VERSION, "product": product, "units": units,
        "processing": processing, "t0": iso(index[0]), "dt_s": int(dt), "n": len(index),
        "stations": list(values),
        "values": {k: _clean(v, ndigits) for k, v in values.items()},
        "meta": meta or {},
    }


def grid_product(processing: str, index: pd.DatetimeIndex, distance_km: np.ndarray,
                 grid: np.ndarray, mask_km: list | None = None, ndigits: int = 1) -> dict:
    return {
        "schema_version": SCHEMA_VERSION, "product": "alongshore_hovmoller", "units": "cm",
        "processing": processing, "t0": iso(index[0]),
        "dt_s": int((index[1] - index[0]).total_seconds()), "n": len(index),
        "distance_km": _clean(distance_km, 1), "values": _clean(grid, ndigits),
        "mask_km": mask_km or [],
    }


def write_json(obj: dict, path: Path | str) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(txt, encoding="utf-8")
    tmp.replace(path)                       # atomic: never leave a half-written product
    return len(txt)
