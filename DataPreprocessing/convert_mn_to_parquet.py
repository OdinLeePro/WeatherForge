"""Convert ONLY Minnesota GHCN-Daily .dly files into one clean Parquet table."""

from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import pandas as pd
import calendar
from typing import Iterator, Optional

# === Paste your existing parser code here (from ghcn_dly_to_csv.py) ===
@dataclass
class DlyRow:
    station_id: str
    date: str
    element: str
    day: int
    value_raw: str
    value_clean: Optional[int | str]
    is_missing: bool
    is_valid_date: bool
    mflag: str
    qflag: str
    sflag: str
    is_trace: bool

def parse_dly_line(line: str) -> Iterator[DlyRow]:
    station_id = line[0:11]
    year = int(line[11:15])
    month = int(line[15:17])
    element = line[17:21]
    for day in range(1, 32):
        start = 21 + (day - 1) * 8
        value_str = line[start:start + 5].rstrip("\n")
        mflag = line[start + 5:start + 6]
        qflag = line[start + 6:start + 7]
        sflag = line[start + 7:start + 8]
        try:
            value = int(value_str)
        except ValueError:
            value = -9999
        is_missing = value == -9999
        is_valid_date = day <= calendar.monthrange(year, month)[1]
        row_date = f"{year:04d}-{month:02d}-{day:02d}" if is_valid_date else ""
        yield DlyRow(
            station_id=station_id,
            date=row_date,
            element=element,
            day=day,
            value_raw="is_null" if is_missing else value_str,
            value_clean=None if is_missing else value,
            is_missing=is_missing,
            is_valid_date=is_valid_date,
            mflag=mflag.strip(),
            qflag=qflag.strip(),
            sflag=sflag.strip(),
            is_trace=False,
        )

def parse_dly_file(path: str | Path) -> list[DlyRow]:
    path = Path(path)
    rows: list[DlyRow] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip():
                rows.extend(parse_dly_line(line))
    return rows
# === End of pasted parser ===

def get_mn_station_ids(stations_txt: str | Path) -> set[str]:
    stations_txt = Path(stations_txt)
    mn_ids = set()
    with stations_txt.open("r", encoding="utf-8") as f:
        for line in f:
            if len(line) >= 40 and line[38:40] == "MN":
                station_id = line[0:11].strip()
                mn_ids.add(station_id)
    return mn_ids

def main():
    INPUT_DIR = Path("../ghcnd_all/ghcnd_all")          # ← change if your path is different
    STATIONS_TXT = Path("ghcnd-stations.txt")
    OUTPUT_DIR = Path("processed")
    OUTPUT_FILE = OUTPUT_DIR / "weather_daily_mn.parquet"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading Minnesota stations...")
    mn_ids = get_mn_station_ids(STATIONS_TXT)
    print(f"Found {len(mn_ids):,} Minnesota stations.")

    relevant_elements = {"TMAX", "TMIN", "PRCP", "SNOW", "SNWD", "AWND"}
    all_wide_dfs = []

    for station_id in sorted(mn_ids):
        dly_path = INPUT_DIR / f"{station_id}.dly"
        if not dly_path.exists():
            continue

        print(f"Processing {station_id} ...")
        raw_rows = parse_dly_file(dly_path)

        # Build DataFrame once per station (tiny memory)
        df = pd.DataFrame([asdict(r) for r in raw_rows])

        # Keep only valid dates + relevant elements
        df = df[df["is_valid_date"] & df["element"].isin(relevant_elements)].copy()

        if df.empty:
            continue

        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value_clean"], errors="coerce")

        # Pivot to wide (one row per station-date)
        wide = df.pivot_table(
            index=["station_id", "date"],
            columns="element",
            values="value"
        ).reset_index()

        # Lowercase columns
        wide.columns = [c.lower() if c not in {"station_id", "date"} else c for c in wide.columns]

        # Convert from GHCN units to real-world units
        scale = {
            "tmax": 0.1,   # → °C
            "tmin": 0.1,   # → °C
            "prcp": 0.1,   # → mm
            "snow": 1.0,   # → mm
            "snwd": 1.0,   # → mm
            "awnd": 0.1,   # → m/s
        }
        for col, factor in scale.items():
            if col in wide.columns:
                wide[col] = wide[col] * factor

        all_wide_dfs.append(wide)

    if not all_wide_dfs:
        print("No Minnesota data found.")
        return

    print("Combining all stations...")
    df_mn = pd.concat(all_wide_dfs, ignore_index=True)

    # Add station metadata (name, lat, lon, elevation)
    stations = pd.read_fwf(
        STATIONS_TXT,
        colspecs=[(0, 11), (12, 20), (21, 30), (31, 37), (38, 40), (41, 71)],
        names=["station_id", "latitude", "longitude", "elevation", "state", "name"],
        header=None,
        dtype={"station_id": str}
    )
    stations = stations[stations["state"] == "MN"].copy()
    stations["name"] = stations["name"].str.strip()

    df_mn = df_mn.merge(
        stations[["station_id", "name", "latitude", "longitude", "elevation"]],
        on="station_id",
        how="left"
    )

    # Final column order
    final_cols = ["station_id", "name", "latitude", "longitude", "elevation", "date",
                  "tmax", "tmin", "prcp", "snow", "snwd", "awnd"]
    df_mn = df_mn[[c for c in final_cols if c in df_mn.columns]]

    df_mn.to_parquet(OUTPUT_FILE, compression="snappy", index=False)

    size_gb = OUTPUT_FILE.stat().st_size / 1_000_000_000
    print(f"\n✅ Done! Saved {len(df_mn):,} daily records to")
    print(f"   {OUTPUT_FILE}")
    print(f"   Size: {size_gb:.2f} GB (ready for analysis)")

if __name__ == "__main__":
    main()
