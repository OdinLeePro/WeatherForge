# WeatherForge

WeatherForge is a SEIS 745 final project for Minnesota severe-weather analytics. It combines NOAA Storm Events records with NOAA GHCN-Daily weather observations, filters the raw national-scale sources into Minnesota-focused analytics layers, and presents county-level risk, storm impact, weather context, and trend views through a Python Shiny dashboard.

## What The Project Analyzes

- Historical severe-weather events across Minnesota counties and zones.
- Event frequency, direct injuries, direct deaths, property damage, crop damage, and hazard mix.
- Same-day statewide weather context joined to storm events.
- County-level risk scoring and choropleth-style visual summaries.
- Current Minnesota alert context through the National Weather Service API in the app's live-alert view.

## Data Sources

- NOAA Storm Events Database.
- NOAA Global Historical Climatology Network Daily, also known as NOAA GHCN-Daily.
- Minnesota county boundary GeoJSON.
- Minnesota county population data used for per-capita risk normalization.

## Final Data Assets Included

The final app-ready assets are under `data/`:

- `data/storm_events_mn.parquet`: cleaned Minnesota NOAA Storm Events records.
- `data/storm_weather_summary_mn.parquet`: storm events joined to same-day statewide weather averages.
- `data/weather_daily_mn.parquet`: cleaned Minnesota GHCN-Daily station-day observations.
- `data/mn_counties.geojson`: Minnesota county boundaries for map views.
- `data/county_populations.csv`: decennial county population anchors used by the dashboard.

The original raw NOAA source archive was roughly 35 GB in the working project. This submission keeps the curated Minnesota outputs and intentionally excludes the raw national archive.

## How To Run The App

From this folder:

```bash
python -m shiny run --host 127.0.0.1 --port 8000 app.py
```

Then open `http://127.0.0.1:8000`.

The app expects the Parquet, GeoJSON, and population files to remain in the local `data/` folder. The `Live Alerts` tab needs network access to `api.weather.gov`; the historical dashboard views use local files.

## Required Dependencies

Dependencies are listed in `requirements.txt`:

- `shiny`
- `shinywidgets`
- `numpy`
- `pandas`
- `matplotlib`
- `plotly`
- `requests`
- `pyarrow`
- `fastparquet`

## Folder Structure

```text
WeatherForge_Final_Submission/
|-- README.md
|-- requirements.txt
|-- app.py
|-- geo_utils.py
|-- data_dictionary.md
|-- data/
|   |-- storm_events_mn.parquet
|   |-- storm_weather_summary_mn.parquet
|   |-- weather_daily_mn.parquet
|   |-- mn_counties.geojson
|   `-- county_populations.csv
|-- pipeline/
|   |-- README.md
|   |-- filter_mn_storm_events.py
|   |-- convert_mn_to_parquet.py
|   |-- create_storm_weather_summary.py
|   |-- ghcn_dly_to_csv.py
|   |-- batch_convert_dly.sh
|   `-- ghcnd-stations.txt
`-- docs/
    |-- README.md
    |-- project-overview.md
    |-- data-pipeline.md
    |-- dashboard-guide.md
    |-- repository-map.md
    |-- WeatherForge_Final_Project_Writeup.docx
    |-- WeatherForge_LiveFeed_FutureChange.pdf
    |-- WeatherForge_StateChange_Guide.pdf
    `-- additional_context/
```

## Data Pipeline Summary

The preserved pipeline scripts are in `pipeline/`:

- `filter_mn_storm_events.py` reads annual NOAA Storm Events `.csv.gz` files, filters `STATE == "MINNESOTA"`, parses dates, cleans damage fields, and writes `storm_events_mn.parquet`.
- `convert_mn_to_parquet.py` reads GHCN-Daily `.dly` files, uses `ghcnd-stations.txt` to keep Minnesota stations, parses fixed-width daily observations, pivots weather elements into columns, applies unit conversions, and writes `weather_daily_mn.parquet`.
- `create_storm_weather_summary.py` reads the two cleaned Parquet layers, computes daily Minnesota-wide weather averages, joins them to storm events on `BEGIN_DATE`, and writes `storm_weather_summary_mn.parquet`.
- `ghcn_dly_to_csv.py` and `batch_convert_dly.sh` are supporting GHCN-Daily parsing/conversion utilities.

The pipeline scripts were preserved mostly as originally written. Some paths are hardcoded for the old working folder layout, so rebuilds may require placing raw files in the expected locations or adjusting `Path(...)` constants in the scripts.

## Known Limitations

- NOAA pre-1996 Storm Events data is less complete than newer records.
- Older storm records are skewed toward better-monitored and more populated areas.
- The GHCN weather join uses same-day statewide daily averages, not event-specific local station matching.
- Some Storm Events rows are county-compatible and map cleanly; other zone-based records are better suited to statewide summaries.
- The raw source data was roughly 35 GB and was filtered down for this Minnesota-focused final submission.
- The design has partial future support for state switching, but this submitted version is Minnesota-focused.

## Reproducibility Notes

- `pipeline/filter_mn_storm_events.py`, `pipeline/convert_mn_to_parquet.py`, and `pipeline/create_storm_weather_summary.py` document the rebuild path for the three Parquet outputs.
- `pipeline/ghcnd-stations.txt` is included because it is small enough for the submission and is needed to identify Minnesota GHCN stations.
- Raw GHCN `.dly` files and raw annual Storm Events `.csv.gz` files are not included because they are large source inputs.
- The files in `data/` are final curated outputs for the demo and submission package.

## Demo And Submission Notes

Use `app.py` as the dashboard entry point. The most important grading path is: read this README, review `data_dictionary.md`, inspect the preserved pipeline scripts, and run the Shiny app against the included `data/` assets.

No StormIQ-branded deliverables are part of the final submission package. Any older StormIQ materials from the working folders were treated as out-of-scope legacy context and were not copied into the clean final folder.
