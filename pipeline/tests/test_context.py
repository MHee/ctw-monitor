"""NOAA CPC context indices: parsing and fail-soft behaviour (rule 8)."""
import json

import pandas as pd

from ctw_monitor import build
from ctw_monitor.products.validate import validate_dir
from ctw_monitor.sources import context

CFG = {"context": {"oni_url": "oni", "roni_url": "roni"}}
NOW = pd.Timestamp("2026-10-08T12:00", tz="UTC")


def test_parse_roni_three_columns():
    rows = context.parse_cpc_index("SEAS   YR  ANOM\nJJA  2026  1.36\nJAS  2026  1.69\n")
    assert rows[-1] == {"season": "JAS", "year": 2026, "anomaly_c": 1.69}


def _index(v):
    return {"season": "JAS", "year": 2026, "anomaly_c": v, "source_url": "u", "info_url": "i",
            "recent": [{"season": "JAS", "year": 2026, "anomaly_c": v}]}


def test_both_indices_written(tmp_path, monkeypatch):
    monkeypatch.setattr(context, "fetch_oni", lambda url: _index(2.16))
    monkeypatch.setattr(context, "fetch_roni", lambda url: _index(1.69))
    st = build.build_context(CFG, tmp_path, NOW)
    d = json.loads((tmp_path / "context.json").read_text())
    assert st["status"] == "ok" and d["oni"]["anomaly_c"] == 2.16 and d["roni"]["anomaly_c"] == 1.69
    assert validate_dir(tmp_path) == []


def test_failed_roni_keeps_last_good_and_marks_stale(tmp_path, monkeypatch):
    lg = tmp_path / "lg"
    lg.mkdir()
    (lg / "context.json").write_text(json.dumps({"schema_version": "0.4.0", "oni": _index(2.0),
                                                 "roni": _index(1.5)}))

    def boom(url):
        raise OSError("timeout")

    monkeypatch.setattr(context, "fetch_oni", lambda url: _index(2.16))
    monkeypatch.setattr(context, "fetch_roni", boom)
    out = tmp_path / "out"
    out.mkdir()
    st = build.build_context(CFG, out, NOW, lg)
    d = json.loads((out / "context.json").read_text())
    assert st["status"] == "stale" and "RONI" in st["message"]
    assert d["oni"]["anomaly_c"] == 2.16 and d["roni"] == {**_index(1.5), "stale": True}
    assert validate_dir(out) == []
