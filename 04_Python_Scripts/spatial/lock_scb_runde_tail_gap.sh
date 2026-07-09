#!/usr/bin/env bash
# Close SCB Runde course-tail gap (~20 m) between operator gold end and panel extent.
#
# Symptom: pool build reports 6925/6945 m labeled — manifest km_end (~6.925) trails
# panel max (~6.945) after corridor_multi_fit. Extends the terminal gravel span and
# patches manifest + corridor km_end to panel extent.
#
# Usage (from repo root, operator Mac with local SCB configs + panel):
#   python3 04_Python_Scripts/spatial/report_gold_coverage.py \
#     --terrain-map config/spatial_terrain_map_scb_runde.json \
#     --panel 03_Processed_Data/spatial/scb_runde_course/panel_1m.parquet
#   ./04_Python_Scripts/spatial/lock_scb_runde_tail_gap.sh
#   ./04_Python_Scripts/spatial/lock_scb_runde_tail_gap.sh --dry-run
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

RACE_ID="scb_runde"
TERRAIN_MAP="config/spatial_terrain_map_${RACE_ID}.json"
MANIFEST="config/spatial_align_manifest_${RACE_ID}.json"
PANEL="03_Processed_Data/spatial/${RACE_ID}_course/panel_1m.parquet"
EDITOR="04_Python_Scripts/spatial/gold_span_editor.py"
MAX_TAIL_GAP_M=50.0

DRY_RUN=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    *)
      echo "Usage: $0 [--dry-run]" >&2
      exit 1
      ;;
  esac
done

for req in "$TERRAIN_MAP" "$MANIFEST" "$PANEL"; do
  if [[ ! -f "$req" ]]; then
    echo "Missing prerequisite: $req" >&2
    echo "Bootstrap: python3 04_Python_Scripts/spatial/bootstrap_map_first_orphan.py --course $RACE_ID" >&2
    exit 1
  fi
done

read -r PANEL_MAX MANIFEST_END CORRIDOR_END TAIL_START TAIL_END GAP_M TAIL_IDX TAIL_SC TAIL_FR TAIL_REASON <<<"$(python3 - <<'PY'
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, "04_Python_Scripts")
from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.validation_dashboard import operator_gold_spans
from spatial.gold_training_common import span_km_bounds

race_id = "scb_runde"
panel_path = Path("03_Processed_Data/spatial/scb_runde_course/panel_1m.parquet")
manifest_path = Path("config/spatial_align_manifest_scb_runde.json")
tmap_path = Path("config/spatial_terrain_map_scb_runde.json")

panel = pd.read_parquet(panel_path)
if "course_km" not in panel.columns and "ref_chainage_m" in panel.columns:
    panel = panel.copy()
    panel["course_km"] = panel["ref_chainage_m"] / 1000.0
panel_max = round(float(panel["course_km"].max()), 3)

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest_end = round(float(manifest["km_analysis_window"][1]), 3)

tmap = load_terrain_map(tmap_path)
corridor_end = round(float((tmap.get("corridor") or {}).get("km_end") or 0.0), 3)

spans = operator_gold_spans(tmap)
if not spans:
    print("ERROR no operator gold spans", file=sys.stderr)
    raise SystemExit(2)

tail_idx = max(range(len(spans)), key=lambda i: span_km_bounds(spans[i])[1])
tail = spans[tail_idx]
tail_lo, tail_hi = span_km_bounds(tail)
gap_m = round(max(0.0, (panel_max - tail_hi) * 1000.0), 1)

tail_sc = str(tail.get("surface_class") or "S2")
tail_fr = str(tail.get("friction_tier") or "F2")
tail_reason = str(tail.get("reason") or "orthophoto: gravel tail extension to panel extent")

print(
    panel_max,
    manifest_end,
    corridor_end,
    round(tail_lo, 3),
    round(tail_hi, 3),
    gap_m,
    tail_idx,
    tail_sc,
    tail_fr,
    tail_reason.replace(" ", "_"),
)
PY
)"

if [[ "$GAP_M" == "ERROR"* ]] || [[ -z "$GAP_M" ]]; then
  echo "Failed to read panel / gold spans" >&2
  exit 1
fi

echo "=== SCB Runde — close tail gap ==="
echo "  panel max:     km ${PANEL_MAX}"
echo "  manifest end:  km ${MANIFEST_END}"
echo "  corridor end:  km ${CORRIDOR_END}"
echo "  gold tail:     km ${TAIL_START}–${TAIL_END} (span [${TAIL_IDX}] ${TAIL_SC}/${TAIL_FR})"
echo "  tail gap:      ${GAP_M} m"
echo ""

patch_km_end() {
  python3 - <<PY
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

panel_max = float("${PANEL_MAX}")
dry = bool("${DRY_RUN}")

def backup(path: Path) -> None:
    if dry or not path.exists():
        return
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2(path, path.with_suffix(f".backup_{ts}.json"))

manifest_path = Path("${MANIFEST}")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
old = float(manifest["km_analysis_window"][1])
if panel_max > old + 1e-6:
    manifest["km_analysis_window"][1] = round(panel_max, 3)
    manifest["km_viewport_window"][1] = round(panel_max + 0.1, 3)
    if not dry:
        backup(manifest_path)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\\n", encoding="utf-8")
    print(f"  manifest km_end {old:.3f} → {panel_max:.3f}")

tmap_path = Path("${TERRAIN_MAP}")
tmap = json.loads(tmap_path.read_text(encoding="utf-8"))
corridor = tmap.setdefault("corridor", {})
old_c = float(corridor.get("km_end") or 0.0)
if panel_max > old_c + 1e-6:
    corridor["km_end"] = round(panel_max, 3)
    if not dry:
        backup(tmap_path)
        tmap_path.write_text(json.dumps(tmap, indent=2) + "\\n", encoding="utf-8")
    print(f"  corridor km_end {old_c:.3f} → {panel_max:.3f}")
PY
}

if awk -v g="$GAP_M" 'BEGIN { exit !(g <= 0.05) }'; then
  if awk -v p="$PANEL_MAX" -v m="$MANIFEST_END" -v c="$CORRIDOR_END" \
    'BEGIN { exit !((p > m + 0.0001) || (p > c + 0.0001)) }'; then
    echo "Gold spans cover panel — patching km_end only."
    patch_km_end
  else
    echo "OK full gold coverage — nothing to do."
  fi
  exit 0
fi

if awk -v g="$GAP_M" -v m="$MAX_TAIL_GAP_M" 'BEGIN { exit !(g > 0.05 && g <= m) }'; then
  :
else
  echo "Tail gap ${GAP_M} m exceeds ${MAX_TAIL_GAP_M} m cap — review orthophoto before locking." >&2
  exit 1
fi

run() {
  if [[ -n "$DRY_RUN" ]]; then
    echo "  [dry-run] $*"
  else
    "$@"
  fi
}

if awk -v g="$GAP_M" 'BEGIN { exit !(g > 0.05) }'; then
  echo "━━━ 1/3 Extend terminal gold span to panel max ━━━"
  TAIL_REASON_DISPLAY="${TAIL_REASON//_/ }"
  if [[ -n "$DRY_RUN" ]]; then
    echo "  delete span [${TAIL_IDX}] km ${TAIL_START}–${TAIL_END}"
    echo "  add km ${TAIL_START}–${PANEL_MAX} ${TAIL_SC}/${TAIL_FR}"
  else
    run python3 "$EDITOR" --terrain-map "$TERRAIN_MAP" delete --index "$TAIL_IDX"
    run python3 "$EDITOR" --terrain-map "$TERRAIN_MAP" add \
      --km-start "$TAIL_START" --km-end "$PANEL_MAX" \
      --surface "$TAIL_SC" --friction "$TAIL_FR" \
      --reason "${TAIL_REASON_DISPLAY} — tail gap closed to panel km ${PANEL_MAX}"
  fi
else
  echo "━━━ 1/3 Gold tail already at panel — skip span edit ━━━"
fi

echo ""
echo "━━━ 2/3 Patch manifest + corridor km_end ━━━"
patch_km_end

echo ""
echo "━━━ 3/3 Coverage verify ━━━"
if [[ -n "$DRY_RUN" ]]; then
  echo "(skipped — dry-run)"
  exit 0
fi

python3 04_Python_Scripts/spatial/report_gold_coverage.py \
  --terrain-map "$TERRAIN_MAP" \
  --panel "$PANEL" \
  --km-end "$PANEL_MAX"

echo ""
echo "Next (optional):"
echo "  python3 04_Python_Scripts/spatial/build_gold_training_set.py --terrain-map $TERRAIN_MAP"
echo "  ./04_Python_Scripts/spatial/train_map_first_gold_pool.sh --with-o1-anchors --with-orphans"
