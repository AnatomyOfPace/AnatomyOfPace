#!/usr/bin/env bash
# Bulk-export SUT_43 full-course HITL decision dashboards (1 km chunks, km 0.5–43.0).
#
# Uses merged operator gold (spatial_terrain_map_sut43_full.json) + race panel_full_1m.
# Review operator gold seam-by-seam before publication / composite re-export.
#
# Prerequisites (operator Mac):
#   03_Processed_Data/spatial/sut43_terrain_ontology/panel_full_1m.parquet
#   config/spatial_terrain_map_sut43_full.json
#
# Usage (repo root):
#   ./04_Python_Scripts/spatial/export_hitl_chunks_sut43_full.sh
#   ./04_Python_Scripts/spatial/export_hitl_chunks_sut43_full.sh --chunk-index 25
#   ./04_Python_Scripts/spatial/open_hitl_review_sut43_full.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT/.mplconfig}"
mkdir -p "$MPLCONFIGDIR"

TERRAIN_MAP="config/spatial_terrain_map_sut43_full.json"
PANEL="03_Processed_Data/spatial/sut43_terrain_ontology/panel_full_1m.parquet"
OUT_DIR="06_Visualizations/sut43_hitl_full"
KM_START="0.5"
KM_END="43.0"
CHUNK_KM="1"
ACTIVITY="SUT43_20260418"
DONOR="Subject_A"

PASS_ARGS=("$@")
EXPORT_CHUNKS=1
CHUNK_INDEX=""

for i in "${!PASS_ARGS[@]}"; do
  if [[ "${PASS_ARGS[$i]}" == "--chunk-index" && -n "${PASS_ARGS[$i+1]:-}" ]]; then
    CHUNK_INDEX="${PASS_ARGS[$i+1]}"
    EXPORT_CHUNKS=0
  fi
done

if [[ ! -f "$TERRAIN_MAP" ]]; then
  echo "Missing terrain map: $TERRAIN_MAP" >&2
  echo "Merge sector maps first (merge_terrain_maps.py) or pull latest branch." >&2
  exit 1
fi

if [[ ! -f "$PANEL" ]]; then
  echo "Missing panel: $PANEL" >&2
  echo "Build panel_full_1m on operator Mac (E4/E5 concat) before full-course HITL export." >&2
  exit 1
fi

python3 - <<'PY'
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, "04_Python_Scripts")
from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.validation_dashboard import operator_gold_spans, resolve_axis_label

tmap = load_terrain_map(Path("config/spatial_terrain_map_sut43_full.json"))
panel = pd.read_parquet("03_Processed_Data/spatial/sut43_terrain_ontology/panel_full_1m.parquet")
p_lo = float(panel["course_km"].min())
p_hi = float(panel["course_km"].max())
gold = operator_gold_spans(tmap)
axis = resolve_axis_label(tmap, panel)
print(f"OK preflight panel km {p_lo:.3f}–{p_hi:.3f} | axis={axis!r} | gold spans={len(gold)}")
if p_lo > 0.6:
    print(f"WARN panel starts at km {p_lo:.3f} — chunks below that km will be empty", file=sys.stderr)
if p_hi < 42.9:
    print(f"WARN panel ends at km {p_hi:.3f} — extend panel_full_1m for km 43 finish band", file=sys.stderr)
PY

mkdir -p "$OUT_DIR"

DASH_ARGS=(
  --terrain-map "$TERRAIN_MAP"
  --panel "$PANEL"
  --activity "$ACTIVITY"
  --map-track-donor "$DONOR"
  --km-start "$KM_START"
  --km-end "$KM_END"
  --chunk-km "$CHUNK_KM"
  --with-map
  --decision-mode
  --verify-export
  --output-dir "$OUT_DIR"
)

if [[ "$EXPORT_CHUNKS" == "1" ]]; then
  DASH_ARGS+=(--export-chunks)
  echo "=== SUT_43 full-course HITL export: km ${KM_START}–${KM_END} (${CHUNK_KM} km chunks) ==="
  echo "    terrain: $TERRAIN_MAP"
  echo "    panel:   $PANEL"
  echo "    output:  $OUT_DIR/"
  echo ""
else
  DASH_ARGS+=(--chunk-index "$CHUNK_INDEX")
  echo "=== SUT_43 full-course HITL single chunk: index ${CHUNK_INDEX} ==="
fi

python3 04_Python_Scripts/spatial/validation_dashboard.py \
  "${DASH_ARGS[@]}" \
  ${PASS_ARGS[@]+"${PASS_ARGS[@]}"}

if [[ "$EXPORT_CHUNKS" == "1" ]]; then
  python3 - <<PY
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, "04_Python_Scripts")
from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.validation_dashboard import operator_gold_spans

root = Path(".")
out_dir = root / "$OUT_DIR"
chunks = sorted(out_dir.glob("chunk_*.png"))
sectors = json.loads((root / "config/spatial_terrain_sectors_sut43.json").read_text(encoding="utf-8"))
sector_rows = [
    {
        "sector_id": s["sector_id"],
        "km_start": s["km_analysis_window"][0],
        "km_end": s["km_analysis_window"][1],
        "terrain_map": s.get("terrain_map"),
        "status": s.get("status"),
    }
    for s in sectors.get("sectors") or []
]
tmap = load_terrain_map(root / "$TERRAIN_MAP")
panel = pd.read_parquet(root / "$PANEL")
manifest = {
    "exported_at": datetime.now(timezone.utc).isoformat(),
    "race_id": "SUT_43",
    "km_start": float("$KM_START"),
    "km_end": float("$KM_END"),
    "chunk_km": float("$CHUNK_KM"),
    "n_chunks": len(chunks),
    "terrain_map": "$TERRAIN_MAP",
    "panel": "$PANEL",
    "operator_gold_spans": len(operator_gold_spans(tmap)),
    "panel_extent_km": [float(panel["course_km"].min()), float(panel["course_km"].max())],
    "sectors": sector_rows,
    "review_command": "./04_Python_Scripts/spatial/open_hitl_review_sut43_full.sh",
    "chunk_glob": f"{out_dir.relative_to(root)}/chunk_*.png",
}
manifest_path = out_dir / "EXPORT_MANIFEST.json"
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {manifest_path}")
print(f"OK {len(chunks)} chunks → {out_dir.relative_to(root)}/")
print(f"    Review: ./04_Python_Scripts/spatial/open_hitl_review_sut43_full.sh")
PY
fi

if [[ "$(uname -s)" == "Darwin" ]] && [[ "$EXPORT_CHUNKS" == "1" ]] && command -v open >/dev/null 2>&1; then
  open "$OUT_DIR"
fi
