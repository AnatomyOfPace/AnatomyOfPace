#!/usr/bin/env bash
# Lock operator gold for Skåfonnlega Sveivida — full HITL spec (map-first orphan).
#
# Usage (from repo root, after bootstrap + HITL export):
#   ./04_Python_Scripts/spatial/lock_skafonnlega_sveivida_gold.sh --force
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

RACE_ID="skafonnlega_sveivida"
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

if [[ ! -f "$TERRAIN_MAP" || ! -f "$PANEL" ]]; then
  echo "Bootstrap + export HITL first: bootstrap_map_first_orphan.py --course $RACE_ID" >&2
  exit 1
fi

if [[ -f "$ML_PRED" ]]; then
  ML_ARG=(--ml-predictions "$ML_PRED")
elif [[ -f "$ML_FALLBACK" ]]; then
  ML_ARG=(--ml-predictions "$ML_FALLBACK")
else
  echo "ML predictions missing — export HITL first." >&2
  exit 1
fi

read -r KM_END SPAN_COUNT <<<"$(python3 - <<PY
import json, sys
from pathlib import Path
sys.path.insert(0, "04_Python_Scripts")
from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.validation_dashboard import operator_gold_spans
race_id = "${RACE_ID}"
km_end = json.loads(Path(f"config/spatial_align_manifest_{race_id}.json").read_text())["km_analysis_window"][1]
print(km_end, len(operator_gold_spans(load_terrain_map(Path(f"config/spatial_terrain_map_{race_id}.json")))))
PY
)"

ml_lock() {
  python3 04_Python_Scripts/spatial/lock_gold_from_ml_filter.py --terrain-map "$TERRAIN_MAP" "$@"
}
gold_ed() {
  python3 04_Python_Scripts/spatial/gold_span_editor.py --terrain-map "$TERRAIN_MAP" "$@"
}

if [[ "$SPAN_COUNT" -gt 0 && -z "$FORCE" ]]; then
  echo "Already has ${SPAN_COUNT} span(s). Use --force to replace." >&2
  exit 1
fi

run() { echo ">> $*"; [[ -z "$DRY_RUN" ]] && "$@"; }
apply_span() {
  local ks="$1" ke="$2" sc="$3" fr="$4" rn="$5"
  if [[ -n "$DRY_RUN" ]]; then echo "  add km ${ks}–${ke} ${sc}/${fr}"; else
    run gold_ed add --km-start "$ks" --km-end "$ke" --surface "$sc" --friction "$fr" --reason "$rn"
  fi
}
ml_pass() {
  local ks="$1" ke="$2" rn="$3"
  local args=("${ML_ARG[@]}" --km-start "$ks" --km-end "$ke"
    --keep-surface S1 S2 S3 S4 S5 S6 --else-surface S4 --else-friction F3 --reason "$rn")
  [[ -n "$DRY_RUN" ]] && ml_lock "${args[@]}" --dry-run || run ml_lock "${args[@]}"
}
ml_s34() {
  local ks="$1" ke="$2" rn="$3"
  local args=("${ML_ARG[@]}" --km-start "$ks" --km-end "$ke"
    --keep-surface S3 S4 --else-surface S3 --else-friction F2 --reason "$rn")
  [[ -n "$DRY_RUN" ]] && ml_lock "${args[@]}" --dry-run || run ml_lock "${args[@]}"
}

echo "=== Skåfonnlega Sveivida — operator gold lock ==="
echo "  window: km 0–${KM_END} | existing spans: ${SPAN_COUNT}"

if [[ -n "$DRY_RUN" ]]; then gold_ed --dry-run clear-window --km-start 0.0 --km-end "$KM_END"
else run gold_ed clear-window --km-start 0.0 --km-end "$KM_END"; fi

ml_pass 0.0 5.0 "Sveivida km 0–5: use ML prediction"
ml_s34 5.0 6.45 "Sveivida km 5–6.45: keep ML S3/S4 else S3/F2"
apply_span 6.45 6.8  S1 F0 "orthophoto: paved km 6.45–6.8"
apply_span 6.8  7.0  S2 F2 "orthophoto: gravel km 6.8–7.0"
apply_span 7.0  8.0  S2 F2 "orthophoto: gravel km 7.0–8.0"
apply_span 8.0  8.1  S2 F2 "orthophoto: gravel km 8.0–8.1"
apply_span 8.1  9.0  S1 F0 "orthophoto: paved km 8.1–9.0"
apply_span 9.0  9.7  S1 F0 "orthophoto: paved km 9.0–9.7"
apply_span 9.7  "$KM_END" S2 F2 "orthophoto: gravel km 9.7–end"

[[ -z "$DRY_RUN" ]] && python3 04_Python_Scripts/spatial/report_gold_coverage.py --terrain-map "$TERRAIN_MAP"
