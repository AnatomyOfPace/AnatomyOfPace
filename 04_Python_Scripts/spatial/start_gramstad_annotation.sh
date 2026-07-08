#!/usr/bin/env bash
# Gramstad Runde — bootstrap (if needed), export HITL PNGs, print labeling commands.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

TERRAIN_MAP="config/spatial_terrain_map_gramstad_runde.json"
PANEL="03_Processed_Data/spatial/gramstad_runde_course/panel_1m.parquet"
OUT_DIR="06_Visualizations/gramstad_runde_hitl"
FIT_ARG=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fit)
      FIT_ARG=(--fit "$2")
      shift 2
      ;;
    --skip-bootstrap)
      SKIP_BOOT=1
      shift
      ;;
    --skip-export)
      SKIP_EXPORT=1
      shift
      ;;
    *)
      echo "Unknown arg: $1 (optional: --fit PATH --skip-bootstrap --skip-export)" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${SKIP_BOOT:-}" ]] && [[ ! -f "$PANEL" ]]; then
  echo "=== Bootstrap Gramstad Runde ==="
  python3 04_Python_Scripts/spatial/bootstrap_gramstad_runde_course.py "${FIT_ARG[@]}"
fi

if [[ ! -f "$PANEL" ]]; then
  echo "Panel still missing. Run:" >&2
  echo "  python3 04_Python_Scripts/spatial/bootstrap_gramstad_runde_course.py --fit 02_Raw_Data/donors/Subject_A/Gramstad_runden_i__solnedgang.fit" >&2
  exit 1
fi

python3 04_Python_Scripts/spatial/preflight_map_first_course.py \
  --terrain-map "$TERRAIN_MAP" --panel "$PANEL"

if [[ -z "${SKIP_EXPORT:-}" ]]; then
  echo "=== Export HITL chunk PNGs ==="
  ./04_Python_Scripts/spatial/export_hitl_chunks_gramstad_runde.sh
fi

KM_END="$(python3 - <<'PY'
import json
from pathlib import Path
m = json.loads(Path("config/spatial_align_manifest_gramstad_runde.json").read_text())
print(m["km_analysis_window"][1])
PY
)"

N_CHUNKS="$(python3 - <<PY
import math
print(max(1, math.ceil(float("${KM_END}"))))
PY
)"

cat <<EOF

=== Gramstad Runde annotation ready ===

  Loop length: ${KM_END} km (${N_CHUNKS} × 1 km PNGs)
  PNG folder:  ${OUT_DIR}/chunk_t*.png
  Terrain map: ${TERRAIN_MAP}

Label each km from orthophoto + strip (Assigned row), then:

  python3 04_Python_Scripts/spatial/gold_span_editor.py \\
    --terrain-map ${TERRAIN_MAP} add \\
    --km-start 0.0 --km-end 1.0 --surface S2 --friction F2 \\
    --reason "gravel climb"

  python3 04_Python_Scripts/spatial/gold_span_editor.py \\
    --terrain-map ${TERRAIN_MAP} list

Each add auto-writes config/spatial_terrain_map_gramstad_runde.gold_local.json (gitignored backup).

After a labeling session, re-export the chunks you changed:

  ./04_Python_Scripts/spatial/export_hitl_chunks_gramstad_runde.sh

Optional in-browser profile (training panel):

  streamlit run 04_Python_Scripts/spatial/hitl_annotator_app.py -- \\
    --terrain-map ${TERRAIN_MAP} \\
    --panel ${PANEL}

EOF
