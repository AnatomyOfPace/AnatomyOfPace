#!/usr/bin/env python3
"""
Export per-metre training frame from panel + operator gold spans.

Output columns: course_km, features..., label_surface, label_friction, is_labeled.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/build_gold_training_set.py \\
        --km-start 29 --km-end 41 \\
        --output 03_Processed_Data/spatial/gold_training_set_sut43.parquet
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.gold_training_common import (
    DEFAULT_HMM_DRAFT,
    DEFAULT_PANEL,
    DEFAULT_TERRAIN_MAP,
    FEATURE_COLUMNS,
    build_training_frame,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUTPUT = BASE_DIR / "03_Processed_Data" / "spatial" / "gold_training_set_sut43.parquet"

EXPORT_COLUMNS = ["course_m", "course_km", *FEATURE_COLUMNS, "draft_class", "label_surface", "label_friction", "is_labeled"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build sparse-gold ML training export from panel + terrain map.")
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--terrain-map", type=Path, default=DEFAULT_TERRAIN_MAP)
    parser.add_argument(
        "--extra-terrain-map",
        type=Path,
        action="append",
        default=None,
        help="Additional terrain map(s) whose operator_gold_spans merge into labels",
    )
    parser.add_argument("--hmm-draft", type=Path, default=DEFAULT_HMM_DRAFT)
    parser.add_argument("--km-start", type=float, default=None, help="Optional course km lower bound (inclusive)")
    parser.add_argument("--km-end", type=float, default=None, help="Optional course km upper bound (exclusive)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--also-csv", action="store_true", help="Write sibling .csv alongside parquet")
    parser.add_argument("--summary-json", type=Path, default=None, help="Optional metadata JSON path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.panel.exists():
        print(f"Panel not found: {args.panel}", file=sys.stderr)
        return 1
    if not args.terrain_map.exists():
        print(f"Terrain map not found: {args.terrain_map}", file=sys.stderr)
        return 1

    frame = build_training_frame(
        panel_path=args.panel,
        terrain_map_path=args.terrain_map,
        extra_terrain_map_paths=args.extra_terrain_map,
        hmm_path=args.hmm_draft,
        km_lo=args.km_start,
        km_hi=args.km_end,
    )
    cols = [c for c in EXPORT_COLUMNS if c in frame.columns]
    out = frame[cols].copy()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.output, index=False)
    if args.also_csv:
        out.to_csv(args.output.with_suffix(".csv"), index=False)

    labeled = int(out["is_labeled"].sum())
    total = len(out)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "panel": str(args.panel),
        "terrain_map": str(args.terrain_map),
        "extra_terrain_maps": [str(p) for p in (args.extra_terrain_map or [])],
        "hmm_draft": str(args.hmm_draft),
        "km_start": args.km_start,
        "km_end": args.km_end,
        "total_metres": total,
        "labeled_metres": labeled,
        "unlabeled_metres": total - labeled,
        "labeled_pct": round(100.0 * labeled / total, 2) if total else 0.0,
        "label_surface_counts": out.loc[out["is_labeled"], "label_surface"].value_counts(dropna=False).to_dict(),
        "label_friction_counts": out.loc[out["is_labeled"], "label_friction"].value_counts(dropna=False).to_dict(),
        "feature_columns": [c for c in FEATURE_COLUMNS if c in out.columns],
        "output_parquet": str(args.output),
    }
    summary_path = args.summary_json or args.output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {total} row(s) ({labeled} labeled) → {args.output}")
    print(f"Summary → {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
