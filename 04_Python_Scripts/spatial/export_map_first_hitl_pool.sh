#!/usr/bin/env bash
# Re-export all Subject_A map-first HITL courses with pooled (or ML_MODEL) gold suggester.
#
# Courses: Tverrfjell, Klepp Runde, Gramstad Runde, Vinje Terrengløp.
# Requires bootstrap + operator gold on each course locally.
#
# Usage (from repo root):
#   ./04_Python_Scripts/spatial/export_map_first_hitl_pool.sh
#   ML_MODEL=07_ML_Models/spatial/gold_suggester_map_first_pool_v0.joblib \
#     ./04_Python_Scripts/spatial/export_map_first_hitl_pool.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export ML_MODEL="${ML_MODEL:-07_ML_Models/spatial/gold_suggester_map_first_pool_v0.joblib}"

if [[ ! -f "$ML_MODEL" ]]; then
  echo "ML model not found: $ML_MODEL" >&2
  echo "Train first: ./04_Python_Scripts/spatial/train_map_first_gold_pool.sh" >&2
  exit 1
fi

echo "=== Map-first HITL pool export (Subject_A) ==="
echo "ML_MODEL=$ML_MODEL"
echo ""

declare -a SCRIPTS=(
  export_hitl_chunks_tverrfjell.sh
  export_hitl_chunks_klepp_runde.sh
  export_hitl_chunks_gramstad_runde.sh
  export_hitl_chunks_vinje_terrenglop.sh
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

echo "OK all Subject_A map-first HITL exports complete (pooled ML strip)."
