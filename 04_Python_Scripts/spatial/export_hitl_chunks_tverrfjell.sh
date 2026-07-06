#!/usr/bin/env bash
# Bulk-export Tverrfjell map-first HITL dashboards (1 km chunks).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT/.mplconfig}"
mkdir -p "$MPLCONFIGDIR"

MANIFEST="config/spatial_align_manifest_tverrfjell.json"
TERRAIN_MAP="config/spatial_terrain_map_tverrfjell.json"
PANEL="03_Processed_Data/spatial/tverrfjell_course/panel_1m.parquet"
OUT_DIR="06_Visualizations/tverrfjell_hitl"

if [[ ! -f "$PANEL" ]]; then
  echo "Panel missing: $PANEL — run bootstrap_tverrfjell_course.py first" >&2
  exit 1
fi

KM_END="$(python3 - <<'PY'
import json
from pathlib import Path
m = json.loads(Path("config/spatial_align_manifest_tverrfjell.json").read_text())
print(m["km_analysis_window"][1])
PY
)"

KM_START=0
N_CHUNKS="$(python3 - <<PY
import math
km_end = float("${KM_END}")
print(max(1, math.ceil(km_end)))
PY
)"

mkdir -p "$OUT_DIR"

python3 04_Python_Scripts/spatial/validation_dashboard.py \
  --terrain-map "$TERRAIN_MAP" \
  --panel "$PANEL" \
  --activity Tverrfjell_20260704 \
  --map-track-donor Subject_A \
  --km-start "$KM_START" \
  --km-end "$KM_END" \
  --chunk-km 1 \
  --export-chunks \
  --decision-mode \
  --output-dir "$OUT_DIR/_bulk" \
  --verify-export

for f in "$OUT_DIR/_bulk"/chunk_*.png; do
  base=$(basename "$f")
  num="${base#chunk_}"
  num="${num%%_*}"
  rest="${base#chunk_${num}_}"
  dest="${OUT_DIR}/chunk_t${num}_${rest}"
  mv -f "$f" "$dest"
  echo "OK → ${dest}"
done

rmdir "$OUT_DIR/_bulk" 2>/dev/null || rm -rf "$OUT_DIR/_bulk"
echo "OK Tverrfjell HITL export complete → $OUT_DIR (${N_CHUNKS} chunks, km ${KM_START}–${KM_END})"
