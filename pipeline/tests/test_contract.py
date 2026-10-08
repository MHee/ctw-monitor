"""Synthetic products must satisfy the data contract; the contract is what the web app reads."""
import json

import numpy as np

from ctw_monitor.products.validate import validate_dir
from ctw_monitor.synthetic import make_synthetic


def test_synthetic_products_validate(tmp_path):
    m = make_synthetic(tmp_path)
    assert m["synthetic"] is True
    assert validate_dir(tmp_path) == []
    for f in m["products"]:
        assert (tmp_path / f).exists(), f


def test_lengths_match_n(tmp_path):
    make_synthetic(tmp_path)
    for f in ["sealevel.json", "bottom_pressure.json", "temperature.json"]:
        d = json.loads((tmp_path / f).read_text())
        assert all(len(v) == d["n"] for v in d["values"].values()), f
    h = json.loads((tmp_path / "hovmoller.json").read_text())
    assert len(h["values"]) == h["n"] * len(h["distance_km"])


def test_total_size_is_small(tmp_path):
    make_synthetic(tmp_path)
    total = sum(p.stat().st_size for p in tmp_path.glob("*.json"))
    assert total < 5e6, total
