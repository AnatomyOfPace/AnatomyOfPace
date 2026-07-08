#!/usr/bin/env bash
# Bulk-export one map-first orphan course HITL dashboards (1 km chunks).
# Usage: ./04_Python_Scripts/spatial/export_hitl_map_first_orphan.sh <race_id>
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT/.mplconfig}"
mkdir -p "$MPLCONFIGDIR"

RACE_ID="${1:-}"
if [[ -z "$RACE_ID" ]]; then
  echo "Usage: $0 <race_id>" >&2
  echo "  e.g. $0 selvikstakken" >&2
  python3 04_Python_Scripts/spatial/bootstrap_map_first_orphan.py --list >&2
  exit 1
fi

MANIFEST="config/spatial_align_manifest_${RACE_ID}.json"
TERRAIN_MAP="config/spatial_terrain_map_${RACE_ID}.json"
PANEL="03_Processed_Data/spatial/${RACE_ID}_course/panel_1m.parquet"
OUT_DIR="06_Visualizations/${RACE_ID}_hitl"
DONOR="Subject_A"

if [[ ! -f "$PANEL" ]]; then
  echo "Panel missing: $PANEL" >&2
  echo "Run: python3 04_Python_Scripts/spatial/bootstrap_map_first_orphan.py --course $RACE_ID" >&2
  exit 1
fi

read -r ACTIVITY KM_END DISPLAY GEO_LABEL <<<"$(python3 - <<PY
import json
import sys
from pathlib import Path

sys.path.insert(0, "04_Python_Scripts")
from spatial.map_first_orphan_registry import get_orphan_course, geography_label

race_id = "${RACE_ID}"
course = get_orphan_course(race_id)
m = json.loads(Path("${MANIFEST}").read_text())
act = (m.get("activities") or [{}])[0].get("activity_id", "Subject_A")
km_end = m["km_analysis_window"][1]
print(act, km_end, course.get("display_name", race_id), geography_label(course))
PY
)"

if ! python3 04_Python_Scripts/spatial/preflight_map_first_course.py \
  --terrain-map "$TERRAIN_MAP" --panel "$PANEL"
then
  echo "Preflight failed — fix issues above before export" >&2
  exit 1
fi

python3 - <<PY
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, "04_Python_Scripts")
from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.validation_dashboard import resolve_axis_label

tmap = load_terrain_map(Path("${TERRAIN_MAP}"))
panel = pd.read_parquet("${PANEL}")
axis = resolve_axis_label(tmap, panel)
if axis.startswith("SUT_43"):
    raise SystemExit("axis label still SUT_43")
race_id = (tmap.get("corridor") or {}).get("race_id")
if race_id != "${RACE_ID}":
    raise SystemExit(f"unexpected race_id: {race_id!r}")
lat = pd.to_numeric(panel["latitude"], errors="coerce")
lon = pd.to_numeric(panel["longitude"], errors="coerce")
print(f"OK preflight axis={axis!r} centroid={lat.mean():.4f}N {lon.mean():.4f}E")
gold = tmap.get("hitl", {}).get("operator_gold_spans") or []
print(f"OK operator_gold_spans: {len(gold)}")
PY

KM_START=0
N_CHUNKS="$(python3 - <<PY
import math
km_end = float("${KM_END}")
print(max(1, math.ceil(km_end)))
PY
)"

mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR"/chunk_t*.png "$OUT_DIR"/chunk_*.png

LOCOMOTION_SIDECAR="03_Processed_Data/spatial/${RACE_ID}_course/locomotion_mode_1m.parquet"
if [[ ! -f "$LOCOMOTION_SIDECAR" ]]; then
  echo "Generating locomotion sidecar → $LOCOMOTION_SIDECAR"
  python3 04_Python_Scripts/spatial/locomotion_mode.py \
    --panel "$PANEL" \
    --terrain-map "$TERRAIN_MAP" \
    --session-type training \
    --sidecar "$LOCOMOTION_SIDECAR"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_map_first_ml_model.sh
source "${SCRIPT_DIR}/_map_first_ml_model.sh"

ML_PRED="03_Processed_Data/spatial/${RACE_ID}_course/${RACE_ID}_ml_predictions.parquet"
ML_ARGS=()
if map_first_resolve_ml_model "$RACE_ID"; then
  echo "OK ML model → $ML_MODEL"
  if [[ ! -f "$ML_PRED" ]] || [[ "$ML_MODEL" -nt "$ML_PRED" ]]; then
    echo "Generating ML predictions → $ML_PRED"
    python3 04_Python_Scripts/spatial/export_ml_predictions.py \
      --terrain-map "$TERRAIN_MAP" \
      --panel "$PANEL" \
      --model "$ML_MODEL" \
      --output "$ML_PRED"
  fi
  ML_ARGS=(--ml-predictions "$ML_PRED")
else
  echo "WARN no ML model — set ML_MODEL=path/to/gold_suggester*.joblib" >&2
fi

python3 04_Python_Scripts/spatial/validation_dashboard.py \
  --terrain-map "$TERRAIN_MAP" \
  --panel "$PANEL" \
  --activity "$ACTIVITY" \
  --map-track-donor "$DONOR" \
  --no-gpx \
  --basemap opentopomap \
  --km-start "$KM_START" \
  --km-end "$KM_END" \
  --chunk-km 1 \
  --export-chunks \
  --decision-mode \
  --output-dir "$OUT_DIR/_bulk" \
  --verify-export \
  ${ML_ARGS[@]+"${ML_ARGS[@]}"}

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

python3 - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

panel = pd.read_parquet("${PANEL}")
lat = pd.to_numeric(panel["latitude"], errors="coerce")
lon = pd.to_numeric(panel["longitude"], errors="coerce")
manifest = {
    "exported_at": datetime.now(timezone.utc).isoformat(),
    "race_id": "${RACE_ID}",
    "display_name": "${DISPLAY}",
    "geography": "${GEO_LABEL}",
    "axis_label": "${RACE_ID} stream km",
    "map_track": {"activity_id": "${ACTIVITY}", "donor_id": "${DONOR}", "gpx_overlay": False},
    "basemap": "opentopomap",
    "gps_centroid": {"lat": round(float(lat.mean()), 5), "lon": round(float(lon.mean()), 5)},
    "km_end": float("${KM_END}"),
    "n_chunks": int("${N_CHUNKS}"),
}
Path("${OUT_DIR}/EXPORT_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\\n")
print("Wrote ${OUT_DIR}/EXPORT_MANIFEST.json")
PY

python3 04_Python_Scripts/spatial/verify_map_first_orphan_exports.py --course "$RACE_ID" --strict

echo "OK ${DISPLAY} HITL export complete → $OUT_DIR (${N_CHUNKS} chunks, km ${KM_START}–${KM_END})"
