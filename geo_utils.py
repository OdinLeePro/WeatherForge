from __future__ import annotations

import re

import pandas as pd


def normalize_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Trim surrounding whitespace from column names without changing the data."""
    rename_map = {}
    for column in df.columns:
        cleaned = str(column).strip()
        if cleaned != column:
            rename_map[column] = cleaned
    return df.rename(columns=rename_map) if rename_map else df


def _canonical_column_key(column_name: object) -> str:
    return re.sub(r"[^0-9a-z]+", "", str(column_name).strip().casefold())


def resolve_column(df: pd.DataFrame, candidates: list[str] | tuple[str, ...]) -> str | None:
    available = {_canonical_column_key(column): column for column in df.columns}
    for candidate in candidates:
        resolved = available.get(_canonical_column_key(candidate))
        if resolved is not None:
            return resolved
    return None


def get_geo_group_column(df: pd.DataFrame) -> str | None:
    return resolve_column(
        df,
        (
            "CZ_NAME",
            "county_name",
            "county",
            "zone_name",
            "zone",
            "location_name",
            "location",
            "name",
            "CZ_FIPS",
            "county_fips",
            "FIPS",
        ),
    )


def get_geo_fips_column(df: pd.DataFrame) -> str | None:
    return resolve_column(df, ("CZ_FIPS", "county_fips", "FIPS", "GEOID"))


def get_begin_date_column(df: pd.DataFrame) -> str | None:
    return resolve_column(df, ("BEGIN_DATE", "begin_date", "date"))


def get_event_id_column(df: pd.DataFrame) -> str | None:
    return resolve_column(df, ("EVENT_ID", "event_id"))


def get_event_type_column(df: pd.DataFrame) -> str | None:
    return resolve_column(df, ("EVENT_TYPE", "event_type"))


def get_cz_type_column(df: pd.DataFrame) -> str | None:
    return resolve_column(df, ("CZ_TYPE", "cz_type"))


def get_damage_property_column(df: pd.DataFrame) -> str | None:
    return resolve_column(df, ("DAMAGE_PROPERTY", "damage_property"))


def get_damage_crops_column(df: pd.DataFrame) -> str | None:
    return resolve_column(df, ("DAMAGE_CROPS", "damage_crops"))


def get_injuries_column(df: pd.DataFrame) -> str | None:
    return resolve_column(df, ("INJURIES_DIRECT", "injuries_direct"))


def get_deaths_column(df: pd.DataFrame) -> str | None:
    return resolve_column(df, ("DEATHS_DIRECT", "deaths_direct"))


def get_precipitation_column(df: pd.DataFrame) -> str | None:
    return resolve_column(df, ("daily_prcp_avg", "prcp", "precipitation"))


def get_max_temperature_column(df: pd.DataFrame) -> str | None:
    return resolve_column(df, ("daily_tmax_avg", "tmax", "max_temperature"))


def get_min_temperature_column(df: pd.DataFrame) -> str | None:
    return resolve_column(df, ("daily_tmin_avg", "tmin", "min_temperature"))


def get_snowfall_column(df: pd.DataFrame) -> str | None:
    return resolve_column(df, ("daily_snow_avg", "snow", "snowfall"))


def get_snow_depth_column(df: pd.DataFrame) -> str | None:
    return resolve_column(df, ("daily_snwd_avg", "snwd", "snow_depth"))


def get_wind_speed_column(df: pd.DataFrame) -> str | None:
    return resolve_column(df, ("daily_awnd_avg", "awnd", "wind_speed"))


def to_county_fips(value: object, state_fips_prefix: str | None = None) -> str | None:
    """Normalise a raw FIPS-like value to a 5-digit string.

    If the value is already 5 digits it is returned as-is.
    If it is 3 digits or fewer and *state_fips_prefix* is supplied (e.g. ``"27"``
    for Minnesota), the prefix is prepended.  When no prefix is available the
    value is zero-padded to 5 digits; callers that need strict state filtering
    should supply the prefix.
    """
    if pd.isna(value):
        return None

    digits = re.sub(r"\D+", "", str(value).strip())
    if not digits:
        return None
    if len(digits) <= 3:
        if state_fips_prefix:
            return f"{state_fips_prefix}{digits.zfill(3)}"
        return digits.zfill(5)
    if len(digits) == 5:
        return digits
    return digits[-5:]


# Backwards-compatible alias — external code importing the old name still works.
def to_minnesota_county_fips(value: object) -> str | None:
    """Deprecated alias for to_county_fips with MN prefix \"27\"."""
    return to_county_fips(value, state_fips_prefix="27")


def build_geo_fips_map(
    df: pd.DataFrame,
    geo_column: str | None = None,
    fips_column: str | None = None,
) -> pd.Series:
    working = normalize_dataframe_columns(df)
    geo_column = geo_column or get_geo_group_column(working)
    fips_column = fips_column or get_geo_fips_column(working)

    if geo_column is None or fips_column is None:
        return pd.Series(dtype="object")

    geo_lookup = working[[geo_column, fips_column]].copy()
    geo_lookup[geo_column] = geo_lookup[geo_column].astype("string").str.strip()
    geo_lookup["FIPS"] = geo_lookup[fips_column].map(to_county_fips)
    geo_lookup = geo_lookup.dropna(subset=[geo_column, "FIPS"])
    geo_lookup = geo_lookup[geo_lookup[geo_column] != ""].drop_duplicates(subset=[geo_column])
    return geo_lookup.set_index(geo_column)["FIPS"]


def filter_summary_for_storms(summary_df: pd.DataFrame, storms_df: pd.DataFrame) -> pd.DataFrame:
    """Keep summary rows aligned with the currently selected storm events."""
    summary_df = normalize_dataframe_columns(summary_df)
    storms_df = normalize_dataframe_columns(storms_df)

    if summary_df.empty or storms_df.empty:
        return summary_df.iloc[0:0].copy()

    summary_event_id = get_event_id_column(summary_df)
    storms_event_id = get_event_id_column(storms_df)
    if summary_event_id and storms_event_id:
        event_ids = storms_df[storms_event_id].dropna().unique()
        return summary_df[summary_df[summary_event_id].isin(event_ids)].copy()

    join_pairs = []
    summary_date = get_begin_date_column(summary_df)
    storms_date = get_begin_date_column(storms_df)
    if summary_date and storms_date:
        join_pairs.append((summary_date, storms_date))

    summary_geo = get_geo_group_column(summary_df)
    storms_geo = get_geo_group_column(storms_df)
    if summary_geo and storms_geo:
        join_pairs.append((summary_geo, storms_geo))

    if not join_pairs:
        return summary_df.iloc[0:0].copy()

    right_columns = list(dict.fromkeys(right for _, right in join_pairs))
    selected_keys = storms_df[right_columns].drop_duplicates().copy()

    return summary_df.merge(
        selected_keys,
        left_on=[left for left, _ in join_pairs],
        right_on=[right for _, right in join_pairs],
        how="inner",
    )