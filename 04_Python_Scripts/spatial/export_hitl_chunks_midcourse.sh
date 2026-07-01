#!/usr/bin/env bash
# Bulk-export dalevatn_midcourse HITL decision dashboards (14 × 1 km, km 8–22).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT/.mplconfig}"
mkdir -p "$MPLCONFIGDIR"

PANEL="03_Processed_Data/spatial/sut43_terrain_ontology/panel_midcourse_1m_spine.parquet"
TERRAIN_MAP="config/spatial_terrain_map_sut43_midcourse.json"
OUT_DIR="06_Visualizations/sut43_hitl_midcourse"
TMP_DIR="${OUT_DIR}/_bulk_chunk_export"

mkdir -p "$OUT_DIR" "$TMP_DIR"

python3 04_Python_Scripts/spatial/validation_dashboard.py \
  --terrain-map "$TERRAIN_MAP" \
  --panel "$PANEL" \
  --activity SUT43_20260418 \
  --map-track-donor Subject_A \
  --km-start 8 \
  --km-end 22 \
  --chunk-km 1 \
  --export-chunks \
  --decision-mode \
  --output-dir "$TMP_DIR" \
  --verify-export

for f in "$TMP_DIR"/chunk_*.png; do
  base=$(basename "$f")
  num="${base#chunk_}"
  num="${num%%_*}"
  rest="${base#chunk_${num}_}"
  dest="${OUT_DIR}/chunk_m${num}_${rest}"
  mv -f "$f" "$dest"
  echo "OK → ${dest}"
done

rmdir "$TMP_DIR" 2>/dev/null || rm -rf "$TMP_DIR"
echo "OK mid-course HITL export complete → $OUT_DIR (14 chunks)"
