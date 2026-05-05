"""Create the joined summary table: storm events + daily MN weather."""

from pathlib import Path
import pandas as pd

def main():
    INPUT_DIR = Path("processed")
    OUTPUT_FILE = INPUT_DIR / "storm_weather_summary_mn.parquet"

    print("Loading weather and storm data...")
    weather = pd.read_parquet(INPUT_DIR / "weather_daily_mn.parquet")
    storms = pd.read_parquet(INPUT_DIR / "storm_events_mn.parquet")

    # Create daily Minnesota-wide weather averages (simple but very useful summary)
    daily_weather = (
        weather.groupby("date")
        .agg({
            "tmax": "mean",
            "tmin": "mean",
            "prcp": "mean",
            "snow": "mean",
            "snwd": "mean",
            "awnd": "mean"
        })
        .round(2)
        .reset_index()
    )

    # Join storm events to daily weather on BEGIN_DATE
    summary = storms.merge(
        daily_weather,
        left_on="BEGIN_DATE",
        right_on="date",
        how="left"
    ).drop(columns=["date"])   # remove duplicate date column

    # Rename weather columns to make it clear they are daily averages
    summary = summary.rename(columns={
        "tmax": "daily_tmax_avg",
        "tmin": "daily_tmin_avg",
        "prcp": "daily_prcp_avg",
        "snow": "daily_snow_avg",
        "snwd": "daily_snwd_avg",
        "awnd": "daily_awnd_avg"
    })

    summary.to_parquet(OUTPUT_FILE, compression="snappy", index=False)

    size_mb = OUTPUT_FILE.stat().st_size / 1_000_000
    print(f"\n✅ Done! Created storm_weather_summary_mn.parquet")
    print(f"   Rows: {len(summary):,}")
    print(f"   Size: {size_mb:.1f} MB")
    print(f"   Columns include: EVENT_TYPE, BEGIN_DATE, CZ_NAME, daily_tmax_avg, daily_prcp_avg, DAMAGE_PROPERTY, etc.")
    print(f"   File saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
