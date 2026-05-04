# WeatherForge Project Overview

WeatherForge is a Minnesota-focused severe-weather analytics project for SEIS 745. It uses NOAA Storm Events and NOAA GHCN-Daily data to support county-level risk analysis, storm/weather summaries, dashboard visualization, and final project documentation.

## Core Questions

1. Which Minnesota counties have the highest frequency and severity of severe-weather events?
2. How do same-day weather conditions relate to recorded storm events?
3. Which counties show elevated risk or changing severe-weather patterns over time?

## Final Architecture

1. Raw NOAA sources were downloaded into the working project.
2. Pipeline scripts filtered the data to Minnesota and converted it into Parquet.
3. Curated outputs were packaged under `data/`.
4. `app.py` reads those local outputs and serves the WeatherForge dashboard.

## Included Analytics

- County risk score and impact maps.
- Hazard mix and event frequency summaries.
- Property and crop damage views.
- Direct injury and direct death summaries.
- Same-day weather context using statewide daily averages.
- Time progression and statewide trend views.
- Live Minnesota alerts from the National Weather Service API.

## Scope

This final submission is Minnesota-focused. Some code paths were designed with future state switching in mind, but the included data, county boundaries, population file, and final demo are for Minnesota.
