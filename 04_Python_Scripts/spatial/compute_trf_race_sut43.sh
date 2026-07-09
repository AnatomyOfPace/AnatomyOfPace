#!/usr/bin/env bash
# SUT_43 race-day TRF — Subject_A + Subject_B + cross-athlete paired review.
#
# Phase 1 — full course (km 0.5–43.0) on panel_full_1m + merged terrain map.
# Phase 2 — gramstad_band spine cross-athlete (km 29–41) with TRF exclusions.
#
# Prerequisites (operator Mac):
#   03_Processed_Data/spatial/sut43_terrain_ontology/panel_full_1m.parquet
#   03_Processed_Data/spatial/sut43_terrain_ontology/panel_race_1m_spine.parquet
#   config/spatial_terrain_map_sut43_full.json
#   config/spatial_terrain_map_sut43.json
#
# Usage (repo root):
#   ./04_Python_Scripts/spatial/compute_trf_race_sut43.sh
#   ./04_Python_Scripts/spatial/compute_trf_race_sut43.sh --spine-only
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

ONTOLOGY="03_Processed_Data/spatial/sut43_terrain_ontology"
FULL_PANEL="${ONTOLOGY}/panel_full_1m.parquet"
SPINE_PANEL="${ONTOLOGY}/panel_race_1m_spine.parquet"
FULL_MAP="config/spatial_terrain_map_sut43_full.json"
GRAMSTAD_MAP="config/spatial_terrain_map_sut43.json"
FULL_OUT="${ONTOLOGY}/race_trf_full"
SPINE_OUT="${ONTOLOGY}/race_trf_spine"
TRF="04_Python_Scripts/spatial/compute_training_residual.py"

SPINE_ONLY=0
for arg in "$@"; do
  if [[ "$arg" == "--spine-only" ]]; then
    SPINE_ONLY=1
  fi
done

if [[ "$SPINE_ONLY" -eq 0 ]]; then
  if [[ ! -f "$FULL_PANEL" ]]; then
    echo "Missing full panel: $FULL_PANEL" >&2
    echo "  Build panel_full_1m on operator Mac (E4/E5 concat) before full-course TRF." >&2
    exit 1
  fi
  if [[ ! -f "$FULL_MAP" ]]; then
    echo "Missing terrain map: $FULL_MAP" >&2
    exit 1
  fi

  echo "=== SUT_43 race TRF — full course (km 0.5–43.0) ==="
  for SUBJECT in Subject_A Subject_B; do
    echo ""
    echo "--- ${SUBJECT} ---"
    python3 "$TRF" \
      --subject "$SUBJECT" \
      --panel "$FULL_PANEL" \
      --terrain-map "$FULL_MAP" \
      --output-dir "$FULL_OUT" \
      --sector-id sut43_full_race \
      --km-start 0.5 \
      --km-end 43.0 \
      --session-type race \
      --baseline-mode cohort_median
  done
fi

if [[ ! -f "$SPINE_PANEL" ]]; then
  echo "Missing spine panel: $SPINE_PANEL" >&2
  echo "  Run reproject_to_spine.py on race activities before cross-athlete TRF." >&2
  exit 1
fi
if [[ ! -f "$GRAMSTAD_MAP" ]]; then
  echo "Missing gramstad terrain map: $GRAMSTAD_MAP" >&2
  exit 1
fi

echo ""
echo "=== SUT_43 race TRF — cross-athlete spine (km 29–41) ==="
python3 "$TRF" \
  --cross-athlete \
  --panel "$SPINE_PANEL" \
  --terrain-map "$GRAMSTAD_MAP" \
  --output-dir "$SPINE_OUT" \
  --sector-id gramstad_band \
  --km-start 29.0 \
  --km-end 41.0 \
  --session-type race \
  --baseline-mode cohort_median

echo ""
echo "OK SUT_43 race TRF complete."
if [[ "$SPINE_ONLY" -eq 0 ]]; then
  echo "  Full course reports → ${FULL_OUT}/training_residual_report_Subject_*.json"
fi
echo "  Cross-athlete summary → ${SPINE_OUT}/cross_athlete_trf_summary.json"
echo "  Per-subject spine reports → ${SPINE_OUT}/training_residual_report_Subject_*.json"
