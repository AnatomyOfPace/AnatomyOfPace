#!/usr/bin/env bash
# Step through SUT_43 full-course HITL PNGs in stream-km order (Mac Preview).
#
# Usage (repo root, after export_hitl_chunks_sut43_full.sh):
#   ./04_Python_Scripts/spatial/open_hitl_review_sut43_full.sh
#   ./04_Python_Scripts/spatial/open_hitl_review_sut43_full.sh --from-chunk 25
#   ./04_Python_Scripts/spatial/open_hitl_review_sut43_full.sh --chunk-index 25
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

OUT_DIR="06_Visualizations/sut43_hitl_full"
FROM_CHUNK=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-chunk|--chunk-index)
      FROM_CHUNK="${2:-0}"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [--from-chunk N]"
      echo "Opens chunk_*.png files in $OUT_DIR sequentially (km 0.5 → 43)."
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "$OUT_DIR" ]]; then
  echo "Missing $OUT_DIR — run ./04_Python_Scripts/spatial/export_hitl_chunks_sut43_full.sh first" >&2
  exit 1
fi

mapfile -t CHUNKS < <(find "$OUT_DIR" -maxdepth 1 -name 'chunk_*.png' | sort)
if [[ ${#CHUNKS[@]} -eq 0 ]]; then
  echo "No chunk_*.png in $OUT_DIR — run export_hitl_chunks_sut43_full.sh first" >&2
  exit 1
fi

echo "SUT_43 full-course HITL review — ${#CHUNKS[@]} chunks in $OUT_DIR"
echo "Sector guide: config/spatial_terrain_sectors_sut43.json"
echo "Gold edits:   hitl.operator_gold_spans[] in sector JSON → re-merge full map"
echo ""

idx=0
for f in "${CHUNKS[@]}"; do
  base=$(basename "$f")
  chunk_num="${base#chunk_}"
  chunk_num="${chunk_num%%_*}"
  if [[ "$chunk_num" =~ ^[0-9]+$ ]] && (( chunk_num < FROM_CHUNK )); then
    continue
  fi
  echo "── [$((idx + 1))/${#CHUNKS[@]}] $base ──"
  if [[ "$(uname -s)" == "Darwin" ]] && command -v open >/dev/null 2>&1; then
    open "$f"
  else
    echo "  $f"
  fi
  read -r -p "Enter = next chunk · q = quit · e = edit sector note: " ans || true
  case "${ans,,}" in
    q|quit) echo "Stopped at $base"; exit 0 ;;
    e)
      read -r -p "  Note (logged only): " note
      echo "  note: ${note:-}" ;;
  esac
  idx=$((idx + 1))
done

echo "OK reviewed all chunks in $OUT_DIR"
