# WeatherForge: Minnesota Severe Weather Risk Intelligence

WeatherForge is an end-to-end data engineering and interactive analytics pipeline designed to investigate and visualize severe weather risk across Minnesota. The project ingests 35 GB of raw historical weather and storm data, processes it through a custom ETL pipeline, and surfaces insights via a highly optimized Python Shiny dashboard. It emphasizes big data curation, Parquet file optimization, complex dimensional modeling, composite risk scoring, and professional UI/UX design.

## Overview

This project was created to transform massive, highly fragmented NOAA datasets into a clean, enriched, and user-friendly data product suitable for regional risk analysis. The final outputs include highly compressed Parquet data layers, custom geographic utility functions, live API integrations, and a multi-tab interactive dashboard that avoids the cluttered "kitchen sink" approach.

The workflow includes:
- Pulling and curating 76 compressed annual NOAA Storm Events files and extracting raw `.dly` files from the NOAA GHCN-Daily archive.
- Building a data pipeline using Python and Bash to filter, clean, and standardize 75 years of historical data specifically for Minnesota.
- Engineering a "Composite Risk Score" that normalizes storm frequency, property/crop damage, direct injuries, and deaths on a per-capita, annualized basis.
- Constructing multi-level aggregations and joining daily statewide weather averages to specific storm events.
- Developing a frontend Shiny application with interactive Plotly choropleths, time-progression animations, and correlation plots.
- Integrating real-time severe weather alerts via the weather.gov API.
- Authoring scalable architecture documentation for future state-level or live-feed expansions.

## Features

- **Curation Layer Construction** — Generates:
  - Standardized historical datasets with normalized metrics, such as converting tenths of degrees Celsius and tenths of millimeters to standard units.
  - A joined summary table enriching individual storm events with same-day statewide weather observations.
  - A population anchor table used for per-capita risk score normalization, interpolating census data from 1950 to 2020.

- **Data Engineering & ETL Pipeline** — Adds:
  - Automated Bash scripting to iterate through massive `.dly` directories.
  - Fast, column-oriented Parquet data structures reducing a 35 GB raw footprint into highly optimized, localized assets.
  - Automated geographic standardization handling FIPS code normalizations across disparate datasets.

- **Interactive Analytics Dashboard** — Produces:
  - **Risk Map & KPIs:** Executive landing page highlighting the most dangerous counties instantly using a 0–100 scaled composite risk score.
  - **County Impacts:** Deep-dive views contrasting property vs. crop damage and volume vs. severity bubble charts.
  - **Weather Context:** Spatial mapping and Pearson correlation analysis identifying the atmospheric drivers (e.g., precipitation, temperature) most closely associated with storm frequency.
  - **Time Progression:** Animated heatmaps and diversity charts revealing how technological improvements in NOAA's data collection (post-1996) impacted historical tracking.
  - **Statewide Trends:** Decadal hazard composition tracking and annual risk seasonality heatmaps.

## Project Structure

```text
/WeatherForge
├── Data/
│   ├── county_populations.csv
│   ├── mn_counties.geojson
│   ├── storm_events_mn.parquet
│   ├── storm_weather_summary_mn.parquet
│   └── weather_daily_mn.parquet
├── DataPreprocessing/
│   ├── batch_convert_dly.sh
│   ├── convert_mn_to_parquet.py
│   ├── create_storm_weather_summary.py
│   ├── filter_mn_storm_events.py
│   ├── ghcn_dly_to_csv.py
│   └── ghcnd-stations.txt
├── Documents/
│   ├── WeatherForge_Demo.gif
│   ├── WeatherForge_LiveFeed_FutureChange.pdf
│   └── WeatherForge_StateChange_Guide.pdf
├── .gitignore
├── LICENSE
├── README.md
├── app.py
├── geo_utils.py
└── requirements.txt
```

## Data Sources

This project utilizes multi-source climate and geographic data spanning historical records and real-time alerts. The data includes:
- **NOAA GHCN-Daily Archive:** Station-based daily weather observations (temperature, precipitation, snowfall, wind).
- **NOAA Storm Events Database:** Event-level records detailing hazard types, locations, financial damage, and human impact.
- **U.S. Census Bureau:** Decennial county population counts used to dynamically calculate per-10,000-resident risk exposure.
- **National Weather Service API:** Live, real-time severe weather alert JSON feeds.
- **Plotly Datasets:** Standardized GeoJSON boundaries for accurate county-level choropleth mapping.

## Key Outputs

### 1. Curated Parquet Data Models
Analytics-ready, highly compressed datasets including:
- **`storm_events_mn.parquet`**: Cleaned, Minnesota-filtered event records.
- **`weather_daily_mn.parquet`**: Cleaned GHCN-Daily weather observations.
- **`storm_weather_summary_mn.parquet`**: Storm records enriched with same-day statewide weather context.

### 2. Composite Risk Engine
A custom algorithm that calculates regional danger by weighting storm frequency, financial impact (square-root scaled), direct injuries, and direct deaths.

*Note: Scores are annualized, per-capita normalized, and dynamically scaled 0–100 based on the user's active filter window.*

### 3. WeatherForge Dashboard
A modular, multi-tab Python Shiny application featuring responsive UI/UX, dynamic text summaries that update based on user filters, and deeply interactive Plotly visualizations.

### 4. Expansion Documentation
Detailed PDF guides providing technical roadmaps for adapting the current architecture to track different states or shifting to an automated, real-time data ingestion pipeline.

## Pipeline Execution (How to Run)

To replicate this data pipeline or run the dashboard locally, execute the following steps in order:

**1. Parse Raw Weather Data**
- **File**: `pipeline/batch_convert_dly.sh` (executes `ghcn_dly_to_csv.py`)
- **Action**: Iterates through the raw GHCN-Daily directory to extract and flatten `.dly` files into standard CSV format.

**2. Filter Storm Events**
- **File**: `pipeline/filter_mn_storm_events.py`
- **Action**: Reads the bulk NOAA Storm Events files and isolates records specific to Minnesota.

**3. Convert Weather to Parquet**
- **File**: `pipeline/convert_mn_to_parquet.py`
- **Action**: Ingests the parsed daily weather CSVs, applies unit conversions, and exports the highly compressed `weather_daily_mn.parquet` layer.

**4. Build the Enriched Summary**
- **File**: `pipeline/create_storm_weather_summary.py`
- **Action**: Joins cleaned storm events with daily weather averages to create the final analysis table.

**5. Launch the Dashboard**
- **File**: `app.py`
- **Action**: Run the Shiny application using `shiny run app.py` (ensure `requirements.txt` dependencies are installed).

## License

This project is licensed under the MIT License.
