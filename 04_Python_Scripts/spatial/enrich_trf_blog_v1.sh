#!/usr/bin/env bash
# TRF blog v1 enrichment — corridor slice (bedrock + late_braking) + ghost-safe figures.
#
# Run after compute_trf_race_sut43.sh (needs race_trf_gramstad + race_trf_full).
#
# Usage (repo root):
#   ./04_Python_Scripts/spatial/enrich_trf_blog_v1.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

ONTOLOGY="03_Processed_Data/spatial/sut43_terrain_ontology"
SPINE_PANEL="${ONTOLOGY}/panel_race_1m_spine.parquet"
GRAMSTAD_MAP="config/spatial_terrain_map_sut43.json"
CORRIDOR_OUT="${ONTOLOGY}/race_trf_bedrock_late_braking"
TRF="04_Python_Scripts/spatial/compute_training_residual.py"
KM_START=31.0
KM_END=34.0

if [[ ! -f "$SPINE_PANEL" ]]; then
  echo "Missing spine panel: $SPINE_PANEL" >&2
  exit 1
fi

echo "=== TRF corridor slice — bedrock + late_braking (km ${KM_START}–${KM_END}) ==="
for SUBJECT in Subject_A Subject_B; do
  echo ""
  echo "--- ${SUBJECT} ---"
  python3 "$TRF" \
    --subject "$SUBJECT" \
    --panel "$SPINE_PANEL" \
    --terrain-map "$GRAMSTAD_MAP" \
    --output-dir "$CORRIDOR_OUT" \
    --sector-id bedrock_late_braking \
    --km-start "$KM_START" \
    --km-end "$KM_END" \
    --session-type race \
    --baseline-mode cohort_median
done

echo ""
echo "=== Blog figures (ghost-safe) ==="
python3 04_Python_Scripts/spatial/render_sut43_gramstad_trf_blog.py

echo ""
echo "=== Bedrock corridor HITL basemap ==="
if [[ -f "$SPINE_PANEL" ]]; then
  ./04_Python_Scripts/spatial/export_bedrock_corridor_basemap.sh
else
  echo "SKIP basemap — missing $SPINE_PANEL" >&2
fi

echo ""
echo "=== Corridor blog QC ==="
python3 04_Python_Scripts/spatial/verify_trf_corridor_blog_cells.py \
  --corridor-dir "$CORRIDOR_OUT" \
  --km-start "$KM_START" \
  --km-end "$KM_END"

echo ""
echo "OK TRF blog v1 enrichment complete."
echo "  Corridor reports → ${CORRIDOR_OUT}/training_residual_report_Subject_*.json"
echo "  Figures → 06_Visualizations/sut43_*_blog.png"
echo ""
echo "Corridor slice top cells (Subject_A):"
python3 -c "
import json
p='${CORRIDOR_OUT}/training_residual_report_Subject_A.json'
r=json.load(open(p))
for c in r.get('top_cells_by_impact',[])[:3]:
    print(f\"  {c.get('friction_tier')} {c.get('grade_band')} {c.get('locomotion_mode')}  ΔTI={c.get('delta_ti_mean'):+.3f}  km {c['course_km_start']:.2f}-{c['course_km_end']:.2f}\")
"
