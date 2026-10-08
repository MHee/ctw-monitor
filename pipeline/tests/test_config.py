from itertools import pairwise

from ctw_monitor.config import alongshore_km, enabled, load_config


def test_neah_bay_is_zero_and_order_is_poleward():
    cfg = load_config()
    g = enabled(cfg["tide_gauges"])
    d = alongshore_km(g, cfg)
    assert abs(d["neah_bay"]) < 5
    xs = [d[s["id"]] for s in g]
    assert all(b >= a - 25 for a, b in pairwise(xs)), "config order should run poleward"
    # 2026 report: San Diego about -1953 km from Neah Bay along the coast
    assert -2150 < d["san_diego"] < -1800, d["san_diego"]
