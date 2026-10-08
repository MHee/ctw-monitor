"""Download the currently deployed products so failed sources can fall back to them."""
from __future__ import annotations

from pathlib import Path

import requests

FILES = ["manifest.json", "stations.json", "sealevel.json", "hovmoller.json",
         "bottom_pressure.json", "temperature.json", "events.json", "context.json"]


def pull_last_good(site_url: str, out_dir: Path | str, timeout: int = 30) -> list[str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    got = []
    for f in FILES:
        try:
            r = requests.get(f"{site_url.rstrip('/')}/data/{f}", timeout=timeout)
            if r.ok and r.headers.get("content-type", "").startswith("application/json"):
                (out / f).write_bytes(r.content)
                got.append(f)
        except requests.RequestException:
            pass
    return got
