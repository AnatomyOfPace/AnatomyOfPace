#!/usr/bin/env bash
# Lock operator gold for Selvikstakken — full orthophoto spec (O₂ scramble anchor).
#
# Usage (from repo root, after bootstrap + HITL export):
#   ./04_Python_Scripts/spatial/lock_selvikstakken_gold.sh --force
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

RACE_ID="selvikstakken"
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
  echo "Terrain map missing. Restore .json.off or bootstrap:" >&2
  echo "  mv config/spatial_terrain_map_selvikstakken.json.off config/spatial_terrain_map_selvikstakken.json" >&2
  echo "  python3 04_Python_Scripts/spatial/bootstrap_map_first_orphan.py --course $RACE_ID" >&2
  exit 1
fi

read -r KM_END SPAN_COUNT <<<"$(python3 - <<PY
import json, sys
from pathlib import Path
sys.path.insert(0, "04_Python_Scripts")
from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.validation_dashboard import operator_gold_spans
race_id = "${RACE_ID}"
km_end = json.loads(Path(f"config/spatial_align_manifest_{race_id}.json").read_text())["km_analysis_window"][1]
print(km_end, len(operator_gold_spans(load_terrain_map(Path(f"config/spatial_terrain_map_{race_id}.json")))))
PY
)"

gold_ed() {
  python3 04_Python_Scripts/spatial/gold_span_editor.py --terrain-map "$TERRAIN_MAP" "$@"
}

echo "=== Selvikstakken — operator gold lock (full course) ==="
echo "  window: km 0–${KM_END} | existing spans: ${SPAN_COUNT}"

if [[ "$SPAN_COUNT" -gt 0 && -z "$FORCE" ]]; then
  echo "Already has gold. Use --force to replace." >&2
  exit 1
fi

run() { echo ">> $*"; [[ -z "$DRY_RUN" ]] && "$@"; }
apply_span() {
  local ks="$1" ke="$2" sc="$3" fr="$4" rn="$5"
  if [[ -n "$DRY_RUN" ]]; then
    echo "  add km ${ks}–${ke} ${sc}/${fr}  (${rn})"
  else
    run gold_ed add --km-start "$ks" --km-end "$ke" \
      --surface "$sc" --friction "$fr" --reason "$rn"
  fi
}

echo "━━━ Clear km 0–${KM_END} ━━━"
if [[ -n "$DRY_RUN" ]]; then
  gold_ed --dry-run clear-window --km-start 0.0 --km-end "$KM_END"
else
  run gold_ed clear-window --km-start 0.0 --km-end "$KM_END"
fi

echo "━━━ Apply operator spans ━━━"
apply_span 0.0  1.7  S2 F2 "orthophoto: gravel km 0–1.7"
apply_span 1.7  6.0  S3 F2 "orthophoto: trail km 1.7–6.0"
apply_span 6.0  7.5  S4 F3 "orthophoto: technical rock km 6.0–7.5"
apply_span 7.5  7.7  S5 F4 "orthophoto: scramble section km 7.5–7.7"
apply_span 7.7  8.7  S4 F3 "orthophoto: technical rock km 7.7–8.7"
apply_span 8.7  9.1  S3 F2 "orthophoto: trail km 8.7–9.1"
apply_span 9.1  "$KM_END" S2 F2 "orthophoto: gravel km 9.1–end"

echo "━━━ Coverage ━━━"
if [[ -z "$DRY_RUN" ]]; then
  python3 04_Python_Scripts/spatial/report_gold_coverage.py --terrain-map "$TERRAIN_MAP"
else
  echo "(skipped — dry-run)"
fi
