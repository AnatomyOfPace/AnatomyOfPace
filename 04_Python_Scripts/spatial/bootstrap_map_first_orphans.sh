#!/usr/bin/env bash
# Bootstrap all map-first orphan Subject_A courses (wash + panel).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
python3 04_Python_Scripts/spatial/bootstrap_map_first_orphan.py --all "$@"
