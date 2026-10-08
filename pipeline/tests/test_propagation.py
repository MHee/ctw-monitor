"""process/propagation.py on synthetic series (CLAUDE.md: process/ gets unit tests)."""
import numpy as np
import pandas as pd

from ctw_monitor.process.propagation import (
    EventRules,
    chain_extrema,
    classify,
    detect_events,
    find_extrema,
    segments,
)

IDX = pd.date_range("2026-01-01", periods=120 * 24, freq="1h", tz="UTC")
TD = (IDX - IDX[0]) / pd.Timedelta(days=1)
DIST = {f"g{i}": -2000.0 + 300.0 * i for i in range(10)}          # 2700 km of coast


def gauss(centre_days, width_days=3.0):
    return np.exp(-0.5 * ((TD - centre_days) / width_days) ** 2)


def coast(speed_m_s=3.0, amp=-20.0, centre=60.0, noise=0.3, seed=0, dist=DIST):
    rng = np.random.default_rng(seed)
    km_per_day = speed_m_s * 86.4 if speed_m_s else np.inf
    x0 = min(dist.values())
    return {k: pd.Series(amp * gauss(centre + (x - x0) / km_per_day)
                         + rng.normal(0, noise, IDX.size), index=IDX) for k, x in dist.items()}


def test_poleward_pulse_gives_its_speed():
    ev = detect_events(coast(3.0), DIST)
    mins = [e for e in ev if e["type"] == "minimum"]
    assert len(mins) == 1
    e = mins[0]
    assert e["n_stations"] == 10 and e["verdict"] == "propagating" and e["major"]
    assert e["speed_ci95"][0] <= 3.0 <= e["speed_ci95"][1]
    assert abs(e["speed_m_s"] - 3.0) < 0.1
    assert e["first"].startswith("2026-03-02")                       # day 60 at g0


def test_whole_coast_at_once_is_not_propagating():
    """Weather forcing moves every gauge together (rule 3): no speed may be claimed."""
    rng = np.random.default_rng(3)
    jitter = {k: rng.normal(0, 0.3) for k in DIST}                # hours-scale timing noise
    s = {k: pd.Series(-20 * gauss(60 + jitter[k]) + rng.normal(0, 0.3, IDX.size), index=IDX)
         for k in DIST}
    ev = [e for e in detect_events(s, DIST) if e["type"] == "minimum"]
    assert len(ev) == 1 and ev[0]["propagating"] is False


def test_southward_pulse_is_labelled_southward():
    s = coast(3.0)
    s = {k: s[f"g{9 - int(k[1:])}"] for k in s}                      # mirror the coast
    ev = [e for e in detect_events(s, DIST) if e["type"] == "minimum"]
    assert ev[0]["verdict"] == "southward" and ev[0]["speed_m_s"] < 0


def test_small_events_and_short_chains_are_dropped():
    assert not [e for e in detect_events(coast(3.0, amp=-4.0, noise=0.05), DIST) if e["type"] == "minimum"]
    few = {k: v for k, v in DIST.items() if k in ("g0", "g1", "g2", "g3", "g4")}
    assert detect_events(coast(3.0, dist=few), few) == []             # 5 gauges < 6


def test_chain_breaks_at_a_long_gap():
    dist = {**{f"s{i}": -6000.0 + 200 * i for i in range(7)},
            **{f"n{i}": -2000.0 + 300 * i for i in range(7)}}
    assert [len(g) for g in segments(dist, 1000.0)] == [7, 7]
    s = coast(2.0, dist=dist)
    chains = [c for c in chain_extrema(s, dist, "minimum") if len(c) > 1]
    assert all({e.station[0] for e in c} in ({"s"}, {"n"}) for c in chains)


def test_each_extremum_joins_one_chain():
    chains = chain_extrema(coast(3.0), DIST, "minimum")
    seen = [(e.station, e.time) for c in chains for e in c]
    assert len(seen) == len(set(seen))


def test_gauge_without_data_is_skipped_not_fatal():
    s = coast(3.0)
    s["g4"] = pd.Series(np.nan, index=IDX)
    ev = [e for e in detect_events(s, DIST) if e["type"] == "minimum"]
    assert ev[0]["n_stations"] == 9 and ev[0]["propagating"]


def test_extrema_at_run_edges_are_dropped():
    s = pd.Series(-20 * gauss(60), index=IDX)
    s[(TD > 59.5) & (TD < 61)] = np.nan                             # 36 h gap: bridged
    assert len(find_extrema(s, "minimum")) == 1
    s[(TD > 58) & (TD < 61)] = np.nan                               # 72 h: not bridged
    assert find_extrema(s, "minimum") == []


def test_classify_needs_a_positive_lower_bound():
    r = EventRules()
    assert classify({"speed_m_s": 3.0, "speed_ci95": [-0.5, 6.5], "r2": 0.9}, r) == "not propagating"
    assert classify({"speed_m_s": 12.0, "speed_ci95": [11, 13], "r2": 0.9}, r) == "not propagating"
    assert classify({"speed_m_s": 3.0, "speed_ci95": [2.0, 4.0], "r2": 0.9}, r) == "propagating"


def test_synthetic_mode_finds_its_3_m_s_pulses(tmp_path):
    import json

    from ctw_monitor.synthetic import SPEED_M_S, make_synthetic
    make_synthetic(tmp_path)
    ev = json.loads((tmp_path / "events.json").read_text())["events"]
    prop = [e for e in ev if e["propagating"] and e["segment"].startswith("san_diego")]
    assert prop, ev
    assert all(e["speed_ci95"][0] <= SPEED_M_S <= e["speed_ci95"][1] for e in prop if e["major"])


def test_parse_oni():
    from ctw_monitor.sources.context import parse_oni
    rows = parse_oni(" SEAS  YR   TOTAL   ANOM\n JJA 2026  29.09   1.80\n JAS 2026  29.12   2.16\n")
    assert rows[-1] == {"season": "JAS", "year": 2026, "total_c": 29.12, "anomaly_c": 2.16}
    assert len(rows) == 2


def test_speed_is_unbiased_under_timing_noise():
    """Time is regressed on distance: day-scale timing scatter must not bias the speed low."""
    from ctw_monitor.process.propagation import Extremum, fit_chain
    rng = np.random.default_rng(5)
    dist = {f"g{i}": 150.0 * i for i in range(17)}
    t0 = pd.Timestamp("2026-05-17", tz="UTC")
    speeds = []
    for _ in range(400):
        chain = [Extremum(k, t0 + pd.Timedelta(days=x / (3.0 * 86.4) + rng.normal(0, 1.0)), -10, 10)
                 for k, x in dist.items()]
        speeds.append(fit_chain(chain, dist)["speed_m_s"])
    assert abs(np.median(speeds) - 3.0) < 0.15


def test_no_finite_bound_when_timing_is_flat():
    from ctw_monitor.process.propagation import Extremum, fit_chain
    t0 = pd.Timestamp("2026-01-01", tz="UTC")
    hours = [0, 7, -5, 3, -8, 6]
    chain = [Extremum(f"g{i}", t0 + pd.Timedelta(hours=h), -10, 10) for i, h in enumerate(hours)]
    f = fit_chain(chain, {f"g{i}": 300.0 * i for i in range(6)})
    assert f["speed_ci95"] is None and classify(f) in ("not propagating", "southward")
