#!/usr/bin/env bash
# Build per-course gold training exports, merge map-first pool, train pooled suggester.
#
# Courses: Tverrfjell, Klepp Runde, Gramstad Runde, Vinje Terrengløp (FIT stream axis).
# Optional O₁ anchors: Stavanger Halvmarathon (S1/F0 asphalt), 3-sjøersløpet (S2/F1 gravel),
# Sunderunde training loop (S2/F1 gravel + S1/F1 asphalt).
#
# Usage (from repo root):
#   ./04_Python_Scripts/spatial/train_map_first_gold_pool.sh --rebuild-exports
#   ./04_Python_Scripts/spatial/train_map_first_gold_pool.sh --with-o1-anchors --rebuild-exports
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

REBUILD=""
WITH_O1=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rebuild-exports) REBUILD=1; shift ;;
    --with-o1-anchors) WITH_O1=1; shift ;;
    *)
      echo "Usage: $0 [--rebuild-exports] [--with-o1-anchors]" >&2
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

if [[ -n "$WITH_O1" ]]; then
  TERRAIN_MAPS+=(
    "config/spatial_terrain_map_stavanger_halvmarathon.json"
    "config/spatial_terrain_map_3_sjoerslopet.json"
    "config/spatial_terrain_map_sunderunde.json"
  )
  PARQUETS+=(
    "${PROCESSED}/gold_training_set_stavanger_halvmarathon.parquet"
    "${PROCESSED}/gold_training_set_3_sjoerslopet.parquet"
    "${PROCESSED}/gold_training_set_sunderunde.parquet"
  )
fi

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
    echo "Missing export: $pq — run with --rebuild-exports (panels must exist locally)" >&2
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
TRAIN_ARGS=(
  --training-set "$POOL"
  --sector-id map_first_pool
  --model-out "$MODEL"
  --metadata-out "$METADATA"
)
if [[ -n "$WITH_O1" ]]; then
  echo "O₁ anchors included — downweighting so trail loops are not drowned (~21 km each)"
  TRAIN_ARGS+=(
    --source-weight stavanger_halvmarathon:0.5
    --source-weight 3_sjoerslopet:0.5
    --source-weight sunderunde:0.5
  )
fi

python3 "$TRAIN" "${TRAIN_ARGS[@]}"

echo ""
echo "OK map-first pool model → $MODEL"
if [[ -n "$WITH_O1" ]]; then
  echo "  (trained with Stavanger Halvmarathon + 3-sjøersløpet + Sunderunde O₁ anchors)"
fi
echo "Re-export trail loops:"
echo "  ./04_Python_Scripts/spatial/export_map_first_hitl_pool.sh"
echo "Re-export O₁ anchors:"
echo "  ./04_Python_Scripts/spatial/export_o1_anchor_hitl_pool.sh"
