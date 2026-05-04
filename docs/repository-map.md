# WeatherForge Repository Map

## Root Files

- `README.md`: main reviewer orientation and run instructions.
- `requirements.txt`: Python dependencies for the app and local data reads.
- `app.py`: WeatherForge Shiny dashboard entry point.
- `geo_utils.py`: schema and county/FIPS helper functions.
- `data_dictionary.md`: field-level descriptions for final packaged data.

## `data/`

Final curated assets used by the app:

- `storm_events_mn.parquet`
- `storm_weather_summary_mn.parquet`
- `weather_daily_mn.parquet`
- `mn_counties.geojson`
- `county_populations.csv`

## `pipeline/`

Reproducibility and lineage scripts:

- `filter_mn_storm_events.py`
- `convert_mn_to_parquet.py`
- `create_storm_weather_summary.py`
- `ghcn_dly_to_csv.py`
- `batch_convert_dly.sh`
- `ghcnd-stations.txt`

## `docs/`

Final writeup, WeatherForge guide PDFs, cleaned documentation, and `additional_context/` material from the source context folder.

## Deliberately Excluded

The clean folder excludes virtual environments, Python caches, `.DS_Store`, zip archives, generated logs/CSV outputs, raw NOAA data folders, and obsolete StormIQ deliverables.
