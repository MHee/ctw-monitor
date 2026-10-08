"""events.json (docs/DATA_CONTRACT.md): detected extrema and along-coast speed fits."""
from __future__ import annotations

import pandas as pd

from .. import SCHEMA_VERSION
from ..process.propagation import DEFAULT_RULES, EventRules, detect_events, rules_dict


def events_product(series: dict[str, pd.Series], dist: dict[str, float],
                   rules: EventRules = DEFAULT_RULES) -> dict:
    """From the low-passed anomalies, hourly in the nightly build (rule 3: extrema timing)."""
    lo, hi = rules.speed_range_m_s
    proc = (f"Minima and maxima of the sea-level anomaly (cm), linked gauge to gauge within "
            f"±{rules.link_days:g} d; speed fitted to their timing against along-coast distance "
            f"(95 % CI); propagating if {lo:g}–{hi:g} m/s, r² ≥ {rules.min_r2:g} and the CI is "
            f"above 0")
    return {"schema_version": SCHEMA_VERSION, "processing": proc, "rules": rules_dict(rules),
            "events": detect_events(series, dist, rules)}
