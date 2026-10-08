from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class SourceResult:
    """Hourly series from one source, keyed by station id (tz-aware UTC index)."""
    source_id: str
    series: dict[str, pd.Series] = field(default_factory=dict)
    air_pressure_hpa: dict[str, pd.Series] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)   # station id -> message

    @property
    def last_observation(self):
        ends = [s.last_valid_index() for s in self.series.values() if s.notna().any()]
        return max(ends) if ends else None
