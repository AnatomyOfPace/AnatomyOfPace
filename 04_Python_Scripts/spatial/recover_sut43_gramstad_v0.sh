#!/usr/bin/env bash
# One-shot: merge full map, rebuild export, retrain v0, re-smoke gramstad REVISE.
#
# Run on operator Mac from repo root. Safe on main after PR #14 merge, or on
# cursor/sut43-sector-retrain-0c6a.
#
# Usage:
#   ./04_Python_Scripts/spatial/recover_sut43_gramstad_v0.sh
#   ./04_Python_Scripts/spatial/recover_sut43_gramstad_v0.sh --skip-train
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

SKIP_TRAIN=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-train) SKIP_TRAIN=1; shift ;;
    *)
      echo "Usage: $0 [--skip-train]" >&2
      exit 1
      ;;
  esac
done

echo "=== SUT_43 gramstad v0 recovery ==="

if ! grep -q "ML REVISE adopted" config/spatial_terrain_map_sut43.json 2>/dev/null; then
  echo "WARN: chunk_09 ML adopt not in spatial_terrain_map_sut43.json" >&2
  echo "  Apply: ./04_Python_Scripts/spatial/lock_sut43_chunk09_ml_adopt.sh" >&2
  echo "  Or:    git checkout cursor/sut43-sector-retrain-0c6a -- config/spatial_terrain_map_sut43.json" >&2
fi

echo "━━━ 1/4 Merge sector maps → full ━━━"
python3 04_Python_Scripts/spatial/merge_terrain_maps.py \
  --sector config/spatial_terrain_map_sut43_start.json:0.5:8.0 \
  --sector config/spatial_terrain_map_sut43_bridge.json:8.0:22.0 \
  --sector config/spatial_terrain_map_sut43_upstream.json:22.0:29.0 \
  --sector config/spatial_terrain_map_sut43.json:29.0:41.0 \
  --sector config/spatial_terrain_map_sut43_finish.json:41.0:42.5 \
  --sector config/spatial_terrain_map_sut43_finish_tail.json:42.5:43.0 \
  --km-start 0.5 --km-end 43.0 \
  --output config/spatial_terrain_map_sut43_full.json \
  --report-json 07_ML_Models/spatial/merge_terrain_map_sut43_full_report.json

echo ""
echo "━━━ 2/4 Rebuild gold_training_set_sut43_full.parquet ━━━"
python3 04_Python_Scripts/spatial/build_gold_training_set.py \
  --terrain-map config/spatial_terrain_map_sut43_full.json \
  --panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_full_1m.parquet \
  --km-start 0.5 --km-end 43.0 \
  --output 03_Processed_Data/spatial/gold_training_set_sut43_full.parquet \
  --summary-json 03_Processed_Data/spatial/gold_training_set_sut43_full_summary.json

if [[ -z "$SKIP_TRAIN" ]]; then
  echo ""
  echo "━━━ 3/4 Retrain v0 ━━━"
  python3 04_Python_Scripts/spatial/train_gold_suggester.py \
    --training-set 03_Processed_Data/spatial/gold_training_set_sut43_full.parquet \
    --model-out 07_ML_Models/spatial/gold_suggester_v0.joblib \
    --metadata-out 07_ML_Models/spatial/gold_suggester_v0_metadata.json
else
  echo ""
  echo "━━━ 3/4 Train skipped ━━━"
fi

echo ""
echo "━━━ 4/4 Re-smoke gramstad (fresh CSV) ━━━"
rm -f 03_Processed_Data/spatial/suggested_revise_sut43_gramstad_sector.csv
python3 04_Python_Scripts/spatial/suggest_gold_spans.py \
  --engine ml --mode all --sector-routing \
  --terrain-map config/spatial_terrain_map_sut43.json \
  --panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet \
  --km-start 29 --km-end 41 \
  --output 03_Processed_Data/spatial/suggested_revise_sut43_gramstad_sector.csv

python3 - <<'PY'
import pandas as pd
from pathlib import Path
p = Path("03_Processed_Data/spatial/suggested_revise_sut43_gramstad_sector.csv")
df = pd.read_csv(p)
print(df["action"].value_counts().to_string())
rev = df[df["action"] == "REVISE"]
print(f"\nREVISE rows: {len(rev)}")
if len(rev):
    cols = ["km_start", "km_end", "surface_class", "friction_tier", "gold_surface", "gold_friction", "confidence"]
    print(rev[cols].to_string(index=False))
PY

echo ""
echo "OK recovery complete."
