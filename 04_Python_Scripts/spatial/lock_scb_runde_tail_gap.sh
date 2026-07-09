#!/usr/bin/env bash
# Repair SCB Runde operator gold gaps (km/m sync, orthophoto holes, tail extend).
#
# Symptom: pool build reports 6925/6945 m labeled — often km 0.98–1.0 grass bridge
# missing and/or stale course_m_end on terminal gravel span.
#
# Usage (from repo root, operator Mac with local SCB configs + panel):
#   python3 04_Python_Scripts/spatial/report_gold_coverage.py \
#     --terrain-map config/spatial_terrain_map_scb_runde.json \
#     --panel 03_Processed_Data/spatial/scb_runde_course/panel_1m.parquet
#   ./04_Python_Scripts/spatial/lock_scb_runde_tail_gap.sh
#   ./04_Python_Scripts/spatial/lock_scb_runde_tail_gap.sh --dry-run
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

DRY_RUN=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    *)
      echo "Usage: $0 [--dry-run]" >&2
      exit 1
      ;;
  esac
done

ARGS=()
if [[ -n "$DRY_RUN" ]]; then
  ARGS+=(--dry-run)
fi

python3 04_Python_Scripts/spatial/fix_scb_runde_gold_gaps.py "${ARGS[@]}"
