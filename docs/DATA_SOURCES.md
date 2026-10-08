# Data sources and attribution

| source | what | access | licence / credit line |
|---|---|---|---|
| Ocean Networks Canada, Oceans 3.0 | NEPTUNE BPRs, CORK seafloor gauges, CTDs | `data.oceannetworks.ca/api` (token) | CC BY 4.0. "Data: Ocean Networks Canada, Oceans 3.0 (data.oceannetworks.ca)" |
| Fisheries and Oceans Canada, CHS IWLS | BC tide gauges, air pressure `ap1` | `api-iwls.dfo-mpo.gc.ca` | Open Government Licence – Canada. "Contains information licensed under the Open Government Licence – Canada" |
| NOAA CO-OPS | US tide gauges, `air_pressure` | `api.tidesandcurrents.noaa.gov` | US public domain; credit NOAA CO-OPS |
| IOC Sea Level Station Monitoring Facility | Mexican and Central American gauges | `ioc-sealevelmonitoring.org` | Real-time, not quality-controlled; credit IOC/VLIZ and the station operators |
| UHSLC fast delivery | Acajutla, La Jolla, backfill | UHSLC ERDDAP `global_hourly_fast` | Credit University of Hawaii Sea Level Center |
| ECCC via CIOOS Pacific / MSC GeoMet | buoys, hourly climate stations (air pressure) | CIOOS ERDDAP `ECCC_MSC_BUOYS`; `api.weather.gc.ca` | Open Government Licence – Canada |
| NOAA NDBC | US buoys (wind) | `ndbc.noaa.gov` stdmet | public domain |
| Copernicus ERA5 | msl, 10 m wind | CDS API (token) | "Contains modified Copernicus Climate Change Service information [year]" |
| NOAA CPC | ONI / Niño 3.4 | `cpc.ncep.noaa.gov` | public domain |

Station list with ids and coordinates: `config/stations.yaml`. Coordinates were taken
from the ONC locations API, the CHS IWLS metadata endpoint and the NOAA CO-OPS metadata
API on 2026-10-07; the coastal-path waypoints are approximate and need checking.

Excluded and why:

- CQS64 / CORK-1364A: the "Seafloor Pressure" stream is a 156 mbsf borehole screen.
- CDFM: no data in 2026. NC27 / CORK-1026 seafloor gauge stopped 2026-07-14.
- La Paz: inside the Gulf of California, off the open-coast path.
- Champerico (`prch`): failed QC in 2026; kept in config with `enabled: false`.
- BCUS vertical profiler (BACVP): no data after 20 May 2026.
