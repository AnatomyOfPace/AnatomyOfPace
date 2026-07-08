#!/usr/bin/env bash
# Export HITL PNGs for all bootstrapped orphan courses (pooled ML strip).
#
# Usage:
#   ./04_Python_Scripts/spatial/export_map_first_orphans_pool.sh
#   ML_MODEL=07_ML_Models/spatial/gold_suggester_map_first_pool_v0.joblib \
#     ./04_Python_Scripts/spatial/export_map_first_orphans_pool.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export ML_MODEL="${ML_MODEL:-07_ML_Models/spatial/gold_suggester_map_first_pool_v0.joblib}"

if [[ ! -f "$ML_MODEL" ]]; then
  echo "ML model not found: $ML_MODEL" >&2
  echo "Train first: ./04_Python_Scripts/spatial/train_map_first_gold_pool.sh --with-o1-anchors" >&2
  exit 1
fi

echo "=== Map-first orphan HITL pool export (Subject_A) ==="
echo "ML_MODEL=$ML_MODEL"
echo ""

EXPORT_SCRIPT="04_Python_Scripts/spatial/export_hitl_map_first_orphan.sh"
if [[ ! -x "$EXPORT_SCRIPT" ]]; then
  chmod +x "$EXPORT_SCRIPT"
fi

while IFS= read -r race_id; do
  [[ -z "$race_id" ]] && continue
  panel="03_Processed_Data/spatial/${race_id}_course/panel_1m.parquet"
  if [[ ! -f "$panel" ]]; then
    echo "SKIP $race_id — panel missing (bootstrap first)" >&2
    continue
  fi
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "→ $race_id"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  "$EXPORT_SCRIPT" "$race_id"
  echo ""
done < <(python3 - <<'PY'
import json
from pathlib import Path
reg = json.loads(Path("config/map_first_orphan_courses.json").read_text())
for c in reg.get("courses") or []:
    print(c["race_id"])
PY
)

echo "OK orphan HITL pool export complete (bootstrapped courses only)."
