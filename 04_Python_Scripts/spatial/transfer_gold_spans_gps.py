#!/usr/bin/env python3
"""
Transfer operator gold spans across course axes via GPS nearest-neighbour.

Use when map-first stream km (gramstad_runde) overlaps geography already labeled
on SUT_43 gramstad_band (organiser km 29–41) or another source panel.

Does not copy km breakpoints — remaps surface/friction by matching each target
panel metre to the nearest labeled source GPS point.

Usage (after gramstad_runde bootstrap):

    python3 04_Python_Scripts/spatial/transfer_gold_spans_gps.py \\
        --source-terrain-map config/spatial_terrain_map_sut43.json \\
        --source-panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet \\
        --source-km-start 29 --source-km-end 41 \\
        --target-terrain-map config/spatial_terrain_map_gramstad_runde.json \\
        --target-panel 03_Processed_Data/spatial/gramstad_runde_course/panel_1m.parquet \\
        --dry-run

Prefer local gold backup when present:

    --source-terrain-map config/spatial_terrain_map_sut43.gold_local.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.gold_span_editor import write_terrain_map  # noqa: E402
from spatial.gold_training_common import attach_gold_labels, span_km_bounds  # noqa: E402
from spatial.spatial_hitl_overlay import load_terrain_map  # noqa: E402
from spatial.validation_dashboard import operator_gold_spans  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _haversine_m(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    r = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _load_panel_window(path: Path, km_lo: float | None, km_hi: float | None) -> pd.DataFrame:
    panel = pd.read_parquet(path)
    if "course_km" not in panel.columns and "ref_chainage_m" in panel.columns:
        panel = panel.copy()
        panel["course_km"] = panel["ref_chainage_m"] / 1000.0
    if km_lo is not None and km_hi is not None:
        panel = panel[(panel["course_km"] >= km_lo) & (panel["course_km"] <= km_hi)].copy()
    return panel.sort_values("course_km").reset_index(drop=True)


def _labeled_source_points(
    panel: pd.DataFrame,
    gold_spans: list[dict[str, Any]],
) -> pd.DataFrame:
    labeled = attach_gold_labels(panel, gold_spans)
    lat = pd.to_numeric(labeled["latitude"], errors="coerce")
    lon = pd.to_numeric(labeled["longitude"], errors="coerce")
    ok = labeled["is_labeled"] & lat.notna() & lon.notna()
    return labeled.loc[ok, ["course_km", "latitude", "longitude", "label_surface", "label_friction"]].copy()


def _match_labels(
    target: pd.DataFrame,
    source: pd.DataFrame,
    *,
    max_match_m: float,
) -> pd.DataFrame:
    out = target.copy()
    out["label_surface"] = None
    out["label_friction"] = None
    out["match_dist_m"] = np.nan

    t_lat = pd.to_numeric(out["latitude"], errors="coerce").to_numpy(dtype=float)
    t_lon = pd.to_numeric(out["longitude"], errors="coerce").to_numpy(dtype=float)
    s_lat = source["latitude"].to_numpy(dtype=float)
    s_lon = source["longitude"].to_numpy(dtype=float)

    valid_t = np.isfinite(t_lat) & np.isfinite(t_lon)
    if not valid_t.any() or source.empty:
        out["is_labeled"] = False
        return out

    # Chunked NN — panels are ~10–25k rows; brute force per target row is fine.
    for idx in np.where(valid_t)[0]:
        dist = _haversine_m(
            np.array([t_lat[idx]]),
            np.array([t_lon[idx]]),
            s_lat,
            s_lon,
        )
        j = int(np.argmin(dist))
        d = float(dist[j])
        if d <= max_match_m:
            out.at[out.index[idx], "label_surface"] = source.iloc[j]["label_surface"]
            out.at[out.index[idx], "label_friction"] = source.iloc[j]["label_friction"]
            out.at[out.index[idx], "match_dist_m"] = d

    out["is_labeled"] = out["label_surface"].notna()
    return out


def _consolidate_spans(
    labeled: pd.DataFrame,
    *,
    min_span_m: float = 15.0,
    gap_tol_m: float = 3.0,
) -> list[dict[str, Any]]:
    """Merge contiguous target-axis metres with identical surface/friction."""
    work = labeled[labeled["is_labeled"]].sort_values("course_km")
    if work.empty:
        return []

    if "course_m" not in work.columns:
        work = work.copy()
        work["course_m"] = work["course_km"] * 1000.0

    spans: list[tuple[float, float, str, str]] = []
    cur_surf = None
    cur_fric = None
    km_start: float | None = None
    km_end: float | None = None
    prev_m: float | None = None

    def _flush() -> None:
        nonlocal km_start, km_end, cur_surf, cur_fric
        if km_start is None or cur_surf is None or cur_fric is None or km_end is None:
            return
        if (km_end - km_start) * 1000.0 >= min_span_m:
            spans.append((km_start, km_end, cur_surf, cur_fric))

    for row in work.itertuples(index=False):
        surf = getattr(row, "label_surface")
        fric = getattr(row, "label_friction")
        km = float(row.course_km)
        cm = float(row.course_m)
        if cur_surf is None:
            cur_surf, cur_fric = surf, fric
            km_start, km_end = km, km
            prev_m = cm
            continue
        gap = cm - float(prev_m)
        if surf == cur_surf and fric == cur_fric and gap <= gap_tol_m:
            km_end = km
            prev_m = cm
            continue
        _flush()
        cur_surf, cur_fric = surf, fric
        km_start, km_end = km, km
        prev_m = cm

    _flush()

    locked_at = date.today().isoformat()
    return [
        {
            "course_km_start": round(s0, 3),
            "course_km_end": round(s1, 3),
            "surface_class": sc,
            "friction_tier": ft,
            "gold_source": "gps_transfer",
            "mode": "operator_gold",
            "locked_at": locked_at,
            "reason": f"GPS transfer from source gold ({locked_at})",
        }
        for s0, s1, sc, ft in spans
    ]


def transfer_gold_spans_gps(
    *,
    source_terrain_map: Path,
    source_panel: Path,
    target_terrain_map: Path,
    target_panel: Path,
    source_km_start: float | None = None,
    source_km_end: float | None = None,
    max_match_m: float = 35.0,
    min_span_m: float = 15.0,
    replace: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    src_map = load_terrain_map(source_terrain_map)
    gold = list(operator_gold_spans(src_map))
    if not gold:
        raise ValueError(f"No operator_gold_spans in {source_terrain_map}")

    src_panel = _load_panel_window(source_panel, source_km_start, source_km_end)
    src_pts = _labeled_source_points(src_panel, gold)
    if src_pts.empty:
        raise ValueError("No labeled source GPS points — check source panel path and km window")

    tgt_panel = _load_panel_window(target_panel, None, None)
    matched = _match_labels(tgt_panel, src_pts, max_match_m=max_match_m)
    new_spans = _consolidate_spans(matched, min_span_m=min_span_m)

    n_tgt = len(tgt_panel)
    n_matched = int(matched["is_labeled"].sum())
    report = {
        "source_terrain_map": str(source_terrain_map),
        "source_panel": str(source_panel),
        "source_gold_spans": len(gold),
        "source_labeled_points": len(src_pts),
        "target_panel": str(target_panel),
        "target_rows": n_tgt,
        "target_labeled_metres": n_matched,
        "target_labeled_pct": round(100.0 * n_matched / max(n_tgt, 1), 1),
        "transferred_spans": len(new_spans),
        "max_match_m": max_match_m,
        "mean_match_m": round(float(matched.loc[matched["is_labeled"], "match_dist_m"].mean()), 2)
        if n_matched
        else None,
    }

    if dry_run:
        report["spans_preview"] = new_spans[:12]
        return report

    tgt_map = load_terrain_map(target_terrain_map)
    hitl = tgt_map.setdefault("hitl", {})
    if replace:
        hitl["operator_gold_spans"] = new_spans
    else:
        existing = list(hitl.get("operator_gold_spans") or [])
        hitl["operator_gold_spans"] = existing + new_spans
    write_terrain_map(target_terrain_map, tgt_map)
    report["written_to"] = str(target_terrain_map)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="GPS-transfer operator gold spans across course axes")
    parser.add_argument("--source-terrain-map", type=Path, required=True)
    parser.add_argument("--source-panel", type=Path, required=True)
    parser.add_argument("--source-km-start", type=float, default=None)
    parser.add_argument("--source-km-end", type=float, default=None)
    parser.add_argument("--target-terrain-map", type=Path, required=True)
    parser.add_argument("--target-panel", type=Path, required=True)
    parser.add_argument("--max-match-m", type=float, default=35.0, help="Max GPS match radius (default 35 m)")
    parser.add_argument("--min-span-m", type=float, default=15.0)
    parser.add_argument("--append", action="store_true", help="Append spans instead of replacing")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    for p in (args.source_terrain_map, args.source_panel, args.target_terrain_map, args.target_panel):
        if not p.exists():
            print(f"Not found: {p}", file=sys.stderr)
            return 1

    try:
        report = transfer_gold_spans_gps(
            source_terrain_map=args.source_terrain_map,
            source_panel=args.source_panel,
            target_terrain_map=args.target_terrain_map,
            target_panel=args.target_panel,
            source_km_start=args.source_km_start,
            source_km_end=args.source_km_end,
            max_match_m=args.max_match_m,
            min_span_m=args.min_span_m,
            replace=not args.append,
            dry_run=args.dry_run,
        )
    except ValueError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2))
    if args.dry_run:
        print("\nDry run — re-run without --dry-run to write spans.")
    else:
        print(f"\nOK wrote {report['transferred_spans']} span(s) → {args.target_terrain_map}")
        print("Review on PNGs, then adjust with gold_span_editor.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
