#!/usr/bin/env bash
# Bulk-export gramstad_band HITL decision dashboards (12 × 1 km, km 29–41).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT/.mplconfig}"
mkdir -p "$MPLCONFIGDIR"

python3 04_Python_Scripts/spatial/validation_dashboard.py \
  --terrain-map config/spatial_terrain_map_sut43.json \
  --panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet \
  --activity SUT43_20260418 \
  --map-track-donor Subject_A \
  --chunk-km 1 \
  --export-chunks \
  --output-dir 06_Visualizations/sut43_hitl \
  --verify-export \
  "$@"
