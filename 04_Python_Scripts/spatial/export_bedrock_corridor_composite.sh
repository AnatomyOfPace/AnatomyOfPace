#!/usr/bin/env bash
# Composite bedrock corridor figure — basemap + elevation + paired delta-TI (shared km axis).
#
# Prerequisites:
#   panel_race_1m_spine.parquet
#   race_trf_spine/cross_athlete_trf_paired.parquet  (compute_trf_race_sut43.sh --spine-only)
#
# Usage (repo root):
#   ./04_Python_Scripts/spatial/export_bedrock_corridor_composite.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT/.mplconfig}"
mkdir -p "$MPLCONFIGDIR"

PANEL="03_Processed_Data/spatial/sut43_terrain_ontology/panel_race_1m_spine.parquet"
SPINE_DIR="03_Processed_Data/spatial/sut43_terrain_ontology/race_trf_spine"
OUTPUT="06_Visualizations/sut43_bedrock_corridor_composite.png"

python3 04_Python_Scripts/spatial/render_sut43_bedrock_corridor_composite.py \
  --panel "$PANEL" \
  --spine-dir "$SPINE_DIR" \
  --output "$OUTPUT" \
  --verify-export \
  "$@"
