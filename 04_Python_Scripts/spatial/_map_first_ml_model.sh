# Shared ML model resolution for map-first HITL export scripts.
# Source from export_hitl_chunks_*.sh — do not execute directly.
#
# Honors ML_MODEL env when set; otherwise: pooled map-first → course-specific.

map_first_resolve_ml_model() {
  local race_id="$1"
  if [[ -n "${ML_MODEL:-}" && -f "${ML_MODEL}" ]]; then
    return 0
  fi
  if [[ -n "${ML_MODEL:-}" && ! -f "${ML_MODEL}" ]]; then
    echo "WARN ML_MODEL not found: ${ML_MODEL} — trying fallbacks" >&2
    unset ML_MODEL
  fi
  local candidate
  for candidate in \
    "07_ML_Models/spatial/gold_suggester_map_first_pool_v0.joblib" \
    "07_ML_Models/spatial/gold_suggester_${race_id}_v0.joblib"
  do
    if [[ -f "$candidate" ]]; then
      export ML_MODEL="$candidate"
      return 0
    fi
  done
  return 1
}
