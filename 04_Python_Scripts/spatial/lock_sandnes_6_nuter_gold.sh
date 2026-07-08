#!/usr/bin/env bash
# Lock operator gold for Sandnes 6 Nuter — full HITL spec (map-first orphan).
#
# Manual: S2/S3 start, S2 gravel bands; ML keep S3/S4 else S3/F2 on trail windows.
#
# Usage (from repo root, after bootstrap + HITL export):
#   ./04_Python_Scripts/spatial/lock_sandnes_6_nuter_gold.sh
#   ./04_Python_Scripts/spatial/lock_sandnes_6_nuter_gold.sh --dry-run
#   ./04_Python_Scripts/spatial/lock_sandnes_6_nuter_gold.sh --force
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

RACE_ID="sandnes_6_nuter"
TERRAIN_MAP="config/spatial_terrain_map_${RACE_ID}.json"
PANEL="03_Processed_Data/spatial/${RACE_ID}_course/panel_1m.parquet"
ML_PRED="${PANEL%/*}/${RACE_ID}_ml_predictions.parquet"
ML_FALLBACK="${PANEL%/*}/ml_predictions.parquet"

DRY_RUN=""
FORCE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --force) FORCE=1; shift ;;
    *)
      echo "Usage: $0 [--dry-run] [--force]" >&2
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

gold_ed() {
  python3 04_Python_Scripts/spatial/gold_span_editor.py \
    --terrain-map "$TERRAIN_MAP" "$@"
}

echo "=== Sandnes 6 Nuter — operator gold lock (full course) ==="
echo "  window:   km 0.000–${KM_END}"
echo "  existing: ${SPAN_COUNT} span(s)"
echo ""

if [[ "$SPAN_COUNT" -gt 0 && -z "$FORCE" ]]; then
  echo "Terrain map already has gold. Re-run with --force to replace." >&2
  exit 1
fi

run() {
  echo ">> $*"
  if [[ -z "$DRY_RUN" ]]; then
    "$@"
  fi
}

ml_window() {
  local ks="$1" ke="$2" label="$3"
  local args=(
    "${ML_ARG[@]}"
    --km-start "$ks" --km-end "$ke"
    --keep-surface S3 S4
    --else-surface S3 --else-friction F2
    --reason "Sandnes 6 Nuter ${label}: keep ML S3/S4 else S3/F2"
  )
  if [[ -n "$DRY_RUN" ]]; then
    ml_lock "${args[@]}" --dry-run
  else
    run ml_lock "${args[@]}"
  fi
}

apply_span() {
  local ks="$1" ke="$2" sc="$3" fr="$4" rn="$5"
  if [[ -n "$DRY_RUN" ]]; then
    echo "  add km ${ks}–${ke} ${sc}/${fr}  (${rn})"
  else
    run gold_ed add --km-start "$ks" --km-end "$ke" \
      --surface "$sc" --friction "$fr" --reason "$rn"
  fi
}

echo "━━━ 1/4 Clear km 0–${KM_END} ━━━"
if [[ -n "$DRY_RUN" ]]; then
  gold_ed --dry-run clear-window --km-start 0.0 --km-end "$KM_END"
else
  run gold_ed clear-window --km-start 0.0 --km-end "$KM_END"
fi

echo ""
echo "━━━ 2/4 Manual start km 0–1.0 ━━━"
apply_span 0.0  0.35  S2 F2 "orthophoto: gravel km 0–0.35"
apply_span 0.35 1.0   S3 F2 "orthophoto: grass/trail km 0.35–1.0"

echo ""
echo "━━━ 3/4 ML filter trail windows ━━━"
ml_window 1.0 4.3  "km 1–4.3"
apply_span 4.3  5.0   S2 F2 "orthophoto: gravel km 4.3–5.0"
ml_window 5.0 12.5 "km 5–12.5"
apply_span 12.5 "$KM_END" S2 F2 "orthophoto: gravel km 12.5–end"

echo ""
echo "━━━ 4/4 Coverage ━━━"
if [[ -z "$DRY_RUN" ]]; then
  python3 04_Python_Scripts/spatial/report_gold_coverage.py --terrain-map "$TERRAIN_MAP"
else
  echo "(skipped — dry-run)"
fi
