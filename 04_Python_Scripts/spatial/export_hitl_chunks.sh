#!/usr/bin/env bash
# Bulk-export gramstad_band HITL decision dashboards (12 × 1 km, km 29–41).
# SPINE_PANEL=1 or --spine-panel → panel_race_1m_spine.parquet + _spine filename suffix.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT/.mplconfig}"
mkdir -p "$MPLCONFIGDIR"

PANEL="03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet"
OUTPUT_SUFFIX=""
USE_SPINE=0
PASS_ARGS=()

for arg in "$@"; do
  if [[ "$arg" == "--spine-panel" ]]; then
    USE_SPINE=1
  else
    PASS_ARGS+=("$arg")
  fi
done

if [[ "${SPINE_PANEL:-0}" == "1" ]] || [[ "$USE_SPINE" == "1" ]]; then
  PANEL="03_Processed_Data/spatial/sut43_terrain_ontology/panel_race_1m_spine.parquet"
  OUTPUT_SUFFIX="_spine"
fi

# Single-chunk exports: append _spine to --output when set and spine mode active.
CHUNK_INDEX=""
EXPORT_CHUNKS=1
for i in "${!PASS_ARGS[@]}"; do
  if [[ "${PASS_ARGS[$i]}" == "--chunk-index" && -n "${PASS_ARGS[$i+1]:-}" ]]; then
    CHUNK_INDEX="${PASS_ARGS[$i+1]}"
    EXPORT_CHUNKS=0
  fi
done

if [[ -n "$OUTPUT_SUFFIX" ]]; then
  NEW_ARGS=()
  skip_next=0
  for i in "${!PASS_ARGS[@]}"; do
    if [[ "$skip_next" == "1" ]]; then
      skip_next=0
      out_path="${PASS_ARGS[$i]}"
      if [[ "$out_path" != *"_spine"* ]]; then
        base="${out_path%.*}"
        ext="${out_path##*.}"
        out_path="${base}${OUTPUT_SUFFIX}.${ext}"
      fi
      NEW_ARGS+=("$out_path")
      continue
    fi
    if [[ "${PASS_ARGS[$i]}" == "--output" || "${PASS_ARGS[$i]}" == "-o" ]]; then
      NEW_ARGS+=("${PASS_ARGS[$i]}")
      skip_next=1
      continue
    fi
    NEW_ARGS+=("${PASS_ARGS[$i]}")
  done
  PASS_ARGS=("${NEW_ARGS[@]}")
fi

DASH_ARGS=(
  --terrain-map config/spatial_terrain_map_sut43.json
  --panel "$PANEL"
  --activity SUT43_20260418
  --map-track-donor Subject_A
  --chunk-km 1
  --verify-export
)

if [[ "$EXPORT_CHUNKS" == "1" ]]; then
  DASH_ARGS+=(--export-chunks --output-dir "06_Visualizations/sut43_hitl${OUTPUT_SUFFIX}")
else
  DASH_ARGS+=(--chunk-index "$CHUNK_INDEX" --output-dir "06_Visualizations/sut43_hitl")
fi

if ((${#PASS_ARGS[@]})); then
  python3 04_Python_Scripts/spatial/validation_dashboard.py \
    "${DASH_ARGS[@]}" \
    "${PASS_ARGS[@]}"
else
  python3 04_Python_Scripts/spatial/validation_dashboard.py \
    "${DASH_ARGS[@]}"
fi
