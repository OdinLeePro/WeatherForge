# WeatherForge Pipeline Notes

These scripts were preserved from the old working project to document how the final Parquet files can be rebuilt.

## Main Rebuild Order

Run from `pipeline/` after placing the large raw inputs in the expected locations or updating the hardcoded paths inside the scripts:

```bash
python filter_mn_storm_events.py
python convert_mn_to_parquet.py
python create_storm_weather_summary.py
```

## Scripts

- `filter_mn_storm_events.py`: filters raw annual NOAA Storm Events `.csv.gz` files to Minnesota and writes `processed/storm_events_mn.parquet`.
- `convert_mn_to_parquet.py`: filters GHCN-Daily station files to Minnesota stations using `ghcnd-stations.txt`, converts selected weather elements, and writes `processed/weather_daily_mn.parquet`.
- `create_storm_weather_summary.py`: joins cleaned storm events to daily statewide weather averages and writes `processed/storm_weather_summary_mn.parquet`.
- `ghcn_dly_to_csv.py`: utility parser for a single GHCN-Daily `.dly` file.
- `batch_convert_dly.sh`: supporting batch conversion helper for `.dly` files.
- `ghcnd-stations.txt`: NOAA station metadata used to identify Minnesota stations.

## Input Notes

The raw source files are intentionally not included in this final submission because the original working data was roughly 35 GB. The scripts still show the intended lineage, but their `Path(...)` values may need adjustment before rerunning them outside the original working folder.
