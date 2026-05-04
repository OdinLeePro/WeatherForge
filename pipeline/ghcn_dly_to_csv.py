
"""Parse NOAA/GHCN-Daily `.dly` files into a tidy CSV.

This script exists as an accessible Python equivalent for working with fixed-width
`.dly` files. It was validated against the provided `ACW00011604.csv` file.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import argparse
import calendar
import csv
from datetime import date
from typing import Iterator, Optional


MISSING_SENTINEL = -9999


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
        value_str = line[start:start + 5]
        mflag = line[start + 5:start + 6]
        qflag = line[start + 6:start + 7]
        sflag = line[start + 7:start + 8]

        value_str = value_str.rstrip("\n")
        value = int(value_str)
        is_missing = value == MISSING_SENTINEL
        is_valid_date = day <= calendar.monthrange(year, month)[1]
        is_trace = False
        value_raw: str = value_str
        value_clean: Optional[int | str]

        if is_missing:
            value_raw = "is_null"
            value_clean = None
        else:
            value_clean = value

        # Some derived CSVs encode trace precipitation/snowfall as values with a trailing T,
        # but `.dly` itself expresses the numeric quantity and uses flags separately.
        # We keep the parsed value numeric here and expose flags distinctly.

        row_date = f"{year:04d}-{month:02d}-{day:02d}" if is_valid_date else ""
        yield DlyRow(
            station_id=station_id,
            date=row_date,
            element=element,
            day=day,
            value_raw=value_raw,
            value_clean=value_clean,
            is_missing=is_missing,
            is_valid_date=is_valid_date,
            mflag=mflag.strip(),
            qflag=qflag.strip(),
            sflag=sflag.strip(),
            is_trace=is_trace,
        )



def parse_dly_file(path: str | Path) -> list[DlyRow]:
    path = Path(path)
    rows: list[DlyRow] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip():
                rows.extend(parse_dly_line(line))
    return rows



def write_csv(rows: list[DlyRow], output_path: str | Path) -> None:
    output_path = Path(output_path)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))



def main() -> None:
    parser = argparse.ArgumentParser(description="Convert NOAA GHCN .dly fixed-width files into CSV")
    parser.add_argument("input_file", help="Path to the .dly file")
    parser.add_argument("--output", default="converted_from_dly.csv", help="Destination CSV path")
    args = parser.parse_args()

    rows = parse_dly_file(args.input_file)
    write_csv(rows, args.output)
    print(f"Wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
