#!/usr/bin/env bash
# Build per-course gold training exports, merge map-first pool, train pooled suggester.
#
# Courses: Tverrfjell, Klepp Runde, Gramstad Runde, Vinje Terrengløp (FIT stream axis).
# Optional O₁ anchors: Stavanger Halvmarathon (S1/F0 asphalt), 3-sjøersløpet (S2/F1 gravel),
# Sunderunde training loop (S2/F1 gravel + S1/F1 asphalt).
#
# Usage (from repo root):
#   ./04_Python_Scripts/spatial/train_map_first_gold_pool.sh --rebuild-exports
#   ./04_Python_Scripts/spatial/train_map_first_gold_pool.sh --with-o1-anchors --rebuild-exports
#   ./04_Python_Scripts/spatial/train_map_first_gold_pool.sh --with-orphans --rebuild-exports
#
# Without --rebuild-exports, stale exports auto-rebuild when:
#   - sibling .summary.json reports unlabeled_metres > 0
#   - terrain map is newer than the parquet
#   - parquet lacks is_labeled or labeled count < row count
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

REBUILD=""
WITH_O1=""
WITH_ORPHANS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rebuild-exports) REBUILD=1; shift ;;
    --with-o1-anchors) WITH_O1=1; shift ;;
    --with-orphans) WITH_ORPHANS=1; shift ;;
    *)
      echo "Usage: $0 [--rebuild-exports] [--with-o1-anchors] [--with-orphans]" >&2
      exit 1
      ;;
  esac
done

BUILD="04_Python_Scripts/spatial/build_gold_training_set.py"
MERGE="04_Python_Scripts/spatial/merge_gold_training_sets.py"
TRAIN="04_Python_Scripts/spatial/train_gold_suggester.py"
PROCESSED="03_Processed_Data/spatial"
MODEL_DIR="07_ML_Models/spatial"

declare -a TERRAIN_MAPS=(
  "config/spatial_terrain_map_tverrfjell.json"
  "config/spatial_terrain_map_klepp_runde.json"
  "config/spatial_terrain_map_gramstad_runde.json"
  "config/spatial_terrain_map_vinje_terrenglop.json"
)

declare -a PARQUETS=(
  "${PROCESSED}/gold_training_set_tverrfjell.parquet"
  "${PROCESSED}/gold_training_set_klepp_runde.parquet"
  "${PROCESSED}/gold_training_set_gramstad_runde.parquet"
  "${PROCESSED}/gold_training_set_vinje_terrenglop.parquet"
)

if [[ -n "$WITH_O1" ]]; then
  TERRAIN_MAPS+=(
    "config/spatial_terrain_map_stavanger_halvmarathon.json"
    "config/spatial_terrain_map_3_sjoerslopet.json"
    "config/spatial_terrain_map_sunderunde.json"
  )
  PARQUETS+=(
    "${PROCESSED}/gold_training_set_stavanger_halvmarathon.parquet"
    "${PROCESSED}/gold_training_set_3_sjoerslopet.parquet"
    "${PROCESSED}/gold_training_set_sunderunde.parquet"
  )
fi

if [[ -n "$WITH_ORPHANS" ]]; then
  while IFS= read -r race_id; do
    tmap="config/spatial_terrain_map_${race_id}.json"
    pq="${PROCESSED}/gold_training_set_${race_id}.parquet"
    if [[ -f "$tmap" ]]; then
      TERRAIN_MAPS+=("$tmap")
      PARQUETS+=("$pq")
    else
      echo "WARN orphan terrain map missing (bootstrap first): $tmap" >&2
    fi
  done < <(python3 - <<'PY'
import json
from pathlib import Path
reg = json.loads(Path("config/map_first_orphan_courses.json").read_text())
for c in reg.get("courses") or []:
    print(c["race_id"])
PY
)
fi

POOL="${PROCESSED}/gold_training_set_map_first_pool.parquet"
MODEL="${MODEL_DIR}/gold_suggester_map_first_pool_v0.joblib"
METADATA="${MODEL_DIR}/gold_suggester_map_first_pool_v0_metadata.json"

SCB_TMAP="config/spatial_terrain_map_scb_runde.json"
SCB_LOCK="04_Python_Scripts/spatial/lock_scb_runde_tail_gap.sh"
if [[ -n "$WITH_ORPHANS" && -f "$SCB_TMAP" && -x "$SCB_LOCK" ]]; then
  echo "=== SCB Runde tail gap (pre-build) ==="
  ./"$SCB_LOCK" || {
    echo "WARN $SCB_LOCK failed — fix operator gold manually before pool train" >&2
  }
  echo ""
fi

needs_rebuild_export() {
  local tmap="$1"
  local pq="$2"
  python3 - <<PY
import json
import sys
from pathlib import Path

import pandas as pd

tmap = Path("$tmap")
pq = Path("$pq")
if not pq.exists():
    print("missing parquet")
    raise SystemExit(0)

summary_path = pq.with_suffix(".summary.json")
if summary_path.exists():
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    unlabeled = int(summary.get("unlabeled_metres") or 0)
    if unlabeled > 0:
        print(f"{unlabeled} unlabeled m in summary")
        raise SystemExit(0)

if tmap.exists() and tmap.stat().st_mtime > pq.stat().st_mtime:
    print("terrain map newer than parquet")
    raise SystemExit(0)

df = pd.read_parquet(pq, columns=["is_labeled"])
labeled = int(df["is_labeled"].sum())
if labeled < len(df):
    print(f"parquet {labeled}/{len(df)} labeled")
    raise SystemExit(0)

raise SystemExit(1)
PY
}

echo "=== Build per-course gold training exports ==="
for i in "${!TERRAIN_MAPS[@]}"; do
  tmap="${TERRAIN_MAPS[$i]}"
  pq="${PARQUETS[$i]}"
  if [[ -n "$REBUILD" || ! -f "$pq" ]]; then
    echo "→ $tmap"
    python3 "$BUILD" --terrain-map "$tmap"
  else
    rebuild_reason="$(needs_rebuild_export "$tmap" "$pq" || true)"
    if [[ -n "$rebuild_reason" ]]; then
      echo "→ $tmap  (rebuild: ${rebuild_reason})"
      python3 "$BUILD" --terrain-map "$tmap"
    else
      echo "OK skip (exists): $pq"
    fi
  fi
done

echo ""
echo "=== Merge map-first pool ==="
MERGE_ARGS=()
for pq in "${PARQUETS[@]}"; do
  if [[ ! -f "$pq" ]]; then
    echo "Missing export: $pq — run with --rebuild-exports (panels must exist locally)" >&2
    exit 1
  fi
  MERGE_ARGS+=(--input "$pq")
done

python3 "$MERGE" \
  "${MERGE_ARGS[@]}" \
  --output "$POOL" \
  --summary-json "${PROCESSED}/gold_training_set_map_first_pool.summary.json"

python3 - <<'PY'
import json
import sys
from pathlib import Path

summary = json.loads(
    Path("03_Processed_Data/spatial/gold_training_set_map_first_pool.summary.json").read_text()
)
gaps = {
    anchor: counts
    for anchor, counts in (summary.get("sources") or {}).items()
    if int(counts.get("labeled", 0)) < int(counts.get("rows", 0))
}
if not gaps:
    raise SystemExit(0)
print("\nERROR incomplete gold coverage in pooled inputs — aborting before train:")
for anchor, counts in sorted(gaps.items()):
    rows = int(counts["rows"])
    labeled = int(counts["labeled"])
    print(f"  {anchor}: {labeled}/{rows} labeled ({rows - labeled} m gap)")
if "scb_runde" in gaps:
    print(
        "\n  scb_runde tail: ./04_Python_Scripts/spatial/lock_scb_runde_tail_gap.sh\n"
        "  then re-run this script (tail lock also runs automatically with --with-orphans)"
    )
raise SystemExit(1)
PY

echo ""
echo "=== Train pooled gold suggester ==="
TRAIN_ARGS=(
  --training-set "$POOL"
  --sector-id map_first_pool
  --model-out "$MODEL"
  --metadata-out "$METADATA"
)
if [[ -n "$WITH_O1" ]]; then
  echo "O₁ anchors included — downweighting so trail loops are not drowned (~21 km each)"
  TRAIN_ARGS+=(
    --source-weight stavanger_halvmarathon:0.5
    --source-weight 3_sjoerslopet:0.5
    --source-weight sunderunde:0.5
  )
fi

python3 "$TRAIN" "${TRAIN_ARGS[@]}"

echo ""
echo "OK map-first pool model → $MODEL"
if [[ -n "$WITH_O1" ]]; then
  echo "  (trained with Stavanger Halvmarathon + 3-sjøersløpet + Sunderunde O₁ anchors)"
fi
if [[ -n "$WITH_ORPHANS" ]]; then
  echo "  (includes labeled orphan courses from map_first_orphan_courses.json when bootstrapped)"
fi
echo "Re-export trail loops:"
echo "  ./04_Python_Scripts/spatial/export_map_first_hitl_pool.sh"
echo "Re-export O₁ anchors:"
echo "  ./04_Python_Scripts/spatial/export_o1_anchor_hitl_pool.sh"
echo "Re-export orphan courses (after bootstrap + label):"
echo "  ./04_Python_Scripts/spatial/export_map_first_orphans_pool.sh"
