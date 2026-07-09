#!/usr/bin/env bash
# Lock operator gold for SCB Runde — full orthophoto spec (map-first orphan).
#
# Clears km 0–end and writes contiguous operator spans. Gap km 0.5–1.0 is S3/F2
# (grass bridge between km 0–0.5 and 1.0–1.8 — change in script if orthophoto differs).
#
# Usage (from repo root, after bootstrap + HITL export):
#   ./04_Python_Scripts/spatial/lock_scb_runde_gold.sh
#   ./04_Python_Scripts/spatial/lock_scb_runde_gold.sh --dry-run
#   ./04_Python_Scripts/spatial/lock_scb_runde_gold.sh --force   # replace existing gold
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

RACE_ID="scb_runde"
TERRAIN_MAP="config/spatial_terrain_map_${RACE_ID}.json"

DRY_RUN=""
FORCE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --force) FORCE=1; shift ;;
    *)
      echo "Usage: $0 [--dry-run] [--force]" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "$TERRAIN_MAP" ]]; then
  echo "Terrain map missing: $TERRAIN_MAP" >&2
  echo "Run: python3 04_Python_Scripts/spatial/bootstrap_map_first_orphan.py --course $RACE_ID" >&2
  exit 1
fi

read -r KM_END SPAN_COUNT <<<"$(python3 - <<PY
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, "04_Python_Scripts")
from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.validation_dashboard import operator_gold_spans

race_id = "${RACE_ID}"
manifest = Path(f"config/spatial_align_manifest_{race_id}.json")
manifest_end = float(json.loads(manifest.read_text())["km_analysis_window"][1])
panel_path = Path(f"03_Processed_Data/spatial/{race_id}_course/panel_1m.parquet")
km_end = manifest_end
if panel_path.exists():
    panel = pd.read_parquet(panel_path)
    if "course_km" not in panel.columns and "ref_chainage_m" in panel.columns:
        panel = panel.copy()
        panel["course_km"] = panel["ref_chainage_m"] / 1000.0
    panel_max = round(float(panel["course_km"].max()), 3)
    km_end = max(manifest_end, panel_max)
tmap = load_terrain_map(Path(f"config/spatial_terrain_map_{race_id}.json"))
print(km_end, len(operator_gold_spans(tmap)))
PY
)"

gold_ed() {
  python3 04_Python_Scripts/spatial/gold_span_editor.py \
    --terrain-map "$TERRAIN_MAP" "$@"
}

echo "=== SCB Runde — operator gold lock (full course) ==="
echo "  window:   km 0.000–${KM_END}"
echo "  existing: ${SPAN_COUNT} span(s)"
echo ""

if [[ "$SPAN_COUNT" -gt 0 && -z "$FORCE" ]]; then
  echo "Terrain map already has gold. Re-run with --force to replace, or run coverage:" >&2
  echo "  python3 04_Python_Scripts/spatial/report_gold_coverage.py --terrain-map $TERRAIN_MAP" >&2
  exit 1
fi

run() {
  echo ">> $*"
  if [[ -z "$DRY_RUN" ]]; then
    "$@"
  fi
}

echo "━━━ 1/2 Clear km 0–${KM_END} ━━━"
if [[ -n "$DRY_RUN" ]]; then
  gold_ed --dry-run clear-window --km-start 0.0 --km-end "$KM_END"
else
  run gold_ed clear-window --km-start 0.0 --km-end "$KM_END"
fi

echo ""
echo "━━━ 2/2 Apply operator spans ━━━"

apply_span() {
  local ks="$1" ke="$2" sc="$3" fr="$4" rn="$5"
  if [[ -n "$DRY_RUN" ]]; then
    echo "  add km ${ks}–${ke} ${sc}/${fr}  (${rn})"
  else
    run gold_ed add --km-start "$ks" --km-end "$ke" \
      --surface "$sc" --friction "$fr" --reason "$rn"
  fi
}

apply_span 0.0   0.5   S3 F2 "orthophoto: grass km 0–0.5"
apply_span 0.5   0.98  S2 F2 "orthophoto: gravel km 0.5–0.98"
apply_span 0.98  1.0   S3 F2 "orthophoto: grass/trail km 0.98–1.0"
apply_span 1.0   1.8   S3 F2 "orthophoto: grass/trail km 1.0–1.8"
apply_span 1.8   2.0   S2 F2 "orthophoto: gravel km 1.8–2.0"
apply_span 2.0   2.8   S2 F2 "orthophoto: gravel km 2.0–2.8"
apply_span 2.8   3.0   S3 F2 "orthophoto: grass/trail km 2.8–3.0"
apply_span 3.0   3.35  S3 F2 "orthophoto: grass/trail km 3.0–3.35"
apply_span 3.35  3.5   S2 F2 "orthophoto: gravel km 3.35–3.5"
apply_span 3.5   3.95  S3 F2 "orthophoto: grass/trail km 3.5–3.95"
apply_span 3.95  4.0   S1 F0 "orthophoto: paved km 3.95–4.0"
apply_span 4.0   4.1   S1 F0 "orthophoto: paved km 4.0–4.1"
apply_span 4.1   4.6   S3 F2 "orthophoto: grass/trail km 4.1–4.6"
apply_span 4.6   5.0   S2 F2 "orthophoto: gravel km 4.6–5.0"
apply_span 5.0   5.83  S2 F2 "orthophoto: gravel km 5.0–5.83"
apply_span 5.83  6.0   S1 F0 "orthophoto: paved km 5.83–6.0"
apply_span 6.0   6.1   S1 F0 "orthophoto: paved km 6.0–6.1"
apply_span 6.1   "$KM_END" S2 F2 "orthophoto: gravel km 6.1–end"

echo ""
echo "━━━ Coverage ━━━"
if [[ -z "$DRY_RUN" ]]; then
  python3 04_Python_Scripts/spatial/report_gold_coverage.py --terrain-map "$TERRAIN_MAP"
else
  echo "(skipped — dry-run)"
fi
