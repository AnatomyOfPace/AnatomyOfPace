#!/usr/bin/env bash
# Bulk-export Tverrfjell map-first HITL dashboards (1 km chunks).
# FIT GPS track only — never SUT_43 organiser GPX (Sandnes/Rogaland).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT/.mplconfig}"
mkdir -p "$MPLCONFIGDIR"

MANIFEST="config/spatial_align_manifest_tverrfjell.json"
TERRAIN_MAP="config/spatial_terrain_map_tverrfjell.json"
PANEL="03_Processed_Data/spatial/tverrfjell_course/panel_1m.parquet"
OUT_DIR="06_Visualizations/tverrfjell_hitl"
ACTIVITY="Tverrfjell_20260704"
DONOR="Subject_A"

if [[ ! -f "$PANEL" ]]; then
  echo "Panel missing: $PANEL — run bootstrap_tverrfjell_course.py first" >&2
  exit 1
fi

if ! python3 - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, "04_Python_Scripts")
import pandas as pd
from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.validation_dashboard import resolve_axis_label

tmap = load_terrain_map(Path("config/spatial_terrain_map_tverrfjell.json"))
panel = pd.read_parquet("03_Processed_Data/spatial/tverrfjell_course/panel_1m.parquet")
axis = resolve_axis_label(tmap, panel)
if axis.startswith("SUT_43"):
    raise SystemExit(
        "axis label still SUT_43 — update validation_dashboard.py (stream_distance fix)"
    )
race_id = (tmap.get("corridor") or {}).get("race_id")
if race_id != "tverrfjell":
    raise SystemExit(f"unexpected race_id: {race_id!r}")
lat = pd.to_numeric(panel["latitude"], errors="coerce")
lon = pd.to_numeric(panel["longitude"], errors="coerce")
print(f"OK preflight axis={axis!r} centroid={lat.mean():.4f}N {lon.mean():.4f}E")
gold = tmap.get("hitl", {}).get("operator_gold_spans") or []
print(f"OK operator_gold_spans: {len(gold)} (re-export reflects these labels on map/strip)")
PY
then
  echo "Preflight failed — git pull origin cursor/tverrfjell-hitl-bootstrap-0c6a" >&2
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
rm -f "$OUT_DIR"/chunk_t*.png "$OUT_DIR"/chunk_*.png

LOCOMOTION_SIDECAR="03_Processed_Data/spatial/tverrfjell_course/locomotion_mode_1m.parquet"
if [[ ! -f "$LOCOMOTION_SIDECAR" ]]; then
  echo "Generating locomotion sidecar → $LOCOMOTION_SIDECAR"
  python3 04_Python_Scripts/spatial/locomotion_mode.py \
    --panel "$PANEL" \
    --terrain-map "$TERRAIN_MAP" \
    --session-type training \
    --sidecar "$LOCOMOTION_SIDECAR"
fi

ML_MODEL="07_ML_Models/spatial/gold_suggester_tverrfjell_v0.joblib"
ML_PRED="03_Processed_Data/spatial/tverrfjell_course/tverrfjell_ml_predictions.parquet"
ML_ARGS=()
if [[ -f "$ML_MODEL" ]]; then
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
  echo "WARN no Tverrfjell ML model at $ML_MODEL — ML predicted strip will be empty" >&2
  echo "  Train: build_gold_training_set.py + train_gold_suggester.py --sector-id tverrfjell" >&2
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
  "${ML_ARGS[@]}"

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
    "race_id": "tverrfjell",
    "geography": "Uskedalen, Kvinnherad, Vestland",
    "axis_label": "tverrfjell stream km",
    "map_track": {"activity_id": "$ACTIVITY", "donor_id": "$DONOR", "gpx_overlay": False},
    "basemap": "opentopomap",
    "gps_centroid": {"lat": round(float(lat.mean()), 5), "lon": round(float(lon.mean()), 5)},
    "km_end": float("$KM_END"),
    "n_chunks": int("$N_CHUNKS"),
    "verify": "Title subtitle must read 'Uskedalen · Kvinnherad · Vestland · tverrfjell stream km'",
}
Path("$OUT_DIR/EXPORT_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
print("Wrote $OUT_DIR/EXPORT_MANIFEST.json")
PY

python3 04_Python_Scripts/spatial/verify_tverrfjell_hitl_exports.py --strict

echo "OK Tverrfjell HITL export complete → $OUT_DIR (${N_CHUNKS} chunks, km ${KM_START}–${KM_END})"
echo "  Verify subtitle: Uskedalen · Kvinnherad · Vestland · tverrfjell stream km"
echo "  NOT Sandnes/Rogaland — if x-axis says SUT_43, pull latest branch before re-export"
