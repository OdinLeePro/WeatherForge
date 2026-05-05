#!/usr/bin/env bash
set -euo pipefail

INPUT_DIR="../ghcnd_all/ghcnd_all"
OUTPUT_DIR="./outputs"
LOG_DIR="./logs"
JOBS=4

mkdir -p "$OUTPUT_DIR" "$LOG_DIR"

find "$INPUT_DIR" -type f -name '*.dly' -print0 \
| xargs -0 -n 1 -P "$JOBS" sh -c '
  in="$1"
  base="$(basename "$in" .dly)"
  out="'"$OUTPUT_DIR"'/${base}.csv"
  log="'"$LOG_DIR"'/${base}.log"

  python3 ./ghcn_dly_to_csv.py "$in" --output "$out" >"$log" 2>&1
' sh
