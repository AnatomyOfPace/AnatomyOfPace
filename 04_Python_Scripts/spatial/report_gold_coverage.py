#!/usr/bin/env python3
"""
Report operator gold coverage gaps on map-first courses.

Maps unlabeled km intervals to HITL chunk PNG indices for operator labeling.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/report_gold_coverage.py \\
        --terrain-map config/spatial_terrain_map_gramstad_runde.json

    python3 04_Python_Scripts/spatial/report_gold_coverage.py \\
        --terrain-map config/spatial_terrain_map_gramstad_runde.json \\
        --json 03_Processed_Data/spatial/gramstad_runde_gold_gaps.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.gold_training_common import attach_gold_labels, resolve_gold_training_defaults
from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.suggest_gold_spans import ungolded_intervals
from spatial.validation_dashboard import operator_gold_spans

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _chunk_index(km: float, chunk_km: float = 1.0) -> int:
    return max(0, int(km // chunk_km))


def _chunk_label(idx: int, km_lo: float, km_hi: float) -> str:
    return f"chunk_t{idx:02d}_km{int(km_lo)}-{km_hi:.0f}"


def _panel_extent(panel_path: Path) -> tuple[float, float]:
    panel = pd.read_parquet(panel_path)
    if "course_km" not in panel.columns and "ref_chainage_m" in panel.columns:
        panel = panel.copy()
        panel["course_km"] = panel["ref_chainage_m"] / 1000.0
    return float(panel["course_km"].min()), float(panel["course_km"].max())


def report_coverage(
    terrain_map_path: Path,
    *,
    panel_path: Path | None = None,
    km_start: float | None = None,
    km_end: float | None = None,
    chunk_km: float = 1.0,
    hitl_dir: Path | None = None,
) -> dict[str, Any]:
    terrain_map_path = terrain_map_path if terrain_map_path.is_absolute() else BASE_DIR / terrain_map_path
    tmap = load_terrain_map(terrain_map_path)
    corridor = tmap.get("corridor") or {}
    race_id = str(corridor.get("race_id") or terrain_map_path.stem.replace("spatial_terrain_map_", ""))

    resolved = resolve_gold_training_defaults(terrain_map_path)
    if panel_path is None:
        panel_path = resolved.get("panel") if resolved else None
    if panel_path is None:
        panel_path = BASE_DIR / "03_Processed_Data" / "spatial" / f"{race_id}_course" / "panel_1m.parquet"
    panel_path = panel_path if panel_path.is_absolute() else BASE_DIR / panel_path

    if km_start is None:
        km_start = float(corridor.get("km_start") or 0.0)
    if km_end is None:
        km_end = float(corridor.get("km_end") or 0.0)
    if panel_path.exists():
        panel_lo, panel_hi = _panel_extent(panel_path)
        if km_end <= km_start + 1e-6:
            km_start, km_end = panel_lo, panel_hi
        else:
            km_end = min(km_end, panel_hi)

    gold_spans = operator_gold_spans(tmap)
    gaps = ungolded_intervals(km_start, km_end, gold_spans)
    total_m = max(0.0, (km_end - km_start) * 1000.0)
    unlabeled_m = sum((b - a) * 1000.0 for a, b in gaps)
    labeled_m = total_m - unlabeled_m

    gap_rows: list[dict[str, Any]] = []
    chunks_touched: set[int] = set()
    for gap_lo, gap_hi in gaps:
        idx_lo = _chunk_index(gap_lo, chunk_km)
        idx_hi = _chunk_index(max(gap_lo, gap_hi - 1e-6), chunk_km)
        for idx in range(idx_lo, idx_hi + 1):
            chunks_touched.add(idx)
        png_hint = _chunk_label(idx_lo, gap_lo, gap_hi)
        if hitl_dir is None:
            hitl_dir_rel = f"06_Visualizations/{race_id}_hitl"
        else:
            hitl_dir_rel = str(hitl_dir.relative_to(BASE_DIR) if hitl_dir.is_absolute() else hitl_dir)
        gap_rows.append(
            {
                "km_start": round(gap_lo, 3),
                "km_end": round(gap_hi, 3),
                "length_m": round((gap_hi - gap_lo) * 1000.0, 1),
                "chunk_index_start": idx_lo,
                "chunk_index_end": idx_hi,
                "png_hint": png_hint,
                "hitl_png_glob": f"{hitl_dir_rel}/chunk_t*.png",
            }
        )

    labeled_from_panel: int | None = None
    if panel_path.exists():
        panel = pd.read_parquet(panel_path)
        if "course_km" not in panel.columns and "ref_chainage_m" in panel.columns:
            panel = panel.copy()
            panel["course_km"] = panel["ref_chainage_m"] / 1000.0
        sub = panel[(panel["course_km"] >= km_start) & (panel["course_km"] < km_end)]
        labeled = attach_gold_labels(sub, gold_spans)
        labeled_from_panel = int(labeled["is_labeled"].sum())

    return {
        "race_id": race_id,
        "terrain_map": str(terrain_map_path.relative_to(BASE_DIR)),
        "panel": str(panel_path.relative_to(BASE_DIR)) if panel_path.is_relative_to(BASE_DIR) else str(panel_path),
        "km_start": km_start,
        "km_end": km_end,
        "total_metres": int(round(total_m)),
        "labeled_metres_span_math": int(round(labeled_m)),
        "labeled_metres_panel": labeled_from_panel,
        "unlabeled_metres": int(round(unlabeled_m)),
        "labeled_pct": round(100.0 * labeled_m / total_m, 2) if total_m else 100.0,
        "operator_gold_spans": len(gold_spans),
        "gap_count": len(gap_rows),
        "chunks_to_review": sorted(chunks_touched),
        "gaps": gap_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Report operator gold coverage gaps")
    parser.add_argument("--terrain-map", type=Path, required=True)
    parser.add_argument("--panel", type=Path, default=None)
    parser.add_argument("--km-start", type=float, default=None)
    parser.add_argument("--km-end", type=float, default=None)
    parser.add_argument("--chunk-km", type=float, default=1.0)
    parser.add_argument("--hitl-dir", type=Path, default=None)
    parser.add_argument("--json", type=Path, default=None, help="Write machine-readable report")
    args = parser.parse_args()

    if not args.terrain_map.exists():
        print(f"Terrain map not found: {args.terrain_map}", file=sys.stderr)
        return 1

    report = report_coverage(
        args.terrain_map,
        panel_path=args.panel,
        km_start=args.km_start,
        km_end=args.km_end,
        chunk_km=args.chunk_km,
        hitl_dir=args.hitl_dir,
    )

    print(f"=== Gold coverage: {report['race_id']} ===")
    print(f"  terrain map: {report['terrain_map']}")
    print(f"  panel:       {report['panel']}")
    print(f"  window:      km {report['km_start']:.3f}–{report['km_end']:.3f}")
    print(f"  spans:       {report['operator_gold_spans']}")
    print(f"  labeled:     {report['labeled_metres_span_math']} m ({report['labeled_pct']:.1f}%)")
    if report["labeled_metres_panel"] is not None:
        print(f"  panel check: {report['labeled_metres_panel']} labeled rows in panel window")
    print(f"  unlabeled:   {report['unlabeled_metres']} m across {report['gap_count']} gap(s)")

    if report["gaps"]:
        print("\n  Gaps (review these PNG chunks):")
        for gap in report["gaps"]:
            chunks = gap["chunk_index_start"]
            if gap["chunk_index_end"] != gap["chunk_index_start"]:
                chunk_range = f"t{gap['chunk_index_start']:02d}–t{gap['chunk_index_end']:02d}"
            else:
                chunk_range = f"t{gap['chunk_index_start']:02d}"
            print(
                f"    km {gap['km_start']:.3f}–{gap['km_end']:.3f} "
                f"({gap['length_m']:.0f} m) → chunk_{chunk_range}"
            )
    else:
        print("\n  OK full coverage — no gaps in window")

    if args.json:
        out = args.json if args.json.is_absolute() else BASE_DIR / args.json
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {out.relative_to(BASE_DIR)}")

    return 0 if report["unlabeled_metres"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
