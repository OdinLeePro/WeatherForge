# ═══════════════════════════════════════════════════════════════════════════════
# IMPORTS
# Standard library → third-party packages → local geo utility helpers.
# All imports are at the top level; nothing is imported inside functions.
# ═══════════════════════════════════════════════════════════════════════════════

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from shiny import App, reactive, render, ui
from shinywidgets import output_widget, render_widget

from geo_utils import (
    get_begin_date_column,
    get_damage_crops_column,
    get_damage_property_column,
    get_deaths_column,
    get_event_id_column,
    get_event_type_column,
    get_geo_fips_column,
    get_geo_group_column,
    get_injuries_column,
    get_max_temperature_column,
    get_precipitation_column,
    get_snow_depth_column,
    get_snowfall_column,
    get_wind_speed_column,
    normalize_dataframe_columns,
    resolve_column,
    to_county_fips,
    filter_summary_for_storms,
)

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# ═══════════════════════════════════════════════════════════════════════════════
# STYLING & BRAND CONFIGURATION
# Plotly theme defaults, brand color palette, and shared axis/font styles
# applied consistently across every chart in the dashboard.
#
# To change the visual identity of all charts at once, edit BRAND_PALETTE,
# _CHART_FONT, or _AXIS_STYLE here — do not hardcode colors in chart builders.
# ═══════════════════════════════════════════════════════════════════════════════

px.defaults.template = "plotly_white"

# ═══════════════════════════════════════════════════════════════════════════════
# STATE CONFIGURATION
# This final submission is Minnesota-focused. These values are isolated to make
# future state adaptation easier, but a real state change also requires swapping
# the bundled data, county boundaries, and population inputs.
#   state_name        – full state name used in UI text
#   state_abbr        – two-letter abbreviation used in the NWS alerts API
#   state_fips_prefix – two-digit state FIPS code used to normalise county FIPS
# ═══════════════════════════════════════════════════════════════════════════════
STATE_CONFIG: dict[str, str] = {
    "state_name":        "Minnesota",
    "state_abbr":        "MN",
    "state_fips_prefix": "27",
}


# ── Brand palette applied consistently across all charts ──────────────────────
BRAND_PALETTE = [
    "#0d6efd",  # Blue (primary)
    "#e63946",  # Red
    "#2a9d8f",  # Teal
    "#f4a261",  # Orange
    "#7b2d8b",  # Purple
    "#06d6a0",  # Mint
    "#ef476f",  # Rose
    "#118ab2",  # Sky
]
px.defaults.color_discrete_sequence = BRAND_PALETTE
_CHART_FONT = {"family": "system-ui, -apple-system, 'Segoe UI', sans-serif", "color": "#212529"}
_AXIS_STYLE = {"gridcolor": "#f0f0f2", "linecolor": "#e9ecef", "tickfont": {"color": "#6c757d", "size": 11}}

# ═══════════════════════════════════════════════════════════════════════════════
# APP-LEVEL CONSTANTS & METRIC DEFINITIONS
#
# FILE PATHS
#   DATA_DIR               – local data directory under the app root
#   COUNTY_GEOJSON_PATH    – local GeoJSON cache; fetched from Plotly CDN if absent
#
# SENTINEL VALUES
#   ALL_HAZARDS            – the "no filter" option label used in every dropdown
#   HAZARD_DISPLAY_COLUMN  – synthetic column name added to both DataFrames
#
# METRIC DICTIONARIES  (used to populate UI dropdowns)
#   COUNTY_METRIC_CHOICES  – metrics available on the County Impacts map
#   SPATIAL_METRIC_CHOICES – metrics available on the Weather Context map
#   ANIMATION_METRIC_CHOICES – metrics available on the Time Progression map
#   METRIC_META            – label, colorscale, and number-format per metric key
#
# TREND / CORRELATION TUNING
#   TREND_LOOKBACK_FRAMES  – how many recent frames the slope classifier uses
#   TREND_MIN_FRAMES       – minimum frames required before classifying a trend
#   TREND_SLOPE_THRESHOLD  – normalized slope boundary: > +X → Increasing, < -X → Decreasing
#   CORRELATION_MIN_POINTS – minimum county-period pairs required for a Pearson r value
# ═══════════════════════════════════════════════════════════════════════════════

DATA_DIR = Path(__file__).resolve().parent / "data"
COUNTY_GEOJSON_PATH = DATA_DIR / "mn_counties.geojson"  # swap this file when redeploying for a new state
ALL_HAZARDS = "All hazards"
HAZARD_DISPLAY_COLUMN = "__hazard_display"
COUNTY_SCOPE_NOTE = f'County-compatible {STATE_CONFIG["state_name"]} county FIPS only'
STATEWIDE_SCOPE_NOTE = "All filtered statewide records"
TREND_LOOKBACK_FRAMES = 15
TREND_MIN_FRAMES = 8
TREND_SLOPE_THRESHOLD = 0.03
CORRELATION_MIN_POINTS = 24

COUNTY_METRIC_CHOICES = {
    "risk_score": "Risk Score (0–100)",
    "event_count": "Storm Event",
    "property_damage": "Property Damage",
    "crop_damage": "Crop Damage",
    "total_damage": "Total Damage",
    "injuries_direct": "Direct Injuries",
    "deaths_direct": "Direct Deaths",
}

SPATIAL_METRIC_CHOICES = {
    "event_count": "Storm Event",
    "avg_precip": "Precipitation",
    "avg_snow": "Snowfall",
    "avg_wind": "Wind Speed",
    "avg_tmax": "Max Temperature",
    "avg_tmin": "Min Temperature",
}

ANIMATION_METRIC_CHOICES = {
    "event_count": "Storm Event",
    "risk_score": "Risk Score (0–100)",
    "property_damage": "Property Damage",
    "injuries_direct": "Direct Injuries",
}

METRIC_META = {
    "risk_score":      {"label": "Risk Score (0–100)", "colorscale": "Reds",    "format": "score"},
    "event_count": {"label": "Storm Event", "colorscale": "OrRd", "format": "count"},
    "property_damage": {"label": "Property Damage ($)", "colorscale": "Reds",    "format": "currency"},
    "injuries_direct": {"label": "Direct Injuries", "colorscale": "Magma", "format": "count"},
    "deaths_direct": {"label": "Direct Deaths", "colorscale": "Purples", "format": "count"},
    "avg_precip":      {"label": "Precipitation (mm)", "colorscale": "Blues",   "format": "float1"},
    "avg_tmax":        {"label": "Max Temp (°C)",      "colorscale": "YlOrRd",  "format": "float1"},
    "avg_tmin":        {"label": "Min Temp (°C)",      "colorscale": "Blues_r", "format": "float1"},
    "avg_wind":        {"label": "Wind Speed (m/s)",   "colorscale": "Viridis", "format": "float2"},
    "avg_snow":        {"label": "Snowfall (mm)",      "colorscale": "PuBu",    "format": "float1"},
    "crop_damage": {"label": "Crop Damage", "colorscale": "YlOrBr", "format": "currency"},
    "total_damage": {"label": "Total Damage", "colorscale": "Reds", "format": "currency"},
}

# Single-hue blue gradient used for all county choropleth maps.
# Anchored to the site's brand blue (#0d6efd) so the map reads as part of
# the same visual language as the cards, tabs, and accent lines.
COUNTY_MAP_COLORSCALE = [
    [0.0, "#e8f2ff"],  # near-white blue (low values)
    [0.3, "#93c5fd"],  # light blue
    [0.6, "#3b82f6"],  # medium blue
    [1.0, "#0d6efd"],  # brand blue (high values)
]

# ── Risk Score formula ─────────────────────────────────────────────────────────
# Single source of truth used by aggregate_county_metrics, build_animation_dataset,
# and the KPI box. Change weights here and all 3 sites update automatically.
#
#   events × 2              frequency signal
#   sqrt(damage/$1M) × 30   financial impact — sqrt-scaled so one catastrophic
#                           event doesn't erase all other signals
#                           e.g. $10M → 95 pts,  $1B → 949 pts
#   injuries × 8            human cost
#   deaths × 80             10× injury weight — fatalities are the worst outcome
#
# After compute_risk_score() the pipeline in aggregate_county_metrics applies:
#   ÷ years_in_window       → annualized (comparable across time filters)
#   ÷ avg_population×10k    → per 10,000 residents (comparable across counties)
#   ÷ dynamic_ceiling×100   → 0–100 scale (ceiling = 99th pct of current window)
#
# KPI thresholds (0–100 scale, annualized statewide):
#   Green  < 25  →  calm / below-average
#   Yellow < 60  →  active / above-average
#   Red   >= 60  →  severe
# ──────────────────────────────────────────────────────────────────────────────
RISK_SCORE_THRESHOLDS = (25, 60)   # (green→yellow, yellow→red) on 0–100 scale


def compute_risk_score(event_count, total_damage_dollars, injuries, deaths):
    """Composite risk score. Vectorised-safe: accepts scalars or pandas Series.

    Raw output is then annualized, per-capita normalized, and scaled 0–100
    by the calling aggregation function — do not compare raw values directly.

    At a "bad but not catastrophic" county-year (50 events, $50M, 10 injuries, 1 death):
      events 100 | damage 212 | injuries 80 | deaths 80  → total 472 pts
    """
    damage_m    = total_damage_dollars / 1_000_000
    sqrt_damage = np.sqrt(np.maximum(damage_m, 0))
    return (
        event_count * 2
        + sqrt_damage * 30
        + injuries * 8
        + deaths * 80
    )


# ── Census populations by county FIPS, loaded from county_populations.csv ────
# Columns: fips, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020
# Swap this file when redeploying for a new state (or use a national file).
# Source: U.S. Census Bureau decennial census, 8 anchor years per county.
# Values are interpolated/extrapolated by get_county_population() for any year.
# Used to normalise the risk score to per-10,000-residents so that high-
# population counties don't automatically dominate the rankings.
# ──────────────────────────────────────────────────────────────────────────────
_POPULATION_FILE = DATA_DIR / "county_populations.csv"

def _load_county_populations() -> dict[str, dict[int, int]]:
    """Load county populations from CSV into the same dict structure the
    interpolation logic expects: {fips_str: {year_int: population_int}}.

    Only rows whose FIPS code starts with STATE_CONFIG["state_fips_prefix"]
    are loaded, so a single national CSV works for any state deployment.
    """
    if not _POPULATION_FILE.exists():
        logger.warning("county_populations.csv not found — per-capita risk scores will use neutral denominator.")
        return {}
    import csv as _csv
    prefix = STATE_CONFIG["state_fips_prefix"]
    populations: dict[str, dict[int, int]] = {}
    with open(_POPULATION_FILE, newline="") as f:
        reader = _csv.DictReader(f)
        for row in reader:
            fips = str(row["fips"]).zfill(5)
            if not fips.startswith(prefix):
                continue
            populations[fips] = {
                int(yr): int(row[yr])
                for yr in reader.fieldnames
                if yr != "fips" and row[yr] not in ("", None)
            }
    return populations

COUNTY_POPULATIONS: dict[str, dict[int, int]] = _load_county_populations()

_CENSUS_YEARS = sorted({yr for d in COUNTY_POPULATIONS.values() for yr in d})


def get_county_population(fips: str, year: int) -> float:
    """Return an estimated population for a county in a given year.

    Strategy:
      • Exact census year  → return as-is
      • Between 1990–2020  → linear interpolation between surrounding decades
      • Before 1990        → linear extrapolation using the 1990→2000 slope
      • After 2020         → linear extrapolation using the 2010→2020 slope
      • Unknown FIPS       → return 10,000 (neutral denominator, no distortion)
    """
    data = COUNTY_POPULATIONS.get(str(fips).zfill(5))
    if data is None:
        return 10_000.0

    if year in data:
        return float(data[year])

    years = sorted(data.keys())

    # Extrapolate before first census year
    if year < years[0]:
        y0, y1 = years[0], years[1]
        slope = (data[y1] - data[y0]) / (y1 - y0)
        return max(1.0, data[y0] + slope * (year - y0))

    # Extrapolate after last census year
    if year > years[-1]:
        y0, y1 = years[-2], years[-1]
        slope = (data[y1] - data[y0]) / (y1 - y0)
        return max(1.0, data[y1] + slope * (year - y1))

    # Interpolate between two surrounding census years
    for i in range(len(years) - 1):
        y0, y1 = years[i], years[i + 1]
        if y0 <= year <= y1:
            t = (year - y0) / (y1 - y0)
            return max(1.0, data[y0] + t * (data[y1] - data[y0]))

    return float(data[years[-1]])  # fallback


def get_avg_population_for_range(fips: str, start_year: int, end_year: int) -> float:
    """Average population across a year range — used to normalise multi-year aggregations."""
    years = range(start_year, end_year + 1)
    return sum(get_county_population(fips, y) for y in years) / max(len(years), 1)


# Forward declaration — replaced by _compute_risk_ceiling() after data loads
RISK_SCORE_CEILING: float = 1_000.0


def _compute_risk_ceiling() -> float:
    """99th-percentile per-capita risk score computed from the storms dataset —
    the same source that drives damage/injuries/deaths in the displayed scores.
    Groups by county across the full dataset so the ceiling matches the same
    temporal aggregate scale as the map."""
    try:
        # Use storms (not summary) — summary_to_use() overwrites damage/injuries/deaths
        # with values from storms, so this is the correct source for the ceiling
        mapped = prepare_county_dataset(storms)
        if mapped.empty:
            return 1_000.0

        count_src  = get_event_id_column(mapped) or "FIPS"
        prop_col   = get_damage_property_column(mapped)
        crop_col   = get_damage_crops_column(mapped)
        inj_col    = get_injuries_column(mapped)
        dth_col    = get_deaths_column(mapped)

        is_sig = pd.Series(False, index=mapped.index)
        if prop_col is not None: is_sig = is_sig | (mapped[prop_col].fillna(0) > 0)
        if crop_col is not None: is_sig = is_sig | (mapped[crop_col].fillna(0) > 0)
        if inj_col is not None:  is_sig = is_sig | (mapped[inj_col].fillna(0) > 0)
        if dth_col is not None:  is_sig = is_sig | (mapped[dth_col].fillna(0) > 0)
        mapped['is_significant'] = is_sig.astype(int)

        agg = {"event_count": ("is_significant", "sum")}
        if prop_col: agg["property_damage"] = (prop_col, "sum")
        if crop_col: agg["crop_damage"]     = (crop_col, "sum")
        if inj_col:  agg["injuries_direct"] = (inj_col,  "sum")
        if dth_col:  agg["deaths_direct"]   = (dth_col,  "sum")

        # Group by county only — same as aggregate_county_metrics
        cy = mapped.groupby("FIPS", dropna=False).agg(**agg).reset_index()
        for col in ("property_damage", "crop_damage", "injuries_direct", "deaths_direct"):
            if col not in cy.columns:
                cy[col] = 0.0
        cy["total_damage"] = cy["property_damage"] + cy["crop_damage"]

        # Annualize over the actual data span — derived from the storms dataset
        # rather than hardcoded, so this stays correct if the data is ever updated
        date_col = get_begin_date_column(mapped)
        if date_col is not None:
            years = pd.to_datetime(mapped[date_col], errors="coerce").dt.year.dropna()
            data_min_year = int(years.min())
            data_max_year = int(years.max())
            data_span = max(data_max_year - data_min_year + 1, 1)
        else:
            data_min_year, data_max_year, data_span = 1950, 2025, 75

        # Use the same year range for population lookup so ceiling and displayed
        # scores use a consistent denominator
        cy["avg_population"] = cy["FIPS"].apply(
            lambda f: get_avg_population_for_range(str(f), data_min_year, data_max_year)
        ).clip(lower=1)

        cy["raw"] = compute_risk_score(
            cy["event_count"], cy["total_damage"],
            cy["injuries_direct"], cy["deaths_direct"],
        )
        cy["annualized"] = cy["raw"] / data_span
        cy["per_capita"] = cy["annualized"] / cy["avg_population"] * 10_000

        ceiling = float(cy["per_capita"].quantile(0.99))
        logger.info(
            "Risk ceiling from storms dataset — "
            "min=%.1f  median=%.1f  99pct=%.1f  max=%.1f",
            cy["per_capita"].min(), cy["per_capita"].median(),
            ceiling, cy["per_capita"].max(),
        )
        return max(ceiling, 1.0)
    except Exception as exc:
        logger.warning("Could not compute risk ceiling: %s", exc)
        return 1_000.0


def compute_dynamic_ceiling(df: pd.DataFrame, start_year: int, end_year: int) -> float:
    """Compute the 99th-percentile per-capita annualized risk score from the
    currently filtered data.  Called reactively so the ceiling always matches
    the selected time window — a 2000-2025 filter is normalised against
    2000-2025 data, not the full 1950-2025 history.

    Returns the static RISK_SCORE_CEILING as a fallback if the data is too
    sparse to compute a meaningful percentile (fewer than 10 counties with data).
    """
    try:
        mapped = prepare_county_dataset(df)
        if mapped.empty:
            return RISK_SCORE_CEILING

        count_src = get_event_id_column(mapped) or "FIPS"
        prop_col  = get_damage_property_column(mapped)
        crop_col  = get_damage_crops_column(mapped)
        inj_col   = get_injuries_column(mapped)
        dth_col   = get_deaths_column(mapped)

        is_sig = pd.Series(False, index=mapped.index)
        if prop_col is not None: is_sig = is_sig | (mapped[prop_col].fillna(0) > 0)
        if crop_col is not None: is_sig = is_sig | (mapped[crop_col].fillna(0) > 0)
        if inj_col is not None:  is_sig = is_sig | (mapped[inj_col].fillna(0) > 0)
        if dth_col is not None:  is_sig = is_sig | (mapped[dth_col].fillna(0) > 0)
        mapped['is_significant'] = is_sig.astype(int)

        agg = {"event_count": ("is_significant", "sum")}
        if prop_col: agg["property_damage"] = (prop_col, "sum")
        if crop_col: agg["crop_damage"]     = (crop_col, "sum")
        if inj_col:  agg["injuries_direct"] = (inj_col,  "sum")
        if dth_col:  agg["deaths_direct"]   = (dth_col,  "sum")

        cy = mapped.groupby("FIPS", dropna=False).agg(**agg).reset_index()
        if len(cy) < 10:
            return RISK_SCORE_CEILING  # too sparse — fall back to static ceiling

        for col in ("property_damage", "crop_damage", "injuries_direct", "deaths_direct"):
            if col not in cy.columns:
                cy[col] = 0.0
        cy["total_damage"] = cy["property_damage"] + cy["crop_damage"]

        years_in_window = max(end_year - start_year + 1, 1)
        cy["avg_population"] = cy["FIPS"].apply(
            lambda f: get_avg_population_for_range(str(f), start_year, end_year)
        ).clip(lower=1)
        cy["raw"] = compute_risk_score(
            cy["event_count"], cy["total_damage"],
            cy["injuries_direct"], cy["deaths_direct"],
        )
        cy["per_capita"] = (cy["raw"] / years_in_window) / cy["avg_population"] * 10_000

        return max(float(cy["per_capita"].quantile(0.99)), 1.0)
    except Exception as exc:
        logger.warning("Could not compute dynamic ceiling: %s", exc)
        return RISK_SCORE_CEILING


HAZARD_DISPLAY_OVERRIDES = {
    "Cold/Wind Chill": "Cold and Wind Chill",
    "Extreme Cold/Wind Chill": "Extreme Cold and Wind Chill",
    "Frost/Freeze": "Frost and Freeze",
}


# ═══════════════════════════════════════════════════════════════════════════════
# GEOJSON LOADING
# Loads county boundaries from the geojson file in the local data directory.
# If that file is missing, the geometry is fetched from the Plotly
# CDN and cached locally for all future runs.
#
# Produces two globals used throughout the chart builders:
#   COUNTY_GEOJSON   – FeatureCollection passed directly to go.Choropleth
#   COUNTY_NAME_MAP  – {fips_str: county_name} lookup dict
#   COUNTY_FIPS      – sorted tuple of all valid county FIPS codes
# ═══════════════════════════════════════════════════════════════════════════════

def load_county_geojson():
    if COUNTY_GEOJSON_PATH.exists():
        geojson = json.loads(COUNTY_GEOJSON_PATH.read_text())
    else:
        response = requests.get(
            "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json",
            timeout=20,
        )
        response.raise_for_status()
        raw_geojson = response.json()
        geojson = {
            "type": "FeatureCollection",
            "features": [feature for feature in raw_geojson["features"] if feature["id"].startswith(STATE_CONFIG["state_fips_prefix"])],
        }
        COUNTY_GEOJSON_PATH.write_text(json.dumps(geojson))

    county_name_map = {
        feature["id"]: feature["properties"].get("NAME", feature["id"])
        for feature in geojson["features"]
    }

    # Derive map bounds by walking every coordinate in every feature's geometry.
    # Supports both Polygon and MultiPolygon so any county shape works correctly.
    all_lons: list[float] = []
    all_lats: list[float] = []
    for feature in geojson["features"]:
        geometry = feature.get("geometry", {})
        coords = geometry.get("coordinates", [])
        geom_type = geometry.get("type", "")
        # MultiPolygon → list of polygons → list of rings → list of [lon, lat]
        # Polygon      → list of rings → list of [lon, lat]
        rings = []
        if geom_type == "MultiPolygon":
            for polygon in coords:
                rings.extend(polygon)
        elif geom_type == "Polygon":
            rings = coords
        for ring in rings:
            for lon, lat in ring:
                all_lons.append(lon)
                all_lats.append(lat)

    if all_lats and all_lons:
        padding = 0.5   # degrees of breathing room around the state edge
        bounds = {
            "lat_min": min(all_lats) - padding,
            "lat_max": max(all_lats) + padding,
            "lon_min": min(all_lons) - padding,
            "lon_max": max(all_lons) + padding,
        }
    else:
        bounds = {"lat_min": 24.0, "lat_max": 50.0, "lon_min": -125.0, "lon_max": -66.0}

    return geojson, county_name_map, bounds


try:
    COUNTY_GEOJSON, COUNTY_NAME_MAP, COUNTY_MAP_BOUNDS = load_county_geojson()
except Exception as error:
    logger.exception("Could not load county geojson: %s", error)
    COUNTY_GEOJSON, COUNTY_NAME_MAP = None, {}
    COUNTY_MAP_BOUNDS = {"lat_min": 24.0, "lat_max": 50.0, "lon_min": -125.0, "lon_max": -66.0}

COUNTY_FIPS = tuple(sorted(COUNTY_NAME_MAP))


# ═══════════════════════════════════════════════════════════════════════════════
# CHART UTILITY HELPERS
#
#   empty_figure          – placeholder figure shown when a chart has no data
#   polish_figure         – applies brand font/bgcolor/hoverlabel to any figure
#   normalize_hazard_label – canonicalizes raw EVENT_TYPE strings (e.g. "Cold/Wind
#                            Chill" → "Cold and Wind Chill") via HAZARD_DISPLAY_OVERRIDES
#   add_hazard_display_column – adds the synthetic HAZARD_DISPLAY_COLUMN to a df
#   get_hazard_display_column – resolves that column (or falls back to EVENT_TYPE)
#   build_chart_title     – assembles a "Title<br><sup>subtitle</sup>" string
#   format_metric_value   – formats a numeric value using the METRIC_META spec
#   selected_hazard_label – human-readable label for the current hazard selection
#   filter_by_hazard      – filters a df to rows matching a hazard dropdown choice
# ═══════════════════════════════════════════════════════════════════════════════

def empty_figure(title: str, message: str):
    fig = px.scatter(title=title)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(showlegend=False, height=480)
    fig.add_annotation(text=message, showarrow=False, x=0.5, y=0.5, xref="paper", yref="paper")
    return fig


def polish_figure(fig):
    """Apply consistent layout polish to any Plotly figure."""
    fig.update_layout(
        font=_CHART_FONT,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        title_font={"size": 15, "color": "#212529", "family": "system-ui, -apple-system, 'Segoe UI', sans-serif"},
        hoverlabel=dict(
            bgcolor="white",
            bordercolor="#dee2e6",
            font_size=13,
            font_family="system-ui, -apple-system, 'Segoe UI', sans-serif",
            align="left",
        ),
    )
    fig.update_xaxes(**_AXIS_STYLE)
    fig.update_yaxes(**_AXIS_STYLE)
    return fig


def normalize_hazard_label(value: object) -> str:
    label = " ".join(str(value).strip().split()) if pd.notna(value) else "Unknown"
    if not label:
        label = "Unknown"
    return HAZARD_DISPLAY_OVERRIDES.get(label, label)


def add_hazard_display_column(df: pd.DataFrame, event_type_column: str | None) -> pd.DataFrame:
    working = df.copy()
    if event_type_column is None:
        working[HAZARD_DISPLAY_COLUMN] = "Unknown"
        return working

    working[HAZARD_DISPLAY_COLUMN] = working[event_type_column].map(normalize_hazard_label)
    return working


def get_hazard_display_column(df: pd.DataFrame) -> str | None:
    if HAZARD_DISPLAY_COLUMN in df.columns:
        return HAZARD_DISPLAY_COLUMN
    return get_event_type_column(df)


def build_chart_title(title: str, subtitle: str | None = None) -> str:
    if not subtitle:
        return title
    return f"{title}<br><sup>{subtitle}</sup>"


def format_metric_value(value, metric_key: str) -> str:
    if pd.isna(value):
        return "N/A"

    meta = METRIC_META.get(metric_key, {})
    fmt = meta.get("format", "float1")
    label = meta.get("label", "")

    # Extract unit suffix from label, e.g. "(mm)" → " mm", "(°C)" → " °C"
    unit_match = re.search(r'\((.*?)\)', label)
    unit = f" {unit_match.group(1)}" if unit_match else ""

    if fmt == "currency":
        return f"${value:,.0f}"
    if fmt == "count":
        return f"{int(round(value)):,}"
    if fmt == "score":
        return f"{value:,.1f}"
    
    # For weather metrics, append the unit (e.g., "12.4 mm")
    return f"{value:,.1f}{unit}"


def selected_hazard_label(hazard_choice: str) -> str:
    return hazard_choice if hazard_choice != ALL_HAZARDS else "All hazards"


def filter_by_hazard(df: pd.DataFrame, hazard_choice: str) -> pd.DataFrame:
    hazard_column = get_hazard_display_column(df)
    if hazard_choice == ALL_HAZARDS or hazard_column is None:
        return df.copy()

    hazard_values = df[hazard_column].astype("string").fillna("").str.strip()

    if hazard_choice in HAZARD_MAP:
        # Translation: Find any row that matches one of the items in our list
        categories_to_find = HAZARD_MAP[hazard_choice]
        return df[hazard_values.isin(categories_to_find)].copy()

    return df[hazard_values.eq(hazard_choice)].copy()


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING & HAZARD TAXONOMY
#
# Both Parquet files are read once at startup into module-level DataFrames:
#   storms  – storm_events_mn.parquet       (one row per event, 1950-2025)
#   summary – storm_weather_summary_mn.parquet (events joined with daily weather)
#
# Column names are resolved via geo_utils helpers and stored as STORM_*/SUMMARY_*
# constants so the rest of the app never hard-codes column strings directly.
#
# HAZARD TAXONOMY
#   EVENT_TYPE_CHOICES – the labels shown in every hazard dropdown
#   HAZARD_MAP         – maps each UI label to one or more raw EVENT_TYPE values
#                        in the Parquet data (the "translation layer")
# ═══════════════════════════════════════════════════════════════════════════════

# Load data once after schema helpers are defined.
storms = normalize_dataframe_columns(pd.read_parquet(DATA_DIR / "storm_events_mn.parquet"))
summary = normalize_dataframe_columns(pd.read_parquet(DATA_DIR / "storm_weather_summary_mn.parquet"))

STORM_DATE_COLUMN = get_begin_date_column(storms)
STORM_GEO_COLUMN = get_geo_group_column(storms)
STORM_FIPS_COLUMN = get_geo_fips_column(storms)
STORM_EVENT_COLUMN = get_event_id_column(storms)
STORM_EVENT_TYPE_COLUMN = get_event_type_column(storms)
STORM_DAMAGE_COLUMN = get_damage_property_column(storms)
STORM_CROP_DAMAGE_COLUMN = get_damage_crops_column(storms)
STORM_INJURIES_COLUMN = get_injuries_column(storms)
STORM_DEATHS_COLUMN = get_deaths_column(storms)

SUMMARY_DATE_COLUMN = get_begin_date_column(summary)
SUMMARY_GEO_COLUMN = get_geo_group_column(summary)
SUMMARY_FIPS_COLUMN = get_geo_fips_column(summary)
SUMMARY_EVENT_COLUMN = get_event_id_column(summary)
SUMMARY_EVENT_TYPE_COLUMN = get_event_type_column(summary)
SUMMARY_DAMAGE_COLUMN = get_damage_property_column(summary)
SUMMARY_CROP_DAMAGE_COLUMN = get_damage_crops_column(summary)
SUMMARY_INJURIES_COLUMN = get_injuries_column(summary)
SUMMARY_DEATHS_COLUMN = get_deaths_column(summary)
SUMMARY_PRECIP_COLUMN = get_precipitation_column(summary)
SUMMARY_TMAX_COLUMN = get_max_temperature_column(summary)
SUMMARY_TMIN_COLUMN = resolve_column(summary, ("daily_tmin_avg", "tmin", "min_temperature"))
SUMMARY_SNOW_COLUMN = get_snowfall_column(summary)
SUMMARY_SNOW_DEPTH_COLUMN = get_snow_depth_column(summary)
SUMMARY_WIND_COLUMN = get_wind_speed_column(summary)

storms = add_hazard_display_column(storms, STORM_EVENT_TYPE_COLUMN)
summary = add_hazard_display_column(summary, SUMMARY_EVENT_TYPE_COLUMN)


# The labels shown in the dropdown UI
EVENT_TYPE_CHOICES = [
    "All hazards",
    "Winter Storms",
    "Extreme Cold",
    "Flooding",
    "Severe Wind & Tornado",
    "Hail",
    "Heat Emergencies",
    "Drought",
    "Ice & Freeze"
]

# The "Translation Key" that connects UI labels to Parquet data values
HAZARD_MAP = {
    "Winter Storms": ["Winter Storm", "Winter Weather", "Heavy Snow", "Blizzard"],
    "Extreme Cold": ["Cold and Wind Chill", "Extreme Cold and Wind Chill"],
    "Flooding": ["Flood", "Flash Flood"],
    "Severe Wind & Tornado": ["High Wind", "Thunderstorm Wind", "Tornado", "Strong Wind"],
    "Heat Emergencies": ["Heat", "Excessive Heat"],
    "Ice & Freeze": ["Ice Storm", "Frost and Freeze"],
    "Hail": ["Hail"],
    "Drought": ["Drought"]
}

# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA VALIDATION
# Logs a WARNING at startup for any expected column that could not be resolved
# in either dataset.  Issues surface here rather than silently producing empty
# charts when the app first loads.  All checks are non-fatal — the app will
# continue running with degraded output.
# ═══════════════════════════════════════════════════════════════════════════════

for dataset_name, required_columns in {
    "storms": {
        "date": STORM_DATE_COLUMN,
        "geo_group": STORM_GEO_COLUMN,
        "event_id": STORM_EVENT_COLUMN,
        "event_type": STORM_EVENT_TYPE_COLUMN,
        "damage": STORM_DAMAGE_COLUMN,
        "injuries": STORM_INJURIES_COLUMN,
    },
    "summary": {
        "date": SUMMARY_DATE_COLUMN,
        "geo_group": SUMMARY_GEO_COLUMN,
        "event_id": SUMMARY_EVENT_COLUMN,
        "event_type": SUMMARY_EVENT_TYPE_COLUMN,
        "precipitation": SUMMARY_PRECIP_COLUMN,
        "max_temperature": SUMMARY_TMAX_COLUMN,
        "wind_speed": SUMMARY_WIND_COLUMN,
    },
}.items():
    missing = [label for label, column in required_columns.items() if column is None]
    if missing:
        columns = list(storms.columns if dataset_name == "storms" else summary.columns)
        logger.warning("%s is missing %s. Available columns: %s", dataset_name, missing, columns)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA PROCESSING & AGGREGATION
# Pure transformation functions — no Shiny inputs, no reactive context.
# Each function takes a filtered DataFrame and returns a ready-to-plot aggregate.
# Keeping these separate from chart builders means they can be tested
# independently and reused across multiple tabs without re-querying raw data.
#
#   prepare_county_dataset        – FIPS normalization & county name join
#   aggregate_county_metrics      – per-county event counts, damage totals,
#                                   weather averages, and composite risk score
#   aggregate_hazard_metrics      – per-hazard-type rollup for comparison charts
#   add_time_frame                – attaches frame_label/frame_sort for animations
#   build_animation_dataset       – county × time-frame grid with zero-fill
#   classify_trend_direction      – maps a normalized slope to Increasing/Stable/Decreasing
#   compute_county_trend_classification – per-county trend over recent N frames
#   compute_weather_correlations  – Pearson r between storm events and weather vars
# ═══════════════════════════════════════════════════════════════════════════════

def prepare_county_dataset(df: pd.DataFrame) -> pd.DataFrame:
    working = normalize_dataframe_columns(df.copy())
    if working.empty or not COUNTY_NAME_MAP:
        return working.iloc[0:0].copy()

    fips_column = get_geo_fips_column(working)
    if fips_column is None:
        return working.iloc[0:0].copy()

    working["FIPS"] = working[fips_column].map(
        lambda v: to_county_fips(v, STATE_CONFIG["state_fips_prefix"])
    )
    working = working[working["FIPS"].isin(COUNTY_FIPS)].copy()
    if working.empty:
        return working

    working["county_name"] = working["FIPS"].map(COUNTY_NAME_MAP)

    geo_column = get_geo_group_column(working)
    if geo_column is not None:
        working["source_geo_name"] = working[geo_column].astype("string").fillna("").str.strip()

    hazard_column = get_hazard_display_column(working)
    if hazard_column is not None:
        working["hazard_label"] = working[hazard_column].astype("string").fillna("Unknown").str.strip()

    date_column = get_begin_date_column(working)
    if date_column is not None:
        working[date_column] = pd.to_datetime(working[date_column], errors="coerce")
        working = working[working[date_column].notna()].copy()

    return working


# ── Ceiling computed here — prepare_county_dataset is now defined ──────────────
RISK_SCORE_CEILING = _compute_risk_ceiling()


def aggregate_county_metrics(
    df: pd.DataFrame,
    start_year: int | None = None,
    end_year: int | None = None,
    ceiling: float | None = None,
) -> pd.DataFrame:
    mapped = prepare_county_dataset(df)
    if mapped.empty:
        return mapped

    # 1. Infer year range from the data if not supplied
    if start_year is None or end_year is None:
        date_col = get_begin_date_column(mapped)
        if date_col is not None:
            years = pd.to_datetime(mapped[date_col], errors="coerce").dt.year.dropna()
            start_year = int(years.min()) if start_year is None and not years.empty else (start_year or 2020)
            end_year   = int(years.max()) if end_year   is None and not years.empty else (end_year   or 2020)
        else:
            start_year, end_year = 2020, 2020

    # 2. Resolve data columns
    count_source  = get_event_id_column(mapped) or "FIPS"
    damage_column = get_damage_property_column(mapped)
    crop_column   = get_damage_crops_column(mapped)
    injuries_column = get_injuries_column(mapped)
    deaths_column = get_deaths_column(mapped)
    precip_column = get_precipitation_column(mapped)
    tmax_column   = get_max_temperature_column(mapped)
    tmin_column   = resolve_column(mapped, ("daily_tmin_avg", "tmin", "min_temperature"))
    wind_column   = get_wind_speed_column(mapped)
    snow_column   = get_snowfall_column(mapped)

    # 3. Flag "significant" events: any event with measurable damage, injury, or death.
    #    sig_events feeds the risk score formula; event_count feeds visual totals.
    is_sig = pd.Series(False, index=mapped.index)
    if damage_column is not None:   is_sig = is_sig | (mapped[damage_column].fillna(0) > 0)
    if crop_column is not None:     is_sig = is_sig | (mapped[crop_column].fillna(0) > 0)
    if injuries_column is not None: is_sig = is_sig | (mapped[injuries_column].fillna(0) > 0)
    if deaths_column is not None:   is_sig = is_sig | (mapped[deaths_column].fillna(0) > 0)
    
    mapped['is_significant'] = is_sig.astype(int)
    
    # 4. Aggregate: every row counts toward event_count (used in charts);
    #    only significant events count toward sig_events (used in risk math).
    agg_kwargs = {
        "event_count": (count_source, "count"),
        "sig_events":  ("is_significant", "sum") 
    }
    
    if damage_column   is not None: agg_kwargs["property_damage"]  = (damage_column,   "sum")
    if crop_column     is not None: agg_kwargs["crop_damage"]      = (crop_column,     "sum")
    if injuries_column is not None: agg_kwargs["injuries_direct"]  = (injuries_column, "sum")
    if deaths_column   is not None: agg_kwargs["deaths_direct"]    = (deaths_column,   "sum")
    if precip_column   is not None: agg_kwargs["avg_precip"]       = (precip_column,   "mean")
    if tmax_column     is not None: agg_kwargs["avg_tmax"]         = (tmax_column,     "mean")
    if tmin_column     is not None: agg_kwargs["avg_tmin"]         = (tmin_column,     "mean")
    if wind_column     is not None: agg_kwargs["avg_wind"]         = (wind_column,     "mean")
    if snow_column     is not None: agg_kwargs["avg_snow"]         = (snow_column,     "mean")

    # 5. Group data by county
    county_data = mapped.groupby(["FIPS", "county_name"], dropna=False).agg(**agg_kwargs).reset_index()

    # 6. Fill missing metrics with defaults
    for column in ("property_damage", "crop_damage", "injuries_direct", "deaths_direct"):
        if column not in county_data.columns:
            county_data[column] = 0.0

    county_data["total_damage"] = county_data["property_damage"] + county_data["crop_damage"]

    for column in ("avg_precip", "avg_tmax", "avg_tmin", "avg_wind", "avg_snow"):
        if column not in county_data.columns:
            county_data[column] = np.nan

    # 7. Raw absolute risk score using 'sig_events' instead of 'event_count'
    county_data["raw_risk_score"] = compute_risk_score(
        county_data["sig_events"],
        county_data["total_damage"],
        county_data["injuries_direct"],
        county_data["deaths_direct"],
    )

    # 8. Normalization (Annualize & Per-Capita)
    years_in_window = max(end_year - start_year + 1, 1)
    county_data["annualized_risk"] = county_data["raw_risk_score"] / years_in_window

    county_data["avg_population"] = county_data["FIPS"].apply(
        lambda fips: get_avg_population_for_range(str(fips), start_year, end_year)
    ).clip(lower=1)

    county_data["per_capita_risk"] = (
        county_data["annualized_risk"] / county_data["avg_population"] * 10_000
    )

    # 9. Scale 0–100 using dynamic ceiling
    effective_ceiling = ceiling if (ceiling is not None and ceiling > 0) else RISK_SCORE_CEILING
    effective_ceiling = max(effective_ceiling, 1.0)
    county_data["risk_score"] = (
        (county_data["per_capita_risk"] / effective_ceiling * 100)
        .clip(upper=100)
        .round(1)
    )

    return county_data.sort_values("risk_score", ascending=False).reset_index(drop=True)

def aggregate_hazard_metrics(df: pd.DataFrame) -> pd.DataFrame:
    working = normalize_dataframe_columns(df.copy())
    hazard_column = get_hazard_display_column(working)
    if working.empty or hazard_column is None:
        return pd.DataFrame()

    working["event_type"] = working[hazard_column].astype("string").fillna("Unknown").str.strip()
    count_source = get_event_id_column(working) or hazard_column
    damage_column = get_damage_property_column(working)
    injuries_column = get_injuries_column(working)
    precip_column = get_precipitation_column(working)
    tmax_column = get_max_temperature_column(working)
    wind_column = get_wind_speed_column(working)
    snow_column = get_snowfall_column(working)

    agg_kwargs = {"event_count": (count_source, "count")}
    if damage_column is not None:
        agg_kwargs["property_damage"] = (damage_column, "sum")
    if injuries_column is not None:
        agg_kwargs["injuries_direct"] = (injuries_column, "sum")
    if precip_column is not None:
        agg_kwargs["avg_precip"] = (precip_column, "mean")
    if tmax_column is not None:
        agg_kwargs["avg_tmax"] = (tmax_column, "mean")
    if wind_column is not None:
        agg_kwargs["avg_wind"] = (wind_column, "mean")
    if snow_column is not None:
        agg_kwargs["avg_snow"] = (snow_column, "mean")

    hazard_data = working.groupby("event_type", dropna=False).agg(**agg_kwargs).reset_index()
    for column in ("property_damage", "injuries_direct", "avg_precip", "avg_tmax", "avg_wind", "avg_snow"):
        if column not in hazard_data.columns:
            hazard_data[column] = np.nan if column.startswith("avg_") else 0.0

    return hazard_data.sort_values("event_count", ascending=False).reset_index(drop=True)


def add_time_frame(
    df: pd.DataFrame,
    date_column: str,
    preferred_frame: str | None = None,
) -> tuple[pd.DataFrame, str | None]:
    working = df.copy()
    working[date_column] = pd.to_datetime(working[date_column], errors="coerce")
    working = working[working[date_column].notna()].copy()
    if working.empty:
        return working, None

    dates = working[date_column]
    monthly_available = dates.dt.to_period("M").nunique() > 1
    if preferred_frame == "Month" and monthly_available:
        monthly_frames = True
    elif preferred_frame == "Year":
        monthly_frames = False
    else:
        span_days = (dates.max() - dates.min()).days
        monthly_frames = span_days <= 730 and monthly_available

    if monthly_frames:
        working["frame_label"] = dates.dt.strftime("%b %Y")
        working["frame_sort"] = dates.dt.to_period("M").dt.to_timestamp()
        return working, "Month"

    working["frame_label"] = dates.dt.year.astype(int).astype(str)
    working["frame_sort"] = dates.dt.to_period("Y").dt.to_timestamp()
    return working, "Year"


def build_animation_dataset(df: pd.DataFrame, ceiling: float | None = None) -> tuple[pd.DataFrame, str | None]:
    mapped = prepare_county_dataset(df)
    date_column = get_begin_date_column(mapped)
    if mapped.empty or date_column is None:
        return mapped.iloc[0:0].copy(), None

    framed, frame_name = add_time_frame(mapped, date_column)
    if framed.empty or frame_name is None:
        return framed.iloc[0:0].copy(), None

    count_source   = get_event_id_column(framed) or "FIPS"
    damage_column  = get_damage_property_column(framed)
    crop_column    = get_damage_crops_column(framed)
    injuries_column = get_injuries_column(framed)
    deaths_column  = get_deaths_column(framed)

    is_sig = pd.Series(False, index=framed.index)
    if damage_column is not None:   is_sig = is_sig | (framed[damage_column].fillna(0) > 0)
    if crop_column is not None:     is_sig = is_sig | (framed[crop_column].fillna(0) > 0)
    if injuries_column is not None: is_sig = is_sig | (framed[injuries_column].fillna(0) > 0)
    if deaths_column is not None:   is_sig = is_sig | (framed[deaths_column].fillna(0) > 0)
    framed['is_significant'] = is_sig.astype(int)

    yearly = (
        framed.groupby(["frame_label", "frame_sort", "FIPS", "county_name"], dropna=False)
        .agg(
            sig_event_count=("is_significant", "sum"),
            event_count=(count_source, "count"),
            property_damage=(damage_column, "sum")  if damage_column  is not None else (count_source, lambda _: 0.0),
            crop_damage=(crop_column, "sum")         if crop_column     is not None else (count_source, lambda _: 0.0),
            injuries_direct=(injuries_column, "sum") if injuries_column is not None else (count_source, lambda _: 0.0),
            deaths_direct=(deaths_column, "sum")     if deaths_column   is not None else (count_source, lambda _: 0.0),
        )
        .reset_index()
    )
    yearly["total_damage"] = yearly["property_damage"] + yearly["crop_damage"]

    # Raw score per county per frame — uses significant event count only
    yearly["raw_risk_score"] = compute_risk_score(
        yearly["sig_event_count"],
        yearly["total_damage"],
        yearly["injuries_direct"],
        yearly["deaths_direct"],
    )

    # Per-capita + 0-100 normalization — same pipeline as aggregate_county_metrics.
    # Each frame is already one period (year or month) so annualization = ÷1.
    # Extract the year from frame_sort to look up the correct population.
    yearly["_year"] = pd.to_datetime(yearly["frame_sort"], errors="coerce").dt.year.fillna(1985).astype(int)
    yearly["avg_population"] = yearly.apply(
        lambda r: get_county_population(str(r["FIPS"]), int(r["_year"])), axis=1
    ).clip(lower=1)
    effective_ceiling = ceiling if (ceiling is not None and ceiling > 0) else RISK_SCORE_CEILING
    effective_ceiling = max(effective_ceiling, 1.0)
    yearly["risk_score"] = (
        (yearly["raw_risk_score"] / yearly["avg_population"] * 10_000 / effective_ceiling * 100)
        .clip(upper=100)
        .round(1)
    )
    yearly.drop(columns=["_year"], inplace=True)

    if frame_name == "Month":
        frame_starts = pd.date_range(framed["frame_sort"].min(), framed["frame_sort"].max(), freq="MS")
        frame_order = pd.DataFrame(
            {"frame_sort": frame_starts, "frame_label": frame_starts.strftime("%b %Y")}
        )
    else:
        frame_starts = pd.date_range(framed["frame_sort"].min(), framed["frame_sort"].max(), freq="YS")
        frame_order = pd.DataFrame(
            {"frame_sort": frame_starts, "frame_label": frame_starts.year.astype(str)}
        )
    full_grid = pd.MultiIndex.from_product(
        [frame_order["frame_label"], COUNTY_FIPS],
        names=["frame_label", "FIPS"],
    ).to_frame(index=False)
    full_grid = full_grid.merge(frame_order, on="frame_label", how="left")
    full_grid["county_name"] = full_grid["FIPS"].map(COUNTY_NAME_MAP)

    yearly = full_grid.merge(yearly, on=["frame_label", "frame_sort", "FIPS", "county_name"], how="left")
    for column in ("event_count", "sig_event_count", "property_damage", "crop_damage", "total_damage",
                   "injuries_direct", "deaths_direct", "risk_score"):
        yearly[column] = yearly[column].fillna(0)

    return yearly.sort_values(["frame_sort", "county_name"]).reset_index(drop=True), frame_name


def classify_trend_direction(normalized_slope: float | None, threshold: float = TREND_SLOPE_THRESHOLD) -> str:
    if normalized_slope is None or pd.isna(normalized_slope):
        return "Short window"
    if normalized_slope > threshold:
        return "Increasing"
    if normalized_slope < -threshold:
        return "Decreasing"
    return "Stable"


def compute_county_trend_classification(
    animation_df: pd.DataFrame,
    metric_key: str = "event_count",
) -> tuple[pd.DataFrame, str | None, int]:
    if animation_df.empty or metric_key not in animation_df.columns:
        return pd.DataFrame(), None, 0

    frame_order = (
        animation_df[["frame_sort", "frame_label"]]
        .drop_duplicates()
        .sort_values("frame_sort")
        .reset_index(drop=True)
    )
    lookback = min(TREND_LOOKBACK_FRAMES, len(frame_order))
    if lookback == 0:
        return pd.DataFrame(), None, 0

    recent_labels = set(frame_order.tail(lookback)["frame_label"])
    recent = animation_df[animation_df["frame_label"].isin(recent_labels)].copy()
    if recent.empty:
        return pd.DataFrame(), None, 0

    rows = []
    for (fips, county_name), group in recent.groupby(["FIPS", "county_name"], dropna=False):
        series = group.sort_values("frame_sort")[metric_key].fillna(0).to_numpy()
        mean_value = float(series.mean()) if len(series) else np.nan
        if len(series) < TREND_MIN_FRAMES:
            normalized_slope = np.nan
        elif np.allclose(series, series[0]):
            normalized_slope = 0.0
        else:
            slope = float(np.polyfit(np.arange(len(series)), series, 1)[0])
            normalized_slope = slope / mean_value if mean_value else 0.0

        rows.append(
            {
                "FIPS": fips,
                "county_name": county_name,
                "trend_slope_norm": normalized_slope,
                "trend_class": classify_trend_direction(normalized_slope),
            }
        )

    return pd.DataFrame(rows), metric_key, lookback


def compute_weather_correlations(df: pd.DataFrame) -> tuple[pd.DataFrame, str | None]:
    mapped = prepare_county_dataset(df)
    date_column = get_begin_date_column(mapped)
    if mapped.empty or date_column is None:
        return pd.DataFrame(), None

    metric_columns = {
        "avg_precip": get_precipitation_column(mapped),
        "avg_tmax": get_max_temperature_column(mapped),
        "avg_wind": get_wind_speed_column(mapped),
        "avg_snow": get_snowfall_column(mapped),
    }
    metric_columns = {key: column for key, column in metric_columns.items() if column is not None}
    if not metric_columns:
        return pd.DataFrame(), None

    working = mapped.copy()
    dates = pd.to_datetime(working[date_column], errors="coerce")
    if dates.isna().all():
        return pd.DataFrame(), None

    working["analysis_period"] = dates.dt.to_period("M").dt.to_timestamp()
    if working["analysis_period"].nunique() < 2:
        working["analysis_period"] = dates.dt.to_period("Y").dt.to_timestamp()
        period_name = "county-year"
    else:
        period_name = "county-month"

    count_source = get_event_id_column(working) or "FIPS"
    agg_kwargs = {"event_count": (count_source, "count")}
    for metric_key, column in metric_columns.items():
        agg_kwargs[metric_key] = (column, "mean")

    grouped = (
        working.groupby(["county_name", "analysis_period"], dropna=False)
        .agg(**agg_kwargs)
        .reset_index()
    )

    rows = []
    for metric_key in metric_columns:
        pairs = grouped[["event_count", metric_key]].dropna()
        if len(pairs) < CORRELATION_MIN_POINTS:
            continue

        correlation = pairs["event_count"].corr(pairs[metric_key])
        rows.append(
            {
                "metric_key": metric_key,
                "metric_label": METRIC_META[metric_key]["label"],
                "correlation": correlation,
                "sample_size": len(pairs),
            }
        )

    correlation_df = pd.DataFrame(rows)
    if correlation_df.empty:
        return correlation_df, period_name

    correlation_df["direction"] = np.where(correlation_df["correlation"] >= 0, "Positive", "Negative")
    correlation_df["correlation_display"] = correlation_df["correlation"].map(lambda value: f"{value:+.2f}")
    correlation_df = correlation_df.sort_values("correlation", ascending=True).reset_index(drop=True)
    return correlation_df, period_name


# ═══════════════════════════════════════════════════════════════════════════════
# CHART BUILDER FUNCTIONS
# Each function accepts a pre-aggregated DataFrame and returns a Plotly figure.
# All builders are stateless — no Shiny inputs or reactive context — so they
# can be unit-tested independently of the server.
#
#   build_county_map              – choropleth with rich hover tooltip
#   build_county_ranking          – horizontal bar, top-10 counties
#   build_overview_donut          – donut chart, hazard composition with totals
#   build_hazard_comparison       – horizontal bar comparing hazard intensities
#   build_county_stacked_bar      – property vs. crop damage stacked by county
#   build_county_scatter          – events × damage bubble (injuries = size)
#   build_hazard_diversity_plot   – unique event types tracked per year
#   build_animation_context_plot  – total statewide storm counts over time (line)
#   build_weather_correlation_figure – horizontal bar of Pearson r values
#   build_trend_counts_figure     – stacked bar, decadal hazard mix
#   build_trend_damage_figure     – bar chart, annual property+crop damage
#   build_storm_season_heatmap    – hazard × month heatmap (event counts)
# ═══════════════════════════════════════════════════════════════════════════════

def build_county_map(
    county_data: pd.DataFrame, 
    metric_key: str, 
    title: str = None, 
    subtitle: str | None = None, 
    weather_context: bool = False,
    is_overview: bool = False
):
    if county_data.empty:
        return empty_figure(title, "No records match this view.")
    if COUNTY_GEOJSON is None:
        return empty_figure(title, "Geometry could not be loaded.")

    plot_data = county_data.copy()

    # Prep display strings
    def fmt(col, key): return plot_data[col].apply(lambda v: format_metric_value(v, key)) if col in plot_data.columns else "N/A"
    
    plot_data["metric_display"]          = plot_data[metric_key].apply(lambda v: format_metric_value(v, metric_key))
    plot_data["event_count_display"]     = fmt("event_count",     "event_count")
    plot_data["property_damage_display"] = fmt("property_damage", "property_damage")
    plot_data["injuries_display"]        = fmt("injuries_direct", "injuries_direct")
    plot_data["deaths_display"]          = fmt("deaths_direct",   "deaths_direct")
    plot_data["risk_score_display"]      = fmt("risk_score",      "risk_score")
    plot_data["avg_precip_display"]      = fmt("avg_precip",      "avg_precip")
    plot_data["avg_wind_display"]        = fmt("avg_wind",        "avg_wind")
    plot_data["avg_tmax_display"]        = fmt("avg_tmax",        "avg_tmax")
    plot_data["avg_tmin_display"]        = fmt("avg_tmin",        "avg_tmin")
    plot_data["avg_snow_display"]        = fmt("avg_snow",        "avg_snow")

    metric_label = METRIC_META[metric_key]["label"]

    # ── GLOBAL STYLE CONSTANTS ───────────────────────────────────────────
    # Bumping sizes for better hierarchy and readability
    H1_STYLE  = "font-size:19px; color:#212529; font-weight:800; line-height:1.2;" # County Name
    H2_STYLE  = "font-size:16px; color:#0d6efd; font-weight:800;"                 # Primary Metric
    DIVIDER   = "<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
    ROW_STYLE = "color:#495057; font-size:13px;"                                 # Secondary Info

    # ── TOOLTIP CONFIGURATION ────────────────────────────────────────────
    
    if weather_context:
        # MODE: Weather Context Tab
        hover_cols = ["county_name", "metric_display", "avg_precip_display", "avg_tmax_display", "avg_tmin_display", "avg_wind_display", "avg_snow_display", "event_count_display"]
        hovertemplate = (
            f"<span style='{H1_STYLE}'>%{{customdata[0]}} County</span><br>"
            f"<span style='{H2_STYLE}'>{metric_label}: %{{customdata[1]}}</span><br>"
            f"{DIVIDER}"
            f"<span style='{ROW_STYLE}'><b>Avg Precipitation:</b> %{{customdata[2]}}</span><br>"
            f"<span style='{ROW_STYLE}'><b>Avg Snowfall:</b> %{{customdata[6]}}</span><br>"
            f"<span style='{ROW_STYLE}'><b>Avg Wind Speed:</b> %{{customdata[5]}}</span><br>"
            f"<span style='{ROW_STYLE}'><b>Avg Max Temp:</b> %{{customdata[3]}}</span><br>"
            f"<span style='{ROW_STYLE}'><b>Avg Min Temp:</b> %{{customdata[4]}}</span><br>"
            f"{DIVIDER}"
            f"<span style='font-size:11px; color:#6c757d;'>Storm Events: %{{customdata[7]}}</span>"
            "<extra></extra>"
        )

    elif is_overview:
        # MODE: Landing Page (Overview Tab)
        hover_cols = ["county_name", "risk_score_display", "property_damage_display", "injuries_display", "deaths_display"]
        hovertemplate = (
            f"<span style='{H1_STYLE}'>%{{customdata[0]}} County</span><br>"
            f"<span style='{H2_STYLE}'>Risk Score: %{{customdata[1]}}</span><br>"
            f"{DIVIDER}"
            f"<span style='{ROW_STYLE}'><b>Total Damage:</b> %{{customdata[2]}}</span><br>"
            f"<span style='{ROW_STYLE}'><b>Direct Injuries:</b> %{{customdata[3]}}</span><br>"
            f"<span style='{ROW_STYLE}'><b>Direct Deaths:</b> %{{customdata[4]}}</span>"
            "<extra></extra>"
        )

    else:
        # MODE: Explorer Mode (County Impacts)
        hover_cols = ["county_name", "metric_display", "event_count_display", "property_damage_display", "injuries_display", "deaths_display", "risk_score_display", "avg_precip_display", "avg_wind_display"]
        hovertemplate = (
            f"<span style='{H1_STYLE}'>%{{customdata[0]}} County</span><br>"
            f"<span style='{H2_STYLE}'>{metric_label}: %{{customdata[1]}}</span><br>"
            f"{DIVIDER}"
            f"<span style='{ROW_STYLE}'><b>Risk Score:</b> %{{customdata[6]}}</span><br>"
            f"<span style='{ROW_STYLE}'><b>Storm Events:</b> %{{customdata[2]}}</span><br>"
            f"<span style='{ROW_STYLE}'><b>Property Damage:</b> %{{customdata[3]}}</span><br>"
            f"<span style='{ROW_STYLE}'><b>Direct Injuries:</b> %{{customdata[4]}}</span><br>"
            f"<span style='{ROW_STYLE}'><b>Direct Deaths:</b> %{{customdata[5]}}</span><br>"
            f"{DIVIDER}"
            f"<span style='font-size:11px; color:#6c757d;'>Avg Precip: %{{customdata[7]}} | Wind: %{{customdata[8]}}</span>"
            "<extra></extra>"
        )

    # ── FIGURE CONSTRUCTION ──────────────────────────────────────────────
    
    all_fips = list(COUNTY_FIPS)
    base_trace = go.Choropleth(
        geojson=COUNTY_GEOJSON,
        locations=all_fips,
        z=[0] * len(all_fips),
        colorscale=[[0, "#f7f7f7"], [1, "#f7f7f7"]],
        showscale=False,
        marker_line_width=1.2,
        marker_line_color="#495057",
        hoverinfo="skip",
    )

    data_trace = go.Choropleth(
        geojson=COUNTY_GEOJSON,
        locations=plot_data["FIPS"],
        z=plot_data[metric_key],
        colorscale=COUNTY_MAP_COLORSCALE,
        showscale=False,
        marker_line_width=1.2,
        marker_line_color="#495057",
        customdata=plot_data[hover_cols].values,
        hovertemplate=hovertemplate,
    )

    fig = go.Figure(data=[base_trace, data_trace])
    fig.update_geos(
        visible=False,
        bgcolor="rgba(0,0,0,0)",
        projection_type="mercator",
        lataxis_range=[COUNTY_MAP_BOUNDS["lat_min"], COUNTY_MAP_BOUNDS["lat_max"]],
        lonaxis_range=[COUNTY_MAP_BOUNDS["lon_min"], COUNTY_MAP_BOUNDS["lon_max"]],
    )
    
    fig.update_layout(
        height=450,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        font_family="system-ui, -apple-system, sans-serif",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        dragmode=False,
        hoverlabel=dict(
            bgcolor="white",
            bordercolor="#dee2e6",
            font_size=13,
            font_color="#212529",
            font_family="system-ui, -apple-system, sans-serif",
            align="left",
        ),
    )
    return fig

def build_county_ranking(df: pd.DataFrame, metric_key: str, weather_context: bool = False):
    if df.empty or metric_key not in df.columns:
        return empty_figure("Ranking", "No data available.")

    metric_label = METRIC_META[metric_key]["label"]
    plot_data = df.dropna(subset=[metric_key]).sort_values(metric_key, ascending=True).tail(10).copy()

    plot_data["metric_display"] = plot_data[metric_key].apply(lambda x: format_metric_value(x, metric_key))
    plot_data["events_display"] = plot_data["event_count"].apply(lambda x: format_metric_value(x, "event_count")) if "event_count" in plot_data.columns else "N/A"
    plot_data["damage_display"] = plot_data["property_damage"].apply(lambda x: format_metric_value(x, "property_damage")) if "property_damage" in plot_data.columns else "N/A"
    plot_data["risk_display"]   = plot_data["risk_score"].apply(lambda x: format_metric_value(x, "risk_score")) if "risk_score" in plot_data.columns else "N/A"
    plot_data["precip_display"] = plot_data["avg_precip"].apply(lambda x: format_metric_value(x, "avg_precip")) if "avg_precip" in plot_data.columns else "N/A"
    plot_data["tmax_display"]   = plot_data["avg_tmax"].apply(lambda x: format_metric_value(x, "avg_tmax")) if "avg_tmax" in plot_data.columns else "N/A"
    plot_data["tmin_display"]   = plot_data["avg_tmin"].apply(lambda x: format_metric_value(x, "avg_tmin")) if "avg_tmin" in plot_data.columns else "N/A"
    plot_data["wind_display"]   = plot_data["avg_wind"].apply(lambda x: format_metric_value(x, "avg_wind")) if "avg_wind" in plot_data.columns else "N/A"
    plot_data["snow_display"]   = plot_data["avg_snow"].apply(lambda x: format_metric_value(x, "avg_snow")) if "avg_snow" in plot_data.columns else "N/A"

    if weather_context:
        # MODE: Weather Context Tab Ranking
        hover_cols    = ["county_name", "metric_display", "precip_display", "tmax_display", "tmin_display", "wind_display", "snow_display", "events_display"]
        hovertemplate = (
            "<span style='font-size:19px; color:#212529; font-weight:800; line-height:1.2;'>%{customdata[0]} County</span><br>"
            f"<span style='font-size:16px; color:#0d6efd; font-weight:800;'>{metric_label}: %{{customdata[1]}}</span><br>"
            "<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Avg Precipitation:</b> %{customdata[2]}</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Avg Snowfall:</b> %{customdata[6]}</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Avg Wind Speed:</b> %{customdata[5]}</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Avg Max Temp:</b> %{customdata[3]}</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Avg Min Temp:</b> %{customdata[4]}</span><br>"
            "<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
            "<span style='font-size:11px; color:#6c757d;'>Storm Event: %{customdata[7]}</span>"
            "<extra></extra>"
        )
    else:
        # MODE: General Ranking (Explorer or other modes)
        hover_cols    = ["county_name", "metric_display", "events_display", "damage_display", "risk_display"]
        hovertemplate = (
            "<span style='font-size:19px; color:#212529; font-weight:800; line-height:1.2;'>%{customdata[0]} County</span><br>"
            f"<span style='font-size:16px; color:#0d6efd; font-weight:800;'>{metric_label}: %{{customdata[1]}}</span><br>"
            "<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Risk Score:</b> %{customdata[4]}</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Storm Event:</b> %{customdata[2]}</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Property Damage:</b> %{customdata[3]}</span>"
            "<extra></extra>"
        )

    fig = px.bar(
        plot_data, x=metric_key, y="county_name", orientation="h",
        title=None, height=205,
        color_discrete_sequence=["#0d6efd"],
        labels={"county_name": "", metric_key: metric_label},
    )
    fig.update_traces(
        customdata=plot_data[hover_cols].values,
        marker_line_width=0,
        opacity=0.85,
        hovertemplate=hovertemplate,
    )

    fig.update_layout(
        margin={"l": 0, "r": 20, "t": 10, "b": 40},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=_CHART_FONT,
        hoverlabel=dict(
            bgcolor="white",
            bordercolor="#dee2e6",
            font_size=13,
            font_family="system-ui, -apple-system, sans-serif",
            align="left",
        ),
    )
    fig.update_xaxes(**_AXIS_STYLE)
    fig.update_yaxes(**_AXIS_STYLE)
    return fig

def build_hazard_diversity_plot(df: pd.DataFrame):
    if df.empty:
        return empty_figure("Diversity", "No data")

    working = df.copy()
    date_col = get_begin_date_column(working)
    
    framed, frame_name = add_time_frame(working, date_col)
    if framed.empty or frame_name is None:
        return empty_figure("Diversity", "No dated records available.")

    diversity = (
        framed.groupby(["frame_sort", "frame_label"])[get_hazard_display_column(framed)]
        .nunique()
        .reset_index(name="unique_types")
        .sort_values("frame_sort")
    )

    if frame_name == "Month":
        # Fill in any months that had zero events so the x-axis is complete
        full_range = pd.date_range(
            diversity["frame_sort"].min(),
            diversity["frame_sort"].max(),
            freq="MS",
        )
        full_df = pd.DataFrame({
            "frame_sort": full_range,
            "frame_label": full_range.strftime("%b %Y"),
        })
        diversity = full_df.merge(diversity, on=["frame_sort", "frame_label"], how="left")
        diversity["unique_types"] = diversity["unique_types"].fillna(0).astype(int)

    if frame_name == "Year":
        diversity["x_axis"] = pd.to_datetime(diversity["frame_sort"]).dt.year
        ordered_x = None
    else:
        # Use the string label so tick text is always visible; lock order via
        # category_orders to prevent Plotly's alphabetical re-sort.
        diversity["x_axis"] = diversity["frame_label"]
        ordered_x = list(diversity["frame_label"])

    fig = px.bar(
        diversity, x="x_axis", y="unique_types",
        title=None, height=205,
        color_discrete_sequence=["#0d6efd"],
        labels={"x_axis": "", "unique_types": "Hazard Types"},
        category_orders={"x_axis": ordered_x} if ordered_x else {},
    )

    fig.update_traces(
        customdata=diversity[["frame_label", "unique_types"]].values,
        marker_line_width=0,
        opacity=0.85,
        hovertemplate=(
            "<span style='font-size:19px; color:#212529; font-weight:800; line-height:1.2;'>%{customdata[0]}</span><br>"
            "<span style='font-size:16px; color:#0d6efd; font-weight:800;'>Unique Hazards: %{customdata[1]}</span><br>"
            "<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
            "<span style='font-size:11px; color:#6c757d;'>Distinct storm types recorded in this period</span>"
            "<extra></extra>"
        )
    )

    fig.update_layout(
        margin={"l": 0, "r": 20, "t": 5, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=_CHART_FONT,
        hoverlabel=dict(
            bgcolor="white", bordercolor="#dee2e6",
            font_size=13, font_family="system-ui, -apple-system, sans-serif",
            align="left",
        ),
    )
    
    fig.update_xaxes(**_AXIS_STYLE, tickangle=-45 if frame_name == "Month" else 0)
    fig.update_yaxes(**_AXIS_STYLE)
    return fig

def build_animation_context_plot(yearly_df: pd.DataFrame, metric_key: str):
    if yearly_df.empty:
        return empty_figure("Context", "No data")

    metric_label = METRIC_META.get(metric_key, {}).get("label", metric_key)

    mapped = (
        yearly_df.groupby(["frame_sort", "frame_label"], dropna=False)[metric_key]
        .sum()
        .reset_index()
        .sort_values("frame_sort")
    )

    # Detect if the frame is monthly (contains letters like 'Jan') or yearly
    is_monthly = mapped["frame_label"].str.contains(r"[a-zA-Z]").any()

    if is_monthly:
        mapped["x_axis"] = mapped["frame_label"]
    else:
        mapped["x_axis"] = pd.to_datetime(mapped["frame_sort"], errors="coerce").dt.year

    mapped["value_display"] = mapped[metric_key].apply(lambda x: format_metric_value(x, metric_key))

    fig = px.line(
        mapped, x="x_axis", y=metric_key,
        markers=True, height=205, title=None,
        color_discrete_sequence=["#0d6efd"],
        labels={"x_axis": "", metric_key: metric_label},
    )

    fig.update_traces(
        customdata=mapped[["frame_label", "value_display"]].values,
        line=dict(width=2),
        marker=dict(size=5, line=dict(width=1, color="white")),
        hovertemplate=(
            "<span style='font-size:19px; color:#212529; font-weight:800; line-height:1.2;'>%{customdata[0]}</span><br>"
            "<span style='font-size:16px; color:#0d6efd; font-weight:800;'>Storm Count: %{customdata[1]}</span><br>"
            "<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
            "<span style='font-size:11px; color:#6c757d;'>Total statewide records for this period</span>"
            "<extra></extra>"
        )
    )

    fig.update_layout(
        margin={"l": 0, "r": 20, "t": 5, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=_CHART_FONT,
        hoverlabel=dict(
            bgcolor="white", bordercolor="#dee2e6",
            font_size=13, font_family="system-ui, -apple-system, sans-serif",
            align="left",
        ),
    )
    fig.update_xaxes(**_AXIS_STYLE, dtick=10 if not is_monthly else None)
    fig.update_yaxes(**_AXIS_STYLE)
    return fig

def build_weather_correlation_figure(correlation_df: pd.DataFrame):
    if correlation_df.empty:
        return empty_figure("Correlation", "No data")

    plot_data = correlation_df.copy()
    plot_data["corr_display"]   = plot_data["correlation"].apply(lambda x: f"{x:+.2f}")
    plot_data["sample_display"] = plot_data["sample_size"].apply(lambda x: f"{x:,} periods")

    fig = px.bar(
        plot_data, x="correlation", y="metric_label", orientation="h",
        color="direction", title=None, height=450,
        color_discrete_map={"Positive": "#0d6efd", "Negative": "#e63946"},
        labels={"correlation": "Pearson r", "metric_label": ""},
        custom_data=["metric_label", "corr_display", "direction", "sample_display"]
    )

    fig.add_vline(x=0, line_dash="dot", line_color="#adb5bd", line_width=1.5)

    fig.update_traces(
        marker_line_width=0,
        opacity=0.85,
        hovertemplate=(
            "<span style='font-size:19px; color:#212529; font-weight:800; line-height:1.2;'>%{customdata[0]}</span><br>"
            "<span style='font-size:16px; color:#0d6efd; font-weight:800;'>Pearson r: %{customdata[1]}</span><br>"
            "<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Trend Direction:</b> %{customdata[2]}</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Sample Size:</b> %{customdata[3]}</span><br>"
            "<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
            "<span style='font-size:11px; color:#6c757d;'>"
            "Correlation with storm event within mapped periods</span>"
            "<extra></extra>"
        ),
    )

    fig.update_layout(
        margin={"l": 0, "r": 30, "t": 10, "b": 40},
        showlegend=False,
        xaxis={"range": [-1, 1]},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=_CHART_FONT,
        hoverlabel=dict(
            bgcolor="white",
            bordercolor="#dee2e6",
            font_size=13,
            font_family="system-ui, -apple-system, sans-serif",
            align="left",
        ),
    )
    fig.update_xaxes(**_AXIS_STYLE)
    fig.update_yaxes(**_AXIS_STYLE)
    return fig

def build_county_stacked_bar(
    raw_df: pd.DataFrame,
    top_n: int = 10,
):
    working = normalize_dataframe_columns(raw_df.copy())
    if working.empty:
        return empty_figure("", "No data available for this selection.")
    
    geo_column = get_geo_group_column(working)
    prop_col = get_damage_property_column(working)
    crop_col = get_damage_crops_column(working)
    event_id_col = get_event_id_column(working)
    
    if geo_column is None or prop_col is None:
        return empty_figure("", "Required damage columns are missing from the dataset.")
        
    # Clean county names for display
    working["county_name"] = working[geo_column].astype(str).str.strip().str.title()
    
    # Aggregate property damage, crop damage, and event count
    count_source = event_id_col if event_id_col else geo_column
    agg_dict = {
        "Property Damage": (prop_col, "sum"),
        "Event Count": (count_source, "count"),
    }
    if crop_col is not None:
        agg_dict["Crop Damage"] = (crop_col, "sum")
        
    grouped = working.groupby("county_name", dropna=False).agg(**agg_dict).reset_index()
    
    if "Crop Damage" in grouped.columns:
        grouped["Total Damage"] = grouped["Property Damage"] + grouped["Crop Damage"]
    else:
        grouped["Total Damage"] = grouped["Property Damage"]
        grouped["Crop Damage"] = 0.0
        
    grouped = grouped.sort_values("Total Damage", ascending=False).head(top_n)
    grouped = grouped.sort_values("Total Damage", ascending=True)  # Plotly draws bottom-up
    
    if grouped.empty or grouped["Total Damage"].sum() == 0:
        return empty_figure("", "No recorded damage for the current selection.")

    # Pre-format tooltip values on the grouped df before melting
    grouped["total_display"] = grouped["Total Damage"].apply(lambda x: f"${x:,.0f}")
    grouped["prop_display"]  = grouped["Property Damage"].apply(lambda x: f"${x:,.0f}")
    grouped["crop_display"]  = grouped["Crop Damage"].apply(lambda x: f"${x:,.0f}")
    grouped["event_display"] = grouped["Event Count"].apply(lambda x: f"{int(x):,}")
    grouped["prop_pct"]  = (grouped["Property Damage"] / grouped["Total Damage"].replace(0, np.nan) * 100).fillna(0).apply(lambda x: f"{x:.1f}%")
    grouped["crop_pct"]  = (grouped["Crop Damage"]    / grouped["Total Damage"].replace(0, np.nan) * 100).fillna(0).apply(lambda x: f"{x:.1f}%")
    grouped["dmg_per_event"] = (grouped["Total Damage"] / grouped["Event Count"].replace(0, np.nan)).fillna(0).apply(lambda x: f"${x:,.0f}")
        
    value_vars = ["Property Damage", "Crop Damage"] if "Crop Damage" in grouped.columns else ["Property Damage"]
    melted = grouped.melt(
        id_vars=["county_name", "total_display", "prop_display", "crop_display",
                 "event_display", "prop_pct", "crop_pct", "dmg_per_event"],
        value_vars=value_vars,
        var_name="Damage Type",
        value_name="Amount",
    )
    melted["Amount_Display"] = melted["Amount"].apply(lambda x: f"${x:,.0f}")
    melted["pct_display"] = np.where(
        melted["Damage Type"] == "Property Damage", melted["prop_pct"], melted["crop_pct"]
    )
    
    fig = px.bar(
        melted, y="county_name", x="Amount", color="Damage Type",
        orientation="h", title=None, height=205,
        color_discrete_map={"Property Damage": "#0d6efd", "Crop Damage": "#f4a261"},
        labels={"county_name": "", "Amount": "Total Damage ($)"},
    )

    # Per-trace custom tooltips (one per damage type)
    for trace in fig.data:
        dtype = trace.name  # "Property Damage" or "Crop Damage"
        mask = melted["Damage Type"] == dtype
        trace_data = melted[mask]
        trace.customdata = trace_data[[
            "county_name", "Amount_Display", "pct_display",
            "total_display", "event_display", "dmg_per_event",
        ]].values
        
        trace_color = "#f4a261" if dtype == "Crop Damage" else "#0d6efd"
        
        # Consistent 19px/16px/13px hierarchy
        trace.hovertemplate = (
            "<span style='font-size:19px; color:#212529; font-weight:800; line-height:1.2;'>%{customdata[0]} County</span><br>"
            f"<span style='font-size:16px; color:{trace_color}; font-weight:800;'>{dtype}: %{{customdata[1]}}</span> "
            "<span style='color:#6c757d; font-size:13px;'>(%{customdata[2]} of total)</span><br>"
            "<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>County Total Damage:</b> %{customdata[3]}</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Storm Event:</b> %{customdata[4]}</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Avg Damage / Event:</b> %{customdata[5]}</span>"
            "<extra></extra>"
        )

    fig.update_layout(
        barmode="stack",
        margin={"l": 0, "r": 20, "t": 5, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=_CHART_FONT,
        legend=dict(
            title="",
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            font=dict(size=11, color="#6c757d"),
        ),
        hoverlabel=dict(
            bgcolor="white",
            bordercolor="#dee2e6",
            font_size=13,
            font_family="system-ui, -apple-system, sans-serif",
            align="left",
        ),
    )
    fig.update_xaxes(**_AXIS_STYLE)
    fig.update_yaxes(**_AXIS_STYLE)
    return fig


def build_county_scatter(
    county_data: pd.DataFrame,
    title: str,
    subtitle: str | None = None,
):
    if county_data.empty:
        return empty_figure(title, "No county data available for this selection.")

    plot_data = county_data.copy()
    
    # Handle NaNs to prevent plotting errors
    for col in ("property_damage", "event_count", "injuries_direct", "deaths_direct", "risk_score"):
        if col not in plot_data.columns:
            plot_data[col] = 0.0
        plot_data[col] = plot_data[col].fillna(0)
    
    # Bubble size: injuries + baseline so zero-injury counties still render
    plot_data["bubble_size"] = plot_data["injuries_direct"] + 1

    # Damage per event ratio
    plot_data["dmg_per_event"] = (
        plot_data["property_damage"] / plot_data["event_count"].replace(0, np.nan)
    ).fillna(0)

    # Pre-format all tooltip values
    plot_data["event_display"]    = plot_data["event_count"].apply(lambda x: f"{int(x):,}")
    plot_data["damage_display"]   = plot_data["property_damage"].apply(lambda x: f"${x:,.0f}")
    plot_data["injuries_display"] = plot_data["injuries_direct"].apply(lambda x: f"{int(x):,}")
    plot_data["deaths_display"]   = plot_data["deaths_direct"].apply(lambda x: f"{int(x):,}")
    plot_data["risk_display"]     = plot_data["risk_score"].apply(lambda x: f"{x:,.1f}")
    plot_data["dpe_display"]      = plot_data["dmg_per_event"].apply(lambda x: f"${x:,.0f}")

    fig = px.scatter(
        plot_data,
        x="event_count",
        y="property_damage",
        size="bubble_size",
        color="risk_score",
        color_continuous_scale=COUNTY_MAP_COLORSCALE,  # Matches the county map
        title=None,
        height=205,
        labels={"event_count": "Storm Events", "property_damage": "Property Damage ($)"},
    )
    
    fig.update_traces(
        customdata=plot_data[[
            "county_name",    # 0
            "risk_display",   # 1
            "event_display",  # 2
            "damage_display", # 3
            "dpe_display",    # 4
            "injuries_display", # 5
            "deaths_display",   # 6
        ]].values,
        marker=dict(
            line=dict(width=1, color="#dee2e6"),
            opacity=0.75,
        ),
        hovertemplate=(
            "<span style='font-size:19px; color:#212529; font-weight:800; line-height:1.2;'>%{customdata[0]} County</span><br>"
            "<span style='font-size:16px; color:#0d6efd; font-weight:800;'>Risk Score: %{customdata[1]}</span><br>"
            "<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Storm Event:</b> %{customdata[2]}</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Property Damage:</b> %{customdata[3]}</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Avg Damage / Event:</b> %{customdata[4]}</span><br>"
            "<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Direct Injuries:</b> %{customdata[5]}</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Direct Deaths:</b> %{customdata[6]}</span><br>"
            "<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
            "<span style='font-size:11px; color:#6c757d;'>Bubble size = human impact (Injuries & Deaths)</span>"
            "<extra></extra>"
        ),
    )
    
    fig.update_layout(
        margin={"l": 0, "r": 20, "t": 5, "b": 30},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=_CHART_FONT,
        coloraxis_showscale=False,
        hoverlabel=dict(
            bgcolor="white",
            bordercolor="#dee2e6",
            font_size=13,
            font_family="system-ui, -apple-system, sans-serif",
            align="left",
        ),
    )
    fig.update_xaxes(**_AXIS_STYLE)
    fig.update_yaxes(**_AXIS_STYLE)
    return fig


def build_overview_donut(hazard_data: pd.DataFrame):
    """Donut chart for the Overview tab — hazard composition with center total annotation."""
    if hazard_data.empty:
        return empty_figure("Hazards", "No data")

    plot_data = hazard_data.sort_values("event_count", ascending=False).copy()
    top_5     = plot_data.head(5).copy()
    other_sum = plot_data.iloc[5:]["event_count"].sum() if len(plot_data) > 5 else 0
    if other_sum > 0:
        other_row = pd.DataFrame({"event_type": ["Other hazards"], "event_count": [other_sum]})
        final_data = pd.concat([top_5, other_row], ignore_index=True)
    else:
        final_data = top_5.copy()

    total = final_data["event_count"].sum()
    final_data["pct"]           = (final_data["event_count"] / total * 100).round(1)
    final_data["count_display"] = final_data["event_count"].apply(lambda x: f"{int(x):,}")

    # Only show percent labels on slices >= 7% — smaller ones are too crowded
    final_data["label_text"] = final_data["pct"].apply(
        lambda p: f"{p:.1f}%" if p >= 7 else ""
    )

    # Pre-build hover strings — go.Pie doesn't resolve customdata[] in hovertemplate
    final_data["hover_text"] = final_data.apply(
        lambda r: (
            f"<span style='font-size:19px; color:#212529; font-weight:800;'>{r['event_type']}</span><br>"
            f"<span style='font-size:16px; color:#0d6efd; font-weight:800;'>{r['count_display']} events</span><br>"
            f"<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
            f"<span style='color:#495057; font-size:13px;'><b>Share of total:</b> {r['pct']:.1f}%</span>"
        ), axis=1
    )

    fig = go.Figure(go.Pie(
        labels=final_data["event_type"],
        values=final_data["event_count"],
        hole=0.62,
        marker=dict(
            colors=BRAND_PALETTE[:len(final_data)],
            line=dict(color="#ffffff", width=2),
        ),
        text=final_data["label_text"],
        textinfo="text",
        textposition="inside",
        textfont=dict(size=12, color="white",
                      family="system-ui, -apple-system, sans-serif"),
        hovertext=final_data["hover_text"],
        hovertemplate="%{hovertext}<extra></extra>",
        # Ring fills the left portion, legend occupies the right
        domain=dict(x=[0.0, 0.65], y=[0.05, 0.95]),
        showlegend=True,
    ))

    # Center annotations — true center of ring domain x=[0.0,0.65] y=[0.05,0.95]
    # center_x = 0.325, center_y = 0.5
    fig.add_annotation(
        text=f"<b>{int(total):,}</b>",
        x=0.325, y=0.535, xanchor="center", yanchor="middle",
        showarrow=False,
        font=dict(size=22, color="#212529",
                  family="system-ui, -apple-system, sans-serif"),
    )
    fig.add_annotation(
        text="TOTAL EVENTS",
        x=0.325, y=0.445, xanchor="center", yanchor="middle",
        showarrow=False,
        font=dict(size=10, color="#6c757d",
                  family="system-ui, -apple-system, sans-serif"),
    )

    fig.update_layout(
        height=450,
        margin={"l": 0, "r": 0, "t": 10, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=_CHART_FONT,
        showlegend=True,
        legend=dict(
            orientation="v",
            x=0.68, y=0.5,
            xanchor="left", yanchor="middle",
            font=dict(size=12, color="#6c757d"),
            itemsizing="constant",
            traceorder="normal",
        ),
        hoverlabel=dict(
            bgcolor="white", bordercolor="#dee2e6",
            font_size=13, font_family="system-ui, -apple-system, sans-serif",
            align="left",
        ),
    )
    return fig


def build_hazard_comparison(hazard_data: pd.DataFrame, metric_key: str, selected_hazard: str, weather_context: bool = False):
    if hazard_data.empty:
        return empty_figure("Comparison", "No data")

    metric_label = METRIC_META[metric_key]["label"]
    plot_data = hazard_data.head(10).sort_values(metric_key, ascending=True).copy()
    plot_data["highlight"] = np.where(plot_data["event_type"].eq(selected_hazard), "Selected", "Other")

    plot_data["metric_display"]  = plot_data[metric_key].apply(lambda x: format_metric_value(x, metric_key))
    plot_data["events_display"]  = plot_data["event_count"].apply(lambda x: format_metric_value(x, "event_count")) if "event_count" in plot_data.columns else "N/A"
    plot_data["damage_display"]  = plot_data["property_damage"].apply(lambda x: format_metric_value(x, "property_damage")) if "property_damage" in plot_data.columns else "N/A"
    plot_data["precip_display"]  = plot_data["avg_precip"].apply(lambda x: format_metric_value(x, "avg_precip")) if "avg_precip" in plot_data.columns else "N/A"
    plot_data["tmax_display"]    = plot_data["avg_tmax"].apply(lambda x: format_metric_value(x, "avg_tmax")) if "avg_tmax" in plot_data.columns else "N/A"
    plot_data["wind_display"]    = plot_data["avg_wind"].apply(lambda x: format_metric_value(x, "avg_wind")) if "avg_wind" in plot_data.columns else "N/A"
    plot_data["snow_display"]    = plot_data["avg_snow"].apply(lambda x: format_metric_value(x, "avg_snow")) if "avg_snow" in plot_data.columns else "N/A"

    if weather_context:
        # MODE: Weather Context Tab (Statewide Comparison)
        hover_cols    = ["event_type", "metric_display", "events_display", "precip_display", "tmax_display", "wind_display", "snow_display"]
        hovertemplate = (
            "<span style='font-size:19px; color:#212529; font-weight:800; line-height:1.2;'>%{customdata[0]}</span><br>"
            f"<span style='font-size:16px; color:#0d6efd; font-weight:800;'>{metric_label}: %{{customdata[1]}}</span><br>"
            "<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Storm Event:</b> %{customdata[2]}</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Avg Precipitation:</b> %{customdata[3]}</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Avg Max Temp:</b> %{customdata[4]}</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Avg Wind Speed:</b> %{customdata[5]}</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Avg Snowfall:</b> %{customdata[6]}</span>"
            "<extra></extra>"
        )
    else:
        # MODE: Standard Comparison (Explorer or Overview)
        hover_cols    = ["event_type", "metric_display", "events_display", "damage_display"]
        hovertemplate = (
            "<span style='font-size:19px; color:#212529; font-weight:800; line-height:1.2;'>%{customdata[0]}</span><br>"
            f"<span style='font-size:16px; color:#0d6efd; font-weight:800;'>{metric_label}: %{{customdata[1]}}</span><br>"
            "<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Storm Event:</b> %{customdata[2]}</span><br>"
            "<span style='color:#495057; font-size:13px;'><b>Property Damage:</b> %{customdata[3]}</span>"
            "<extra></extra>"
        )

    fig = px.bar(
        plot_data, x=metric_key, y="event_type", orientation="h",
        title=None, height=205,
        color="highlight",
        color_discrete_map={"Selected": "#0d6efd", "Other": "#93c5fd"},
        labels={"event_type": "", metric_key: metric_label},
    )
    fig.update_traces(
        customdata=plot_data[hover_cols].values,
        marker_line_width=0,
        opacity=0.85,
        hovertemplate=hovertemplate,
    )

    fig.update_layout(
        margin={"l": 0, "r": 20, "t": 10, "b": 40},
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=_CHART_FONT,
        hoverlabel=dict(
            bgcolor="white",
            bordercolor="#dee2e6",
            font_size=13,
            font_family="system-ui, -apple-system, sans-serif",
            align="left",
        ),
    )
    fig.update_xaxes(**_AXIS_STYLE)
    fig.update_yaxes(**_AXIS_STYLE)
    return fig


def build_trend_counts_figure(df: pd.DataFrame, subtitle: str | None = None):
    working = normalize_dataframe_columns(df.copy())
    event_type_column = get_hazard_display_column(working)
    date_column = get_begin_date_column(working)
    count_source = get_event_id_column(working) or date_column
    
    if working.empty or event_type_column is None or date_column is None:
        return empty_figure("Storm Activity", "No hazard or date column is available for trends.")

    framed, frame_name = add_time_frame(working, date_column)
    if framed.empty or frame_name is None:
        return empty_figure("Storm Activity", "No dated storm records are available.")

    framed["event_type"] = framed[event_type_column].astype("string").fillna("Unknown").str.strip()
    top_hazards = framed["event_type"].value_counts().head(6).index
    framed["hazard_group"] = framed["event_type"].where(framed["event_type"].isin(top_hazards), "Other hazards")

    if frame_name == "Month":
        framed["grouping_key"] = framed["frame_sort"]
        framed["grouping_label"] = framed["frame_label"]
        x_title = "Month"
    else:
        framed["year"] = framed["frame_sort"].dt.year
        framed["grouping_key"] = (framed["year"] // 10 * 10)
        framed["grouping_label"] = framed["grouping_key"].astype(str) + "s"
        x_title = "Decade"

    trend_data = (
        framed.groupby(["grouping_key", "grouping_label", "hazard_group"], dropna=False)
        .agg(event_count=(count_source, "count"))
        .reset_index()
        .sort_values("grouping_key")
    )

    # When monthly, fill gaps so every month appears (even months with zero events)
    # and build an ordered label list to prevent Plotly's alphabetical re-sort.
    if frame_name == "Month":
        full_range = pd.date_range(
            framed["frame_sort"].min(),
            framed["frame_sort"].max(),
            freq="MS",
        )
        all_hazard_groups = trend_data["hazard_group"].unique()
        idx = pd.MultiIndex.from_product(
            [full_range, all_hazard_groups],
            names=["grouping_key", "hazard_group"],
        )
        full_grid = idx.to_frame(index=False)
        full_grid["grouping_label"] = pd.to_datetime(full_grid["grouping_key"]).dt.strftime("%b %Y")
        trend_data = full_grid.merge(
            trend_data[["grouping_key", "grouping_label", "hazard_group", "event_count"]],
            on=["grouping_key", "grouping_label", "hazard_group"],
            how="left",
        )
        trend_data["event_count"] = trend_data["event_count"].fillna(0).astype(int)
        trend_data = trend_data.sort_values("grouping_key")
    ordered_labels = list(
        trend_data.drop_duplicates("grouping_key").sort_values("grouping_key")["grouping_label"]
    )

    # Pre-compute totals for tooltip
    totals = trend_data.groupby("grouping_label")["event_count"].sum().to_dict()
    trend_data["total"] = trend_data["grouping_label"].map(totals)
    trend_data["pct_of_total"] = (trend_data["event_count"] / trend_data["total"].replace(0, np.nan) * 100).fillna(0).round(1)
    
    trend_data["total_display"] = trend_data["total"].apply(lambda x: f"{int(x):,}")
    trend_data["count_display"] = trend_data["event_count"].apply(lambda x: f"{int(x):,}")
    trend_data["pct_display"] = trend_data["pct_of_total"].apply(lambda x: f"{x:.1f}%")

    fig = px.bar(
        trend_data,
        x="grouping_label",
        y="event_count",
        color="hazard_group",
        color_discrete_sequence=BRAND_PALETTE,
        title=None,
        labels={"grouping_label": x_title, "event_count": "Storm Events", "hazard_group": "Hazard"},
        height=510,
        barmode="stack",
        custom_data=["hazard_group", "count_display", "pct_display", "total_display", "grouping_label"],
        category_orders={"grouping_label": ordered_labels},
    )

    for trace in fig.data:
        hazard_name = trace.name
        hazard_color = trace.marker.color 
        trace.hovertemplate = (
            f"<span style='font-size:19px; color:{hazard_color}; font-weight:800; line-height:1.2;'>%{{customdata[4]}} {hazard_name}</span><br>"
            "<span style='font-size:16px; color:#0d6efd; font-weight:800;'>Storm Count: %{customdata[1]}</span><br>"
            "<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
            "<span style='font-size:11px; color:#6c757d;'>Contribution to periodic storm volume</span>"
            "<extra></extra>"
        )
    
    fig.update_layout(
        legend_title_text="",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            font=dict(size=11, color="#495057"),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
        ),
        margin={"l": 10, "r": 10, "t": 40, "b": 40},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=_CHART_FONT,
        hoverlabel=dict(
            bgcolor="white", bordercolor="#dee2e6",
            font_size=13, font_family="system-ui, -apple-system, sans-serif",
            align="left",
        ),
        xaxis_title=x_title,
        yaxis_title="Storm Events",
    )
    fig.update_xaxes(**_AXIS_STYLE, title_font={"size": 11, "color": "#6c757d"})
    fig.update_yaxes(**_AXIS_STYLE, title_font={"size": 11, "color": "#6c757d"})
    return fig


def build_trend_damage_figure(df: pd.DataFrame, subtitle: str | None = None):
    working = normalize_dataframe_columns(df.copy())
    date_column = get_begin_date_column(working)
    prop_col = get_damage_property_column(working)
    crop_col = get_damage_crops_column(working)
    if working.empty or date_column is None or prop_col is None:
        return empty_figure("Financial Toll", "No dated damage records are available.")

    # REMOVED preferred_frame="Year" so it dynamically shifts to Month in Live Mode
    framed, frame_name = add_time_frame(working, date_column)
    if framed.empty or frame_name is None:
        return empty_figure("Financial Toll", "No dated damage records are available.")

    agg_kwargs = {"property_damage": (prop_col, "sum")}
    if crop_col is not None:
        agg_kwargs["crop_damage"] = (crop_col, "sum")

    damage_data = (
        framed.groupby(["frame_sort", "frame_label"], dropna=False)
        .agg(**agg_kwargs)
        .reset_index()
        .sort_values("frame_sort")
    )
    if crop_col is not None:
        damage_data["total_damage"] = damage_data["property_damage"] + damage_data["crop_damage"]
    else:
        damage_data["total_damage"] = damage_data["property_damage"]

    # When monthly, fill gaps so every month in the window appears
    if frame_name == "Month":
        full_range = pd.date_range(
            damage_data["frame_sort"].min(),
            damage_data["frame_sort"].max(),
            freq="MS",
        )
        full_df = pd.DataFrame({
            "frame_sort": full_range,
            "frame_label": full_range.strftime("%b %Y"),
        })
        damage_data = full_df.merge(damage_data, on=["frame_sort", "frame_label"], how="left")
        damage_data["property_damage"] = damage_data["property_damage"].fillna(0)
        if crop_col is not None:
            damage_data["crop_damage"] = damage_data["crop_damage"].fillna(0)
        damage_data["total_damage"] = damage_data["total_damage"].fillna(0)

    # Dynamically set the X-axis plotting column
    if frame_name == "Year":
        damage_data["x_axis"] = pd.to_datetime(damage_data["frame_sort"], errors="coerce").dt.year
        x_title = "Year"
        ordered_x = None
    else:
        # Use the string label so tick text is always visible; lock order via
        # category_orders to prevent Plotly alphabetical re-sort.
        damage_data["x_axis"] = damage_data["frame_label"]
        x_title = "Month"
        ordered_x = list(damage_data["frame_label"])

    damage_data["damage_display"]   = damage_data["total_damage"].apply(lambda x: f"${x:,.0f}")
    damage_data["prop_display"]     = damage_data["property_damage"].apply(lambda x: f"${x:,.0f}")
    damage_data["crop_display"]     = damage_data.get("crop_damage", pd.Series(0, index=damage_data.index)).apply(lambda x: f"${x:,.0f}")

    fig = px.bar(
        damage_data, x="x_axis", y="total_damage",
        title=None,
        labels={"x_axis": x_title, "total_damage": "Total Damage ($)"},
        height=235,
        category_orders={"x_axis": ordered_x} if ordered_x else {},
    )
    
    fig.update_traces(
        marker_color="#0d6efd",
        marker_line_width=0,
        opacity=0.85,
        customdata=damage_data[["frame_label", "damage_display", "prop_display", "crop_display"]].values,
        hovertemplate=(
            "<span style='font-size:19px; color:#212529; font-weight:800; line-height:1.2;'>%{customdata[0]} Economic Impact</span><br>"
            "<span style='font-size:16px; color:#0d6efd; font-weight:800;'>Total Damage: %{customdata[1]}</span><br>"
            "<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
            "<span style='font-size:13px; color:#495057;'><b>Property Loss:</b> %{customdata[2]}</span><br>"
            "<span style='font-size:13px; color:#495057;'><b>Crop Loss:</b> %{customdata[3]}</span>"
            "<extra></extra>"
        ),
    )

    fig.update_layout(
        margin={"l": 10, "r": 10, "t": 10, "b": 40},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=_CHART_FONT,
        xaxis_title=x_title,
        yaxis_title="Total Damage ($)",
        hoverlabel=dict(
            bgcolor="white", bordercolor="#dee2e6",
            font_size=13, font_family="system-ui, -apple-system, sans-serif",
            align="left",
        ),
    )
    
    fig.update_xaxes(
        **_AXIS_STYLE,
        dtick=10 if frame_name == "Year" else None,
        tickangle=-45 if frame_name == "Month" else 0,
        title_font={"size": 11, "color": "#6c757d"},
    )
    fig.update_yaxes(**_AXIS_STYLE, title_font={"size": 11, "color": "#6c757d"})
    return fig


def build_storm_season_heatmap(df: pd.DataFrame):
    """Monthly heatmap: hazard type × month, colored by historical event frequency."""
    working = normalize_dataframe_columns(df.copy())
    date_col = get_begin_date_column(working)
    hazard_col = get_hazard_display_column(working)

    if working.empty or date_col is None or hazard_col is None:
        return empty_figure("Season", "No data available.")

    working[date_col] = pd.to_datetime(working[date_col], errors="coerce")
    working = working.dropna(subset=[date_col])
    working["month"] = working[date_col].dt.month
    working["hazard"] = working[hazard_col].astype("string").fillna("Unknown").str.strip()

    # Keep only the top 10 most frequent hazard types
    top_hazards = working["hazard"].value_counts().head(10).index.tolist()
    working = working[working["hazard"].isin(top_hazards)].copy()

    counts = (
        working.groupby(["hazard", "month"])
        .size()
        .reset_index(name="count")
    )
    pivot = (
        counts.pivot(index="hazard", columns="month", values="count")
        .reindex(columns=range(1, 13), fill_value=0)
        .fillna(0)
    )
    # Most active hazard at top
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]

    MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=MONTH_LABELS,
        y=pivot.index.tolist(),
        colorscale=COUNTY_MAP_COLORSCALE,
        showscale=False,
        hoverongaps=False,
        hovertemplate=(
                "<span style='font-size:19px; color:#212529; font-weight:800; line-height:1.2;'>%{y} Intensity</span><br>"
                "<span style='font-size:16px; color:#0d6efd; font-weight:800;'>Events: %{z:.0f}</span><br>"
                "<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
                "<span style='color:#495057; font-size:13px;'><b>Active Month:</b> %{x}</span>"
                "<extra></extra>"
        ),
    ))
    fig.update_layout(
        height=235,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=_CHART_FONT,
        hoverlabel=dict(
            bgcolor="white", bordercolor="#dee2e6",
            font_size=13, font_family="system-ui, -apple-system, sans-serif",
            align="left",
        ),
    )
    fig.update_xaxes(
        tickfont={"color": "#495057", "size": 11},
        gridcolor="#f0f0f2", linecolor="#e9ecef",
        title_text="",
    )
    fig.update_yaxes(
        tickfont={"color": "#495057", "size": 10},
        gridcolor="#f0f0f2", linecolor="#e9ecef",
        autorange="reversed",
        title_text="",
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# UI LAYOUT  (app_ui)
# Defines the complete HTML/CSS structure of the dashboard.
#
# TOP LEVEL
#   Global <style> block – all custom CSS lives here; Bootstrap classes handle
#                          the rest via Shiny's bslib defaults
#   .app-header            – centered title, subtitle, byline
#   ui.layout_sidebar      – sidebar (filters) + main content area (tabs)
#
# SIDEBAR
#   Live Feed toggle       – switches between historical window and recent-N-months
#   Year Scope slider      – date range filter (historical mode only)
#   Past Months radio      – lookback window selector (live mode only)
#   County Focus text      – free-text county name filter
#
# TABS
#   Overview          – KPI boxes, county risk map, top-risk table, summary
#   County Impacts    – per-county choropleth + scatter + stacked bar
#   Weather Context   – weather metric maps & correlation chart
#   Time Progression  – slider-driven county map + hazard diversity chart
#   Statewide Trends  – decadal hazard mix + annual damage + season heatmap
#   Live Alerts       – real-time NWS severe weather alerts (state-configurable)
# ═══════════════════════════════════════════════════════════════════════════════

app_ui = ui.page_fluid(
    ui.tags.style(
        """
        body {
            font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", "Noto Sans", "Liberation Sans", Arial, sans-serif;
            background-color: #ffffff;
        }

        /* --- 1. Main Header Branding --- */
        .app-header { 
            padding: 20px 0 30px 0; 
            text-align: center; 
        }
        .main-title {
            font-size: 3rem; 
            font-weight: 800; 
            color: #212529;
            margin: 0 0 14px 0; 
            display: inline-block; 
            position: relative; 
            letter-spacing: -0.5px;
        }
        .main-title::after {
            content: ""; 
            position: absolute; 
            left: -10%; 
            bottom: -2px; 
            width: 120%; 
            height: 3px; 
            background-color: #0d6efd; 
            border-radius: 10px;
        }
        .sub-title {
            font-size: 0.85rem; 
            color: #6c757d; 
            font-weight: 600;
            text-transform: uppercase; 
            letter-spacing: 1.5px;
        }
        .byline-text {
            font-size: 0.75rem;
            margin: 8px auto 0 auto;
            color: #adb5bd;
            font-weight: 500;
        }

        /* --- 2. Sidebar Layout & Container --- */
        .sidebar-container { 
            display: flex; 
            flex-direction: column; 
            align-items: center; 
            width: 100%; 
            padding: 10px 0;
        }
        
        .sidebar-title {
            font-size: 1.25rem; 
            font-weight: 700; 
            color: #212529;
            margin: 0 0 25px 0; 
            display: inline-block; 
            position: relative;
            text-transform: uppercase; 
            letter-spacing: 1px;
            border: none !important;
            line-height: 1;
        }
        .sidebar-title::after {
            content: ""; 
            position: absolute; 
            left: -15%; 
            bottom: 10px; 
            width: 130%; 
            height: 2px; 
            background-color: #0d6efd; 
            border-radius: 10px;
        }

        /* --- 3. Modernized Live Feed Toggle --- */
        .live-feed-wrapper {
            display: flex;
            align-items: center;
            justify-content: space-between;
            width: 100%;
            padding: 12px 16px;
            background-color: #f8f9fa;
            border-radius: 12px;
            margin-bottom: 0px;
            border: 1px solid #e9ecef;
            transition: all 0.3s ease;
        }
        .live-feed-wrapper:has(input:checked) {
            background-color: #f0f7ff;
            border-color: #cce3fd;
        }
        .live-feed-text {
            font-size: 1rem;
            font-weight: 700;
            color: #495057;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin: 0;
            user-select: none;
            white-space: nowrap; 
        }
        .live-feed-wrapper .form-check.form-switch {
            margin: 0 !important;
            padding-left: 0 !important; 
            display: flex !important;
            align-items: center !important;
            justify-content: flex-end; 
            min-width: 50px;
        }
        .live-feed-wrapper .form-check-input {
            width: 46px !important;
            height: 24px !important;
            margin: 0 !important;
            cursor: pointer;
            background-color: #ced4da;
            border: none;
            box-shadow: none !important;
            border-radius: 50px;
            transition: background-color 0.2s ease;
            float: none !important; 
            transform: translateY(14px);
        }
        .live-feed-wrapper .form-check-input:checked {
            background-color: #0d6efd;
        }

        /* --- 4. Secondary Labels & Spacing --- */
        .sidebar-label {
            font-size: 0.75rem; 
            font-weight: 700; 
            color: #6c757d;
            text-transform: uppercase; 
            letter-spacing: 1.5px;
            margin-top: 50px;
            margin-bottom: 15px; 
            text-align: center;
        }

        /* --- 5. Segmented Radio Button Grid --- */
        .shiny-options-group {
            display: grid !important;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            width: 100%;
        }
        .shiny-options-group .form-check { padding: 0; margin: 0; }
        .shiny-options-group input[type="radio"] { display: none; }
        .shiny-options-group label {
            display: flex; align-items: center; justify-content: center;
            height: 48px; background: #ffffff; border: 1px solid #dee2e6;
            border-radius: 8px; font-size: 0.8rem; font-weight: 600;
            color: #495057; cursor: pointer; transition: all 0.2s;
            margin: 0;
        }
        .shiny-options-group input[type="radio"]:checked + span {
            background-color: #0d6efd; color: white; border-color: #0d6efd;
            display: flex; align-items: center; justify-content: center;
            width: 100%; height: 100%; border-radius: 8px;
        }

        /* --- 6. Input Box Styling --- */
        .shiny-input-container input {
            text-align: center; 
            border-radius: 8px; 
            height: 48px; 
            border: 1px solid #dee2e6;
        }
        .sidebar-footer-text {
            font-size: 0.75rem;
            color: #adb5bd;
            margin-top: 0px;
            max-width: 220px;
            line-height: 1.4;
            text-align: center;
        }

        /* --- 7. Modern Navigation Tabs --- */
        .nav-tabs {
            border-bottom: 2px solid #e9ecef;
            margin-bottom: 5px;
            gap: 5px; 
        }
        .nav-tabs .nav-link {
            color: #adb5bd;
            font-weight: 700;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            border: none !important;
            padding: 12px 20px;
            margin-bottom: -2px;
            transition: all 0.2s ease;
            background: transparent !important;
            position: relative;
        }
        .nav-tabs .nav-link:hover { color: #6c757d; }
        .nav-tabs .nav-link.active { color: #0d6efd !important; }
        .nav-tabs .nav-link.active::after {
            content: "";
            position: absolute;
            bottom: 0;
            left: 10%;
            width: 80%;
            height: 3px;
            background-color: #0d6efd;
            border-radius: 10px 10px 0 0;
        }
        .tab-copy {
            font-size: 0.95rem;
            color: #6c757d;
            margin-bottom: 0px;
            line-height: 1.5;
            max-width: 800px;
        }

        /* --- 8. Polished Dropdowns (Fixing the Ghosting) --- */
        .shiny-input-container {
            width: 100% !important;
            margin-bottom: 30px !important;
        }

        .control-label {
            display: block !important;
            text-align: center !important;
            width: 100% !important;
            font-size: 0.7rem !important; 
            font-weight: 800 !important; 
            color: #adb5bd !important;
            text-transform: uppercase !important; 
            letter-spacing: 2px !important;
            margin-bottom: 12px !important;
        }

        /* Style for BOTH standard selects (Map Metric) and Selectize (Hazards) */
        .form-select, 
        .selectize-input, 
        .selectize-control.single .selectize-input {
            width: 100% !important;
            max-width: 340px !important;
            margin: 0 auto !important;
            height: 46px !important;
            border-radius: 10px !important;
            border: 1px solid #e9ecef !important;
            background-color: #ffffff !important;
            font-size: 0.85rem !important;
            color: #212529 !important;
            font-weight: 600 !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02) !important;
            display: flex !important;
            align-items: center !important;
            padding: 0 15px !important;
            transition: all 0.2s ease !important;
        }

        /* THE SECRET SAUCE: Only hide the "ghost" input if it's part of a selectize control */
        .selectize-control .form-control, 
        .selectize-control .shiny-input-select {
            display: none !important;
        }

        /* Keep the standard Map Metric dropdown visible */
        select.form-select {
            display: flex !important;
            appearance: none; /* Removes the default browser arrow for a cleaner look */
            background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3e%3cpath fill='none' stroke='%23343a40' stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='m2 5 6 6 6-6'/%3e%3c/svg%3e");
            background-repeat: no-repeat;
            background-position: right 0.75rem center;
            background-size: 16px 12px;
        }

        /* --- 9. Plotly Title Overrides --- */
        .gtitle {
            font-size: 1.1rem !important;
            font-weight: 800 !important;
            fill: #212529 !important;
            letter-spacing: -0.5px !important;
        }
        .gsubtitle {
            font-size: 0.75rem !important;
            fill: #adb5bd !important;
            font-weight: 500 !important;
        }

        /* --- 10. Chart Cards ---
             Same white-card + blue-accent language as the header/sidebar/tabs.
             The top border echoes the ::after underline on titles. */
        .widget-output {
            background: #ffffff;
            border-radius: 12px;
            border: 1px solid #e9ecef;
            border-top: 3px solid #0d6efd;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
            padding: 8px 4px 4px 4px;
            margin-bottom: 20px;
            overflow: hidden;
        }

        /* Hide the Plotly hover menu globally */
        .modebar {
            display: none !important;
        }   

        /* --- 11. Info / Summary Cards ---
             Mirrors the live-feed-wrapper style: light gray bg, blue left accent. */
        .info-card {
            background-color: #f8f9fa;
            border: 1px solid #e9ecef;
            border-left: 3px solid #0d6efd;
            border-radius: 10px;
            padding: 14px 18px;
            margin-top: 8px;
            margin-bottom: 20px;
            font-size: 0.88rem;
            line-height: 1.7;
            color: #495057;
        }
        .info-card strong { color: #212529; }

        /* --- 12. Top Risk Counties Table ---
             Uses the same border-top accent as chart cards. */
        .risk-table-card {
            background: #ffffff;
            border-radius: 12px;
            border: 1px solid #e9ecef;
            border-top: 3px solid #0d6efd;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
            padding: 20px 22px;
            margin-bottom: 20px;
        }
        .risk-table-card h4 {
            font-size: 1rem;
            font-weight: 800;
            color: #212529;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin: 0 0 4px 0;
        }
        .risk-table-card .table {
            font-size: 0.84rem;
            margin-bottom: 10px;
        }
        .risk-table-card .table thead th {
            font-size: 0.68rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            color: #adb5bd;
            border-bottom: 2px solid #e9ecef;
            background: transparent;
            padding: 8px 10px;
        }
        .risk-table-card .table tbody td {
            padding: 10px 10px;
            border-bottom: 1px solid #f0f2f5;
            vertical-align: middle;
            color: #343a40;
        }
        .risk-table-card .table tbody tr:last-child td { border-bottom: none; }
        .risk-table-card .table-striped > tbody > tr:nth-of-type(odd) > td {
            background-color: #f8f9fa;
        }
        .risk-table-card .tab-copy { font-size: 0.78rem; color: #6c757d; margin: 0; }

        /* --- 13. Chart Section Headers ---
             Matches the uppercase label language used in the sidebar and risk
             table. A subtle blue left-border ties it to the card accent color. */
        .chart-header {
            font-size: 0.75rem;
            font-weight: 800;
            color: #6c757d;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin: 8px 0 6px 0;
            padding-left: 10px;
            border-left: 3px solid #0d6efd;
            line-height: 1.4;
        }

        /* --- 14. Live Alert Cards ---
             Same card shape; left accent in red to signal severity. */
        @keyframes livepulse {
            0%, 100% { opacity: 1; }
            50%       { opacity: 0.3; }
        }
        .live-dot {
            display: inline-block;
            width: 9px; height: 9px;
            border-radius: 50%;
            background: #22c55e;
            animation: livepulse 2s ease-in-out infinite;
            margin-right: 8px;
            flex-shrink: 0;
        }
        .live-status-bar {
            display: flex;
            align-items: center;
            padding: 12px 18px;
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-left: 3px solid #22c55e;
            border-radius: 10px;
            margin-bottom: 20px;
            gap: 6px;
            flex-wrap: wrap;
        }
        .alerts-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 14px;
        }
        .alert-card-v2 {
            background: #ffffff;
            border-radius: 10px;
            border: 1px solid #e9ecef;
            padding: 16px 18px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.04);
            transition: box-shadow 0.2s ease;
        }
        .alert-card-v2:hover { box-shadow: 0 4px 14px rgba(0,0,0,0.09); }
        .severity-badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 999px;
            font-size: 0.65rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 1px;
            white-space: nowrap;
        }
        .no-alerts-state {
            text-align: center;
            padding: 60px 20px;
            color: #6c757d;
        }
        .no-alerts-state .check-icon {
            font-size: 2.5rem;
            color: #22c55e;
            margin-bottom: 14px;
        }
        .alerts-error {
            background: #fff5f5;
            border: 1px solid #fecaca;
            border-left: 3px solid #dc3545;
            border-radius: 10px;
            padding: 14px 18px;
            color: #dc3545;
            font-size: 0.88rem;
        }
        /* --- 15. KPI Value Box Sizing & Theme Contrast --- */
        /* Target the main container */
        .bslib-value-box {
            height: 81px !important;
            overflow: hidden !important;
        }

        /* Target the internal card structure */
        .bslib-value-box .card, 
        .bslib-value-box .card-body,
        .bslib-value-box .value-box-grid {
            height: 100% !important;
            overflow: hidden !important;
            padding: 2px 8px !important; /* Extremely tight padding to fit the 81px limit */
        }

        /* Target the 'Showcase' (Icon) area specifically */
        /* Sometimes the icon is what pushes the height over the limit */
        .bslib-value-box .value-box-showcase {
            max-height: 50px !important;
            display: flex;
            align-items: center;
            overflow: hidden !important;
        }

        /* Add space between the title and the number */
        .bslib-value-box .value-box-title {
            margin-bottom: 20px !important; /* Increase this to add more space */
            align-items: flex-start !important; /* This pushes everything to the left */
        }

        /* This literally grabs the contents and nudges them up */
        .bslib-value-box > * {
            transform: translateY(-13px) !important; 
            text-align: left !important;
            padding-left: 0px !important; /* Adjust this to move it closer/further from the left edge */
        }

        /* Remove the ghost space above the animation slider */
        #animation_frame_idx-label {
            margin-top: -15px !important;
            margin-bottom: 0px !important;
        }
    
        """
    ),
    # Header Section
    ui.div(
        ui.h1("WeatherForge", class_="main-title"),
        ui.h4(f'{STATE_CONFIG["state_name"]} Severe Weather Risk Intelligence System', class_="sub-title"),
        ui.p("Built by David Braun, Jannah Elnemr, and Odin Lee", class_="byline-text"),
        class_="app-header"
    ),
    
    ui.layout_sidebar(
        ui.sidebar(
            ui.div(
                ui.h4("Filters", class_="sidebar-title"),
                
                ui.div(
                    ui.span("Live Feed", class_="live-feed-text"),
                    ui.input_switch("live_mode", "", value=False),
                    class_="live-feed-wrapper"
                ),
                
                # Conditional Logic for Time Filtering
                ui.panel_conditional(
                    "!input.live_mode",
                    ui.div(ui.p("Year Scope", class_="sidebar-label")),
                    ui.input_slider("year_range", "", min=1950, max=2025, value=(1950, 2025), step=1, sep=""),
                ),
                
                ui.panel_conditional(
                    "input.live_mode",
                    ui.div(ui.p("Past Months", class_="sidebar-label")),
                    ui.input_radio_buttons(
                        "live_period",
                        "",
                        choices=["1 Month", "3 Months", "6 Months", "1 Year"],
                        selected="1 Year",
                    ),
                ),
                
                # Geographic Control
                ui.div(ui.p("County Focus", class_="sidebar-label")),
                ui.input_text("county_filter", "", placeholder="Enter County Name"),
                
                ui.hr(style="width: 80%; margin: 40px 0; border-top: 1px solid #dee2e6;"),
                ui.p("Advanced analytics parameters for statewide storm intelligence.", 
                     class_="sidebar-footer-text"),
                class_="sidebar-container"
            ),
        ),
        
        # Dashboard Content Tabs
        ui.navset_tab(
            ui.nav_panel(
                "Overview",
                ui.row(
                    ui.column(3, ui.value_box("Total Events",    ui.output_text("total_events"))),
                    ui.column(3, ui.value_box("Direct Injuries", ui.output_text("total_injuries"))),
                    ui.column(3, ui.value_box("Total Damage",    ui.output_text("total_damage"))),
                    ui.column(3, ui.output_ui("risk_score_box")),
                ),
                ui.row(
                    ui.column(6,
                        ui.h4("Geographic Risk Distribution", class_="chart-header"),
                        output_widget("county_map"),
                    ),
                    ui.column(6,
                        ui.h4("Hazard Composition", class_="chart-header"),
                        output_widget("overview_donut"),
                    ),
                ),
                ui.output_ui("top_risk_counties_panel"),
                ui.output_ui("overview_summary"),
            ),
            ui.nav_panel(
                "County Impacts",
                ui.row(
                    ui.column(6, ui.input_select("county_metric", "County map metric", choices=COUNTY_METRIC_CHOICES, selected="risk_score",),),
                    ui.column(6, ui.input_select( "county_hazard_focus", "Hazard filter", choices=EVENT_TYPE_CHOICES, selected=ALL_HAZARDS,),),
                ),
                ui.row(
                    # Left side: Map
                    ui.column(
                        6,
                        ui.h4("Geographic Risk Distribution", class_="chart-header"),
                        output_widget("county_explorer_map")
                    ),
                    # Right side: The Bar Chart and Scatter Plot share 5 columns vertically
                    ui.column(
                        6,
                        ui.h4("Economic Impact Breakdown", class_="chart-header"),
                        output_widget("county_stacked_bar"),
                        ui.div(style="height: 10px;"), # Tightened spacer
                        ui.h4("Volume vs. Severity Correlation", class_="chart-header"),
                        output_widget("county_impact_scatter")
                    ),
                ),
                ui.output_ui("county_explorer_summary"),
            ),
            ui.nav_panel(
                "Weather Context",
                ui.row(
                    ui.column(6, ui.input_select("spatial_metric", "Select Weather Metric", choices=SPATIAL_METRIC_CHOICES, selected="event_count")),
                    ui.column(6, ui.input_select("spatial_hazard_focus", "Filter by Hazard", choices=EVENT_TYPE_CHOICES, selected=ALL_HAZARDS)),
                ),
                # ROW 1: Map left | two stacked charts right
                ui.row(
                    ui.column(6,
                        ui.h4("Geographic Weather Patterns", class_="chart-header"),
                        output_widget("spatial_weather_map"),
                    ),
                    ui.column(6,
                        ui.h4("County Weather Extremes", class_="chart-header"),
                        output_widget("spatial_top_counties"),
                        ui.div(style="height: 10px;"),
                        ui.h4("Comparative Hazard Profiles", class_="chart-header"),
                        output_widget("spatial_hazard_comparison"),
                    ),
                ),
                # ROW 2: Full-width correlation chart
                ui.row(
                    ui.column(12,
                        ui.h4("Drivers of Storm Frequency", class_="chart-header"),
                        output_widget("weather_correlation_plot"),
                    ),
                ),
                ui.output_ui("weather_correlation_summary"),
                ui.output_ui("spatial_weather_summary"),
            ),
            ui.nav_panel(
                "Time Progression",
                ui.row(
                    ui.column(6, ui.input_select("animation_metric", "Select Playback Metric", choices=ANIMATION_METRIC_CHOICES, selected="event_count")),
                    ui.column(6, ui.input_select("animation_hazard_focus", "Filter by Hazard", choices=EVENT_TYPE_CHOICES, selected=ALL_HAZARDS)),
                ),
                ui.row(
                    # LEFT: two stacked charts
                    ui.column(
                        6,
                        ui.h4("Reporting Volume Trends", class_="chart-header"),
                        output_widget("animation_context_plot"),
                        ui.div(style="height: 10px;"),
                        ui.h4("Hazard Variety Over Time", class_="chart-header"),
                        output_widget("hazard_diversity_plot"),
                    ),
                    # RIGHT: frame-driven map + Shiny slider
                    ui.column(
                        6,
                        ui.h4("Historical Risk Explorer", class_="chart-header"),
                        output_widget("animated_heatmap"),
                        ui.output_ui("animation_current_period"),
                        ui.output_ui("animation_frame_controls"),
                    ),
                ),
                ui.output_ui("animation_summary"),
            ),
            ui.nav_panel(
                "Statewide Trends",
                ui.row(
                    # LEFT: anchor — stacked area chart
                    ui.column(6,
                        ui.h4("Hazard Composition Trends", class_="chart-header"),
                        output_widget("trend_plot"),
                    ),
                    # RIGHT: two stacked charts 
                    ui.column(6,
                        ui.h4("Economic Impact Timeline", class_="chart-header"),
                        output_widget("trend_damage_plot"),
                        ui.div(style="height: 10px;"),
                        ui.h4("Annual Risk Seasonality", class_="chart-header"),
                        output_widget("storm_season_heatmap"),
                    ),
                ),
                ui.output_ui("trends_summary"),
            ),
            ui.nav_panel(
                "Live Alerts",
                ui.div(
                    ui.span("", class_="live-dot"),
                    ui.span("LIVE FEED", style="font-size:0.75rem; font-weight:800; color:#212529; text-transform:uppercase; letter-spacing:2px;"),
                    ui.span("·", style="color:#dee2e6; margin:0 6px;"),
                    ui.span(f'Active severe weather alerts for {STATE_CONFIG["state_name"]}', style="font-size:0.82rem; color:#6c757d;"),
                    ui.span("·", style="color:#dee2e6; margin:0 6px;"),
                    ui.span("Source: weather.gov", style="font-size:0.82rem; color:#adb5bd;"),
                    class_="live-status-bar",
                ),
                ui.output_ui("live_alerts"),
            ),
        ),
    ),
)


# ═══════════════════════════════════════════════════════════════════════════════
# SERVER FUNCTION
# All reactive logic lives inside server().  Structured in three layers:
#
#   1. Helper closures    – formatting, subtitle assembly, mapping-share notes.
#                           Pure functions; no reactive reads.
#
#   2. Reactive layer     – @reactive.Calc computations that derive filtered /
#                           aggregated DataFrames from the sidebar inputs.
#                           Shiny caches each result, so multiple render functions
#                           sharing the same Calc don't re-run the transform.
#
#                           Key reactive chain:
#                             sidebar inputs
#                               → data_to_use()        (filtered storms df)
#                               → summary_to_use()     (filtered summary df)
#                               → county_*_data()      (aggregated per tab)
#                               → dynamic_ceiling()    (risk score normalizer)
#
#   3. Render functions   – @render.* / @render_widget outputs wired to the UI.
#                           Grouped by tab below for easier navigation:
#                             Overview → County Impacts → Weather Context →
#                             Time Progression → Statewide Trends → Live Alerts
# ═══════════════════════════════════════════════════════════════════════════════

def server(input, output, session):
    def current_filter_context() -> str:
        if input.live_mode():
            context = f"Recent window: last {input.live_period().lower()}"
        else:
            start_year, end_year = input.year_range()
            context = f"Historical window: {start_year}-{end_year}"

        county_text = input.county_filter().strip()
        if county_text:
            context += f" | county text: {county_text}"
        else:
            context += " | county text: none"
        return context

    def current_subtitle(scope_note: str, hazard_choice: str | None = None, extra: str | None = None) -> str:
        parts = [current_filter_context()]
        if hazard_choice is not None:
            parts.append(f"Hazard: {selected_hazard_label(hazard_choice)}")
        parts.append(scope_note)
        if extra:
            parts.append(extra)
        return " | ".join(part for part in parts if part)

    def mapping_share_note(selected_df: pd.DataFrame, mapped_df: pd.DataFrame) -> str:
        if selected_df.empty:
            return "No filtered records are in scope."
        share = len(mapped_df) / len(selected_df)
        return (
            f"{len(mapped_df):,} mapped county records across "
            f"{mapped_df['county_name'].nunique() if not mapped_df.empty else 0} counties "
            f"({share:.0%} of the filtered records)."
        )

    def trend_method_note(frame_name: str | None, lookback: int) -> str:    
        if frame_name is None or lookback == 0:
            return "Trend classification is unavailable for this selection."
            
        # Dynamically pluralize year/month
        period_plural = f"{frame_name.lower()}s" 
        
        return (
            f"Trend classification uses the slope of storm events over the last {lookback} "
            f"{period_plural}, normalized by the county's historical mean. "
            f"A change of more than +{TREND_SLOPE_THRESHOLD:.0%} per {frame_name.lower()} is Increasing, "
            f"less than -{TREND_SLOPE_THRESHOLD:.0%} is Decreasing; otherwise Stable."
        )

    def correlation_strength_label(value: float) -> str:
        absolute = abs(value)
        if absolute < 0.2:
            return "weak"
        if absolute < 0.4:
            return "moderate"
        return "strong"

    # ── Reactive Data Layer ────────────────────────────────────────────────────
    # Each @reactive.Calc derives a filtered/aggregated DataFrame from the
    # sidebar inputs.  Shiny caches the result so downstream render functions
    # sharing the same Calc don't re-run the same transformation.
    #
    # Dependency chain (simplified):
    #   input.year_range / input.live_mode / input.county_filter
    #     → data_to_use()         raw storms filtered by date + county
    #     → summary_to_use()      summary filtered to match storms
    #     → county_*_data()       aggregated per-tab DataFrames
    #     → dynamic_ceiling()     99th-pct risk score for current window
    # ──────────────────────────────────────────────────────────────────────────

    @reactive.Calc
    def data_to_use():
        df = storms.copy()

        if STORM_DATE_COLUMN is None:
            return df.iloc[0:0].copy()

        if input.live_mode():
            period = input.live_period()
            days = {"1 Month": 30, "3 Months": 90, "6 Months": 180, "1 Year": 365}.get(period, 365)
            max_date = storms[STORM_DATE_COLUMN].max()
            cutoff = max_date - timedelta(days=days)
            df = df[df[STORM_DATE_COLUMN] >= cutoff].copy()
        else:
            start_year, end_year = input.year_range()
            df = df[
                (df[STORM_DATE_COLUMN].dt.year >= start_year)
                & (df[STORM_DATE_COLUMN].dt.year <= end_year)
            ].copy()

        if input.county_filter():
            search = input.county_filter().strip().lower()
            geo_column = get_geo_group_column(df)
            if geo_column is None:
                logger.warning("County filter requested but no geographic grouping column is available.")
                return df.iloc[0:0].copy()

            geo_values = df[geo_column].astype("string").fillna("").str.strip().str.lower()
            df = df[geo_values.str.contains(search, na=False)].copy()

        return df

    @render.ui
    def filter_context():
        return ui.div(
            f"Global filters: {current_filter_context()}",
            class_="app-context-note",
        )

    @reactive.Calc
    def summary_to_use():
        filtered_summary = filter_summary_for_storms(summary, data_to_use())
        if filtered_summary.empty:
            return filtered_summary

        if STORM_EVENT_COLUMN and SUMMARY_EVENT_COLUMN:
            storms_now = data_to_use().set_index(STORM_EVENT_COLUMN)
            if SUMMARY_DAMAGE_COLUMN and STORM_DAMAGE_COLUMN and STORM_DAMAGE_COLUMN in storms_now.columns:
                filtered_summary[SUMMARY_DAMAGE_COLUMN] = filtered_summary[SUMMARY_EVENT_COLUMN].map(
                    storms_now[STORM_DAMAGE_COLUMN]
                )
            if SUMMARY_INJURIES_COLUMN and STORM_INJURIES_COLUMN and STORM_INJURIES_COLUMN in storms_now.columns:
                filtered_summary[SUMMARY_INJURIES_COLUMN] = filtered_summary[SUMMARY_EVENT_COLUMN].map(
                    storms_now[STORM_INJURIES_COLUMN]
                )
            if SUMMARY_DEATHS_COLUMN and STORM_DEATHS_COLUMN and STORM_DEATHS_COLUMN in storms_now.columns:
                filtered_summary[SUMMARY_DEATHS_COLUMN] = filtered_summary[SUMMARY_EVENT_COLUMN].map(
                    storms_now[STORM_DEATHS_COLUMN]
                )

        return filtered_summary

    @reactive.Calc
    def county_selection():
        return filter_by_hazard(summary_to_use(), input.county_hazard_focus())

    @reactive.Calc
    def spatial_selection():
        return filter_by_hazard(summary_to_use(), input.spatial_hazard_focus())

    @reactive.Calc
    def animation_selection():
        # Use raw storms data so animation event counts reflect ALL events
        return filter_by_hazard(data_to_use(), input.animation_hazard_focus())

    @reactive.Calc
    def selected_year_range() -> tuple[int, int]:
        """Returns (start_year, end_year) for the current sidebar selection."""
        if input.live_mode():
            days = {"1 Month": 30, "3 Months": 90, "6 Months": 180, "1 Year": 365}[input.live_period()]
            end = pd.Timestamp.now().year
            start = (pd.Timestamp.now() - pd.Timedelta(days=days)).year
            return start, end
        start, end = input.year_range()
        return int(start), int(end)

    @reactive.Calc
    def dynamic_ceiling() -> float:
        """99th-pct per-capita annualized score computed from the current year-
        filtered storms data.  Recomputed whenever the year range changes so the
        0-100 scale always reflects the selected window — a 2000-2025 filter is
        normalised against 2000-2025 county scores, not all-time history."""
        s, e = selected_year_range()
        return compute_dynamic_ceiling(data_to_use(), s, e)

    @reactive.Calc
    def county_overview_data():
        s, e = selected_year_range()
        # Use raw storms data so county event counts reflect ALL events, not just weather-matched subset
        return aggregate_county_metrics(data_to_use(), start_year=s, end_year=e, ceiling=dynamic_ceiling())

    @reactive.Calc
    def county_explorer_data():
        s, e = selected_year_range()
        # Filter storms by selected hazard for accurate per-hazard county counts
        storms_filtered = filter_by_hazard(summary_to_use(), input.county_hazard_focus())
        return aggregate_county_metrics(storms_filtered, start_year=s, end_year=e, ceiling=dynamic_ceiling())

    @reactive.Calc
    def spatial_data():
        s, e = selected_year_range()
        return aggregate_county_metrics(spatial_selection(), start_year=s, end_year=e, ceiling=dynamic_ceiling())

    @reactive.Calc
    def animation_data():
        return build_animation_dataset(animation_selection(), ceiling=dynamic_ceiling())

    @reactive.Calc
    def overview_hazard_data():
        return aggregate_hazard_metrics(summary_to_use())

    @reactive.Calc
    def spatial_hazard_data():
        return aggregate_hazard_metrics(summary_to_use())

    @reactive.Calc
    def overview_time_data():
        return build_animation_dataset(data_to_use(), ceiling=dynamic_ceiling())

    @reactive.Calc
    def overview_trend_data():
        yearly, frame_name = overview_time_data()
        trend_df, _, lookback = compute_county_trend_classification(yearly, "event_count")
        return trend_df, frame_name, lookback

    @reactive.Calc
    def weather_correlation_data():
        return compute_weather_correlations(spatial_selection())

    @reactive.Calc
    def get_risk_score():
        """Returns the median county risk score from the current overview data.
        Uses the same 0–100 scale as the county map so the KPI thresholds are
        directly meaningful — green/yellow/red reflect where the typical county
        sits, not a compressed statewide aggregate."""
        counties = county_overview_data()
        if counties.empty or "risk_score" not in counties.columns:
            return 0.0
        return round(float(counties["risk_score"].median()), 1)

    # ── Render Functions ───────────────────────────────────────────────────────
    # Each @render.* / @render_widget is wired to a named output in app_ui.
    # Grouped by dashboard tab:
    #   Overview → County Impacts → Weather Context →
    #   Time Progression → Statewide Trends → Live Alerts
    # ──────────────────────────────────────────────────────────────────────────

    # -- Overview Tab ----------------------------------------------------------

    @render.text
    def total_events():
        return f"{len(data_to_use()):,}"

    @render.text
    def total_injuries():
        total = data_to_use()[STORM_INJURIES_COLUMN].sum() if STORM_INJURIES_COLUMN else 0
        return f"{total:,}"

    @render.text
    def total_damage():
        df    = data_to_use()
        prop  = df[STORM_DAMAGE_COLUMN].sum()      if STORM_DAMAGE_COLUMN      else 0
        crop  = df[STORM_CROP_DAMAGE_COLUMN].sum() if STORM_CROP_DAMAGE_COLUMN else 0
        total = prop + crop
        if total >= 1_000_000_000:
            return f"${total / 1_000_000_000:.1f}B"
        return f"${total / 1_000_000:.0f}M"

    @render.ui
    def risk_score_box():
        score = get_risk_score()
        low, high = RISK_SCORE_THRESHOLDS
        if score < low:
            theme = "success"
        elif score < high:
            theme = "warning"
        else:
            theme = "danger"
        return ui.value_box("Risk Score (0–100)", f"{score:.1f}", theme=theme)

    @render_widget
    def county_map():
        return build_county_map(
            county_overview_data(),
            "risk_score",
            "Statewide county risk score",
            current_subtitle(COUNTY_SCOPE_NOTE),
            is_overview=True
        )

    @render_widget
    def county_stacked_bar():
        # Passing the raw selection so we can access Crop Damage
        return build_county_stacked_bar(county_selection()
        )

    @render_widget
    def county_impact_scatter():
        # Passing the aggregated data
        return build_county_scatter(
            county_explorer_data(),
            "Event Frequency vs. Property Damage",
            "Bubble size represents direct injuries"
        )

    @render_widget
    def overview_donut():
        return build_overview_donut(overview_hazard_data())

    @render.ui
    def overview_summary():
        selected       = data_to_use()
        summary_sel    = summary_to_use()
        mapped         = prepare_county_dataset(summary_sel)
        hazards        = aggregate_hazard_metrics(summary_sel)
        counties       = county_overview_data()

        if selected.empty:
            return ui.p("No storm events match the current sidebar filters.")

        total_events = len(selected)
        top_hazard   = hazards.iloc[0]["event_type"]   if not hazards.empty  else "N/A"
        top_county   = counties.iloc[0]["county_name"] if not counties.empty else "N/A"
        top_risk     = counties.iloc[0]["risk_score"]  if not counties.empty else 0
        top_pct      = (hazards.iloc[0]["event_count"] / hazards["event_count"].sum() * 100) if not hazards.empty and hazards["event_count"].sum() > 0 else 0
        mapped_count = mapped["county_name"].nunique() if not mapped.empty else 0

        # Calculate damage and choose B vs M formatting
        prop  = selected[STORM_DAMAGE_COLUMN].sum()      if STORM_DAMAGE_COLUMN      else 0
        crop  = selected[STORM_CROP_DAMAGE_COLUMN].sum() if STORM_CROP_DAMAGE_COLUMN else 0
        total_dmg_raw = prop + crop
        
        if total_dmg_raw >= 1_000_000_000:
            dmg_display = f"${total_dmg_raw / 1_000_000_000:.1f}B"
        else:
            dmg_display = f"${total_dmg_raw / 1_000_000:,.1f}M"

        # Count counties at maximum risk for the selected window
        maxed_counties = int((counties["risk_score"] >= 100).sum()) if not counties.empty else 0
        maxed_note = (
            f" <strong>{maxed_counties} counties have reached the maximum relative risk (100) for this window</strong> — "
            f"indicating high intensity compared to historical norms."
        ) if maxed_counties >= 3 else ""

        return ui.HTML(
            "<div class='info-card'>"
            f"<strong>Executive Summary:</strong> A total of <strong>{total_events:,}</strong> storm events are in scope across <strong>{mapped_count}</strong> mapped {STATE_CONFIG['state_name']} counties. "
            f"The dominant hazard is <strong>{top_hazard}</strong>, accounting for <strong>{top_pct:.0f}%</strong> of all recorded activity. "
            f"<strong>{top_county}</strong> county leads the state in relative risk with a score of <strong>{top_risk:,.0f}</strong>. "
            f"Combined property and crop damage totals <strong>{dmg_display}</strong> across the selected time window. "
            f"{maxed_note} "
            f"Refine these results using the sidebar filters, or navigate to the specialized tabs above for deeper analysis of county impacts and historical trends."
            "</div>"
        )

    @render.ui
    def top_risk_counties_panel():
        county_data = county_overview_data()
        trend_data, frame_name, lookback = overview_trend_data()
        if county_data.empty:
            return ui.p("No county-level risk panel is available for the current filters.")

        table = county_data.merge(
            trend_data[["FIPS", "trend_class"]] if not trend_data.empty else pd.DataFrame(columns=["FIPS", "trend_class"]),
            on="FIPS",
            how="left",
        )
        table["trend_class"] = table["trend_class"].fillna("Short window")
        table = table.head(8).copy()

        badge_styles = {
            "Increasing":   {"bg": "#f8d7da", "color": "#842029", "icon": "↑"},
            "Stable":       {"bg": "#e9ecef", "color": "#41464b", "icon": "→"},
            "Decreasing":   {"bg": "#d1e7dd", "color": "#0f5132", "icon": "↓"},
            "Short window": {"bg": "#fff3cd", "color": "#664d03", "icon": "~"},
        }
        rows = []
        for _, row in table.iterrows():
            bstyle = badge_styles.get(row["trend_class"], badge_styles["Short window"])
            badge_html = (
                f"<span style='display:inline-block; padding:0.2rem 0.6rem; border-radius:999px; "
                f"background:{bstyle['bg']}; color:{bstyle['color']}; font-weight:700; font-size:0.75rem;'>"
                f"{bstyle['icon']} {row['trend_class']}</span>"
            )
            rows.append(
                "<tr>"
                f"<td style='font-weight:600;'>{row['county_name']}</td>"
                f"<td style='text-align: right; padding-right: 15px;'>{format_metric_value(row['risk_score'], 'risk_score')}</td>"
                f"<td style='text-align: right; padding-right: 15px;'>{format_metric_value(row['event_count'], 'event_count')}</td>"
                f"<td style='text-align: right; padding-right: 15px;'>{format_metric_value(row['property_damage'], 'property_damage')}</td>"
                f"<td style='text-align: center;'>{badge_html}</td>"
                "</tr>"
            )

        method_note = trend_method_note(frame_name, lookback)
        return ui.HTML(
            "<div class='risk-table-card'>"
            "<h4>County Risk & Trajectory</h4>"
            "<p class='tab-copy' style='margin-bottom:12px;'>Top counties driving statewide risk based on current filters, ranked by Risk Score.</p>"
            "<div class='table-responsive'>"
            "<table class='table table-sm table-striped'>"
            "<thead><tr>"
            "<th>County</th>"
            "<th style='text-align: right; padding-right: 15px;'>Risk score</th>"
            "<th style='text-align: right; padding-right: 15px;'>Storm event</th>"
            "<th style='text-align: right; padding-right: 15px;'>Property damage</th>"
            "<th style='text-align: center;'>Trend</th>"
            "</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table>"
            "</div>"
            f"<p style='font-size:0.78rem;color:#6c757d;margin:0;'>{method_note}</p>"
            "</div>"
        )

    # -- County Impacts Tab ----------------------------------------------------

    @render_widget
    def county_explorer_map():
        metric_key = input.county_metric()
        title = (
            f"{COUNTY_METRIC_CHOICES[metric_key]} by county"
        )
        return build_county_map(
            county_explorer_data(),
            metric_key,
            title,
            current_subtitle(COUNTY_SCOPE_NOTE, input.county_hazard_focus()),
        )

    @render.ui
    def county_explorer_summary():
        county_data = county_explorer_data()
        summary_selected = county_selection()
        mapped = prepare_county_dataset(summary_selected)

        if county_data.empty:
            return ui.p("No localized storm records match your current filters. Try selecting 'All Hazards' or expanding the date range.")

        leader = county_data.iloc[0]
        mapped_share = len(mapped) / len(summary_selected) if len(summary_selected) else 0
        metric_key = input.county_metric()

        # Refined Coverage Logic
        if mapped_share < 0.7:
            coverage_note = (
                "Note: Since many events are reported at the state level, this map focuses exclusively on "
                "records with confirmed county-specific impacts."
            )
        else:
            coverage_note = "providing high-confidence regional insights that closely align with broader statewide trends."

        formatted_value = format_metric_value(leader[metric_key], metric_key)
        share_text = mapping_share_note(summary_selected, mapped)

        return ui.HTML(
            "<div class='info-card'>"
            f"<strong>Top Regional Impact:</strong> {leader['county_name']} currently shows the highest risk "
            f"level with a score of <strong>{formatted_value}</strong>. This analysis incorporates "
            f"{share_text} {coverage_note}"
            "</div>"
        )

    # -- Weather Context Tab ---------------------------------------------------

    @render_widget
    def spatial_weather_map():
        return build_county_map(spatial_data(), input.spatial_metric(), weather_context=True)

    @render_widget
    def spatial_top_counties():
        return build_county_ranking(spatial_data(), input.spatial_metric(), weather_context=True)

    @render_widget
    def spatial_hazard_comparison():
        return build_hazard_comparison(
            spatial_hazard_data(),
            input.spatial_metric(),
            input.spatial_hazard_focus(),
            weather_context=True,
        )

    @render_widget
    def weather_correlation_plot():
        correlation_df, _ = weather_correlation_data()
        return build_weather_correlation_figure(correlation_df)

    @render.ui
    def weather_correlation_summary():
        correlation_df, period_name = weather_correlation_data()
        if correlation_df.empty or period_name is None:
            return ui.p("No weather-correlation summary is available for the current selection.")

        # 1. Identify the strongest atmospheric driver
        strongest = correlation_df.iloc[correlation_df["correlation"].abs().argmax()]
        direction = "positive" if strongest["correlation"] >= 0 else "negative"
        strength  = correlation_strength_label(float(strongest["correlation"]))
        r_value   = f"{strongest['correlation']:+.2f}"

        # 2. Return the Executive Correlation Analysis
        return ui.HTML(
            "<div class='info-card'>"
            f"<strong>Correlation Analysis:</strong> Within observed storm periods, "
            f"<strong>{strongest['metric_label']}</strong> shows the strongest association with <strong>Storm Event</strong> "
            f"(<strong>r = {r_value}</strong>). While this indicates a <strong>{strength} {direction}</strong> relationship, "
            f"it identifies the primary atmospheric driver for the current selection. "
            f"<br><span style='font-size: 12px; color: #6c757d; font-style: italic;'>"
            f"Note: This association is measured across {period_name}s within mapped storm windows and does not imply a causal effect.</span>"
            "</div>"
        )

    @render.ui
    def spatial_weather_summary():
        metric_key = input.spatial_metric()
        county_data = spatial_data()
        hazard_data = spatial_hazard_data()
        selection = spatial_selection()
        mapped = prepare_county_dataset(selection)

        if county_data.empty:
            return ui.p("No county-compatible weather-context view is available for the selected hazard. Try All hazards or a broader date window.")

        # 1. Identify the peak regional intensity
        leader = county_data.dropna(subset=[metric_key]).sort_values(metric_key, ascending=False).head(1)
        statewide = hazard_data.dropna(subset=[metric_key]).sort_values(metric_key, ascending=False).head(1)
        
        leader_name = leader.iloc[0]["county_name"] if not leader.empty else "N/A"
        leader_val  = leader.iloc[0][metric_key] if not leader.empty else np.nan
        state_haz   = statewide.iloc[0]["event_type"] if not statewide.empty else "N/A"
        
        # 2. Calculate Integrity Metrics
        mapped_count = len(mapped)
        mapped_share = len(mapped) / len(selection) if len(selection) else 0
        percent_mapped = f"{mapped_share:.0%}"

        # 3. Dynamic Coverage Note focused on confidence
        coverage_note = (
            "ensuring high regional confidence and alignment between geographic and statewide trends."
            if mapped_share >= 0.7
            else "suggesting localized focus is required due to significant zone-coded record distribution."
        )

        metric_label = SPATIAL_METRIC_CHOICES[metric_key].lower()

        return ui.HTML(
            "<div class='info-card'>"
            f"<strong>Weather Dynamics Summary:</strong> <strong>{leader_name}</strong> exhibits the peak intensity for <strong>{metric_label}</strong> "
            f"with <strong>{format_metric_value(leader_val, metric_key)}</strong>. "
            f"Across all filtered statewide data, <strong>{state_haz}</strong> represents the most frequent hazard occurrence. "
            f"This assessment is backed by <strong>{mapped_count:,}</strong> mapped records (<strong>{percent_mapped}</strong> coverage), "
            f"{coverage_note}"
            "</div>"
        )

    # -- Time Progression Tab --------------------------------------------------

    @reactive.Calc
    def animation_frame_data():
        """Returns (sorted_frame_labels, frame_name) for the current selection."""
        yearly, frame_name = animation_data()
        if yearly.empty:
            return [], None
        labels = (
            yearly[["frame_sort", "frame_label"]]
            .drop_duplicates()
            .sort_values("frame_sort")["frame_label"]
            .tolist()
        )
        return labels, frame_name

    @render.ui
    def animation_frame_controls():
        """Shiny slider that drives the map."""
        labels, frame_name = animation_frame_data()
        if not labels:
            return ui.p(
                "No time frames available for the current selection.",
                style="color:#adb5bd;font-size:0.8rem;text-align:center;margin-top:8px;",
            )
            
        if frame_name == "Year":
            min_val = int(labels[0])
            max_val = int(labels[-1])
            return ui.div(
                ui.input_slider("animation_frame_idx", "Year", min=min_val, max=max_val, value=min_val, step=1, ticks=False, sep=""),
                style="padding:0 12px; margin-top:6px;",
            )
        else:
            # Parse 'Jan 2026' strings into real datetime objects for the slider
            try:
                dates = [datetime.strptime(lbl, "%b %Y").date() for lbl in labels]
                min_val = dates[0]
                max_val = dates[-1]
            except Exception:
                min_val, max_val = 0, len(labels) - 1
                
            return ui.div(
                ui.input_slider(
                    "animation_frame_idx", 
                    "Month", 
                    min=min_val, 
                    max=max_val, 
                    value=min_val, 
                    time_format="%b %Y", # Forces the slider to show 'Feb 2026'
                    ticks=False
                ),
                style="padding:0 12px; margin-top:6px;",
            )

    @render.ui
    def animation_current_period():
        return None

    @render_widget
    def animated_heatmap():
        metric_key = input.animation_metric()
        yearly, _ = animation_data()
        labels, frame_name = animation_frame_data()

        if yearly.empty or not labels:
            return empty_figure("Playback", "No data for the current selection.")

        slider_val = input.animation_frame_idx()

        if frame_name == "Year":
            try:
                target_label = str(int(slider_val))
            except Exception:
                target_label = labels[-1]
                
            if target_label not in labels:
                try:
                    target_label = min(labels, key=lambda l: abs(int(l) - int(slider_val)))
                except Exception:
                    target_label = labels[-1]
        else:
            # Slider passes a datetime object back to python
            if hasattr(slider_val, "strftime"):
                target_label = slider_val.strftime("%b %Y")
            else:
                target_label = labels[-1] # Fallback
                
            if target_label not in labels:
                try:
                    target_date = datetime.strptime(target_label, "%b %Y")
                    target_label = min(labels, key=lambda l: abs(datetime.strptime(l, "%b %Y") - target_date))
                except Exception:
                    target_label = labels[-1]

        frame_data = yearly[yearly["frame_label"] == target_label].copy()

        if frame_data.empty:
            return empty_figure("Playback", "No county data for this frame.")

        # Lightweight single-trace choropleth for smooth animation playback.
        # build_county_map (two go.Choropleth traces) is too slow to re-render
        # every second — px.choropleth with a single trace is ~3x faster.
        z_max = yearly[metric_key].max()
        if z_max == 0 or pd.isna(z_max):
            z_max = 1

        metric_label = METRIC_META[metric_key]["label"]

        fig = px.choropleth(
            frame_data,
            geojson=COUNTY_GEOJSON,
            locations="FIPS",
            color=metric_key,
            color_continuous_scale=COUNTY_MAP_COLORSCALE,
            range_color=[0, z_max],
            height=400,
            hover_name="county_name",
            title=None,
        )

        fig.update_traces(
                marker_line_width=1.2,
                marker_line_color="#495057",
                hovertemplate=(
                    "<span style='font-size:19px; color:#212529; font-weight:800; line-height:1.2;'>%{hovertext} County</span><br>"
                    f"<span style='font-size:16px; color:#0d6efd; font-weight:800;'>{metric_label}: %{{z:,.1f}}</span><br>"
                    "<span style='color:#dee2e6;'>▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</span><br>"
                    "<span style='font-size:11px; color:#6c757d;'>Historical risk snapshot for the selected year</span>"
                    "<extra></extra>"
                ),
            )

        fig.update_geos(
            visible=False,
            bgcolor="rgba(0,0,0,0)",
            showland=False,
            showcoastlines=False,
            showframe=False,
            projection_type="mercator",
            lataxis_range=[COUNTY_MAP_BOUNDS["lat_min"], COUNTY_MAP_BOUNDS["lat_max"]],
            lonaxis_range=[COUNTY_MAP_BOUNDS["lon_min"], COUNTY_MAP_BOUNDS["lon_max"]],
        )

        fig.update_layout(
            margin={"l": 35, "r": 0, "t": 0, "b": 0},
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_family="system-ui, -apple-system, sans-serif",
            dragmode=False,
            coloraxis_showscale=False,
            hoverlabel=dict(
                bgcolor="white", bordercolor="#dee2e6",
                font_size=13, font_family="system-ui, -apple-system, sans-serif",
                align="left",
            ),
        )
        return fig

    @render_widget
    def animation_context_plot():
        yearly, _ = build_animation_dataset(
            filter_by_hazard(summary_to_use(), input.animation_hazard_focus()),
            ceiling=dynamic_ceiling(),
        )
        return build_animation_context_plot(yearly, input.animation_metric())

    @render_widget
    def hazard_diversity_plot():
        # Pass the global data to show how many types we've tracked over time
        return build_hazard_diversity_plot(data_to_use())

    @render.ui
    def animation_summary():
        yearly, frame_name = animation_data()
        metric_key = input.animation_metric()
        selection = animation_selection()
        mapped = prepare_county_dataset(selection)
        
        if yearly.empty or frame_name is None:
            return ui.p("No historical summary is available for the current selection.")

        # 1. Calculate Peak Period Trends
        totals = (
            yearly.groupby("frame_label", dropna=False)[metric_key]
            .sum()
            .reset_index()
            .sort_values(metric_key, ascending=False)
        )
        
        peak_frame = totals.iloc[0]["frame_label"] if not totals.empty else "N/A"
        peak_val   = totals.iloc[0][metric_key] if not totals.empty else np.nan
        frame_cnt  = yearly["frame_label"].nunique()
        
        # 2. Integrity Metrics
        mapped_count   = len(mapped)
        mapped_share   = len(mapped) / len(selection) if len(selection) else 0
        percent_mapped = f"{mapped_share:.0%}"

        # 3. Dynamic Analysis Note
        coverage_note = (
            "this tool allows for a high-fidelity comparison of how regional risk patterns have evolved over decades."
            if mapped_share >= 0.7
            else "the explorer provides a targeted look at mapped events, though many records for this hazard remain zone-coded at the statewide level."
        )

        return ui.HTML(
            "<div class='info-card'>"
            f"<strong>Temporal Trend Analysis:</strong> This interactive explorer synthesizes <strong>{frame_cnt}</strong> annual snapshots, "
            f"identifying <strong>{peak_frame}</strong> as the peak period for <strong>{METRIC_META[metric_key]['label']}</strong> "
            f"reaching <strong>{format_metric_value(peak_val, metric_key)}</strong>. "
            f"With <strong>{mapped_count:,}</strong> records (<strong>{percent_mapped}</strong>) geocoded, "
            f"{coverage_note}"
            "</div>"
        )

    # -- Statewide Trends Tab --------------------------------------------------

    @render_widget
    def trend_plot():
        return build_trend_counts_figure(data_to_use())

    @render_widget
    def trend_damage_plot():
        return build_trend_damage_figure(data_to_use())

    @render_widget
    def storm_season_heatmap():
        return build_storm_season_heatmap(data_to_use())

    @render.ui
    def trends_summary():
        df = data_to_use()
        if df.empty:
            return ui.p("No data for the current selection.")

        date_col = get_begin_date_column(df)
        prop_col = get_damage_property_column(df)
        crop_col = get_damage_crops_column(df)

        if not date_col:
            return ui.p("No dates available to calculate trends.")

        # Use the helper to automatically frame the data by Month or Year
        framed, frame_name = add_time_frame(df, date_col)
        if framed.empty or frame_name is None:
            return ui.p("No valid dates to calculate trends.")

        # dynamically injects the word "year" or "month" into the UI string
        period_type = frame_name.lower() 

        # 1. Identify Peak Damage Period (Economic Toll)
        peak_dmg_period = "N/A"
        peak_dmg_total = 0.0

        if prop_col:
            framed["total_dmg"] = framed[prop_col].fillna(0)
            if crop_col:
                framed["total_dmg"] += framed[crop_col].fillna(0)
            
            period_dmg = framed.groupby("frame_label")["total_dmg"].sum()
            if not period_dmg.empty:
                peak_dmg_period = str(period_dmg.idxmax())
                peak_dmg_total = period_dmg.max() / 1_000_000  # Convert to Millions

        # 2. Identify Peak Storm Count Period (Volume)
        peak_count_period = "N/A"
        peak_count_val = 0

        period_counts = framed.groupby("frame_label").size()
        if not period_counts.empty:
            peak_count_period = str(period_counts.idxmax())
            peak_count_val = period_counts.max()

        # 3. Peak Storm Month (Seasonality)
        peak_month_name = "N/A"
        framed["month_num"] = framed[date_col].dt.month
        month_counts = framed["month_num"].dropna().astype(int).value_counts()
        if not month_counts.empty:
            MONTH_NAMES = {1:"January", 2:"February", 3:"March", 4:"April", 5:"May", 6:"June",
                           7:"July", 8:"August", 9:"September", 10:"October", 11:"November", 12:"December"}
            peak_month_name = MONTH_NAMES.get(month_counts.idxmax(), "N/A")

        # 4. Return the Actuarial Risk Profile
        return ui.HTML(
            "<div class='info-card'>"
            f"<strong>Executive Trend Summary:</strong> Historical records identify <strong>{peak_dmg_period}</strong> as the peak "
            f"economic loss period with <strong>${peak_dmg_total:,.1f}M</strong> in total damages. "
            f"In terms of volume, <strong>{peak_count_period}</strong> stands as the most active {period_type} for <strong>Storm Count</strong> "
            f"reaching <strong>{peak_count_val:,}</strong> records. Seasonally, <strong>{peak_month_name}</strong> represents the highest "
            f'operational risk period for {STATE_CONFIG["state_name"]} across all hazard categories.'
            "</div>"
        )

    # -- Live Alerts Tab -------------------------------------------------------

    @render.ui
    def live_alerts():
        # Severity → visual treatment
        SEVERITY_STYLE = {
            "Extreme": {
                "border": "#dc3545", "badge_bg": "#dc3545",
                "badge_text": "white", "label": "EXTREME",
            },
            "Severe": {
                "border": "#e63946", "badge_bg": "#e63946",
                "badge_text": "white", "label": "SEVERE",
            },
            "Moderate": {
                "border": "#f4a261", "badge_bg": "#f4a261",
                "badge_text": "white", "label": "MODERATE",
            },
            "Minor": {
                "border": "#0d6efd", "badge_bg": "#0d6efd",
                "badge_text": "white", "label": "MINOR",
            },
        }
        DEFAULT_STYLE = {
            "border": "#6c757d", "badge_bg": "#6c757d",
            "badge_text": "white", "label": "ADVISORY",
        }

        def fmt_time(iso: str) -> str:
            """Turn an ISO timestamp into a readable local string."""
            if not iso:
                return ""
            try:
                dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                # Use f-string formatting instead of %-m/%-d (Linux-only strftime codes)
                return f"{dt.month}/{dt.day} at {dt.strftime('%I:%M %p').lstrip('0')} UTC"
            except Exception:
                return iso[:16]

        try:
            response = requests.get(
                f'https://api.weather.gov/alerts/active?area={STATE_CONFIG["state_abbr"]}',
                headers={"User-Agent": f'SEIS745-{STATE_CONFIG["state_name"].replace(" ", "-")}-Dashboard'},
                timeout=15,
            )
            response.raise_for_status()
            alerts = response.json().get("features", [])

            if not alerts:
                return ui.HTML(
                    "<div class='no-alerts-state'>"
                    "<div class='check-icon'>✓</div>"
                    "<div style='font-size:1.1rem; font-weight:700; color:#212529; margin-bottom:8px;'>"
                    "No Active Alerts</div>"
                    f"<div style='font-size:0.88rem;'>{STATE_CONFIG['state_name']} has no active severe weather alerts right now.</div>"
                    "</div>"
                )

            cards = []
            for alert in alerts[:10]:
                props = alert.get("properties", {})
                event      = props.get("event", "Weather Alert")
                area       = props.get("areaDesc", STATE_CONFIG["state_name"])
                headline   = props.get("headline", "")
                severity   = props.get("severity", "Unknown")
                expires    = fmt_time(props.get("expires", ""))
                sender     = props.get("senderName", "")
                # Trim area to first 3 counties if very long
                area_parts = [a.strip() for a in area.split(";")]
                area_short = ", ".join(area_parts[:3])
                if len(area_parts) > 3:
                    area_short += f" +{len(area_parts) - 3} more"

                style = SEVERITY_STYLE.get(severity, DEFAULT_STYLE)

                footer_parts = []
                if expires:
                    footer_parts.append(f"Expires {expires}")
                if sender:
                    footer_parts.append(sender)
                footer_html = (
                    f"<div style='margin-top:10px; font-size:0.75rem; color:#adb5bd; "
                    f"display:flex; gap:14px; flex-wrap:wrap;'>"
                    + "".join(f"<span>{p}</span>" for p in footer_parts)
                    + "</div>"
                ) if footer_parts else ""

                cards.append(
                    f"<div class='alert-card-v2' "
                    f"style='border-left:3px solid {style['border']};'>"
                    f"<div style='display:flex; justify-content:space-between; "
                    f"align-items:flex-start; gap:10px; margin-bottom:8px;'>"
                    f"<strong style='font-size:0.95rem; color:#212529; "
                    f"line-height:1.3;'>{event}</strong>"
                    f"<span class='severity-badge' style='background:{style['badge_bg']}; "
                    f"color:{style['badge_text']};'>{style['label']}</span>"
                    f"</div>"
                    f"<div style='font-size:0.82rem; color:#495057; margin-bottom:6px;'>"
                    f"{area_short}</div>"
                    f"<div style='font-size:0.82rem; color:#6c757d; line-height:1.5;'>"
                    f"{headline}</div>"
                    f"{footer_html}"
                    f"</div>"
                )

            count_label = f"{len(alerts)} active alert{'s' if len(alerts) != 1 else ''}"
            grid_html = (
                f"<div style='font-size:0.78rem; color:#6c757d; "
                f"margin-bottom:14px; font-weight:600;'>{count_label}</div>"
                f"<div class='alerts-grid'>{''.join(cards)}</div>"
            )
            return ui.HTML(grid_html)

        except Exception as error:
            return ui.HTML(
                f"<div class='alerts-error'>"
                f"<strong>Could not fetch alerts</strong> — {error}<br>"
                f"<span style='font-size:0.8rem;'>Check your connection or try refreshing.</span>"
                f"</div>"
            )


app = App(app_ui, server)

if __name__ == "__main__":
    app.run()
