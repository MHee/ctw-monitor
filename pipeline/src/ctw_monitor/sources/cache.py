"""Raw-data cache: hourly series per source and station as gzipped CSV under .cache/raw.

Nightly runs fetch only from the end of the cached series (minus an overlap, so late
arrivals and preliminary-to-verified updates of the last days are picked up). In Actions
the directory is kept with actions/cache; it is never committed (rule 6).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

OVERLAP = pd.Timedelta(days=3)


def empty_series() -> pd.Series:
    return pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC").as_unit("ns"))


class RawCache:
    def __init__(self, root: Path | str | None, full: bool = False):
        self.root = Path(root) if root else None
        self.full = full

    def _path(self, kind: str, sid: str) -> Path:
        return self.root / kind / f"{sid}.csv.gz"

    def load(self, kind: str, sid: str) -> pd.Series:
        if self.root is None or self.full:
            return empty_series()
        p = self._path(kind, sid)
        if not p.exists():
            return empty_series()
        d = pd.read_csv(p, index_col=0)
        s = d.iloc[:, 0].astype(float)
        s.index = pd.DatetimeIndex(pd.to_datetime(s.index, utc=True)).as_unit("ns")
        return s.dropna()

    def save(self, kind: str, sid: str, s: pd.Series) -> None:
        if self.root is None:
            return
        p = self._path(kind, sid)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.parent / (p.name + ".tmp")
        s.dropna().rename("value").to_csv(tmp, index_label="time", float_format="%.4f",
                                          compression="gzip")
        tmp.replace(p)

    def get(self, kind: str, sid: str, start, end, fetch) -> pd.Series:
        """Hourly series for [start, end]: cached values plus fresh fetches for what is missing.

        fetch(a, b) must return an hourly Series with a tz-aware UTC index.
        """
        start, end = pd.Timestamp(start), pd.Timestamp(end)
        old = self.load(kind, sid)
        parts = []
        if old.empty:
            parts.append(fetch(start, end))
        else:
            if old.index[0] > start + pd.Timedelta(days=1):
                parts.append(fetch(start, old.index[0]))
            parts.append(fetch(max(start, old.index[-1] - OVERLAP), end))
        new = pd.concat([p for p in parts if not p.empty]) if any(not p.empty for p in parts) \
            else pd.Series(dtype=float)
        if not new.empty:
            new.index = new.index.as_unit("ns")
            new = new[~new.index.duplicated(keep="last")]
        s = new.combine_first(old) if not old.empty else new      # fresh values win
        s = s.sort_index()
        if not s.empty:
            self.save(kind, sid, s[s.index >= start - pd.Timedelta(days=31)])
        return s[(s.index >= start) & (s.index <= end)]
