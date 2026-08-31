#!/usr/bin/env bash
# Wash + year-over-year compare — Stavanger Halvmarathon 2025 vs 2026 (Subject_A).
#
# Expects FIT files under 02_Raw_Data/donors/Subject_A/ (gitignored):
#   Stavanger_Halvmarathon_20250830.fit  (2025 — rename from Stavanger_Halvmarathon.fit if needed)
#   Stavanger_Halvmarathon_20260829.fit  (2026)
#
# Usage (repo root, on Mac):
#   ./04_Python_Scripts/spatial/compare_stavanger_halvmarathon_races.sh
#   ./04_Python_Scripts/spatial/compare_stavanger_halvmarathon_races.sh --compare-only
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT/.mplconfig}"
mkdir -p "$MPLCONFIGDIR"

DONOR="Subject_A"
RACE="stavanger_halvmarathon"
ACT_A="Stavanger_Halvmarathon_20250830"
ACT_B="Stavanger_Halvmarathon_20260829"
CANONICAL_FIT_A="02_Raw_Data/donors/${DONOR}/${ACT_A}.fit"
FIT_B="02_Raw_Data/donors/${DONOR}/${ACT_B}.fit"
# Legacy filenames (first anchor ingest used alternate spelling)
FIT_A_LEGACY_CANDIDATES=(
  "02_Raw_Data/donors/${DONOR}/Stavanger_Halvmarathon_20250830.fit"
  "02_Raw_Data/donors/${DONOR}/Stavanger_Halvmarathon.fit"
  "02_Raw_Data/donors/${DONOR}/Stavanger_Halvmaraton.fit"
  "02_Raw_Data/Stavanger_Halvmaraton.fit"
)

resolve_fit_a() {
  if [[ -f "$CANONICAL_FIT_A" ]]; then
    echo "$CANONICAL_FIT_A"
    return 0
  fi
  local candidate
  for candidate in "${FIT_A_LEGACY_CANDIDATES[@]}"; do
    if [[ -f "$candidate" ]]; then
      echo "NOTE: using 2025 FIT → $candidate (optional: cp to ${CANONICAL_FIT_A})" >&2
      echo "$candidate"
      return 0
    fi
  done
  echo "Missing 2025 FIT. Expected one of:" >&2
  printf '  %s\n' "$CANONICAL_FIT_A" "${FIT_A_LEGACY_CANDIDATES[@]}" >&2
  return 1
}

COMPARE_ONLY=0
for arg in "$@"; do
  if [[ "$arg" == "--compare-only" ]]; then
    COMPARE_ONLY=1
  fi
done

wash_one() {
  local activity="$1"
  local fit="$2"
  if [[ ! -f "$fit" ]]; then
    echo "Missing FIT: $fit" >&2
    return 1
  fi
  echo "━━━ Wash $activity ━━━"
  python3 04_Python_Scripts/15_fit_micro_wash.py \
    --donor "$DONOR" \
    --activity "$activity" \
    --fit "$fit" \
    --race "$RACE" \
    --project-course \
    --enrich-ti \
    --no-privacy-clip
}

if [[ "$COMPARE_ONLY" == "0" ]]; then
  RESOLVED_FIT_A="$(resolve_fit_a)"
  wash_one "$ACT_A" "$RESOLVED_FIT_A"
  wash_one "$ACT_B" "$FIT_B"
  echo ""
  echo "━━━ Rebuild dual-activity panel ━━━"
  python3 04_Python_Scripts/spatial/corridor_multi_fit.py \
    --manifest config/spatial_align_manifest_stavanger_halvmarathon.json \
    --enrich-if-needed
  echo ""
fi

python3 04_Python_Scripts/spatial/compare_stavanger_halvmarathon_races.py \
  --donor "$DONOR" \
  --activity-a "$ACT_A" \
  --activity-b "$ACT_B" \
  --label-a 2025 \
  --label-b 2026 \
  --manifest config/spatial_align_manifest_stavanger_halvmarathon.json

if [[ "$(uname -s)" == "Darwin" ]] && command -v open >/dev/null 2>&1; then
  open "06_Visualizations/stavanger_halvmarathon_race_compare.png"
fi
