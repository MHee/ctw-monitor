"""sources/onc.py and the bottom-pressure chain, with the ONC API mocked (no network, no token)."""
import json

import numpy as np
import pandas as pd
import pytest
import requests

from ctw_monitor import build
from ctw_monitor.process import steps, tides
from ctw_monitor.products.validate import validate_dir
from ctw_monitor.sources import onc
from ctw_monitor.sources.base import SourceResult
from ctw_monitor.sources.cache import RawCache

FAKE = "abc123-not-a-real-token"


class Resp:
    def __init__(self, status, payload):
        self.status_code, self._p = status, payload
        self.text = json.dumps(payload)

    def json(self):
        return self._p


@pytest.fixture(autouse=True)
def no_keyring(monkeypatch):
    """Tests never read the developer's real credential store."""
    monkeypatch.setattr(onc, "_keyring_token", lambda: None)


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setenv("ONC_API_TOKEN", FAKE)


def test_token_from_keyring_when_env_missing(monkeypatch):
    monkeypatch.delenv("ONC_API_TOKEN", raising=False)
    monkeypatch.setattr(onc, "_keyring_token", lambda: FAKE)
    assert onc.onc_token() == FAKE


def test_scrub_removes_token(token):
    msg = f"HTTPSConnectionPool: Max retries exceeded with url: /api/x?token={FAKE}&a=1 ({FAKE})"
    out = onc.scrub(msg)
    assert FAKE not in out and "token=***" in out


def test_api_get_no_data_and_errors_are_scrubbed(token, monkeypatch):
    calls = iter([
        Resp(400, {"errors": [{"errorCode": 127, "errorMessage": "Invalid parameter value"}]}),
        Resp(401, {"errors": [{"errorCode": 128, "errorMessage": f"bad token {FAKE}"}]}),
    ])
    monkeypatch.setattr(onc.requests, "get", lambda *a, **k: next(calls))
    with pytest.raises(onc.NoData):
        onc.api_get("scalardata/device")
    with pytest.raises(RuntimeError) as e:
        onc.api_get("scalardata/device")
    assert FAKE not in str(e.value)


def test_api_get_connection_error_hides_url(token, monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError(f"Max retries exceeded with url: /api/x?token={FAKE}")
    monkeypatch.setattr(onc.requests, "get", boom)
    monkeypatch.setattr(onc.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError) as e:
        onc.api_get("x", retries=1)
    assert FAKE not in str(e.value) and "token" not in str(e.value)


def test_no_token_fails_softly(monkeypatch):
    monkeypatch.delenv("ONC_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        onc.fetch_bottom_pressure([{"id": "x", "location_code": "X"}], "2026-01-01", "2026-01-02")


def _sensor(name, times, values, flags=None):
    flags = flags or [7] * len(values)
    return {"sensorName": name, "sensorCategoryCode": "pressure",
            "data": [{"sampleTime": t, "value": v, "qaqcFlag": f}
                     for t, v, f in zip(times, values, flags, strict=True)]}


def test_device_series_picks_by_name_flags_and_pages(token, monkeypatch):
    t1 = ["2026-01-01T00:00:00.000Z", "2026-01-01T00:15:00.000Z"]
    t2 = ["2026-01-01T00:30:00.000Z", "2026-01-01T00:45:00.000Z"]
    pages = [
        {"sensorData": [_sensor("AZA Raw Pressure", t1, [1.0, 1.0]),
                        _sensor("Seafloor Pressure", t1, [400.0, 400.1], [7, 4])],
         "next": {"parameters": {"deviceCode": "D", "token": FAKE, "dateFrom": t2[0]}}},
        {"sensorData": [_sensor("Seafloor Pressure", t2, [400.2, 400.3])], "next": None},
    ]
    seen = []

    def fake(path, **params):
        seen.append(params)
        return pages[len(seen) - 1]
    monkeypatch.setattr(onc, "api_get", fake)
    s, name = onc.device_series("D", "2026-01-01", "2026-01-02", onc.PRESSURE_NAMES,
                                onc.PRESSURE_EXCLUDE)
    assert name == "Seafloor Pressure"
    assert list(s.to_numpy()) == [400.0, 400.2, 400.3]      # flag 4 dropped, raw channel ignored
    assert "token" not in seen[1]                            # api_get adds it, never the caller


def test_bottom_pressure_chain_removes_basin_signal():
    rng = np.random.default_rng(3)
    idx = pd.date_range("2026-01-01", periods=24 * 120, freq="1h", tz="UTC")
    td = np.arange(idx.size) / 24.0
    rec = {"constituents": {"M2": {"amp_cm": 80.0, "phase_deg": 10.0},
                            "K1": {"amp_cm": 40.0, "phase_deg": 100.0}},
           "start": "2025-01-01T00:00:00Z", "end": "2026-01-01T00:00:00Z"}
    tide = tides.predict(rec, idx)
    basin = 3 * np.sin(2 * np.pi * td / 30)                        # common ocean-mass signal
    event = 10 * np.exp(-0.5 * ((td - 60) / 5) ** 2)               # shelf/slope event
    pa = {k: (tide + basin + rng.normal(0, 0.2, idx.size) + off) * steps.PA_PER_CM
          for k, off in [("cne20", 25000), ("cbc27", 26000)]}
    pa["ncbc"] = (tide + basin + event + 4000) * steps.PA_PER_CM
    out, meta = steps.bottom_pressure_chain(pa, {k: rec for k in pa}, ["ncbc"], ["cne20", "cbc27"])
    want = event - event.mean()
    ok = out["ncbc"].notna().to_numpy()
    lin = np.polyval(np.polyfit(td[ok], want[ok], 1), td[ok])     # the drift step removes a line
    assert np.sqrt(np.mean((out["ncbc"].to_numpy()[ok] - (want[ok] - lin)) ** 2)) < 0.3
    assert meta["ncbc"]["basin_reference"] == ["cne20", "cbc27"]
    with pytest.raises(ValueError):
        steps.bottom_pressure_chain({"ncbc": pa["ncbc"]}, {}, ["ncbc"], ["cne20"])


def test_build_bottom_pressure_and_temperature(tmp_path, monkeypatch):
    cfg = build.load_config()

    def fake_bpr(stations, start, end, cache=None):
        idx = pd.date_range(start.floor("h"), end, freq="1h")
        r = SourceResult("onc_bpr")
        for st in stations:
            r.series[st["id"]] = pd.Series(4.0e6 + np.sin(np.arange(idx.size) / 200), idx)
            r.meta[st["id"]] = {"provider": "fake"}
        return r

    def fake_ctd(stations, start, end, cache=None):
        idx = pd.date_range(start.floor("D"), end, freq="1D")
        r = SourceResult("onc_ctd")
        for st in stations[:3]:
            r.series[st["id"]] = pd.Series(4.0 + 0.01 * np.arange(idx.size), idx)
        return r

    monkeypatch.setattr(build.onc, "fetch_bottom_pressure", fake_bpr)
    monkeypatch.setattr(build.onc, "fetch_temperature", fake_ctd)
    now = pd.Timestamp("2026-10-01T00:00:00Z")
    start = now - pd.Timedelta(days=60)
    st1 = build.build_bottom_pressure(cfg, tmp_path, start, now, RawCache(None), {}, None)
    st2 = build.build_temperature(cfg, tmp_path, start, now, RawCache(None), None)
    assert st1["status"] == "ok" and st2["status"] == "ok"
    assert validate_dir(tmp_path) == []
    bp = json.loads((tmp_path / "bottom_pressure.json").read_text())
    assert bp["stations"] == ["fgpd", "ncbc", "nc89"]                 # section gauges only
    assert "CNE20, CBC27" in bp["processing"] and "not IB-corrected" in bp["processing"]
    assert json.loads((tmp_path / "temperature.json").read_text())["units"] == "degC"

    # ONC down: both products come from last good, marked stale
    def down(*a, **k):
        raise RuntimeError(f"ONC scalardata -> HTTP 503 token={FAKE}")
    monkeypatch.setattr(build.onc, "fetch_bottom_pressure", down)
    out2 = tmp_path / "second"
    out2.mkdir()
    st3 = build.build_bottom_pressure(cfg, out2, start, now, RawCache(None), {}, tmp_path)
    assert st3["status"] == "stale" and FAKE not in st3["message"]
    assert (out2 / "bottom_pressure.json").exists()


def test_screens_drop_absurd_values():
    idx = pd.date_range("2026-01-01", periods=6, freq="15min", tz="UTC")
    p = pd.Series([2689.5, 2689.6, -5113.2, 2689.7, 2711.0, 2689.4], idx)   # dbar
    assert list(onc.screen_pressure(p).round(1)) == [2689.5, 2689.6, 2689.7, 2689.4]
    t = pd.Series([3.1, -551.88, 3.2, 41.0, 3.0, 3.1], idx)                   # degC
    assert list(onc.screen_temperature(t)) == [3.1, 3.2, 3.0, 3.1]
