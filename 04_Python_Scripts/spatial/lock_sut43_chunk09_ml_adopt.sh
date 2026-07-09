#!/usr/bin/env bash
# Adopt ML S3/F3 for gramstad_band km 38.35–39.0 (chunk_09); gravel S2/F3 from km 39.0.
#
# Idempotent: rewrites operator_gold_spans via gold_span_editor after removing
# overlapping 38.35–39.135 locks. Run once on operator Mac after pulling map edit,
# or if map not yet pulled, this script applies the same spans locally.
#
# Usage (from repo root):
#   ./04_Python_Scripts/spatial/lock_sut43_chunk09_ml_adopt.sh
#   ./04_Python_Scripts/spatial/lock_sut43_chunk09_ml_adopt.sh --dry-run
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

TMAP="config/spatial_terrain_map_sut43.json"
EDITOR="04_Python_Scripts/spatial/gold_span_editor.py"
DRY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY=1; shift ;;
    *)
      echo "Usage: $0 [--dry-run]" >&2
      exit 1
      ;;
  esac
done

echo "=== SUT_43 chunk_09 ML adopt (km 38.35–39.0 S3/F3) ==="

# If committed map already has the adopt, skip destructive edits.
if python3 - <<'PY'
import json
from pathlib import Path
spans = json.loads(Path("config/spatial_terrain_map_sut43.json").read_text())["hitl"]["operator_gold_spans"]
for s in spans:
    if s.get("course_km_start") == 38.35 and s.get("course_km_end") == 39.0:
        if s.get("surface_class") == "S3" and "ML REVISE adopted" in (s.get("reason") or ""):
            raise SystemExit(0)
raise SystemExit(1)
PY
then
  echo "OK terrain map already has ML adopt @ km 38.35–39.0 — nothing to do."
  exit 0
fi

run() {
  if [[ -n "$DRY" ]]; then
    echo "  [dry-run] $*"
  else
    "$@"
  fi
}

echo "Removing overlapping spans km 38.35–39.135 (if present)..."
while IFS= read -r idx; do
  [[ -z "$idx" ]] && continue
  run python3 "$EDITOR" --terrain-map "$TMAP" delete --index "$idx"
done < <(python3 - <<'PY'
import json
from pathlib import Path
spans = json.loads(Path("config/spatial_terrain_map_sut43.json").read_text())["hitl"]["operator_gold_spans"]
for i, s in enumerate(spans):
    lo, hi = float(s["course_km_start"]), float(s["course_km_end"])
    if hi <= 38.35 + 1e-9 or lo >= 39.135 - 1e-9:
        continue
    if lo < 39.135 - 1e-9 and hi > 38.35 + 1e-9:
        print(i)
PY
)

run python3 "$EDITOR" --terrain-map "$TMAP" add \
  --km-start 38.35 --km-end 39.0 --surface S3 --friction F3 \
  --reason "operator gold: forest dirt / muddy tread (chunk_09) — ML REVISE adopted 2026-07-09 S3/F3 km 38.35–39.0"

run python3 "$EDITOR" --terrain-map "$TMAP" add \
  --km-start 39.0 --km-end 39.135 --surface S2 --friction F3 \
  --reason "operator gold: Paradisskaret gravel km 39.0–39.135 to stile — post ML adopt chunk_09"

echo "OK chunk_09 ML adopt applied → $TMAP"
echo "Next: merge full map + optional v0 retrain (see retrain_sut43_sector_suggester.sh --merge-maps)"
