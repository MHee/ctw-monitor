# Data contract (schema_version 0.2.0)

Everything the web app reads lives under `data/` on the site. Every file validates
against a JSON Schema in `schema/`; CI validates the synthetic set and each nightly
build validates before deploying.

| file | schema | content |
|---|---|---|
| `manifest.json` | `manifest.schema.json` | build time, pipeline version, `synthetic` flag, per-source status, file list |
| `stations.json` | `stations.schema.json` | station metadata incl. along-coast distance |
| `sealevel.json` | `timeseries.schema.json` | gauge anomalies, cm |
| `hovmoller.json` | `grid.schema.json` | distance–time grid of sea-level anomaly, cm |
| `bottom_pressure.json` | `timeseries.schema.json` | basin-referenced BPR anomalies, cm of water |
| `temperature.json` | `timeseries.schema.json` | temperature anomalies, °C |
| `events.json` | `events.schema.json` | detected extrema and along-coast speed fits |

## Conventions

- Times are ISO 8601 UTC with `Z`. Regular series are `t0` + `dt_s` + `n`, not an
  array of timestamps.
- Missing values are `null`. Values are rounded (cm to 0.1, °C to 0.001).
- `values` is an object keyed by station id; every array has length `n`.
- `processing` is a one-line human-readable description shown under each panel.
- Per-station `meta` records what was done to that series (for example
  `ib_source: "station" | "eccc" | "era5" | "none"`).
- Bump `schema_version` (semver) on any change; the web app refuses a major version it
  does not know and shows the banner "data format changed".

## Example (`sealevel.json`, abridged)

```json
{
  "schema_version": "0.2.0",
  "product": "sealevel_anomaly",
  "units": "cm",
  "processing": "Despiked, detided (frozen constants), IB-corrected, Godin low-pass, minus 2013–2025 day-of-year mean; 6-hourly",
  "t0": "2025-09-01T00:00:00Z",
  "dt_s": 21600,
  "n": 1600,
  "stations": ["acajutla", "puerto_vallarta", "...", "prince_rupert"],
  "values": {"neah_bay": [1.2, 1.4, null, 1.9]},
  "meta": {"neah_bay": {"ib_source": "station", "last_valid": "2026-10-06T18:00:00Z"}}
}
```

`stations.json` also carries `coastal_path`: the waypoints (name, lat, lon,
`alongshore_km`) that define the along-coast distance, so the map draws the same path.
0.2.0 added it.

`hovmoller.json` holds `distance_km` (grid centres, poleward positive, 0 at Neah Bay),
`t0`/`dt_s`/`n`, and `values` as a flat row-major array of length `n × len(distance_km)`
(time is the slow axis), plus `mask_km` listing gaps with no gauge within 150 km
(for example the Baja California gap) so the heatmap can hatch them rather than
interpolate across them.
