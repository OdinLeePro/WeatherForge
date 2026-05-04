# WeatherForge Data Pipeline

The pipeline reduces large national NOAA sources into compact Minnesota-focused Parquet assets used by the dashboard.

## Source Inputs

- NOAA Storm Events annual `StormEvents_details-ftp_v1.0_dYYYY_*.csv.gz` files.
- NOAA GHCN-Daily `.dly` station files.
- `pipeline/ghcnd-stations.txt` station metadata.
- Minnesota county boundary GeoJSON.
- County population anchors for risk normalization.

Raw GHCN-Daily and raw Storm Events files are not included in this final folder because the original working data was roughly 35 GB.

## Main Scripts

### `pipeline/filter_mn_storm_events.py`

Filters raw annual Storm Events files to `STATE == "MINNESOTA"`, keeps event/geography/impact/narrative fields, parses `BEGIN_DATE`, cleans property and crop damage values, and writes `processed/storm_events_mn.parquet` in the original working layout.

### `pipeline/convert_mn_to_parquet.py`

Uses `ghcnd-stations.txt` to identify Minnesota GHCN stations, parses fixed-width `.dly` records, keeps `TMAX`, `TMIN`, `PRCP`, `SNOW`, `SNWD`, and `AWND`, converts units, merges station metadata, and writes `processed/weather_daily_mn.parquet` in the original working layout.

### `pipeline/create_storm_weather_summary.py`

Loads the cleaned weather and storm Parquet files, computes daily statewide weather averages, joins those averages to storm events on `BEGIN_DATE`, and writes `processed/storm_weather_summary_mn.parquet` in the original working layout.

## Final Packaged Outputs

- `data/storm_events_mn.parquet`
- `data/weather_daily_mn.parquet`
- `data/storm_weather_summary_mn.parquet`
- `data/mn_counties.geojson`
- `data/county_populations.csv`

## Rebuild Caveat

The scripts are preserved for lineage and reproducibility, but several paths still reflect the old working project structure. Before rerunning them in a fresh environment, update input/output `Path(...)` values or recreate the expected raw-data layout.
