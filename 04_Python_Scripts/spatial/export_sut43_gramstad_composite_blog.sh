#!/usr/bin/env bash
# Blog composite — Dalsnuten summit (km 25) → Gramstad band end (km 41).
# Grey label-free basemap; map course-km labels every 5 km; shared-km elevation + delta-TI gap.
#
# Re-run cross-athlete TRF first if paired gap starts after km 25:
#   ./04_Python_Scripts/spatial/compute_trf_race_sut43.sh --spine-only
#
# Usage (repo root, on Mac with local panel + TRF spine):
#   ./04_Python_Scripts/spatial/export_sut43_gramstad_composite_blog.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT/.mplconfig}"
mkdir -p "$MPLCONFIGDIR"

OUTPUT="06_Visualizations/sut43_gramstad_composite_blog.png"

python3 04_Python_Scripts/spatial/render_sut43_bedrock_corridor_composite.py \
  --panel "03_Processed_Data/spatial/sut43_terrain_ontology/panel_race_1m_spine.parquet" \
  --spine-dir "03_Processed_Data/spatial/sut43_terrain_ontology/race_trf_spine" \
  --output "$OUTPUT" \
  --blog-style \
  --verify-export \
  "$@"

if [[ "$(uname -s)" == "Darwin" ]] && command -v open >/dev/null 2>&1; then
  open "$OUTPUT"
fi
