"""Filter NOAA Storm Events (.csv.gz files) to Minnesota only → Parquet."""

from pathlib import Path
import pandas as pd

def parse_damage(val):
    """Convert '0K', '25K', '2.5M', '0' etc. into actual numbers (dollars)."""
    if pd.isna(val) or val == 0 or str(val).strip() == '0':
        return 0.0
    s = str(val).upper().strip()
    try:
        if s.endswith('K'):
            return float(s[:-1]) * 1_000
        elif s.endswith('M'):
            return float(s[:-1]) * 1_000_000
        else:
            return float(s)
    except:
        return 0.0

def main():
    INPUT_DIR = Path("storm_events_raw")
    OUTPUT_DIR = Path("processed")
    OUTPUT_FILE = OUTPUT_DIR / "storm_events_mn.parquet"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    gz_files = sorted(INPUT_DIR.glob("StormEvents_details-ftp_v1.0_d*.csv.gz"))

    print(f"Found {len(gz_files)} .gz files. Filtering to Minnesota only...")

    all_mn = []

    for gz_path in gz_files:
        year = gz_path.stem.split("_d")[1][:4]
        print(f"Processing {year}...")

        df = pd.read_csv(gz_path, compression="gzip", low_memory=False)

        df_mn = df[df["STATE"] == "MINNESOTA"].copy()

        if df_mn.empty:
            continue

        keep_cols = [
            "EVENT_ID", "BEGIN_YEARMONTH", "BEGIN_DAY", "BEGIN_TIME",
            "END_YEARMONTH", "END_DAY", "END_TIME", "EVENT_TYPE",
            "CZ_NAME", "CZ_TYPE", "CZ_FIPS", "BEGIN_LAT", "BEGIN_LON",
            "INJURIES_DIRECT", "DEATHS_DIRECT", "DAMAGE_PROPERTY",
            "DAMAGE_CROPS", "MAGNITUDE", "TOR_F_SCALE",
            "EPISODE_NARRATIVE", "EVENT_NARRATIVE"
        ]
        df_mn = df_mn[[c for c in keep_cols if c in df_mn.columns]]

        # Clean dates
        df_mn["BEGIN_DATE"] = pd.to_datetime(
            df_mn["BEGIN_YEARMONTH"].astype(str) + df_mn["BEGIN_DAY"].astype(str).str.zfill(2),
            format="%Y%m%d", errors="coerce"
        )

        all_mn.append(df_mn)

    if not all_mn:
        print("No Minnesota events found.")
        return

    print("Combining all years...")
    df_final = pd.concat(all_mn, ignore_index=True)
    df_final = df_final.sort_values("BEGIN_DATE").reset_index(drop=True)

    # ←←← FIX: Convert damage columns to numeric
    print("Cleaning DAMAGE_PROPERTY and DAMAGE_CROPS columns...")
    for col in ["DAMAGE_PROPERTY", "DAMAGE_CROPS"]:
        if col in df_final.columns:
            df_final[col] = df_final[col].apply(parse_damage)

    df_final.to_parquet(OUTPUT_FILE, compression="snappy", index=False)

    size_mb = OUTPUT_FILE.stat().st_size / 1_000_000
    print(f"\n✅ Done! Saved {len(df_final):,} Minnesota storm events to")
    print(f"   {OUTPUT_FILE}")
    print(f"   Size: {size_mb:.1f} MB (ready for Spark / analysis)")

if __name__ == "__main__":
    main()
