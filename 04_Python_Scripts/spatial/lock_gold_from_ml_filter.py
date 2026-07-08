#!/usr/bin/env python3
"""
Lock operator gold spans from per-metre ML predictions with surface filtering.

Keeps ML surface/friction where pred_class is in a keep-set; otherwise applies
a default surface (and friction) for trail-heavy labeling workflows.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/lock_gold_from_ml_filter.py \\
        --terrain-map config/spatial_terrain_map_gjesdal_terrenglop_kongeparken.json \\
        --km-start 1.0 --km-end 2.0 \\
        --keep-surface S3 S4 S5 \\
        --else-surface S3 --else-friction F2 \\
        --dry-run

    python3 04_Python_Scripts/spatial/lock_gold_from_ml_filter.py \\
        --terrain-map config/spatial_terrain_map_gjesdal_terrenglop_kongeparken.json \\
        --km-start 1.0 --km-end 2.0 \\
        --keep-surface S3 S4 S5 --else-surface S3 --else-friction F2
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.gold_span_editor import find_overlapping_spans, write_terrain_map
from spatial.gold_training_common import span_km_bounds, spans_overlap
from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.validation_dashboard import operator_gold_spans, resolve_map_first_ml_predictions_path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
KM_EPS = 1e-6


def _coalesce_spans(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    ordered = sorted(rows, key=lambda r: (float(r["course_km_start"]), float(r["course_km_end"])))
    merged: list[dict[str, Any]] = []
    for row in ordered:
        if (
            merged
            and merged[-1]["surface_class"] == row["surface_class"]
            and merged[-1]["friction_tier"] == row["friction_tier"]
            and abs(float(merged[-1]["course_km_end"]) - float(row["course_km_start"])) <= KM_EPS
        ):
            merged[-1]["course_km_end"] = row["course_km_end"]
            reason = row.get("reason", "")
            if reason:
                prev = merged[-1].get("reason", "")
                merged[-1]["reason"] = f"{prev}; {reason}".strip("; ")
        else:
            merged.append(dict(row))
    return merged


def build_filtered_spans(
    pred: pd.DataFrame,
    *,
    km_start: float,
    km_end: float,
    keep_surfaces: set[str],
    else_surface: str,
    else_friction: str,
    reason_prefix: str,
) -> list[dict[str, Any]]:
    work = pred.copy()
    work["course_km"] = pd.to_numeric(work["course_km"], errors="coerce")
    work = work[(work["course_km"] >= km_start - KM_EPS) & (work["course_km"] <= km_end + KM_EPS)]
    work = work.sort_values("course_km").reset_index(drop=True)
    if work.empty:
        raise ValueError(f"No ML predictions in km {km_start}–{km_end}")

    rows: list[dict[str, Any]] = []
    locked_at = date.today().isoformat()
    for i, row in work.iterrows():
        km_lo = float(row["course_km"])
        km_hi = km_lo + 0.001
        if i + 1 < len(work):
            km_hi = float(work.iloc[i + 1]["course_km"])
        else:
            km_hi = min(km_end, km_lo + 0.001)

        pred_surf = str(row.get("pred_class") or row.get("pred_surface") or "").strip()
        pred_fric = str(row.get("pred_friction") or "").strip()
        if pred_surf in keep_surfaces:
            surf = pred_surf
            fric = pred_fric if pred_fric in {"F0", "F1", "F2", "F3", "F4"} else else_friction
            note = f"{reason_prefix}: keep ML {pred_surf}/{pred_fric} @ {km_lo:.3f}"
        else:
            surf, fric = else_surface, else_friction
            note = f"{reason_prefix}: ML {pred_surf or '?'} → {surf}/{fric} @ {km_lo:.3f}"

        rows.append(
            {
                "course_km_start": round(km_lo, 3),
                "course_km_end": round(km_hi, 3),
                "surface_class": surf,
                "friction_tier": fric,
                "gold_source": "operator",
                "mode": "operator_gold",
                "locked_at": locked_at,
                "reason": note,
            }
        )

    return _coalesce_spans(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Lock gold spans from ML predictions with surface filter")
    parser.add_argument("--terrain-map", type=Path, required=True)
    parser.add_argument("--ml-predictions", type=Path, default=None)
    parser.add_argument("--km-start", type=float, required=True)
    parser.add_argument("--km-end", type=float, required=True)
    parser.add_argument(
        "--keep-surface",
        nargs="+",
        default=["S3", "S4", "S5"],
        help="Keep ML surface+friction when pred_class is in this set",
    )
    parser.add_argument("--else-surface", default="S3", help="Surface when ML pred not in keep-set")
    parser.add_argument("--else-friction", default="F2", help="Friction when ML pred not in keep-set")
    parser.add_argument("--reason", default="ML filter lock", help="Reason prefix on spans")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    terrain_map_path = args.terrain_map if args.terrain_map.is_absolute() else BASE_DIR / args.terrain_map
    tmap = load_terrain_map(terrain_map_path)
    corridor = tmap.get("corridor") or {}
    race_id = str(corridor.get("race_id") or "")
    panel_path = BASE_DIR / "03_Processed_Data" / "spatial" / f"{race_id}_course" / "panel_1m.parquet"

    if args.ml_predictions is not None:
        ml_path = args.ml_predictions if args.ml_predictions.is_absolute() else BASE_DIR / args.ml_predictions
    else:
        ml_path = resolve_map_first_ml_predictions_path(panel_path, tmap)
    if ml_path is None or not ml_path.exists():
        print(f"ML predictions not found for {race_id}: {ml_path}", file=sys.stderr)
        return 1

    pred = pd.read_parquet(ml_path)
    keep = {s.upper() for s in args.keep_surface}
    new_spans = build_filtered_spans(
        pred,
        km_start=float(args.km_start),
        km_end=float(args.km_end),
        keep_surfaces=keep,
        else_surface=str(args.else_surface).upper(),
        else_friction=str(args.else_friction).upper(),
        reason_prefix=str(args.reason).strip(),
    )

    existing = operator_gold_spans(tmap)
    for span in new_spans:
        s0, s1 = span_km_bounds(span)
        if find_overlapping_spans(existing, s0, s1):
            print(
                f"Error: new span km {s0:.3f}–{s1:.3f} overlaps existing gold — "
                "clear-window first or narrow km range",
                file=sys.stderr,
            )
            return 1

    print(f"ML source: {ml_path.relative_to(BASE_DIR) if ml_path.is_relative_to(BASE_DIR) else ml_path}")
    print(f"Window km {args.km_start}–{args.km_end} | keep {sorted(keep)} | else {args.else_surface}/{args.else_friction}")
    print(f"Spans to add: {len(new_spans)}")
    for span in new_spans:
        s0, s1 = span_km_bounds(span)
        print(f"  km {s0:.3f}–{s1:.3f}  {span['surface_class']}/{span['friction_tier']}")

    if args.dry_run:
        print(json.dumps(new_spans, indent=2))
        return 0

    hitl = tmap.setdefault("hitl", {})
    spans: list[dict[str, Any]] = list(hitl.get("operator_gold_spans") or [])
    spans.extend(new_spans)
    spans.sort(key=lambda s: span_km_bounds(s)[0])
    hitl["operator_gold_spans"] = spans
    write_terrain_map(terrain_map_path, tmap)
    mirror = terrain_map_path.with_name(f"{terrain_map_path.stem}.gold_local.json")
    print(f"OK appended {len(new_spans)} span(s) → {terrain_map_path.name}")
    print(f"Mirror → {mirror}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
