"""Processing steps. Thin wrappers over vendor/ctw_analysis.py so the rules in CLAUDE.md
are enforced in one place."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..vendor import ctw_analysis as ca
from . import drift, tides

RHO_G = 1025.0 * 9.81          # Pa per m of water
PA_PER_CM = RHO_G / 100.0      # ~100.6 Pa per cm
NEAREST_BAROMETER_KM = 250.0   # subtidal air pressure is coherent over this distance


def despike(s: pd.Series, tide: pd.Series | None = None, nmad: float = 6.0,
            iters: int = 3) -> tuple[pd.Series, int]:
    """Drop points whose high-passed tidal residual exceeds nmad x MAD (iterated).

    With a frozen-constant prediction `tide`, the residual is s - tide. Without one, use the
    vendor's window harmonic fit (`despike_detide`). Returns (cleaned series, n removed)."""
    if tide is None:
        clean, _, _, nrem = ca.despike_detide(s, nmad=nmad, iters=iters)
        return clean, nrem
    s = s.copy()
    nrem = 0
    for _ in range(iters):
        r = s - tide
        hp = r - r.rolling(25, center=True, min_periods=6).median()
        mad = np.nanmedian(np.abs(hp - np.nanmedian(hp))) * 1.4826
        bad = (np.abs(hp) > nmad * mad).to_numpy()
        if not bad.any():
            break
        nrem += int(bad.sum())
        s[bad] = np.nan
    return s, nrem


def detide_frozen(s: pd.Series, constants: dict) -> pd.Series:
    """Subtract a tidal prediction from frozen constants (rule 5)."""
    return s - tides.predict(constants, s.index)


def ib_correct_gauge(sea_level_cm: pd.Series, p_hpa: pd.Series) -> pd.Series:
    """Rule 2: gauges only. Never call for bottom pressure."""
    return ca.ib_correct(sea_level_cm, p_hpa)


def fill_pressure(primary: pd.Series, fallbacks: list[pd.Series]) -> pd.Series:
    """Fill gaps in a barometer record from other barometers, each shifted by its median
    offset from the primary over their overlap (station elevations differ)."""
    p = primary.copy()
    for fb in fallbacks:
        fb = fb.reindex(p.index)
        both = p.notna() & fb.notna()
        offset = float((p[both] - fb[both]).median()) if both.any() else 0.0
        p = p.combine_first(fb + offset)
    return p


def pressure_for(station: dict, pressures: dict[str, pd.Series], coords: dict[str, tuple],
                 index: pd.DatetimeIndex) -> tuple[pd.Series | None, str]:
    """Air pressure (hPa) for one gauge and a label for meta.ib_source.

    Order (rule 2): the gauge's own barometer, else the nearest barometer within
    NEAREST_BAROMETER_KM. Gaps in the chosen record are filled from the next nearest ones.
    Gauges marked pressure: era5 get none until the weekly ERA5 job exists."""
    sid = station["id"]
    if station.get("pressure") == "era5":
        return None, "none"
    lat, lon = coords[sid]
    others = sorted(
        ((float(ca.haversine_km(lat, lon, *coords[k])), k) for k in pressures if k != sid),
        key=lambda x: x[0])
    others = [(d, k) for d, k in others if d <= NEAREST_BAROMETER_KM]
    if sid in pressures:
        chosen, label = pressures[sid], "station"
    elif others:
        d, k = others.pop(0)
        chosen, label = pressures[k], f"nearest:{k} ({d:.0f} km)"
    else:
        return None, "none"
    p = chosen.reindex(index).interpolate(limit=6, limit_area="inside")
    return fill_pressure(p, [pressures[k] for _, k in others]), label


def godin(s: pd.Series, maxgap_h: int = 12) -> pd.Series:
    return ca.godin_lowpass(s, maxgap_h=maxgap_h)


def basin_reference(pressure_pa: dict[str, pd.Series], ref_ids: list[str]) -> pd.Series:
    """Rule 4: mean of available basin gauges (after detiding and de-meaning each)."""
    refs = [pressure_pa[i] - pressure_pa[i].mean() for i in ref_ids if i in pressure_pa]
    if not refs:
        raise ValueError("no basin reference series available")
    return pd.concat(refs, axis=1).mean(axis=1, skipna=True)


def anomaly_doy(s: pd.Series, baseline: dict | None) -> pd.Series:
    """Minus day-of-year baseline (M4). Without a baseline: minus the window mean, and
    say so in the product's `processing` line."""
    if baseline is None:
        return s - s.mean()
    raise NotImplementedError


def detide(s_cm: pd.Series, constants: dict | None) -> tuple[pd.Series, dict]:
    """Despike and detide an hourly series in cm (frozen constants, else a window fit)."""
    tide = tides.predict(constants, s_cm.index) if constants else None
    clean, nrem = despike(s_cm, tide)
    if tide is not None:
        src = f"frozen constants ({constants['start'][:10]} to {constants['end'][:10]})"
        return clean - tide, {"despiked": nrem, "tide_source": src}
    resid = clean - ca.harmonic_fit(clean)[0]
    return resid, {"despiked": nrem, "tide_source": "window fit (no frozen constants)"}


def gauge_chain(sea_level_cm: pd.Series, p_hpa: pd.Series | None,
                constants: dict | None) -> tuple[pd.Series, dict]:
    """Hourly sea level (cm, regular hourly index) -> hourly low-passed anomaly (cm) and meta.

    despike -> detide (frozen constants, else a window fit) -> IB (if pressure) -> Godin ->
    minus window mean."""
    resid, meta = detide(sea_level_cm, constants)
    if p_hpa is not None and p_hpa.notna().any():
        resid = ib_correct_gauge(resid, p_hpa)
    lp = godin(resid)
    return anomaly_doy(lp, None), meta


def remove_linear_drift(s: pd.Series) -> pd.Series:
    """Least-squares straight line removed over the window (open decision, see METHODS)."""
    ok = s.notna().to_numpy()
    if ok.sum() < 2:
        return s
    x = (s.index - s.index[0]).total_seconds().to_numpy() / 86400.0
    a, b = np.polyfit(x[ok], s.to_numpy()[ok], 1)
    return s - (a * x + b)


def model_mismatch(model: dict | None, device: str | None, devices: dict[str, str],
                   refs: list[str]) -> str | None:
    """Why a frozen drift model does not apply now, or None if it does (review item 5)."""
    if not model:
        return "no frozen drift model"
    if model.get("deviceCode") != device:
        return f"model is for {model.get('deviceCode')}, now {device}"
    basin = model.get("basin_devices")
    if basin is None:
        return None                    # older model: section device checked only
    if sorted(basin) != sorted(refs):
        return f"basin gauges changed ({', '.join(sorted(basin))} -> {', '.join(sorted(refs))})"
    for r, d in basin.items():
        if devices.get(r) != d["deviceCode"]:
            return f"basin gauge {r} is now {devices.get(r)}, model used {d['deviceCode']}"
    return None


def bottom_pressure_chain(pressure_pa: dict[str, pd.Series], constants: dict,
                          section_ids: list[str], ref_ids: list[str],
                          drift_models: dict[str, dict] | None = None,
                          devices: dict[str, str] | None = None,
                          ) -> tuple[dict[str, pd.Series], dict[str, dict]]:
    """Hourly seafloor pressure (Pa, common hourly index) -> hourly low-passed, basin-referenced
    anomaly in cm of water for each section gauge.

    Pa -> cm of water (rho g) -> despike + detide -> minus the basin reference (rule 4: mean of
    the de-meaned basin gauges, before filtering) -> drift removed -> Godin -> minus window
    mean. Never IB-corrected (rule 2): a BPR already sees only the departure from the
    inverse-barometer response.

    Drift: the frozen per-deployment model (process/drift.py) when it still applies: same
    section device, and (when the model records them) the same basin devices and basin
    gauges, since the model was fitted to section minus basin and so holds the basin drift
    too. Otherwise a straight line over the window, and meta says which."""
    drift_models, devices = drift_models or {}, devices or {}
    detided, meta = {}, {}
    for k, s in pressure_pa.items():
        detided[k], meta[k] = detide(s / PA_PER_CM, constants.get(k))
    refs = [k for k in ref_ids if k in detided and detided[k].notna().any()]
    ref = basin_reference(detided, refs)          # raises if no basin gauge has data
    out = {}
    for k in section_ids:
        if k not in detided or detided[k].isna().all():
            continue
        x = detided[k] - detided[k].mean() - ref
        model = drift_models.get(k)
        why_not = model_mismatch(model, devices.get(k), devices, refs)
        if why_not is None:
            x = x - drift.evaluate(model, x.index)
            how = (f"frozen exp + linear fit ({model['fit_from']} to {model['fit_to']}, "
                   f"{model['slope_cm_per_yr']} cm/yr)")
            if "basin_devices" not in model:
                how += "; basin devices not recorded in this model"
        else:
            x = remove_linear_drift(x)
            how = f"linear over window ({why_not})"
        out[k] = anomaly_doy(godin(x), None)
        meta[k] |= {"basin_reference": refs, "drift": how}
    return out, meta
