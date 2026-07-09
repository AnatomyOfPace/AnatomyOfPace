#!/usr/bin/env bash
# Build Baseline TI matrix + per-metre course grid for SUT_43 full course (km 0.5–43.0).
#
# Prerequisite: panel_full_1m.parquet and spatial_terrain_map_sut43_full.json on operator Mac.
# Chain after recover_sut43_gramstad_v0.sh when the full map / gold export was rebuilt.
#
# Usage (repo root):
#   ./04_Python_Scripts/spatial/build_baseline_ti_sut43.sh
#   ./04_Python_Scripts/spatial/build_baseline_ti_sut43.sh --strict-reference-elite
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

PANEL="03_Processed_Data/spatial/sut43_terrain_ontology/panel_full_1m.parquet"
TMAP="config/spatial_terrain_map_sut43_full.json"

if [[ ! -f "$PANEL" ]]; then
  echo "Panel missing: $PANEL" >&2
  echo "  Build panel_full on operator Mac (E4/E5 concat) before Baseline TI." >&2
  exit 1
fi
if [[ ! -f "$TMAP" ]]; then
  echo "Terrain map missing: $TMAP" >&2
  echo "  Run: ./04_Python_Scripts/spatial/recover_sut43_gramstad_v0.sh (step 1 merge)" >&2
  exit 1
fi

echo "=== SUT_43 full course Baseline TI (C2) ==="
python3 04_Python_Scripts/spatial/build_baseline_ti.py \
  --terrain-map "$TMAP" \
  --panel "$PANEL" \
  --km-start 0.5 --km-end 43.0 \
  "$@"

echo ""
echo "OK Baseline TI complete."
echo "  Grid:   03_Processed_Data/spatial/baseline_ti_sut43_full.parquet"
echo "  Matrix: 03_Processed_Data/spatial/baseline_ti_sut43_full_matrix.parquet"
echo "  Report: 07_ML_Models/spatial/baseline_ti_sut43_full_report.json"
echo "  QC:     06_Visualizations/sut43_baseline_ti_qc.png"
