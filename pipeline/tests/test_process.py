"""process/ and the sea-level build on synthetic series (no network)."""
import json

import numpy as np
import pandas as pd
import pytest

from ctw_monitor import build
from ctw_monitor.process import steps, tides
from ctw_monitor.products.validate import validate_dir
from ctw_monitor.sources.base import SourceResult
from ctw_monitor.sources.cache import RawCache

TRUE = {"constituents": {"M2": {"amp_cm": 90.0, "phase_deg": 40.0},
                         "K1": {"amp_cm": 45.0, "phase_deg": 200.0},
                         "O1": {"amp_cm": 28.0, "phase_deg": 300.0},
                         "S2": {"amp_cm": 25.0, "phase_deg": 75.0}},
        "start": "2024-01-01T00:00:00Z", "end": "2025-01-01T00:00:00Z"}


def hourly(start, days):
    return pd.date_range(start, periods=24 * days, freq="1h", tz="UTC")


def test_nodal_factor_ranges():
    idx = pd.date_range("2000-01-01", "2019-01-01", freq="30D", tz="UTC")
    f, _ = tides.nodal(idx, ["M2", "K1", "O1", "S2"])
    assert 0.96 < f[:, 0].min() < 0.97 and 1.03 < f[:, 0].max() < 1.04
    assert f[:, 1].max() - f[:, 1].min() > 0.2      # K1 varies ~ +-11 %
    assert np.allclose(f[:, 3], 1.0)


def test_fit_then_predict_years_later():
    rng = np.random.default_rng(0)
    idx = hourly("2024-01-01", 365)
    s = tides.predict(TRUE, idx) + 5 + rng.normal(0, 2, idx.size)
    s[rng.random(idx.size) < 0.1] = np.nan                     # gaps are fine
    rec = tides.fit_constants(s)
    for k, v in TRUE["constituents"].items():
        assert rec["constituents"][k]["amp_cm"] == pytest.approx(v["amp_cm"], rel=0.01)
    later = hourly("2029-06-01", 30)                           # nodal phase has moved on
    err = tides.predict(rec, later) - tides.predict(TRUE, later)
    assert np.sqrt(np.mean(err ** 2)) < 1.0


def test_fit_needs_enough_data():
    idx = hourly("2024-01-01", 60)
    with pytest.raises(ValueError):
        tides.fit_constants(tides.predict(TRUE, idx))


def test_despike_against_frozen_tide():
    rng = np.random.default_rng(1)
    idx = hourly("2025-01-01", 60)
    tide = tides.predict(TRUE, idx)
    s = tide + rng.normal(0, 1, idx.size)
    spikes = rng.choice(idx.size, 10, replace=False)
    s.iloc[spikes] += 80
    clean, n = steps.despike(s, tide)
    assert clean.iloc[spikes].isna().all()
    assert n >= 10 and clean.isna().sum() < 25


def test_fill_pressure_uses_offset():
    idx = hourly("2025-01-01", 5)
    a = pd.Series(1010.0 + np.sin(np.arange(idx.size) / 10), idx)
    b = a - 3.0                                                # lower barometer elevation
    a.iloc[50:60] = np.nan
    filled = steps.fill_pressure(a, [b])
    assert filled.notna().all()
    assert np.allclose(filled.iloc[50:60], (b + 3.0).iloc[50:60])


def test_pressure_for_order():
    idx = hourly("2025-01-01", 2)
    p = pd.Series(1015.0, idx)
    coords = {"a": (48.0, -125.0), "b": (48.5, -125.0), "c": (55.0, -125.0)}
    assert steps.pressure_for({"id": "a"}, {"a": p, "b": p}, coords, idx)[1] == "station"
    assert steps.pressure_for({"id": "a"}, {"b": p}, coords, idx)[1].startswith("nearest:b")
    assert steps.pressure_for({"id": "c"}, {"b": p}, coords, idx)[1] == "none"   # 720 km away
    assert steps.pressure_for({"id": "a", "pressure": "era5"}, {"a": p}, coords, idx) == (None, "none")


def test_gauge_chain_recovers_subtidal_and_removes_ib():
    rng = np.random.default_rng(2)
    idx = hourly("2025-01-01", 120)
    td = np.arange(idx.size) / 24.0
    signal = 10 * np.exp(-0.5 * ((td - 60) / 5) ** 2)               # a 10 cm event
    pa = pd.Series(1013 + 15 * np.sin(2 * np.pi * td / 9), idx)     # 9-day weather cycle
    ib = -(pa - pa.mean()) * 0.9945
    s = tides.predict(TRUE, idx) + signal + ib + 300 + rng.normal(0, 1, idx.size)
    lp, meta = steps.gauge_chain(s, pa, TRUE)
    want = pd.Series(signal, idx) - signal.mean()
    ok = lp.notna()
    assert ok.sum() > 0.9 * idx.size
    assert np.sqrt(np.mean((lp[ok] - want[ok]) ** 2)) < 0.6
    assert meta["tide_source"].startswith("frozen")
    lp_no_ib, _ = steps.gauge_chain(s, None, TRUE)                 # without IB the weather stays
    assert np.sqrt(np.mean((lp_no_ib[ok] - want[ok]) ** 2)) > 5


def test_cache_fetches_only_the_tail(tmp_path):
    calls = []
    idx_all = hourly("2025-01-01", 30)
    truth = pd.Series(np.arange(idx_all.size, dtype=float), idx_all)

    def fetch(a, b):
        calls.append((a, b))
        return truth[(truth.index >= a) & (truth.index <= b)]

    c = RawCache(tmp_path)
    s1 = c.get("x", "st", idx_all[0], idx_all[400], fetch)
    s2 = c.get("x", "st", idx_all[0], idx_all[-1], fetch)
    assert len(calls) == 2 and calls[1][0] == idx_all[400] - pd.Timedelta(days=3)
    assert s1.equals(truth.iloc[:401]) and s2.equals(truth)
    assert RawCache(tmp_path, full=True).load("x", "st").empty


def _fake_source(ids, fail=False):
    def fn(stations, start, end, cache=None):
        if fail:
            raise RuntimeError("no station returned data: test")
        idx = pd.date_range(start.floor("h"), end, freq="1h")
        r = SourceResult("fake")
        for i, st in enumerate(s for s in stations if s["id"] in ids):
            td = np.arange(idx.size) / 24.0
            r.series[st["id"]] = (tides.predict(TRUE, idx) + 5 * np.sin(2 * np.pi * td / 20 + i))
            r.air_pressure_hpa[st["id"]] = pd.Series(1013.0, idx)
            r.meta[st["id"]] = {"provider": "fake"}
        return r
    return fn


def test_build_sealevel_writes_valid_products_and_falls_back(tmp_path, monkeypatch):
    cfg = build.load_config()
    noaa = [g["id"] for g in cfg["tide_gauges"] if g["provider"] == "noaa_coops"]
    chs = [g["id"] for g in cfg["tide_gauges"] if g["provider"] == "chs_iwls"]
    monkeypatch.setattr(build, "SEALEVEL_SOURCES", [
        ("noaa_coops", _fake_source(noaa), "noaa_coops"),
        ("chs_iwls", _fake_source(chs), "chs_iwls"),
    ])
    now = pd.Timestamp("2026-10-01T00:00:00Z")
    start = now - pd.Timedelta(days=60)
    first = tmp_path / "run1"
    first.mkdir()
    st = build.build_sealevel(cfg, first, start, now, RawCache(None), {}, None)
    assert {s["status"] for s in st} == {"ok"}
    assert validate_dir(first) == []
    sl = json.loads((first / "sealevel.json").read_text())
    assert set(noaa + chs) <= set(sl["stations"])
    assert "window fit" in sl["meta"]["neah_bay"]["tide_source"]
    assert sl["meta"]["neah_bay"]["ib_source"] == "station"

    # second run: CHS fails, its stations come from the first run's products, marked stale
    monkeypatch.setattr(build, "SEALEVEL_SOURCES", [
        ("noaa_coops", _fake_source(noaa), "noaa_coops"),
        ("chs_iwls", _fake_source(chs, fail=True), "chs_iwls"),
    ])
    second = tmp_path / "run2"
    second.mkdir()
    st = build.build_sealevel(cfg, second, start, now, RawCache(None), {}, first)
    assert {s["id"]: s["status"] for s in st} == {"noaa_coops": "ok", "chs_iwls": "stale"}
    sl2 = json.loads((second / "sealevel.json").read_text())
    assert sl2["meta"]["tofino"]["stale"] is True
    assert sl2["values"]["tofino"] == sl["values"]["tofino"]
    assert validate_dir(second) == []
