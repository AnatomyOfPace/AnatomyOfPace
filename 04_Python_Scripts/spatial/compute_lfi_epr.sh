#!/usr/bin/env bash
# LFI EPR — Subject_A vs Reference_Elite_A on race_corridors.json sub-corridors.
#
# Prerequisites:
#   03_Processed_Data/micro/Subject_A/activity_LFI_20260606.parquet
#   03_Processed_Data/micro/Reference_Elite_A/activity_18815539842.parquet
#
# Usage (repo root):
#   ./04_Python_Scripts/spatial/compute_lfi_epr.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

ATHLETE="03_Processed_Data/micro/Subject_A/activity_LFI_20260606.parquet"
ELITE="03_Processed_Data/micro/Reference_Elite_A/activity_18815539842.parquet"

if [[ ! -f "$ATHLETE" ]]; then
  echo "Missing Subject_A LFI micro parquet: $ATHLETE" >&2
  echo "  Wash: python3 04_Python_Scripts/15_fit_micro_wash.py --donor Subject_A --activity LFI_20260606 --fit <path> --race LFI --project-course --enrich-ti" >&2
  exit 1
fi
if [[ ! -f "$ELITE" ]]; then
  echo "Missing Reference_Elite_A micro parquet: $ELITE" >&2
  exit 1
fi

echo "=== LFI EPR (Subject_A vs Reference_Elite_A) ==="
python3 04_Python_Scripts/spatial/compute_lfi_epr.py "$@"
