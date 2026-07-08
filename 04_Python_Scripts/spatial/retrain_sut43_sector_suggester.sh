#!/usr/bin/env bash
# Rebuild SUT_43 full gold export and retrain sector-routed gold suggesters.
#
# Run on operator Mac after gramstad/upstream REVISE locks are written to sector
# terrain maps. Refreshes gold_training_set_sut43_full.parquet, trains start /
# bridge / downstream sector models, smoke-tests hybrid routing, and updates
# config/gold_suggester_routing.json when promotion gates pass.
#
# Usage (from repo root):
#   ./04_Python_Scripts/spatial/retrain_sut43_sector_suggester.sh
#   ./04_Python_Scripts/spatial/retrain_sut43_sector_suggester.sh --merge-maps
#   ./04_Python_Scripts/spatial/retrain_sut43_sector_suggester.sh --train-only
#   ./04_Python_Scripts/spatial/retrain_sut43_sector_suggester.sh --smoke-only
#   ./04_Python_Scripts/spatial/retrain_sut43_sector_suggester.sh --full-42k
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

BUILD="04_Python_Scripts/spatial/build_gold_training_set.py"
MERGE_MAPS="04_Python_Scripts/spatial/merge_terrain_maps.py"
EVAL_SECTORS="04_Python_Scripts/spatial/eval_gold_suggester_sectors.py"
EVAL_42K="04_Python_Scripts/spatial/eval_sut43full_42k_retrain.py"

PROCESSED="03_Processed_Data/spatial"
ONTOLOGY="${PROCESSED}/sut43_terrain_ontology"
FULL_MAP="config/spatial_terrain_map_sut43_full.json"
FULL_PANEL="${ONTOLOGY}/panel_full_1m.parquet"
FULL_EXPORT="${PROCESSED}/gold_training_set_sut43_full.parquet"
CAL_POOL="${PROCESSED}/gold_training_set_calibration_pool.parquet"
HMM_DRAFT="07_ML_Models/terrain_hmm_sut43_draft_predictions.parquet"

MERGE_MAPS_FLAG=""
SKIP_EXPORT=""
TRAIN_ONLY=""
SMOKE_ONLY=""
FULL_42K=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --merge-maps) MERGE_MAPS_FLAG=1; shift ;;
    --skip-export) SKIP_EXPORT=1; shift ;;
    --train-only) TRAIN_ONLY=1; shift ;;
    --smoke-only) SMOKE_ONLY=1; shift ;;
    --full-42k) FULL_42K=1; shift ;;
    *)
      echo "Usage: $0 [--merge-maps] [--skip-export] [--train-only] [--smoke-only] [--full-42k]" >&2
      exit 1
      ;;
  esac
done

echo "=== SUT_43 sector suggester retrain ==="
echo ""

echo "━━━ Preflight ━━━"
missing=0
for req in \
  "$FULL_PANEL" \
  "$CAL_POOL" \
  "$HMM_DRAFT" \
  "config/spatial_terrain_map_sut43_start.json" \
  "config/spatial_terrain_map_sut43_bridge.json" \
  "config/spatial_terrain_map_sut43_upstream.json" \
  "config/spatial_terrain_map_sut43.json" \
  "config/spatial_terrain_map_sut43_finish.json" \
  "${ONTOLOGY}/panel_start_1m.parquet" \
  "${ONTOLOGY}/panel_bridge_1m.parquet" \
  "${ONTOLOGY}/panel_1m.parquet"
do
  if [[ ! -f "$req" ]]; then
    echo "  MISSING: $req" >&2
    missing=1
  fi
done
if [[ "$missing" == "1" ]]; then
  echo "" >&2
  echo "SUT_43 panels and calibration pool are local-only (gitignored)." >&2
  echo "Bootstrap / export on operator Mac before retrain." >&2
  exit 1
fi
echo "  OK panels, calibration pool, HMM draft"
echo ""

if [[ -n "$MERGE_MAPS_FLAG" ]]; then
  echo "━━━ Merge sector terrain maps → full course ━━━"
  python3 "$MERGE_MAPS" \
    --sector config/spatial_terrain_map_sut43_start.json:0.5:8.0 \
    --sector config/spatial_terrain_map_sut43_bridge.json:8.0:22.0 \
    --sector config/spatial_terrain_map_sut43_upstream.json:22.0:29.0 \
    --sector config/spatial_terrain_map_sut43.json:29.0:41.0 \
    --sector config/spatial_terrain_map_sut43_finish.json:41.0:42.5 \
    --sector config/spatial_terrain_map_sut43_finish_tail.json:42.5:43.0 \
    --km-start 0.5 \
    --km-end 43.0 \
    --output "$FULL_MAP" \
    --report-json 07_ML_Models/spatial/merge_terrain_map_sut43_full_report.json
  echo ""
fi

if [[ -z "$SKIP_EXPORT" && -z "$SMOKE_ONLY" ]]; then
  echo "━━━ Rebuild full-course gold training export ━━━"
  python3 "$BUILD" \
    --terrain-map "$FULL_MAP" \
    --panel "$FULL_PANEL" \
    --km-start 0.5 \
    --km-end 43.0 \
    --output "$FULL_EXPORT" \
    --summary-json "${PROCESSED}/gold_training_set_sut43_full_summary.json"
  echo "  → $FULL_EXPORT"
  echo ""
fi

EVAL_ARGS=()
[[ -n "$TRAIN_ONLY" ]] && EVAL_ARGS+=(--train-only)
[[ -n "$SMOKE_ONLY" ]] && EVAL_ARGS+=(--smoke-only)

echo "━━━ Train + evaluate sector models ━━━"
python3 "$EVAL_SECTORS" "${EVAL_ARGS[@]}"
echo ""

if [[ -n "$FULL_42K" && -z "$SMOKE_ONLY" ]]; then
  echo "━━━ Optional full 42k retrain matrix ━━━"
  python3 "$EVAL_42K"
  echo ""
fi

echo "OK sector retrain complete."
echo "  Eval summary: 07_ML_Models/spatial/gold_suggester_sector_eval.json"
echo "  Routing:       config/gold_suggester_routing.json"
echo ""
echo "Re-export gramstad REVISE HITL:"
echo "  python3 04_Python_Scripts/spatial/suggest_gold_spans.py \\"
echo "    --engine ml --mode all --sector-routing \\"
echo "    --terrain-map config/spatial_terrain_map_sut43.json \\"
echo "    --panel ${ONTOLOGY}/panel_1m.parquet \\"
echo "    --km-start 29 --km-end 41 \\"
echo "    --output ${PROCESSED}/suggested_revise_sut43_gramstad_sector.csv"
