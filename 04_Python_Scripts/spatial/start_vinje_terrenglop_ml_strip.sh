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
  if [[ ${#FIT_ARG[@]} -eq 0 ]]; then
    echo "No --fit passed; trying auto-discover (Vinje + Terrengl in filename)..."
    python3 04_Python_Scripts/spatial/bootstrap_vinje_terrenglop_course.py --discover || true
  fi
  python3 04_Python_Scripts/spatial/bootstrap_vinje_terrenglop_course.py "${FIT_ARG[@]}"
fi

PANEL="03_Processed_Data/spatial/vinje_terrenglop_course/panel_1m.parquet"
if [[ ! -f "$PANEL" ]]; then
  echo "Panel missing — run with --fit 02_Raw_Data/donors/Subject_A/Vinje_Terrenglop_20251005.fit" >&2
  exit 1
fi

_resolve_ml_model() {
  local candidate
  if [[ -n "${ML_MODEL:-}" && -f "${ML_MODEL}" ]]; then
    return 0
  fi
  if [[ -n "${ML_MODEL:-}" && ! -f "${ML_MODEL}" ]]; then
    echo "WARN ML_MODEL not found: ${ML_MODEL} — trying fallbacks" >&2
    unset ML_MODEL
  fi
  for candidate in \
    "07_ML_Models/spatial/gold_suggester_map_first_pool_v0.joblib" \
    "07_ML_Models/spatial/gold_suggester_gramstad_runde_v0.joblib" \
    "07_ML_Models/spatial/gold_suggester_klepp_runde_v0.joblib" \
    "07_ML_Models/spatial/gold_suggester_tverrfjell_v0.joblib" \
    "07_ML_Models/spatial/gold_suggester_v0.joblib"
  do
    if [[ -f "$candidate" ]]; then
      export ML_MODEL="$candidate"
      return 0
    fi
  done
  return 1
}

if ! _resolve_ml_model; then
  echo "No ML model found under 07_ML_Models/spatial/. Available .joblib files:" >&2
  ls -1 07_ML_Models/spatial/gold_suggester*.joblib 2>/dev/null >&2 || echo "  (none)" >&2
  echo "" >&2
  echo "Train or pass an existing model, e.g.:" >&2
  echo "  $0 --skip-bootstrap --model 07_ML_Models/spatial/gold_suggester_gramstad_runde_v0.joblib" >&2
  exit 1
fi

echo "=== Export HITL PNGs with ML suggester strip (model: $ML_MODEL) ==="
./04_Python_Scripts/spatial/export_hitl_chunks_vinje_terrenglop.sh

echo ""
echo "OK Vinje Terrengløp ML strip → 06_Visualizations/vinje_terrenglop_hitl/chunk_t*.png"
