#!/usr/bin/env bash
# Re-export O₁ half-marathon / gravel-anchor HITL courses with pooled (or ML_MODEL) gold suggester.
#
# Courses: Stavanger Halvmarathon, 3-sjøersløpet, Sunderunde training loop.
# Requires local panels from anchor ingest (corridor_multi_fit).
#
# Usage (from repo root):
#   ./04_Python_Scripts/spatial/export_o1_anchor_hitl_pool.sh
#   ML_MODEL=07_ML_Models/spatial/gold_suggester_map_first_pool_v0.joblib \
#     ./04_Python_Scripts/spatial/export_o1_anchor_hitl_pool.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export ML_MODEL="${ML_MODEL:-07_ML_Models/spatial/gold_suggester_map_first_pool_v0.joblib}"

if [[ ! -f "$ML_MODEL" ]]; then
  echo "ML model not found: $ML_MODEL" >&2
  echo "Train first: ./04_Python_Scripts/spatial/train_map_first_gold_pool.sh --with-o1-anchors" >&2
  exit 1
fi

echo "=== O₁ anchor HITL pool export (Subject_A) ==="
echo "ML_MODEL=$ML_MODEL"
echo ""

declare -a SCRIPTS=(
  export_hitl_chunks_stavanger_halvmarathon.sh
  export_hitl_chunks_3_sjoerslopet.sh
  export_hitl_chunks_sunderunde.sh
)

for script in "${SCRIPTS[@]}"; do
  path="04_Python_Scripts/spatial/${script}"
  if [[ ! -x "$path" ]]; then
    echo "Missing export script: $path" >&2
    exit 1
  fi
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "→ $script"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  "$path"
  echo ""
done

echo "OK all O₁ anchor HITL exports complete (pooled ML strip)."
