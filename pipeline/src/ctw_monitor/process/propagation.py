"""Extrema detection and along-coast speed (M3; docs/METHODS.md "Events and speed").

Rule 3: speed comes from the timing of extrema, fitted against along-coast distance
(vendor propagation_fit), never from whole-window lag correlation. Defaults were accepted
by Martin on 2026-10-08 from a test on 399 days of live data.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import pairwise

import numpy as np
import pandas as pd
from scipy import stats
from scipy.signal import find_peaks

from ..vendor import ctw_analysis as ca


@dataclass(frozen=True)
class EventRules:
    prominence_cm: float = 3.0              # per gauge
    separation_days: float = 5.0            # between extrema of one type at one gauge
    link_days: float = 5.0                  # max timing difference between linked gauges
    max_gap_km: float = 1000.0              # a chain never links across a longer gap
    bridge_gap_h: float = 48.0              # interior gaps bridged before peak finding
    min_gauges: int = 6
    min_span_km: float = 1000.0
    min_median_prominence_cm: float = 5.0
    speed_range_m_s: tuple[float, float] = (1.0, 10.0)
    min_r2: float = 0.7
    major_prominence_cm: float = 15.0


DEFAULT_RULES = EventRules()


@dataclass(frozen=True)
class Extremum:
    station: str
    time: pd.Timestamp
    value_cm: float
    prominence_cm: float


def find_extrema(s: pd.Series, kind: str, rules: EventRules = DEFAULT_RULES,
                 station: str = "") -> list[Extremum]:
    """Minima or maxima of a regular series (cm) with the rules' prominence and separation.
    Peaks at the edge of a data run are dropped: their timing and prominence are unknown."""
    s = s.astype(float)
    if s.dropna().size < 3:
        return []
    dt_h = (s.index[1] - s.index[0]) / pd.Timedelta(hours=1)
    x = s.interpolate(limit=max(1, int(rules.bridge_gap_h / dt_h)), limit_area="inside")
    y = (-x if kind == "minimum" else x).to_numpy()
    ok = np.isfinite(y)
    distance = max(1, round(rules.separation_days * 24 / dt_h))
    out = []
    edges = np.flatnonzero(np.diff(ok.astype(int))) + 1
    for run in np.split(np.arange(y.size), edges):
        if not ok[run[0]] or run.size < 3:
            continue
        pk, props = find_peaks(y[run], prominence=rules.prominence_cm, distance=distance)
        for i, p in zip(pk, props["prominences"]):
            if 0 < i < run.size - 1:
                j = run[i]
                out.append(Extremum(station, s.index[j], float(x.iloc[j]), float(p)))
    return out


def _has_data(s: pd.Series, t: pd.Timestamp, half_window: pd.Timedelta) -> bool:
    w = s.loc[t - half_window: t + half_window]
    return w.size > 0 and w.notna().mean() >= 0.5


def chain_extrema(series: dict[str, pd.Series], dist_km: dict[str, float], kind: str,
                  rules: EventRules = DEFAULT_RULES) -> list[list[Extremum]]:
    """Link extrema of one type from gauge to gauge along the coast.

    Gauges are visited in order of along-coast distance. At each gauge, open chains and the
    gauge's extrema are matched greedily by smallest timing difference (within link_days),
    so each extremum joins at most one chain. A chain that finds no partner stays open if
    the gauge has no data around its time, and is closed otherwise. A chain never links
    across more than max_gap_km.
    """
    link = pd.Timedelta(days=rules.link_days)
    order = sorted((k for k in series if k in dist_km), key=dist_km.get)
    closed, open_ = [], []
    for st in order:
        ex = find_extrema(series[st], kind, rules, st)
        reach = [c for c in open_ if dist_km[st] - dist_km[c[-1].station] <= rules.max_gap_km]
        closed += [c for c in open_ if dist_km[st] - dist_km[c[-1].station] > rules.max_gap_km]
        pairs = sorted((abs(e.time - c[-1].time), ci, ei)
                       for ci, c in enumerate(reach) for ei, e in enumerate(ex)
                       if abs(e.time - c[-1].time) <= link)
        used_c, used_e, nxt = set(), set(), []
        for _, ci, ei in pairs:
            if ci in used_c or ei in used_e:
                continue
            used_c.add(ci)
            used_e.add(ei)
            nxt.append(reach[ci] + [ex[ei]])
        for ci, c in enumerate(reach):
            if ci in used_c:
                continue
            (closed if _has_data(series[st], c[-1].time, link) else nxt).append(c)
        nxt += [[e] for ei, e in enumerate(ex) if ei not in used_e]
        open_ = nxt
    return closed + open_


def segments(dist_km: dict[str, float], max_gap_km: float) -> list[list[str]]:
    """Stretches of the gauge chain separated by gaps longer than max_gap_km."""
    order = sorted(dist_km, key=dist_km.get)
    out = [[order[0]]] if order else []
    for a, b in pairwise(order):
        if dist_km[b] - dist_km[a] > max_gap_km:
            out.append([])
        out[-1].append(b)
    return out


def fit_chain(chain: list[Extremum], dist_km: dict[str, float]) -> dict:
    """Peak-timing propagation fit with a 95 % t interval on the speed."""
    times = pd.DatetimeIndex([e.time for e in chain])
    xs = np.array([dist_km[e.station] for e in chain], float)
    n = len(chain)
    if n < 3 or times.max() == times.min():
        return {"speed_m_s": None, "speed_ci95": None, "r2": 0.0}
    f = ca.propagation_fit(times, xs)
    tq = float(stats.t.ppf(0.975, n - 2))
    lo, hi = f["speed_ms"] - tq * f["se_ms"], f["speed_ms"] + tq * f["se_ms"]
    return {"speed_m_s": float(f["speed_ms"]), "speed_ci95": [float(lo), float(hi)],
            "r2": float(f["r"] ** 2)}


def classify(fit: dict, rules: EventRules = DEFAULT_RULES) -> str:
    """'propagating', 'southward' or 'not propagating' (METHODS.md, items 6 and 9)."""
    c = fit["speed_m_s"]
    if c is None:
        return "not propagating"
    lo, hi = rules.speed_range_m_s
    if lo <= c <= hi and fit["r2"] >= rules.min_r2 and fit["speed_ci95"][0] > 0:
        return "propagating"
    return "southward" if c < 0 else "not propagating"


def detect_events(series: dict[str, pd.Series], dist_km: dict[str, float],
                  rules: EventRules = DEFAULT_RULES) -> list[dict]:
    """Events in the events.json contract, newest first.

    series: regular (ideally hourly) low-passed anomaly per gauge, cm, tz-aware UTC index.
    dist_km: along-coast distance per gauge (0 at Neah Bay, poleward positive).
    """
    series = {k: v for k, v in series.items() if k in dist_km and v.notna().any()}
    seg_of = {k: seg for seg in segments(dist_km, rules.max_gap_km) for k in seg}
    events = []
    for kind in ("minimum", "maximum"):
        for chain in chain_extrema(series, dist_km, kind, rules):
            xs = [dist_km[e.station] for e in chain]
            prom = float(np.median([e.prominence_cm for e in chain]))
            if (len(chain) < rules.min_gauges or max(xs) - min(xs) < rules.min_span_km
                    or prom < rules.min_median_prominence_cm):
                continue
            fit = fit_chain(chain, dist_km)
            verdict = classify(fit, rules)
            first = min(chain, key=lambda e: e.time)
            seg = seg_of[chain[0].station]
            ev = {
                "id": f"{kind[:3]}-{first.time:%Y%m%dT%H}-{first.station}",
                "type": kind,
                "first": first.time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "segment": f"{seg[0]}..{seg[-1]}",
                "n_stations": len(chain),
                "span_km": round(max(xs) - min(xs), 1),
                "prominence_cm": round(prom, 1),
                "major": prom >= rules.major_prominence_cm,
                "speed_m_s": None if fit["speed_m_s"] is None else round(fit["speed_m_s"], 2),
                "r2": round(fit["r2"], 3),
                "propagating": verdict == "propagating",
                "verdict": verdict,
                "label": f"{kind}, {chain[0].station} to {chain[-1].station}",
                "extrema": [{"station": e.station, "time": e.time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                             "value_cm": round(e.value_cm, 1),
                             "prominence_cm": round(e.prominence_cm, 1)} for e in chain],
            }
            if fit["speed_ci95"] is not None:
                ev["speed_ci95"] = [round(v, 2) for v in fit["speed_ci95"]]
            events.append(ev)
    return sorted(events, key=lambda e: e["first"], reverse=True)


def rules_dict(rules: EventRules = DEFAULT_RULES) -> dict:
    d = asdict(rules)
    d["speed_range_m_s"] = list(d["speed_range_m_s"])
    return d
