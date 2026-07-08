#!/usr/bin/env bash
# Complete Gramstad Runde operator gold — gap report, GPS transfer, ML gap-fill, retrain.
#
# Run on operator Mac after bootstrap + partial labeling (~52% locked).
# Does not auto-lock without review unless --apply-ml-locks is passed.
#
# Usage (from repo root):
#   ./04_Python_Scripts/spatial/complete_gramstad_gold_wave.sh
#   ./04_Python_Scripts/spatial/complete_gramstad_gold_wave.sh --apply-gps-transfer
#   ./04_Python_Scripts/spatial/complete_gramstad_gold_wave.sh --apply-ml-locks
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

TERRAIN_MAP="config/spatial_terrain_map_gramstad_runde.json"
PANEL="03_Processed_Data/spatial/gramstad_runde_course/panel_1m.parquet"
OUT_DIR="06_Visualizations/gramstad_runde_hitl"
MODEL="${ML_MODEL:-07_ML_Models/spatial/gold_suggester_map_first_pool_v0.joblib}"
SUGGEST_CSV="03_Processed_Data/spatial/suggested_locks_gramstad_runde_gaps.csv"
GAP_JSON="03_Processed_Data/spatial/gramstad_runde_gold_gaps.json"

APPLY_GPS=""
APPLY_ML=""
SKIP_GPS=""
SKIP_ML=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply-gps-transfer) APPLY_GPS=1; shift ;;
    --apply-ml-locks) APPLY_ML=1; shift ;;
    --skip-gps-transfer) SKIP_GPS=1; shift ;;
    --skip-ml-suggest) SKIP_ML=1; shift ;;
    *)
      echo "Usage: $0 [--apply-gps-transfer] [--apply-ml-locks] [--skip-gps-transfer] [--skip-ml-suggest]" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "$PANEL" ]]; then
  echo "Panel missing: $PANEL" >&2
  echo "Run: python3 04_Python_Scripts/spatial/bootstrap_gramstad_runde_course.py --fit <FIT>" >&2
  exit 1
fi

read -r KM_END <<<"$(python3 - <<'PY'
import json
from pathlib import Path
m = json.loads(Path("config/spatial_align_manifest_gramstad_runde.json").read_text())
print(m["km_analysis_window"][1])
PY
)"

echo "=== Gramstad Runde gold completion wave ==="
echo "  window: km 0–${KM_END}"
echo "  model:  ${MODEL}"
echo ""

echo "━━━ 1/5 Coverage report ━━━"
set +e
python3 04_Python_Scripts/spatial/report_gold_coverage.py \
  --terrain-map "$TERRAIN_MAP" \
  --panel "$PANEL" \
  --km-end "$KM_END" \
  --json "$GAP_JSON"
COV_RC=$?
set -e
echo ""

if [[ -z "$SKIP_GPS" ]]; then
  echo "━━━ 2/5 GPS transfer from SUT_43 gramstad_band (dry-run) ━━━"
  SOURCE_MAP="config/spatial_terrain_map_sut43.gold_local.json"
  if [[ ! -f "$SOURCE_MAP" ]]; then
    SOURCE_MAP="config/spatial_terrain_map_sut43.json"
  fi
  GPS_ARGS=(
    --source-terrain-map "$SOURCE_MAP"
    --source-panel "03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet"
    --source-km-start 29 --source-km-end 41
    --target-terrain-map "$TERRAIN_MAP"
    --target-panel "$PANEL"
    --max-match-m 35
  )
  if [[ -n "$APPLY_GPS" ]]; then
    echo "Applying GPS transfer → $TERRAIN_MAP"
    python3 04_Python_Scripts/spatial/transfer_gold_spans_gps.py "${GPS_ARGS[@]}"
  else
    python3 04_Python_Scripts/spatial/transfer_gold_spans_gps.py "${GPS_ARGS[@]}" --dry-run
    echo "  (pass --apply-gps-transfer to write spans)"
  fi
  echo ""
else
  echo "━━━ 2/5 GPS transfer skipped ━━━"
  echo ""
fi

if [[ -z "$SKIP_ML" ]]; then
  echo "━━━ 3/5 ML gap suggestions (pooled model) ━━━"
  if [[ ! -f "$MODEL" ]]; then
    echo "WARN model missing: $MODEL — train pool first" >&2
  else
    python3 04_Python_Scripts/spatial/suggest_gold_spans.py \
      --engine ml --mode gaps-only \
      --terrain-map "$TERRAIN_MAP" \
      --panel "$PANEL" \
      --model "$MODEL" \
      --no-hmm-draft \
      --km-start 0 --km-end "$KM_END" \
      --output "$SUGGEST_CSV" \
      --print-sample
    echo "  → $SUGGEST_CSV"
  fi
  echo ""

  echo "━━━ 4/5 ML auto-lock (HIGH confidence NEW only) ━━━"
  if [[ ! -f "$MODEL" ]]; then
    echo "  skipped — no model"
  elif [[ -n "$APPLY_ML" ]]; then
    python3 04_Python_Scripts/spatial/auto_lock_gold_spans.py \
      --terrain-map "$TERRAIN_MAP" \
      --panel "$PANEL" \
      --model "$MODEL" \
      --no-hmm-draft \
      --km-start 0 --km-end "$KM_END" \
      --sector-name gramstad_runde
  else
    python3 04_Python_Scripts/spatial/auto_lock_gold_spans.py \
      --terrain-map "$TERRAIN_MAP" \
      --panel "$PANEL" \
      --model "$MODEL" \
      --no-hmm-draft \
      --km-start 0 --km-end "$KM_END" \
      --sector-name gramstad_runde \
      --dry-run
    echo "  (pass --apply-ml-locks to accept HIGH-confidence gap fills)"
  fi
  echo ""
else
  echo "━━━ 3–4/5 ML suggest/auto-lock skipped ━━━"
  echo ""
fi

echo "━━━ 5/5 Manual review + retrain ━━━"
cat <<EOF

Review gaps in HITL PNGs:
  open ${OUT_DIR}/chunk_t*.png
  gaps JSON: ${GAP_JSON}

Add spans manually:
  python3 04_Python_Scripts/spatial/gold_span_editor.py \\
    --terrain-map ${TERRAIN_MAP} list

  python3 04_Python_Scripts/spatial/gold_span_editor.py \\
    --terrain-map ${TERRAIN_MAP} add \\
    --km-start <lo> --km-end <hi> --surface S2 --friction F2 \\
    --reason "orthophoto lock"

When coverage is 100%:
  python3 04_Python_Scripts/spatial/report_gold_coverage.py \\
    --terrain-map ${TERRAIN_MAP} --panel ${PANEL} --km-end ${KM_END}

  ./04_Python_Scripts/spatial/train_map_first_gold_pool.sh --with-o1-anchors --rebuild-exports
  ./04_Python_Scripts/spatial/export_hitl_chunks_gramstad_runde.sh

EOF

if [[ "$COV_RC" -eq 0 ]]; then
  echo "OK Gramstad Runde already fully golded in window."
else
  echo "Coverage incomplete — continue labeling wave above."
fi
