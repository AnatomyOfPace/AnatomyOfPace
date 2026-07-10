#!/usr/bin/env bash
# HITL-style basemap — operator bedrock corridor slice (km 31.08–33.80) on Kartverket topo.
#
# Prerequisites: panel_race_1m_spine.parquet + config/spatial_terrain_map_sut43.json
#
# Usage (repo root):
#   ./04_Python_Scripts/spatial/export_bedrock_corridor_basemap.sh
#   SPINE_PANEL=0 ./04_Python_Scripts/spatial/export_bedrock_corridor_basemap.sh  # legacy panel_1m
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT/.mplconfig}"
mkdir -p "$MPLCONFIGDIR"

PANEL="03_Processed_Data/spatial/sut43_terrain_ontology/panel_race_1m_spine.parquet"
OUTPUT="06_Visualizations/sut43_bedrock_corridor_hitl_basemap.png"

if [[ "${SPINE_PANEL:-1}" == "0" ]]; then
  PANEL="03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet"
fi

python3 04_Python_Scripts/spatial/render_sut43_bedrock_corridor_basemap.py \
  --panel "$PANEL" \
  --output "$OUTPUT" \
  --verify-export \
  "$@"
