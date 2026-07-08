#!/usr/bin/env bash
# Apply operator gold for SCB Runde (map-first orphan training loop).
#
# Full course km 0–end: ML filter keep S2/S3/S4/S5 else S2/F2 (gravel-primary).
# Override individual km windows via gold_span_editor after export if orthophoto
# disagrees with ML.
#
# Usage (from repo root, after bootstrap + HITL export):
#   ./04_Python_Scripts/spatial/lock_scb_runde_gold.sh
#   ./04_Python_Scripts/spatial/lock_scb_runde_gold.sh --dry-run
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

RACE_ID="scb_runde"
TERRAIN_MAP="config/spatial_terrain_map_${RACE_ID}.json"
PANEL="03_Processed_Data/spatial/${RACE_ID}_course/panel_1m.parquet"
ML_PRED="${PANEL%/*}/${RACE_ID}_ml_predictions.parquet"
ML_FALLBACK="${PANEL%/*}/ml_predictions.parquet"

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

if [[ ! -f "$TERRAIN_MAP" ]]; then
  echo "Terrain map missing: $TERRAIN_MAP" >&2
  echo "Run: python3 04_Python_Scripts/spatial/bootstrap_map_first_orphan.py --course $RACE_ID" >&2
  exit 1
fi

if [[ ! -f "$PANEL" ]]; then
  echo "Panel missing: $PANEL" >&2
  exit 1
fi

if [[ -f "$ML_PRED" ]]; then
  ML_ARG=(--ml-predictions "$ML_PRED")
elif [[ -f "$ML_FALLBACK" ]]; then
  ML_ARG=(--ml-predictions "$ML_FALLBACK")
else
  echo "ML predictions missing — export HITL first:" >&2
  echo "  ML_MODEL=07_ML_Models/spatial/gold_suggester_map_first_pool_v0.joblib \\" >&2
  echo "    ./04_Python_Scripts/spatial/export_hitl_map_first_orphan.sh $RACE_ID" >&2
  exit 1
fi

read -r KM_END SPAN_COUNT <<<"$(python3 - <<PY
import json
import sys
from pathlib import Path

sys.path.insert(0, "04_Python_Scripts")
from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.validation_dashboard import operator_gold_spans

race_id = "${RACE_ID}"
manifest = Path(f"config/spatial_align_manifest_{race_id}.json")
km_end = json.loads(manifest.read_text())["km_analysis_window"][1]
tmap = load_terrain_map(Path(f"config/spatial_terrain_map_{race_id}.json"))
print(km_end, len(operator_gold_spans(tmap)))
PY
)"

ml_lock() {
  python3 04_Python_Scripts/spatial/lock_gold_from_ml_filter.py \
    --terrain-map "$TERRAIN_MAP" "$@"
}

echo "=== SCB Runde — operator gold apply ==="
echo "  window:     km 0.000–${KM_END}"
echo "  existing:   ${SPAN_COUNT} span(s)"
echo "  ML source:  ${ML_PRED}"
echo ""

if [[ "$SPAN_COUNT" -gt 0 ]]; then
  echo "Warning: terrain map already has ${SPAN_COUNT} gold span(s)." >&2
  echo "  Re-run is safe only on a fresh map (0 spans). Clear spans manually if re-applying." >&2
  exit 1
fi

run() {
  echo ">> $*"
  if [[ -z "$DRY_RUN" ]]; then
    "$@"
  fi
}

echo "━━━ 1/2 ML filter full course km 0–${KM_END} ━━━"
ML_ARGS=(
  "${ML_ARG[@]}"
  --km-start 0.0 --km-end "$KM_END"
  --keep-surface S2 S3 S4 S5 --else-surface S2 --else-friction F2
  --reason "SCB Runde gravel/trail ML filter"
)
if [[ -n "$DRY_RUN" ]]; then
  ml_lock "${ML_ARGS[@]}" --dry-run
else
  run ml_lock "${ML_ARGS[@]}"
fi

echo ""
echo "━━━ 2/2 Coverage report ━━━"
if [[ -z "$DRY_RUN" ]]; then
  python3 04_Python_Scripts/spatial/report_gold_coverage.py --terrain-map "$TERRAIN_MAP"
else
  echo "(skipped — dry-run)"
fi
