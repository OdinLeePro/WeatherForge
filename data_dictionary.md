# WeatherForge Data Dictionary

This dictionary describes the final files included in `WeatherForge_Final_Submission/data/`.

## `data/storm_events_mn.parquet`

Cleaned Minnesota slice of NOAA Storm Events records.

- Grain: one row per Minnesota storm event record.
- Rows: 55,384.
- Date range: 1950-06-15 through 2025-12-28.
- Primary use: event counts, hazard mix, damage, injuries, deaths, county/zone summaries, and dashboard filters.

| Column | Type | Description |
|---|---:|---|
| `EVENT_ID` | int64 | NOAA event identifier. |
| `BEGIN_YEARMONTH`, `BEGIN_DAY`, `BEGIN_TIME` | int64 | Event start date/time components from NOAA. |
| `END_YEARMONTH`, `END_DAY`, `END_TIME` | int64 | Event end date/time components from NOAA. |
| `EVENT_TYPE` | string | Hazard category such as hail, tornado, blizzard, thunderstorm wind, etc. |
| `CZ_NAME` | string | County or zone name. |
| `CZ_TYPE` | string | NOAA county/zone type. |
| `CZ_FIPS` | int64 | County or zone FIPS-like code. |
| `BEGIN_LAT`, `BEGIN_LON` | double | Approximate event start location when available. |
| `INJURIES_DIRECT`, `DEATHS_DIRECT` | int64 | Direct human impact counts. |
| `DAMAGE_PROPERTY`, `DAMAGE_CROPS` | double | Cleaned numeric damage estimates in dollars. |
| `MAGNITUDE` | double | Hazard magnitude when reported. |
| `TOR_F_SCALE` | string | Tornado F/EF scale when applicable. |
| `EPISODE_NARRATIVE`, `EVENT_NARRATIVE` | string | NOAA narrative text fields. |
| `BEGIN_DATE` | timestamp | Parsed event start date used for joins and filters. |

## `data/storm_weather_summary_mn.parquet`

Storm Events records enriched with same-day statewide weather averages from the cleaned GHCN-Daily table.

- Grain: one row per storm event, with joined daily weather context.
- Rows: 55,384.
- Date range: 1950-06-15 through 2025-12-28.
- Primary use: Weather Context dashboard views, correlation summaries, and combined storm/weather analysis.

This file contains all columns from `storm_events_mn.parquet`, plus:

| Column | Type | Description |
|---|---:|---|
| `daily_tmax_avg` | double | Mean statewide maximum temperature for the event date, degrees C. |
| `daily_tmin_avg` | double | Mean statewide minimum temperature for the event date, degrees C. |
| `daily_prcp_avg` | double | Mean statewide precipitation for the event date, mm. |
| `daily_snow_avg` | double | Mean statewide snowfall for the event date, mm. |
| `daily_snwd_avg` | double | Mean statewide snow depth for the event date, mm. |
| `daily_awnd_avg` | double | Mean statewide average wind speed for the event date, m/s. |

The weather fields are statewide daily averages. They provide broad context and should not be interpreted as exact local observations at each event location.

## `data/weather_daily_mn.parquet`

Cleaned Minnesota GHCN-Daily weather observations.

- Grain: one row per station per day.
- Rows: 9,008,748.
- Date range: 1877-08-05 through 2026-03-22.
- Primary use: rebuilding daily weather averages, weather context features, and future station-level analysis.

| Column | Type | Description |
|---|---:|---|
| `station_id` | string | GHCN station identifier. |
| `name` | string | Station name. |
| `latitude`, `longitude` | double | Station coordinates. |
| `elevation` | double | Station elevation in meters. |
| `date` | timestamp | Observation date. |
| `tmax` | double | Daily maximum temperature, degrees C. |
| `tmin` | double | Daily minimum temperature, degrees C. |
| `prcp` | double | Daily precipitation, mm. |
| `snow` | double | Daily snowfall, mm. |
| `snwd` | double | Daily snow depth, mm. |
| `awnd` | double | Average wind speed, m/s, when available. |

## `data/mn_counties.geojson`

Minnesota county boundary file used by the dashboard choropleth maps.

- Format: GeoJSON `FeatureCollection`.
- Features: 87 Minnesota counties.
- Primary join key: county FIPS in each feature `id`, with supporting county attributes in `properties`.

## `data/county_populations.csv`

County population anchor table used for per-capita risk normalization.

- Grain: one row per Minnesota county FIPS code.
- Primary key: `fips`.
- Columns: `fips`, `1950`, `1960`, `1970`, `1980`, `1990`, `2000`, `2010`, `2020`.
- Primary use: app-side interpolation/extrapolation of county population by year for risk score normalization.
