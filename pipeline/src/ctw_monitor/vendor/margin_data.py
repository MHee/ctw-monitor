"""Vendored from the Claude Science skill `ne-pacific-margin-data` (October 2026). See vendor/README.md.

Imports are inside functions, so heavy optional packages (xarray for ERA5 netCDF) are only needed
by the functions that use them."""
# ruff: noqa
"""ne-pacific-margin-data: fetchers for tide gauges, buoys, weather stations and ERDDAP servers on the
NE Pacific margin (Mexico to Alaska). Functions only; every import sits inside a function body."""


def mexican_pacific_stations():
    """Station table used for the 2026 southern-propagation test (north -> south).

    Returns a pandas DataFrame with name, source ('ioc' or 'uhslc'), code, preferred sensor,
    lat, lon and a note. The 2026 status was checked on 2026-10-07:
    - No 2026 data on IOC or UHSLC: Ensenada (ense), Isla de Cedros (cedr), Cabo San Lucas (cabo),
      Mazatlan (maza/maza2), Acapulco (acap/acap2), Manzanillo_MX (manz), La Paz (lpaz).
      This leaves a ~1,900 km gap on the Baja California coast.
    - Acapulco Club de Yates (acya) has only ~140 valid hours in Apr-Aug 2026, so it is unusable.
    - Champerico (prch) 'rad' reports ~6 samples/h, and its M2 amplitude (20 cm vs 68 cm next door)
      failed QC.
    - Isla Clarion (iclr) is an offshore island with a suspiciously small range; it was not used.
    """
    import pandas as pd
    rows = [
        ("La Jolla", "uhslc", "554", None, 32.867, -117.257, "UHSLC FD; IOC lajo (bwl) also works"),
        ("La Paz", "ioc", "lpaz2", "rad", 24.267, -110.333, "inside Gulf of California"),
        ("Puerto Vallarta", "ioc", "puer2", "rad", 20.658, -105.243, "flt also available"),
        ("Manzanillo", "ioc", "mnza", "rad", 19.061, -104.301, "bub also available"),
        ("Lazaro Cardenas", "ioc", "laza2", "rad", 17.940, -102.178, "flt also available"),
        ("Zihuatanejo", "ioc", "zihu2", "rad", 17.636, -101.558, "flt also available"),
        ("Puerto Angel", "ioc", "ptan", "rad", 15.665, -96.492, ""),
        ("Huatulco", "ioc", "huat2", "rad", 15.750, -96.117, "huat: April only"),
        ("Salina Cruz", "ioc", "sali", "flt", 16.168, -95.197, "sali2: April only"),
        ("Puerto Chiapas", "ioc", "chia", "rad", 14.712, -92.401, "made (flt) is a backup"),
        ("Champerico", "ioc", "prch", "rad", 14.297, -91.916, "failed QC in 2026"),
        ("Puerto San Jose", "ioc", "prsj", "rad", 13.922, -90.801, "bat channel = battery, not sea level"),
        ("Acajutla", "uhslc", "82", None, 13.574, -89.837, "UHSLC FD"),
    ]
    return pd.DataFrame(rows, columns=["name", "source", "code", "sensor", "lat", "lon", "note"])


def ioc_station_list(timeout=60):
    """IOC Sea Level Station Monitoring Facility station list.

    Endpoint: https://www.ioc-sealevelmonitoring.org/service.php?query=stationlist&showall=all
    Returns a DataFrame with Code, Location, country, Lat, Lon, sensor, status, ... (one row per
    station-sensor; codes can repeat). Gotcha: being in the list does NOT mean data exist for
    your window. Probe each station with ioc_sea_level() over 1 day before a long pull.
    """
    import requests, pandas as pd
    r = requests.get("https://www.ioc-sealevelmonitoring.org/service.php",
                     params={"query": "stationlist", "showall": "all"}, timeout=timeout)
    r.raise_for_status()
    return pd.DataFrame(r.json())


def ioc_sea_level(code, start, end, chunk_days=10, timeout=120, retries=3, pause_s=5):
    """Raw IOC SLSMF sea level for one station, all sensors, in long format.

    Endpoint: service.php?query=data&code=<code>&timestart=<ISO>&timestop=<ISO>&format=json
    Returns a DataFrame indexed by UTC time with columns 'sensor' and 'slevel' (metres, arbitrary
    datum; real-time and NOT quality-controlled; typically 1-min sampling).
    Gotchas:
    - An empty list '[]' (HTTP 200) means no data, not an error.
    - Requests are chunked (10 days worked; ~43k rows per chunk at 1-min sampling) with retries.
      A full 5-month pull for ~18 stations took ~12 min.
    - Several sensors (rad, flt, bub, prs, bat) can be interleaved. 'bat' at some
      Guatemalan stations is battery voltage, so pick the sensor explicitly.
    - Stations sharing a site use separate codes (e.g. puert vs puer2), and the one with data may be
      the '2' code.
    """
    import time, requests, pandas as pd
    t0, t1 = pd.Timestamp(start), pd.Timestamp(end)
    frames = []
    a = t0
    while a < t1:
        b = min(a + pd.Timedelta(days=chunk_days), t1)
        url = "https://www.ioc-sealevelmonitoring.org/service.php"
        params = {"query": "data", "code": code, "timestart": a.strftime("%Y-%m-%dT%H:%M:%S"),
                  "timestop": b.strftime("%Y-%m-%dT%H:%M:%S"), "format": "json"}
        js = []
        for k in range(retries):
            try:
                rr = requests.get(url, params=params, timeout=timeout)
                rr.raise_for_status()
                js = rr.json()
                break
            except Exception:
                if k == retries - 1:
                    raise
                time.sleep(pause_s)
        if js:
            frames.append(pd.DataFrame(js))
        a = b
    if not frames:
        return pd.DataFrame(columns=["sensor", "slevel"],
                            index=pd.DatetimeIndex([], tz="UTC", name="time"))
    d = pd.concat(frames, ignore_index=True)
    d["time"] = pd.to_datetime(d["stime"], utc=True)
    d = d.drop_duplicates(["time", "sensor"]).set_index("time").sort_index()
    return d[["sensor", "slevel"]]


def ioc_hourly(raw, sensor, min_samples=None, to_cm=True):
    """Hourly median of one IOC sensor, with hours that have too few samples set to NaN.

    raw: output of ioc_sea_level(). min_samples defaults to 10 (for 1-min data). Use 3 for
    stations that report every ~10 min (e.g. Champerico 'rad' had ~6 samples/h).
    Returns a Series (cm if to_cm, else m) on an hourly UTC index. The hourly median is robust
    to the isolated spikes common in real-time IOC data.
    """
    import numpy as np, pandas as pd
    if min_samples is None:
        min_samples = 10
    s = raw.loc[raw["sensor"] == sensor, "slevel"].astype(float)
    if s.empty:
        return pd.Series(dtype=float, name=sensor)
    h = s.resample("1h").median()
    n = s.resample("1h").count()
    h[n < min_samples] = np.nan
    if to_cm:
        h = h * 100.0
    h.name = sensor
    return h


def uhslc_fast_hourly(uhslc_id, start, end, timeout=90):
    """UHSLC fast-delivery hourly sea level via ERDDAP (dataset global_hourly_fast).

    Endpoint: https://uhslc.soest.hawaii.edu/erddap/tabledap/global_hourly_fast.csv
              ?time,sea_level&uhslc_id=<id>&time>=<start>&time<=<end>
    Returns a Series in cm (the source is mm) with a UTC index.
    Gotchas:
    - The CSV has a units row under the header; skip it.
    - A window without data returns HTTP 404 with 'Your query produced no matching results',
      which here becomes an empty Series.
    - The station-list field last_rq_date is the research-quality end date. Fast-delivery data can
      run well past it (e.g. Acajutla, id 82). Mexican ids 34 Cabo, 90 Socorro, 316 Acapulco,
      317 Ensenada and 395 Manzanillo had NO 2026 fast-delivery data.
    """
    import io, requests, pandas as pd
    url = ("https://uhslc.soest.hawaii.edu/erddap/tabledap/global_hourly_fast.csv"
           "?time,sea_level&uhslc_id=%s&time>=%s&time<=%s"
           % (uhslc_id, pd.Timestamp(start).strftime("%Y-%m-%dT%H:%M:%SZ"),
              pd.Timestamp(end).strftime("%Y-%m-%dT%H:%M:%SZ")))
    r = requests.get(url, timeout=timeout)
    if r.status_code == 404:
        return pd.Series(dtype=float, name="sea_level_cm")
    r.raise_for_status()
    d = pd.read_csv(io.StringIO(r.text), skiprows=[1])
    d["time"] = pd.to_datetime(d["time"], utc=True)
    s = d.set_index("time")["sea_level"].astype(float) / 10.0
    s.name = "sea_level_cm"
    return s


def uhslc_fast_stations(lat_min, lat_max, lon_min_east, lon_max_east, timeout=90):
    """Distinct UHSLC fast-delivery stations in a box (longitude in 0-360 degrees east).

    Returns a DataFrame with station_name, station_country, uhslc_id, latitude, longitude and
    last_rq_date.
    """
    import io, requests, pandas as pd
    url = ("https://uhslc.soest.hawaii.edu/erddap/tabledap/global_hourly_fast.csv"
           "?station_name,station_country,uhslc_id,latitude,longitude,last_rq_date&distinct()"
           "&latitude>=%s&latitude<=%s&longitude>=%s&longitude<=%s"
           % (lat_min, lat_max, lon_min_east, lon_max_east))
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text), skiprows=[1])


def era5_msl_fetch(area, start, end, out_path, grid=None, hours_step=3, token=None,
                   budget_s=3600, poll_s=20):
    """Retrieve ERA5 mean sea-level pressure for a box and date range from the CDS retrieve API.

    area: [North, West, South, East] in degrees (-180..180). grid defaults to [0.5, 0.5].
    The request covers every day in the months spanned by start..end, at hours 0, hours_step, ...
    Use one calendar year per call (CDS cost limit). The token defaults to $CDS_API_TOKEN.
    Returns out_path (netCDF).
    Gotchas:
    - Do not use cdsapi; its submit call has hung unkillably on this host. Use plain requests.
    - The download URL is on object-store.os-api.cci2.ecmwf.int, which must also be allowlisted.
      Without it, submit returns 200 and the download fails with a proxy 403.
    - Box 33.5N-13N, 118W-89W, at 0.5 deg, 3-hourly, for Apr-Aug 2026 was 5 MB and took ~3 min.
    """
    import os, time, requests, pandas as pd
    if grid is None:
        grid = [0.5, 0.5]
    if token is None:
        token = os.environ.get("CDS_API_TOKEN")
    if not token:
        raise RuntimeError("CDS_API_TOKEN absent; declare the credential on the cell")
    t0, t1 = pd.Timestamp(start), pd.Timestamp(end)
    if t0.year != t1.year:
        raise ValueError("one calendar year per request")
    months = sorted({"%02d" % m for m in pd.date_range(t0.normalize(), t1.normalize(), freq="D").month})
    days = sorted({"%02d" % d for d in pd.date_range(t0.normalize(), t1.normalize(), freq="D").day})
    body = {"inputs": {"product_type": ["reanalysis"], "variable": ["mean_sea_level_pressure"],
                       "year": [str(t0.year)], "month": months, "day": days,
                       "time": ["%02d:00" % h for h in range(0, 24, hours_step)],
                       "area": list(area), "grid": [str(g) for g in grid],
                       "data_format": "netcdf", "download_format": "unarchived"}}
    base = "https://cds.climate.copernicus.eu/api/retrieve/v1"
    head = {"PRIVATE-TOKEN": token, "Accept": "application/json", "Content-Type": "application/json"}
    r = requests.post(base + "/processes/reanalysis-era5-single-levels/execution",
                      headers=head, json=body, timeout=(10, 180))
    if r.status_code not in (200, 201):
        raise RuntimeError("CDS submit %s: %s" % (r.status_code, r.text[:300]))
    jid = r.json()["jobID"]
    t_start = time.time()
    while time.time() - t_start < budget_s:
        time.sleep(poll_s)
        try:
            st = requests.get(base + "/jobs/" + jid, headers=head, timeout=(10, 60)).json().get("status")
        except Exception:
            continue
        if st in ("accepted", "running"):
            continue
        if st != "successful":
            raise RuntimeError("CDS job %s ended %s" % (jid, st))
        res = requests.get(base + "/jobs/%s/results" % jid, headers=head, timeout=(10, 60)).json()
        href = res["asset"]["value"]["href"]
        with requests.get(href, stream=True, timeout=(10, 900)) as dl:
            dl.raise_for_status()
            with open(out_path, "wb") as fh:
                for chunk in dl.iter_content(1 << 20):
                    fh.write(chunk)
        return out_path
    raise TimeoutError("CDS job %s still pending after %s s (resubmit later; it is cached)" % (jid, budget_s))


def era5_point_pressure(nc_path, lat, lon, index=None):
    """ERA5 msl (hPa) at the nearest grid cell as a UTC Series, optionally time-interpolated onto
    `index` (e.g. an hourly tide-gauge index). The time coordinate is 'valid_time' in current CDS
    files (older files use 'time'). A stray 'expver' dimension is collapsed with max().
    Gotcha: pandas time interpolation holds the last value past the end of the ERA5 record, so
    request at least one extra day beyond the tide-gauge window.
    """
    import pandas as pd, xarray as xr
    with xr.open_dataset(nc_path) as ds:
        tname = "valid_time" if "valid_time" in ds.coords else "time"
        p = ds["msl"].sel(latitude=lat, longitude=lon, method="nearest").load()
        if "expver" in p.dims:
            p = p.max("expver")
        ps = pd.Series(p.values / 100.0, pd.to_datetime(p[tname].values, utc=True), name="msl_hPa")
    if index is not None:
        ps = ps.reindex(ps.index.union(index)).interpolate(method="time").reindex(index)
    return ps


def http_get(url, params=None, timeout=120, retries=3, backoff_s=5):
    """GET with retries. Returns the requests.Response (raises after the last try).

    Gotcha: a proxy/allowlist block raises ProxyError immediately; retrying does not help,
    so the function re-raises ProxyError without retrying.
    """
    import time
    import requests
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                last = RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                time.sleep(backoff_s * (attempt + 1))
                continue
            return r
        except requests.exceptions.ProxyError:
            raise
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last = e
            time.sleep(backoff_s * (attempt + 1))
    raise last


def to_utc_ns(index):
    """Return a tz-aware UTC DatetimeIndex in nanosecond units.

    Gotcha: pandas raised "AttributeError: 'Index' object has no attribute 'tz'" when
    subtracting two Series whose UTC indexes had different units (datetime64[us, UTC]
    from pd.to_datetime on strings vs datetime64[ns, UTC] from parquet). Normalise
    every index with this before aligning.
    """
    import pandas as pd
    idx = pd.DatetimeIndex(pd.to_datetime(index, utc=True))
    return idx.as_unit("ns")


def find_chs_station(code):
    """Look up a CHS IWLS station by its 5-digit code (e.g. '07120' Victoria Harbour).

    Endpoint: https://api-iwls.dfo-mpo.gc.ca/api/v1/stations?code=<code>
    Returns dict with id, officialName, latitude, longitude and available time-series codes.
    Known ids: Tofino 5cebf1e23d0f4a073c4bc07c, Bamfield 5cebf1e23d0f4a073c4bc062,
    Port Renfrew 5cebf1e23d0f4a073c4bc060, Winter Harbour 5cebf1e23d0f4a073c4bc097,
    Victoria Harbour 5cebf1df3d0f4a073c4bbd1e, Prince Rupert 5cebf1de3d0f4a073c4bba06.
    """
    r = http_get("https://api-iwls.dfo-mpo.gc.ca/api/v1/stations", params={"code": code}, timeout=60)
    r.raise_for_status()
    js = r.json()
    if not js:
        return None
    s = js[0]
    return {"id": s["id"], "officialName": s.get("officialName"), "latitude": s.get("latitude"),
            "longitude": s.get("longitude"), "timeSeries": [t["code"] for t in s.get("timeSeries", [])]}


def fetch_chs_iwls(station_id, start, end, code="wlo", resolution="FIFTEEN_MINUTES", window_days=6):
    """CHS IWLS water level for one station as a Series in metres (chart datum), UTC index.

    Endpoint: https://api-iwls.dfo-mpo.gc.ca/api/v1/stations/<id>/data
    Parameters: time-series-code ('wlo' observed, 'wlp' official prediction, 'wlf' forecast),
    from/to ISO 'YYYY-MM-DDTHH:MM:SSZ', resolution ONE_MINUTE | THREE_MINUTES | FIVE_MINUTES |
    FIFTEEN_MINUTES | SIXTY_MINUTES.
    Gotchas: requests are limited in length; 6-day windows at 15-min and 30-day windows at
    SIXTY_MINUTES worked. Online 'wlo' holdings for Tofino/Bamfield/Winter Harbour/Prince
    Rupert only start around 2019-2020. Residual = wlo - wlp (both on chart datum).
    """
    import pandas as pd
    t0, t1 = to_utc_ns([start, end])
    edges = list(pd.date_range(t0, t1, freq=f"{window_days}D"))
    if edges[-1] < t1:
        edges.append(t1)
    parts = []
    for a, b in zip(edges[:-1], edges[1:]):
        r = http_get(f"https://api-iwls.dfo-mpo.gc.ca/api/v1/stations/{station_id}/data",
                     params={"time-series-code": code, "from": a.strftime("%Y-%m-%dT%H:%M:%SZ"),
                             "to": b.strftime("%Y-%m-%dT%H:%M:%SZ"), "resolution": resolution}, timeout=120)
        if r.status_code != 200:
            continue
        d = pd.DataFrame(r.json())
        if d.empty:
            continue
        parts.append(pd.Series(d["value"].astype(float).values, index=to_utc_ns(d["eventDate"])))
    if not parts:
        return pd.Series(dtype=float, name=code)
    s = pd.concat(parts)
    s = s[~s.index.duplicated()].sort_index()
    s.name = code
    return s


def chs_residual(station_id, start, end, resolution="FIFTEEN_MINUTES", window_days=6):
    """Observed minus CHS prediction (wlo - wlp) in cm, UTC index. Uses fetch_chs_iwls twice."""
    obs = fetch_chs_iwls(station_id, start, end, "wlo", resolution, window_days)
    prd = fetch_chs_iwls(station_id, start, end, "wlp", resolution, window_days)
    res = (obs - prd) * 100.0
    res.name = "residual_cm"
    return res


def list_eccc_climate_stations(bbox, hourly_after=None):
    """ECCC climate stations in a lon/lat bbox (minlon,minlat,maxlon,maxlat) as a DataFrame.

    Endpoint: https://api.weather.gc.ca/collections/climate-stations/items
    hourly_after: e.g. '2026' keeps only stations whose HLY_LAST_DATE starts with/after it.
    Gotchas: query hourly data by CLIMATE_IDENTIFIER (not STN_ID). Several stations have two
    ids (Tofino A: 1038210 'Aviation-Auto' has complete hourly data, 1038204 staffed is
    partial, 1038205 returns nothing). Lightstations (Cape Beale, Lennard Island, Amphitrite
    Point, Pachena Point) have no hourly pressure or wind in the archive.
    """
    import pandas as pd
    r = http_get("https://api.weather.gc.ca/collections/climate-stations/items",
                 params={"f": "json", "bbox": ",".join(str(x) for x in bbox), "limit": 1000}, timeout=120)
    r.raise_for_status()
    rows = []
    for f in r.json().get("features", []):
        p = f["properties"]
        rows.append({"STATION_NAME": p.get("STATION_NAME"), "CLIMATE_IDENTIFIER": p.get("CLIMATE_IDENTIFIER"),
                     "STN_ID": p.get("STN_ID"), "STATION_TYPE": p.get("STATION_TYPE"),
                     "HLY_FIRST_DATE": p.get("HLY_FIRST_DATE"), "HLY_LAST_DATE": p.get("HLY_LAST_DATE"),
                     "lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1]})
    df = pd.DataFrame(rows)
    if hourly_after is not None and len(df):
        df = df[df["HLY_LAST_DATE"].fillna("") >= str(hourly_after)]
    return df.reset_index(drop=True)


def fetch_eccc_climate_hourly(climate_id, start, end, page_size=1000):
    """ECCC hourly climate observations for one station, UTC index.

    Endpoint: https://api.weather.gc.ca/collections/climate-hourly/items
    Parameters: CLIMATE_IDENTIFIER, datetime='<start>/<end>' (ISO Z), sortby=UTC_DATE,
    limit/offset paging (page_size <= 10000; 1000 used).
    Returns columns: station_pressure_hPa (converted from kPa STATION_PRESSURE; this is
    station-level, not mean sea level, so use anomalies or add an elevation offset),
    wind_speed_kmh, wind_dir_deg (converted from tens of degrees), temp_C, precip_mm.
    Gotchas: STATION_PRESSURE is kPa and WIND_DIRECTION is in tens of degrees; some stations
    report direction rarely (Estevan Point CS). Archive lags real time by a few days.
    """
    import pandas as pd
    out, off = [], 0
    dt = f"{pd.Timestamp(start).strftime('%Y-%m-%dT%H:%M:%SZ')}/{pd.Timestamp(end).strftime('%Y-%m-%dT%H:%M:%SZ')}"
    while True:
        r = http_get("https://api.weather.gc.ca/collections/climate-hourly/items",
                     params={"f": "json", "CLIMATE_IDENTIFIER": climate_id, "datetime": dt,
                             "limit": page_size, "offset": off, "sortby": "UTC_DATE"}, timeout=180)
        r.raise_for_status()
        fs = r.json().get("features", [])
        out += [f["properties"] for f in fs]
        if len(fs) < page_size:
            break
        off += page_size
    if not out:
        return pd.DataFrame()
    d = pd.DataFrame(out)
    df = pd.DataFrame(index=to_utc_ns(d["UTC_DATE"]))
    df["station_pressure_hPa"] = pd.to_numeric(d["STATION_PRESSURE"], errors="coerce").values * 10.0
    df["wind_speed_kmh"] = pd.to_numeric(d["WIND_SPEED"], errors="coerce").values
    df["wind_dir_deg"] = pd.to_numeric(d["WIND_DIRECTION"], errors="coerce").values * 10.0
    df["temp_C"] = pd.to_numeric(d["TEMP"], errors="coerce").values
    df["precip_mm"] = pd.to_numeric(d["PRECIP_AMOUNT"], errors="coerce").values
    df["station"] = d["STATION_NAME"].values
    return df.sort_index()


def fetch_eccc_buoys_cioos(start, end, name_regex=None, variables=None):
    """ECCC moored-buoy observations from the CIOOS Pacific ERDDAP (dataset ECCC_MSC_BUOYS).

    Endpoint: https://data.cioospacific.ca/erddap/tabledap/ECCC_MSC_BUOYS.csv
    name_regex: ERDDAP regex on stn_nam, default '(?i).*(PEROUSE|BROOKS).*'. Station names:
    LA PEROUSE BANK (46206), SOUTH BROOKS (46132), EAST DELLWOOD (46207), WEST SEA OTTER
    (46204), SOUTH/MIDDLE/NORTH NOMAD (46036/46004/46184), HALIBUT BANK, SENTRY SHOAL.
    Units: wind km/h (10-min mean), direction degrees FROM, pressures hPa, temperature degC.
    Returns a long DataFrame (UTC index) with stn_nam and the requested variables.
    Gotchas: DFO MEDS archive files stop in Dec 2022 and GeoMet swob keeps ~30 days, so this
    is the only source found for 2026 buoy data. Observations are stamped at hh:05 - floor to
    the hour before merging (see buoy_hourly). La Perouse Bank had ~22 % missing hours in
    May-June 2026. The second CSV row holds units and must be skipped.
    """
    import io
    import pandas as pd
    if name_regex is None:
        name_regex = "(?i).*(PEROUSE|BROOKS).*"
    if variables is None:
        variables = ["avg_wnd_spd_pst10mts", "avg_wnd_dir_pst10mts", "avg_stn_pres_pst10mts",
                     "avg_mslp_pst10mts", "avg_air_temp_pst10mts", "avg_sea_sfc_temp_pst10mts"]
    cols = ",".join(["time", "wmo_synop_id", "stn_nam", "latitude", "longitude"] + list(variables))
    t0 = pd.Timestamp(start).strftime("%Y-%m-%dT%H:%M:%SZ")
    t1 = pd.Timestamp(end).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (f"https://data.cioospacific.ca/erddap/tabledap/ECCC_MSC_BUOYS.csv?{cols}"
           f"&time>={t0}&time<={t1}&stn_nam=~\"{name_regex}\"")
    r = http_get(url, timeout=300)
    if r.status_code == 404:  # ERDDAP returns 404 when no rows match
        return pd.DataFrame()
    r.raise_for_status()
    d = pd.read_csv(io.StringIO(r.text), skiprows=[1])
    d.index = to_utc_ns(d.pop("time"))
    return d.sort_index()


def buoy_hourly(df, station):
    """Hourly mean of one buoy from fetch_eccc_buoys_cioos output (index floored to the hour)."""
    x = df[df["stn_nam"] == station].drop(columns=["stn_nam"]).select_dtypes("number").copy()
    x.index = x.index.floor("h")
    return x.groupby(level=0).mean()


def fetch_noaa_coops(station, start, end, product="hourly_height", datum="MSL"):
    """NOAA CO-OPS series as a Series (m for water level, hPa for air_pressure), UTC index.

    Endpoint: https://api.tidesandcurrents.noaa.gov/api/prod/datagetter
    product: 'hourly_height', 'predictions' (interval=h), 'air_pressure', 'water_level'.
    Gotchas: hourly_height and predictions are limited to about one year per request
    (31 days for 6-min water_level); request time_zone=gmt; keep the same datum for
    observations and predictions. Station ids: San Francisco 9414290, Crescent City 9419750,
    Port Orford 9431647, South Beach 9435380, Toke Point 9440910, Neah Bay 9443090.
    """
    import pandas as pd
    p = {"product": product, "station": station, "begin_date": pd.Timestamp(start).strftime("%Y%m%d %H:%M"),
         "end_date": pd.Timestamp(end).strftime("%Y%m%d %H:%M"), "units": "metric", "time_zone": "gmt",
         "format": "json", "application": "research"}
    if product in ("hourly_height", "predictions", "water_level"):
        p["datum"] = datum
    if product == "predictions":
        p["interval"] = "h"
    r = http_get("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter", params=p, timeout=120)
    r.raise_for_status()
    js = r.json()
    rows = js.get("predictions", js.get("data", []))
    if not rows:
        return pd.Series(dtype=float, name=product)
    d = pd.DataFrame(rows)
    s = pd.Series(pd.to_numeric(d["v"], errors="coerce").values, index=to_utc_ns(d["t"]), name=product)
    return s


def era5_point_nc(nc_path, lat, lon, variables=None):
    """Nearest-grid-point ERA5 series from a local single-level netCDF (CDS download).

    Returns DataFrame (UTC index) with u10, v10 (m/s) and msl converted to hPa.
    Gotchas: CDS netCDF uses 'valid_time' (naive UTC) rather than 'time'; latitude is
    descending. Open lazily and .load() only the point to keep memory small.
    """
    import xarray as xr
    if variables is None:
        variables = ["u10", "v10", "msl"]
    with xr.open_dataset(nc_path) as ds:
        tname = "valid_time" if "valid_time" in ds.dims else "time"
        p = ds[variables].sel(latitude=lat, longitude=lon, method="nearest").load()
        df = p.to_dataframe()[variables]
    df.index = to_utc_ns(df.index)
    if "msl" in df:
        df["msl"] = df["msl"] / 100.0
    return df



def fetch_ndbc_stdmet(station, year, months=None):
    """NOAA NDBC standard meteorological data for one buoy and year, from the monthly files
    https://www.ndbc.noaa.gov/data/stdmet/{Mon}/{station}{m}{year}.txt.gz (m = month number without padding;
    recent months may sit uncompressed at .../{station}.txt instead). Returns hourly-ish DataFrame (UTC) with
    WDIR, WSPD, GST, PRES, ATMP, WTMP; 99/999/9999 fill values set to NaN.
    Gotcha: ECCC buoys such as 46206 (La Perouse) are absent for 2026; use fetch_eccc_buoys_cioos instead."""
    import io, gzip, calendar, requests, pandas as pd, numpy as np
    if months is None:
        months = range(1, 13)
    parts = []
    for m in months:
        mon = calendar.month_abbr[m]
        for url in (f"https://www.ndbc.noaa.gov/data/stdmet/{mon}/{station}{m}{year}.txt.gz",
                    f"https://www.ndbc.noaa.gov/data/stdmet/{mon}/{station}.txt"):
            r = requests.get(url, timeout=60)
            if r.ok and len(r.content) > 200:
                raw = gzip.decompress(r.content) if url.endswith(".gz") else r.content
                df = pd.read_csv(io.BytesIO(raw), sep=r"\s+", skiprows=[1], na_values=[99.0, 999.0, 9999.0, "MM"])
                df = df.rename(columns={"#YY": "YY"})
                t = pd.to_datetime(dict(year=df["YY"], month=df["MM"], day=df["DD"], hour=df["hh"], minute=df["mm"]), utc=True)
                parts.append(df.set_index(t)[[c for c in ("WDIR", "WSPD", "GST", "PRES", "ATMP", "WTMP") if c in df]])
                break
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts).sort_index()
    return out[~out.index.duplicated()]


def fetch_erddap_table(server, dataset, variables, t0, t1, constraints=None, order_by_mean=None, timeout=900):
    """Generic ERDDAP tabledap CSV fetch as a DataFrame with a UTC 'time' index.

    server: e.g. 'https://erddap.dataexplorer.oceanobservatories.org/erddap' (OOI),
            'https://data.cioospacific.ca/erddap' (CIOOS Pacific), 'https://uhslc.soest.hawaii.edu/erddap'.
    variables: list of variable names ('time' added if missing); constraints: list like ['station_id="46206"'].
    order_by_mean: e.g. 'time/1hour' or 'time/1day' to let the server average (OOI subtidal work);
    OOI requests can take minutes, so keep timeout long and windows short (months, not years)."""
    import io, urllib.parse, requests, pandas as pd
    v = list(variables)
    if "time" not in v:
        v = ["time"] + v
    q = ",".join(v) + f"&time>={t0}&time<={t1}"
    for c in (constraints or []):
        q += "&" + c
    if order_by_mean:
        q += f'&orderByMean("{order_by_mean}")'
    url = f"{server}/tabledap/{dataset}.csv?" + urllib.parse.quote(q, safe="=&,<>()/\":")
    r = requests.get(url, timeout=timeout)
    if not r.ok:
        raise RuntimeError(f"ERDDAP {r.status_code}: {r.text[:300]} (check names with erddap_variables)")
    df = pd.read_csv(io.StringIO(r.text), skiprows=[1])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df.set_index("time")


def erddap_variables(server, dataset, timeout=120):
    """List variable names (and units where given) of an ERDDAP dataset, from /info/{dataset}/index.csv.
    Call this before fetch_erddap_table: OOI names are long CF names, e.g. sea_water_pressure_at_sea_floor."""
    import io, requests, pandas as pd
    r = requests.get(f"{server}/info/{dataset}/index.csv", timeout=timeout)
    r.raise_for_status()
    info = pd.read_csv(io.StringIO(r.text))
    v = info[info["Row Type"] == "variable"]["Variable Name"].tolist()
    u = info[(info["Row Type"] == "attribute") & (info["Attribute Name"] == "units")].set_index("Variable Name")["Value"].to_dict()
    return {name: u.get(name, "") for name in v}


def erddap_search(server, text, n=20, timeout=120):
    """Free-text dataset search on an ERDDAP server; returns a DataFrame of Dataset ID and Title."""
    import io, urllib.parse, requests, pandas as pd
    r = requests.get(f"{server}/search/index.csv?searchFor={urllib.parse.quote(text)}&page=1&itemsPerPage={n}", timeout=timeout)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text))[["Dataset ID", "Title"]]

