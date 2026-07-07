#!/usr/bin/env bash
# Vinje Terrengløp — bootstrap FIT, run pooled/course gold suggester, export HITL PNGs with ML strip.
# No operator gold required; Assigned row empty until you label.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

FIT_ARG=()
SKIP_BOOT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --fit) FIT_ARG=(--fit "$2"); shift 2 ;;
    --skip-bootstrap) SKIP_BOOT=1; shift ;;
    --model) export ML_MODEL="$2"; shift 2 ;;
    *)
      echo "Usage: $0 --fit PATH [--model path/to/gold_suggester.joblib] [--skip-bootstrap]" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$SKIP_BOOT" ]]; then
  echo "=== Bootstrap Vinje Terrengløp ==="
  python3 04_Python_Scripts/spatial/bootstrap_vinje_terrenglop_course.py "${FIT_ARG[@]}"
fi

PANEL="03_Processed_Data/spatial/vinje_terrenglop_course/panel_1m.parquet"
if [[ ! -f "$PANEL" ]]; then
  echo "Panel missing — run with --fit 02_Raw_Data/donors/Subject_A/Vinje_Terrenglop_20251005.fit" >&2
  exit 1
fi

if [[ -z "${ML_MODEL:-}" ]]; then
  if [[ -f "07_ML_Models/spatial/gold_suggester_map_first_pool_v0.joblib" ]]; then
    export ML_MODEL="07_ML_Models/spatial/gold_suggester_map_first_pool_v0.joblib"
  elif [[ -f "07_ML_Models/spatial/gold_suggester_gramstad_runde_v0.joblib" ]]; then
    export ML_MODEL="07_ML_Models/spatial/gold_suggester_gramstad_runde_v0.joblib"
  fi
fi

if [[ -z "${ML_MODEL:-}" || ! -f "${ML_MODEL}" ]]; then
  echo "No ML model found. Train pooled model first, e.g.:" >&2
  echo "  merge_gold_training_sets.py + train_gold_suggester.py → gold_suggester_map_first_pool_v0.joblib" >&2
  echo "Or pass: $0 --fit <path> --model 07_ML_Models/spatial/gold_suggester_gramstad_runde_v0.joblib" >&2
  exit 1
fi

echo "=== Export HITL PNGs with ML suggester strip (model: $ML_MODEL) ==="
./04_Python_Scripts/spatial/export_hitl_chunks_vinje_terrenglop.sh

echo ""
echo "OK Vinje Terrengløp ML strip → 06_Visualizations/vinje_terrenglop_hitl/chunk_t*.png"
