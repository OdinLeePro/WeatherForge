# WeatherForge: Minnesota Severe Weather Risk Intelligence

This repository contains a SEIS 745 final project focused on building a practical weather-data pipeline and analytics application for Minnesota. The project combines NOAA Storm Events records with NOAA GHCN-Daily weather observations, reshapes them into analysis-friendly Parquet datasets, and serves an interactive Shiny dashboard for exploring severe-weather risk across counties and over time.

## What Is In This Project

- A large local data workspace built from NOAA historical weather and storm-event files
- Python scripts that clean and convert raw data into Minnesota-specific Parquet tables
- An interactive Shiny dashboard in `data/linexandspectrogramprograms/processed/app.py`
- Supporting legacy conversion utilities for `.dly` and older IDL plotting workflows
- Proposal and rubric documents for the course deliverable

## Main Deliverables

- `weather_daily_mn.parquet`
  Minnesota GHCN-Daily weather observations with 9,008,748 station-day rows spanning 1877-08-05 through 2026-03-22
- `storm_events_mn.parquet`
  Minnesota NOAA Storm Events records with 55,384 rows spanning 1950-06-15 through 2025-12-28
- `storm_weather_summary_mn.parquet`
  A joined analytics table that attaches daily statewide weather averages to each storm event
- `WeatherForge`
  A Shiny dashboard with overview, county impact, weather context, time progression, statewide trend, methods, and live-alert views

## Tech Stack

### Frontend

- Python Shiny UI components for the application layout, tabs, filters, value boxes, and interactive controls
- Plotly for charts, choropleths, animations, and other interactive visualizations
- `shinywidgets` and `ipywidgets` for widget-backed Plotly rendering inside the Shiny app
- Custom inline HTML and CSS for app-specific styling, insight panels, and pipeline visuals
- Bootstrap and bundled frontend libraries that ship with Shiny for the base browser UI layer

### Backend

- Python as the application runtime
- Shiny for Python as the web application framework
- Uvicorn as the local ASGI server used when the app is launched with `shiny run`
- Local module-based app architecture with `app.py` as the entrypoint and `geo_utils.py` for schema and geography helpers

### Data And Analytics

- Pandas for filtering, aggregation, reshaping, joins, and general tabular analysis
- NumPy for numerical calculations such as risk scoring, correlations, and trend classification support
- Parquet as the primary analytics storage format
- PyArrow for Parquet read support in the local environment
- GeoJSON for Minnesota county boundary geometry used in choropleth maps
- NOAA Storm Events and NOAA GHCN-Daily as the core analytical datasets

### External Integrations

- National Weather Service `api.weather.gov` for live Minnesota alerts in the app's `Live Alerts` tab
- Plotly county GeoJSON source as a fallback only when the local Minnesota county GeoJSON file is not available

## Data Sources

- NOAA Storm Events Database
- NOAA Global Historical Climatology Network Daily (`ghcnd_all.tar.gz`)
- National Weather Service live alert feed from `api.weather.gov` for the dashboard's live-alert tab

## Project Scale

- Entire workspace size: about 35 GB
- Extracted `ghcnd_all` directory: about 31 GB
- `storm_events_raw`: about 296 MB across 76 compressed annual files
- Minnesota station IDs referenced in `ghcnd-stations.txt`: 2,675
- Extracted `.dly` files present in `data/ghcnd_all/ghcnd_all`: 129,591

## Quick Start

The runnable application lives under `data/linexandspectrogramprograms/processed`.

```bash
cd "data/linexandspectrogramprograms/processed"
../.venv/bin/python -m shiny run --host 127.0.0.1 --port 8000 app.py
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

Notes:

- The historical analytics tabs run from local Parquet files already included in the workspace.
- The `Live Alerts` tab makes a network request to `api.weather.gov`; if the network is unavailable, only that tab is affected.
- The local `requirements.txt` covers part of the scientific stack, but the dashboard also uses `shiny`, `shinywidgets`, `plotly`, `requests`, and Parquet support.

## Rebuilding The Data Products

The pipeline scripts are under `data/linexandspectrogramprograms/` and are intended to be run from that directory:

```bash
cd "data/linexandspectrogramprograms"
./.venv/bin/python filter_mn_storm_events.py
./.venv/bin/python convert_mn_to_parquet.py
./.venv/bin/python create_storm_weather_summary.py
```

This produces the three main Parquet files inside `data/linexandspectrogramprograms/processed/`.

## Repository Layout

```text
.
|-- README.md
|-- docs/
|-- Data Lake Engineering Project Proposal.docx
|-- Data Lake Engineering Project Proposal.pdf
|-- Project Requirements & Rubric.docx
`-- data/
    |-- ghcnd_all.tar.gz
    |-- ghcnd_all/
    |   `-- ghcnd_all/              # extracted NOAA .dly files
    `-- linexandspectrogramprograms/
        |-- .venv/
        |-- filter_mn_storm_events.py
        |-- convert_mn_to_parquet.py
        |-- create_storm_weather_summary.py
        |-- ghcn_dly_to_csv.py
        |-- rbsp_tools.py
        |-- storm_events_raw/
        |-- outputs/
        |-- logs/
        `-- processed/
            |-- app.py
            |-- geo_utils.py
            |-- mn_counties.geojson
            |-- storm_events_mn.parquet
            |-- storm_weather_summary_mn.parquet
            |-- weather_daily_mn.parquet
            `-- old/
```

## Documentation

- [Documentation Index](docs/README.md)
- [Project Overview](docs/project-overview.md)
- [Data Pipeline](docs/data-pipeline.md)
- [Dashboard Guide](docs/dashboard-guide.md)
- [Repository Map](docs/repository-map.md)

## Important Context

- The implemented analytics layer is local Python and Pandas over Parquet files. The workspace is structured in a way that could move into Spark later, but Spark notebooks or jobs are not present here.
- The dashboard intentionally separates county-safe mapped views from statewide summaries. Not every Storm Events row can be drawn honestly as a Minnesota county polygon.
- This repository includes intermediate outputs, archives, and a checked-in virtual environment, so it behaves more like a working project folder than a minimal source-only repo.
