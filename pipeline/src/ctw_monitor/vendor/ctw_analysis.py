"""Vendored from the Claude Science skill `coastal-trapped-wave-analysis` (October 2026). See vendor/README.md.

Imports are inside functions, so heavy optional packages (utide for detide_utide) are only needed
by the functions that use them."""
# ruff: noqa
"""coastal-trapped-wave-analysis: detiding, low-pass, IB correction, event metrics, propagation tests,
lag correlation with effective DOF, wind stress, and a forced damped CTW model. Functions only."""


def tidal_constituents():
    """Constituent frequencies (cycles per hour) for a 1-5-month least-squares fit.
    K2/S2 and P1/K1 need ~183 days to separate by the Rayleigh criterion. In shorter records
    they are fitted anyway; any leakage lies in the tidal bands and is removed by a Godin filter.
    """
    return {"Q1": 0.0372185, "O1": 0.0387307, "P1": 0.0415526, "K1": 0.0417807, "J1": 0.0432929,
            "OO1": 0.0448308, "2N2": 0.0774871, "MU2": 0.0776955, "N2": 0.0789992, "NU2": 0.0792016,
            "M2": 0.0805114, "L2": 0.0820236, "S2": 0.0833333, "K2": 0.0835615, "M3": 0.1207671,
            "MK3": 0.1222921, "MN4": 0.1595106, "M4": 0.1610228, "MS4": 0.1638447, "S4": 0.1666667,
            "M6": 0.2415342}


def harmonic_fit(s, constituents=None):
    """Least-squares fit of mean + linear trend + tidal constituents to an hourly Series (gaps OK).
    No nodal corrections (fine for windows of a few months). Long-period tides (Mm, MSf) are
    deliberately excluded so subtidal signals are not absorbed.
    Returns (tide_prediction Series, {constituent: amplitude}).
    """
    import numpy as np, pandas as pd
    if constituents is None:
        constituents = tidal_constituents()
    t = (s.index - s.index[0]).total_seconds().values / 3600.0
    ok = np.isfinite(s.values)
    cols = [np.ones_like(t), t / 1000.0]
    for f in constituents.values():
        cols += [np.cos(2 * np.pi * f * t), np.sin(2 * np.pi * f * t)]
    A = np.column_stack(cols)
    coef = np.linalg.lstsq(A[ok], s.values[ok], rcond=None)[0]
    tide = pd.Series(A[:, 2:] @ coef[2:], s.index)
    amp = {k: float(np.hypot(coef[2 + 2 * i], coef[3 + 2 * i])) for i, k in enumerate(constituents)}
    return tide, amp


def despike_detide(s, nmad=6.0, iters=3):
    """Iterative QC and detiding. Fit tides, high-pass the residual against a 25-h running
    median, and drop points beyond nmad x MAD. Repeat until no points are removed.
    Returns (cleaned Series, detided residual, constituent amplitudes, number removed).
    Check the M2 amplitude against neighbours: a mismatch flags a bad channel (Champerico, 2026).
    """
    import numpy as np
    s = s.copy()
    nrem = 0
    for _ in range(iters):
        tide, amp = harmonic_fit(s)
        r = s - tide
        hp = r - r.rolling(25, center=True, min_periods=6).median()
        mad = np.nanmedian(np.abs(hp - np.nanmedian(hp))) * 1.4826
        bad = np.abs(hp) > nmad * mad
        nrem += int(bad.sum())
        s[bad] = np.nan
        if not bad.any():
            break
    tide, amp = harmonic_fit(s)
    return s, s - tide, amp, nrem


def godin_lowpass(s, maxgap_h=12):
    """Godin 24-24-25 h running-mean low-pass of an hourly Series. Interior gaps up to maxgap_h
    are linearly interpolated first. Longer gaps stay NaN, because full windows are required.
    """
    x = s.interpolate(limit=maxgap_h, limit_area="inside")
    for w in (24, 24, 25):
        x = x.rolling(w, center=True, min_periods=w).mean()
    return x


def inverse_barometer_cm(p_hpa, cm_per_hpa=None):
    """Inverse-barometer sea-level response (cm) from a pressure Series (hPa), as an anomaly
    about its own mean. IB = -(P - Pbar) * 0.993 cm/hPa. Subtract it from sea level:
    corrected = residual - IB.
    """
    if cm_per_hpa is None:
        cm_per_hpa = 0.993
    return -(p_hpa - p_hpa.mean()) * cm_per_hpa


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km (scalars or numpy arrays)."""
    import numpy as np
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin((p2 - p1) / 2) ** 2
         + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def alongshore_distance(waypoints, start_km=None, direction=None):
    """Cumulative distance along a list of (name, lat, lon) coastal waypoints.
    start_km is the distance of the first waypoint (default 0). With direction=-1 (default) the
    distance decreases along the list (for a path walking south when 'north positive').
    Returns {name: km}. In 2026 the open-coast path went from San Diego (-1953 km from Neah Bay)
    via Ensenada, Punta Baja, Punta Eugenia, Punta Abreojos, Cabo San Lazaro and Cabo San Lucas,
    then across the Gulf mouth to Cabo Corrientes and down the mainland.
    """
    if start_km is None:
        start_km = 0.0
    if direction is None:
        direction = -1
    out = {waypoints[0][0]: float(start_km)}
    s = float(start_km)
    for a, b in zip(waypoints[:-1], waypoints[1:]):
        s += direction * float(haversine_km(a[1], a[2], b[1], b[2]))
        out[b[0]] = s
    return out


def event_metrics(lp, rise_window=None, min_window=None, max_window=None, rise_span_h=None):
    """Timing and size metrics on a low-passed hourly Series (cm).
    - steepest rise: maximum of x(t + span/2) - x(t - span/2) inside rise_window
      (default span 120 h = 5 days)
    - minimum inside min_window, maximum inside max_window
    Windows are (start, end) strings or Timestamps (UTC). Returns a dict with Timestamps and values.
    """
    import pandas as pd
    if rise_span_h is None:
        rise_span_h = 120
    T = lambda x: pd.Timestamp(x, tz="UTC") if pd.Timestamp(x).tzinfo is None else pd.Timestamp(x)
    out = {}
    if rise_window is not None:
        h = rise_span_h // 2
        d = (lp.shift(-h) - lp.shift(h))[T(rise_window[0]):T(rise_window[1])]
        out["t_rise"] = d.idxmax(); out["rise_cm"] = float(d.max())
    if min_window is not None:
        w = lp[T(min_window[0]):T(min_window[1])]
        out["t_min"] = w.idxmin(); out["min_cm"] = float(w.min())
    if max_window is not None:
        w = lp[T(max_window[0]):T(max_window[1])]
        out["t_max"] = w.idxmax(); out["max_cm"] = float(w.max())
    return out


def propagation_fit(times, distances_km, t0=None):
    """Least-squares fit of alongshore distance against event time (the peak-timing propagation test).
    times: Timestamps; distances_km: same length (north positive gives a positive speed for
    poleward propagation). Returns a dict with speed_ms, se_ms, r, intercept_km, t0, and
    arrival(dist_km) -> Timestamp, which extrapolates the arrival time at another distance.
    """
    import numpy as np, pandas as pd
    times = pd.DatetimeIndex(times)
    if t0 is None:
        t0 = times.min()
    tt = np.asarray((times - t0).total_seconds() / 86400.0)
    xx = np.asarray(distances_km, float)
    p = np.polyfit(tt, xx, 1)
    res = xx - np.polyval(p, tt)
    se = np.sqrt(np.sum(res ** 2) / (len(tt) - 2) / np.sum((tt - tt.mean()) ** 2))
    return {"speed_ms": p[0] * 1000 / 86400, "se_ms": se * 1000 / 86400,
            "r": float(np.corrcoef(tt, xx)[0, 1]), "intercept_km": p[1], "t0": t0,
            "arrival": lambda d: t0 + pd.Timedelta(days=(d - p[1]) / p[0])}


def bandpass_daily(x, short_days=None, long_days=None, order=3):
    """Zero-phase Butterworth band-pass of a daily Series (default 3-60 days). Interior gaps are
    interpolated for filtering and re-masked afterwards. Leading and trailing NaNs are dropped
    from the filter input.
    """
    import numpy as np, pandas as pd
    from scipy.signal import butter, filtfilt
    if short_days is None:
        short_days = 3
    if long_days is None:
        long_days = 60
    v = x.interpolate(limit_area="inside")
    m = v.notna()
    b, a = butter(order, [1.0 / long_days, 1.0 / short_days], btype="band", fs=1.0)
    out = pd.Series(np.nan, x.index)
    vv = v[m]
    out[m] = filtfilt(b, a, vv.values - vv.mean(), padlen=min(90, len(vv) - 1))
    out[x.isna()] = np.nan
    return out


def lag_correlation(x, y, max_lag=None, min_n=None):
    """r(k) = corr(x(t), y(t + k)) for k = -max_lag..max_lag (default 25 samples).
    Positive k means x leads y. Returns a Series indexed by lag.
    """
    import numpy as np, pandas as pd
    if max_lag is None:
        max_lag = 25
    if min_n is None:
        min_n = 30
    out = {}
    for k in range(-max_lag, max_lag + 1):
        b = y.shift(-k)
        m = x.notna() & b.notna()
        out[k] = np.corrcoef(x[m], b[m])[0, 1] if m.sum() > min_n else np.nan
    return pd.Series(out)


def effective_dof(x, y, max_lag=None):
    """Effective number of independent samples for corr(x, y), following Bretherton et al. (1999):
    N / (1 + 2 * sum_k rho_x(k) rho_y(k)), summed over lags 1..max_lag (default 60).
    """
    import numpy as np
    if max_lag is None:
        max_lag = 60
    m = x.notna() & y.notna()
    N = int(m.sum())

    def acf(v):
        v = v - np.nanmean(v)
        n = len(v)
        out = []
        for k in range(1, max_lag):
            a, b = v[: n - k], v[k:]
            ok = np.isfinite(a) & np.isfinite(b)
            out.append(np.corrcoef(a[ok], b[ok])[0, 1])
        return np.array(out)

    s = 1 + 2 * np.nansum(acf(x[m].values) * acf(y[m].values))
    return N / max(s, 1.0)


def r_critical(n_eff, alpha=None):
    """Two-sided critical correlation for n_eff effective samples (default alpha 0.05).
    This is a single-lag threshold. It does NOT account for picking the maximum over many lags.
    """
    import numpy as np
    from scipy import stats
    if alpha is None:
        alpha = 0.05
    t = stats.t.ppf(1 - alpha / 2, n_eff - 2)
    return float(t / np.sqrt(n_eff - 2 + t ** 2))


def met_dir_to_uv(speed, dir_from_deg):
    """Convert wind speed and meteorological direction (FROM, degrees) to u (east), v (north)."""
    import numpy as np
    d = np.deg2rad(np.asarray(dir_from_deg, dtype=float))
    s = np.asarray(speed, dtype=float)
    return -s * np.sin(d), -s * np.cos(d)


def wind_stress_large_pond(u, v, rho_air=1.22):
    """Wind stress (Pa) from 10 m wind components (m/s), Large and Pond (1981) drag coefficient.

    Cd = 1.2e-3 for U < 11 m/s, (0.49 + 0.065 U) 1e-3 above. Returns (tau_x, tau_y) arrays.
    """
    import numpy as np
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)
    U = np.hypot(u, v)
    cd = np.where(U < 11, 1.2e-3, (0.49 + 0.065 * U) * 1e-3)
    return rho_air * cd * U * u, rho_air * cd * U * v


def alongshore_component(tau_x, tau_y, coast_bearing_deg=304.0):
    """Project a vector on the coast direction (bearing in degrees true). 304 deg = poleward
    along SW Vancouver Island (Cape Beale to Estevan Point); positive = downwelling-favourable."""
    import numpy as np
    th = np.deg2rad(coast_bearing_deg)
    return np.asarray(tau_x) * np.sin(th) + np.asarray(tau_y) * np.cos(th)


def ib_correct(sea_level_cm, pressure_hPa, rho=1025.0, g=9.81):
    """Inverse-barometer-corrected sea level (cm): eta + p_a'/(rho g), p_a' = anomaly from the
    series mean. Both inputs are Series on the same index. 1 hPa = 0.9945 cm for rho=1025.
    A BPR measures rho*g*eta' + p_a', so its pressure/(rho g) should be compared with this."""
    pa = pressure_hPa - pressure_hPa.mean()
    return sea_level_cm + pa * (100.0 / (rho * g) * 100.0)


def detide_utide(series, lat, constit="auto"):
    """Residual of an hourly series after a UTide OLS harmonic fit with linear trend.

    Use at least several months of data (a year resolves the main constituents). Returns a
    Series on the input index (NaNs dropped before fitting). Gotcha: ONC hourly averages are
    stamped at hh:30, CHS/NOAA hourly values at hh:00 - shift before comparing hour by hour.
    """
    import pandas as pd
    import utide
    x = series.dropna()
    t = x.index.tz_convert(None).to_pydatetime()
    co = utide.solve(t, x.values, lat=lat, method="ols", conf_int="none", trend=True,
                     verbose=False, constit=constit)
    rec = utide.reconstruct(t, co, verbose=False)
    return pd.Series(x.values - rec.h, index=x.index, name=f"{series.name}_detided" if series.name else None)


def event_amplitude(series, peak_window, background_windows, smooth_hours=13):
    """Event amplitude = max of a centred running mean inside peak_window minus the mean of
    that running mean over the background windows.

    peak_window: (start, end) strings; background_windows: list of (start, end).
    Returns dict(background, peak, t_peak, amplitude, hourly_max, t_hourly_max).
    """
    import pandas as pd
    ss = series.rolling(smooth_hours, center=True, min_periods=max(1, int(0.75 * smooth_hours))).mean()
    bg = pd.concat([ss.loc[a:b] for a, b in background_windows]).mean()
    w = ss.loc[peak_window[0]:peak_window[1]]
    raw = series.loc[peak_window[0]:peak_window[1]]
    return {"background": bg, "peak": w.max(), "t_peak": w.idxmax(), "amplitude": w.max() - bg,
            "hourly_max": raw.max(), "t_hourly_max": raw.idxmax()}


def propagation_test(peak_times, coords, order, wave_speed_ms=3.1):
    """Compare observed peak lags along a coastal path with a free-wave travel time.

    peak_times: dict station -> Timestamp; coords: dict station -> (lat, lon); order: list of
    stations along the path (first = upstream). Distance is the sum of great-circle legs.
    Returns DataFrame with cumulative distance (km), observed lag (h) from the first station
    and expected lag (h) at wave_speed_ms. Near-zero observed lags over hundreds of km mean
    atmospheric (weather-system) forcing rather than a propagating coastal-trapped wave.
    """
    import pandas as pd
    rows, dist = [], 0.0
    for i, s in enumerate(order):
        if i > 0:
            a, b = coords[order[i - 1]], coords[s]
            dist += float(haversine_km(a[0], a[1], b[0], b[1]))
        lag = (pd.Timestamp(peak_times[s]) - pd.Timestamp(peak_times[order[0]])) / pd.Timedelta("1h")
        rows.append({"station": s, "distance_km": dist, "observed_lag_h": lag,
                     "expected_lag_h": dist * 1e3 / wave_speed_ms / 3600.0})
    return pd.DataFrame(rows)



def ctw_model(tau, s_out_km, c=3.5, T_days=3.0, b=1.0, boundary=None, s0_km=None):
    """Forced, damped single-mode coastal-trapped wave, d(eta)/dt + c d(eta)/dy + eta/T = b*tau.

    Integrated backward along characteristics y = y_out - c*u (hourly steps).
    tau: DataFrame, hourly UTC index, columns = alongshore position in km (increasing in the direction
         of propagation, i.e. poleward), values = alongshore wind stress (Pa, poleward positive).
    s_out_km: positions (km, same axis) where eta is wanted.
    c: phase speed (m/s); T_days: friction time; b: coupling (cm per Pa per hour if eta in cm).
       Fit b by least squares afterwards: run with b=1 and regress observed sea level on the output.
    boundary: optional hourly Series of sea level at s0_km (southern end, e.g. San Francisco anomaly),
       carried north as eta_b(t - (s - s0)/c) * exp(-(s - s0)/(c T)).
    Returns DataFrame (index = tau.index, columns = s_out_km).
    Lessons: take tau 40 km seaward of the coast (check the sign of the offset), and route the path
    through the capes so it never crosses land; band-pass both model and data (e.g. 3-60 d) before fitting.
    """
    import numpy as np, pandas as pd
    pos = np.asarray(tau.columns, dtype=float)
    order = np.argsort(pos); pos = pos[order]
    X = tau.to_numpy(dtype=float)[:, order]
    X = np.where(np.isfinite(X), X, 0.0)
    if s0_km is None:
        s0_km = float(pos[0])
    dkm = c * 3.6                      # km travelled per hour
    T_h = T_days * 24.0
    n = len(tau.index)
    out = {}
    for s in np.atleast_1d(s_out_km):
        K = int(max(0, np.floor((s - s0_km) / dkm)))
        eta = np.zeros(n)
        for k in range(K + 1):
            p = s - k * dkm
            if p < pos[0] or p > pos[-1]:
                continue
            j = np.searchsorted(pos, p); j = min(max(j, 1), len(pos) - 1)
            w = (p - pos[j - 1]) / (pos[j] - pos[j - 1])
            col = (1 - w) * X[:, j - 1] + w * X[:, j]
            shifted = np.roll(col, k); shifted[:k] = 0.0
            eta += b * shifted * np.exp(-k / T_h)
        if boundary is not None:
            lag_h = (s - s0_km) / dkm
            bb = boundary.reindex(tau.index).interpolate(limit_area="inside").to_numpy(dtype=float)
            sh = int(round(lag_h))
            bs = np.roll(bb, sh); bs[:sh] = np.nan
            eta = eta + np.nan_to_num(bs) * np.exp(-lag_h / T_h)
        out[float(s)] = eta
    return pd.DataFrame(out, index=tau.index)


def isotherm_heave(dT, dTdz):
    """Vertical displacement (m, positive downward) implied by a temperature change dT at fixed depth
    and the local vertical gradient dTdz (degC per m, negative when temperature falls with depth).
    Example: dT = +0.08 C, dTdz = -0.0032 C/m gives 25 m downward."""
    return -dT / dTdz

