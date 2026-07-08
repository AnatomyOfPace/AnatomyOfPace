#!/usr/bin/env bash
# Bulk-export Sunderunde training-loop O₁ gravel anchor HITL dashboards (1 km chunks).
# FIT stream-distance axis — low-intensity gravel/asphalt calibration.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT/.mplconfig}"
mkdir -p "$MPLCONFIGDIR"

MANIFEST="config/spatial_align_manifest_sunderunde.json"
TERRAIN_MAP="config/spatial_terrain_map_sunderunde.json"
PANEL="03_Processed_Data/spatial/sunderunde_training_loop/panel_1m.parquet"
OUT_DIR="06_Visualizations/sunderunde_hitl"
DONOR="Subject_A"
RACE_ID="Sunderunde"
ML_RACE_KEY="sunderunde"

if [[ ! -f "$PANEL" ]]; then
  echo "Panel missing: $PANEL" >&2
  echo "Rebuild: python3 04_Python_Scripts/spatial/corridor_multi_fit.py --manifest $MANIFEST --enrich-if-needed" >&2
  exit 1
fi

read -r ACTIVITY KM_END <<<"$(python3 - <<PY
import json
from pathlib import Path
m = json.loads(Path("$MANIFEST").read_text())
acts = m.get("activities") or []
act = next((a.get("activity_id") for a in acts if a.get("donor_id") == "Subject_A"), "Sunderunde")
print(act, m["km_analysis_window"][1])
PY
)"

if ! python3 04_Python_Scripts/spatial/preflight_map_first_course.py \
  --terrain-map "$TERRAIN_MAP" --panel "$PANEL"
then
  echo "Preflight failed — fix issues above before export" >&2
  exit 1
fi

KM_START=0
N_CHUNKS="$(python3 - <<PY
import math
print(max(1, math.ceil(float("${KM_END}"))))
PY
)"

mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR"/chunk_t*.png "$OUT_DIR"/chunk_*.png

LOCOMOTION_SIDECAR="03_Processed_Data/spatial/sunderunde_training_loop/locomotion_mode_1m.parquet"
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

ML_PRED="03_Processed_Data/spatial/sunderunde_training_loop/sunderunde_ml_predictions.parquet"
ML_ARGS=()
if map_first_resolve_ml_model "$ML_RACE_KEY"; then
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

panel = pd.read_parquet("$PANEL")
lat = pd.to_numeric(panel["latitude"], errors="coerce")
lon = pd.to_numeric(panel["longitude"], errors="coerce")
manifest = {
    "exported_at": datetime.now(timezone.utc).isoformat(),
    "race_id": "$RACE_ID",
    "geography": "Sunderunde · Sandnes · Rogaland",
    "axis_label": "Sunderunde stream km",
    "map_track": {"activity_id": "$ACTIVITY", "donor_id": "$DONOR", "gpx_overlay": False},
    "basemap": "opentopomap",
    "gps_centroid": {"lat": round(float(lat.mean()), 5), "lon": round(float(lon.mean()), 5)},
    "km_end": float("$KM_END"),
    "n_chunks": int("$N_CHUNKS"),
}
Path("$OUT_DIR/EXPORT_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
print("Wrote $OUT_DIR/EXPORT_MANIFEST.json")
PY

python3 04_Python_Scripts/spatial/verify_sunderunde_hitl_exports.py --strict

echo "OK Sunderunde HITL export complete → $OUT_DIR (${N_CHUNKS} chunks, km ${KM_START}–${KM_END})"
