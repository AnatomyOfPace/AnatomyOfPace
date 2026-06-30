#!/usr/bin/env python3
"""
Pool multiple gold training parquets into one export with source_anchor traceability.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/merge_gold_training_sets.py \\
        --input 03_Processed_Data/spatial/gold_training_set_stavanger_halvmarathon.parquet \\
        --input 03_Processed_Data/spatial/gold_training_set_sunderunde.parquet \\
        --input 03_Processed_Data/spatial/gold_training_set_3_sjoerslopet.parquet \\
        --output 03_Processed_Data/spatial/gold_training_set_calibration_pool.parquet
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUTPUT = BASE_DIR / "03_Processed_Data" / "spatial" / "gold_training_set_calibration_pool.parquet"


def _source_anchor(path: Path) -> str:
    stem = path.stem
    prefix = "gold_training_set_"
    if stem.startswith(prefix):
        return stem[len(prefix) :]
    return stem


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge gold training parquets with source_anchor column.")
    parser.add_argument("--input", type=Path, action="append", required=True, dest="inputs")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-json", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    frames: list[pd.DataFrame] = []
    per_source: dict[str, dict[str, int]] = {}

    for path in args.inputs:
        if not path.exists():
            print(f"Input not found: {path}", file=sys.stderr)
            return 1
        anchor = _source_anchor(path)
        df = pd.read_parquet(path)
        df = df.copy()
        df["source_anchor"] = anchor
        frames.append(df)
        labeled = int(df["is_labeled"].sum())
        per_source[anchor] = {"rows": len(df), "labeled": labeled}

    pooled = pd.concat(frames, ignore_index=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pooled.to_parquet(args.output, index=False)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output": str(args.output),
        "total_rows": len(pooled),
        "total_labeled": int(pooled["is_labeled"].sum()),
        "sources": per_source,
        "inputs": [str(p) for p in args.inputs],
    }
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"Pooled {len(pooled)} rows from {len(args.inputs)} inputs → {args.output}")
    for anchor, counts in per_source.items():
        print(f"  {anchor}: {counts['rows']} rows ({counts['labeled']} labeled)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
