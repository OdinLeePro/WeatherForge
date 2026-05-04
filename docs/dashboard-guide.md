# WeatherForge Dashboard Guide

The dashboard entry point is `app.py`; shared helper functions live in `geo_utils.py`. The app reads its local data from `data/`.

## Main Views

- Overview: statewide KPIs, risk map, hazard mix, county ranking, and summary insight text.
- County Impacts: county choropleth, leaderboard, county profile, and hazard breakdown.
- Weather Context: storm/weather summary views using the joined Parquet layer.
- Time Progression: animated county-level changes over time.
- Statewide Trends: longer-term trend, damage timing, and seasonality views.
- Methods and Pipeline: dashboard-facing explanation of data preparation and interpretation limits.
- Live Alerts: active Minnesota weather alerts from `api.weather.gov`.

## Risk Score

The app computes a heuristic score from event count, damage, injuries, deaths, year range, and county population. It is useful for comparison and prioritization inside the dashboard, but it is not a formal actuarial or forecasting model.

## Mapping Rules

County maps use Minnesota county FIPS values and `data/mn_counties.geojson`. Rows that cannot be matched to valid county geometry are better interpreted in statewide summaries than in county choropleths.

## Startup

Run from `WeatherForge_Final_Submission/`:

```bash
python -m shiny run --host 127.0.0.1 --port 8000 app.py
```

Historical views use local Parquet files. The live-alert view requires network access.
