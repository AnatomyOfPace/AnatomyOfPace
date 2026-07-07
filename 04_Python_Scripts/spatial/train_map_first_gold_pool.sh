#!/usr/bin/env bash
# Build per-course gold training exports, merge map-first pool, train pooled suggester.
#
# Courses: Tverrfjell, Klepp Runde, Gramstad Runde, Vinje Terrengløp (FIT stream axis).
# Requires operator gold on each course (terrain map or .gold_local.json mirror).
#
# Usage (from repo root):
#   ./04_Python_Scripts/spatial/train_map_first_gold_pool.sh
#   ./04_Python_Scripts/spatial/train_map_first_gold_pool.sh --rebuild-exports
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

REBUILD=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rebuild-exports) REBUILD=1; shift ;;
    *)
      echo "Usage: $0 [--rebuild-exports]" >&2
      exit 1
      ;;
  esac
done

BUILD="04_Python_Scripts/spatial/build_gold_training_set.py"
MERGE="04_Python_Scripts/spatial/merge_gold_training_sets.py"
TRAIN="04_Python_Scripts/spatial/train_gold_suggester.py"
PROCESSED="03_Processed_Data/spatial"
MODEL_DIR="07_ML_Models/spatial"

declare -a TERRAIN_MAPS=(
  "config/spatial_terrain_map_tverrfjell.json"
  "config/spatial_terrain_map_klepp_runde.json"
  "config/spatial_terrain_map_gramstad_runde.json"
  "config/spatial_terrain_map_vinje_terrenglop.json"
)

declare -a PARQUETS=(
  "${PROCESSED}/gold_training_set_tverrfjell.parquet"
  "${PROCESSED}/gold_training_set_klepp_runde.parquet"
  "${PROCESSED}/gold_training_set_gramstad_runde.parquet"
  "${PROCESSED}/gold_training_set_vinje_terrenglop.parquet"
)

POOL="${PROCESSED}/gold_training_set_map_first_pool.parquet"
MODEL="${MODEL_DIR}/gold_suggester_map_first_pool_v0.joblib"
METADATA="${MODEL_DIR}/gold_suggester_map_first_pool_v0_metadata.json"

echo "=== Build per-course gold training exports ==="
for i in "${!TERRAIN_MAPS[@]}"; do
  tmap="${TERRAIN_MAPS[$i]}"
  pq="${PARQUETS[$i]}"
  if [[ -n "$REBUILD" || ! -f "$pq" ]]; then
    echo "→ $tmap"
    python3 "$BUILD" --terrain-map "$tmap"
  else
    echo "OK skip (exists): $pq"
  fi
done

echo ""
echo "=== Merge map-first pool ==="
MERGE_ARGS=()
for pq in "${PARQUETS[@]}"; do
  if [[ ! -f "$pq" ]]; then
    echo "Missing export: $pq — run with --rebuild-exports" >&2
    exit 1
  fi
  MERGE_ARGS+=(--input "$pq")
done

python3 "$MERGE" \
  "${MERGE_ARGS[@]}" \
  --output "$POOL" \
  --summary-json "${PROCESSED}/gold_training_set_map_first_pool.summary.json"

echo ""
echo "=== Train pooled gold suggester ==="
python3 "$TRAIN" \
  --training-set "$POOL" \
  --sector-id map_first_pool \
  --model-out "$MODEL" \
  --metadata-out "$METADATA"

echo ""
echo "OK map-first pool model → $MODEL"
echo "Use on any map-first course export, e.g.:"
echo "  ML_MODEL=$MODEL ./04_Python_Scripts/spatial/export_hitl_chunks_vinje_terrenglop.sh"
