#!/usr/bin/env bash
# Portfolio operator-gold audit — all terrain maps before publication / TRF re-run.
#
# Usage (repo root):
#   ./04_Python_Scripts/spatial/audit_operator_gold_portfolio.sh
#   ./04_Python_Scripts/spatial/audit_operator_gold_portfolio.sh --fail-on-gaps
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

python3 04_Python_Scripts/spatial/audit_operator_gold_portfolio.py \
  --json "03_Processed_Data/spatial/gold_portfolio_audit.json" \
  "$@"
