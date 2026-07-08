#!/usr/bin/env python3
"""
Verify map-first orphan HITL PNG exports (FIT GPS geography).

Usage:
    python3 04_Python_Scripts/spatial/verify_map_first_orphan_exports.py --course selvikstakken
    python3 04_Python_Scripts/spatial/verify_map_first_orphan_exports.py --all
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "04_Python_Scripts") not in sys.path:
    sys.path.insert(0, str(_REPO / "04_Python_Scripts"))

from spatial.map_first_orphan_registry import (  # noqa: E402
    get_orphan_course,
    hitl_dir,
    list_orphan_courses,
    panel_path,
    terrain_map_path,
)
from spatial.spatial_hitl_overlay import load_terrain_map  # noqa: E402
from spatial.validation_dashboard import resolve_axis_label  # noqa: E402


def _chunk_windows(km_end: float, chunk_km: float = 1.0) -> list[tuple[int, float, float]]:
    out: list[tuple[int, float, float]] = []
    lo = 0.0
    idx = 0
    while lo < km_end - 1e-9:
        hi = min(lo + chunk_km, km_end)
        out.append((idx, lo, hi))
        lo = hi
        idx += 1
    return out


def _gps_window(panel: pd.DataFrame, km_lo: float, km_hi: float) -> tuple[float, float, int]:
    sub = panel[(panel["course_km"] >= km_lo) & (panel["course_km"] <= km_hi)]
    lat = pd.to_numeric(sub["latitude"], errors="coerce")
    lon = pd.to_numeric(sub["longitude"], errors="coerce")
    valid = lat.notna() & lon.notna()
    if not valid.any():
        return float("nan"), float("nan"), 0
    return float(lat[valid].mean()), float(lon[valid].mean()), int(valid.sum())


def verify_course(race_id: str, *, strict: bool = False) -> int:
    course = get_orphan_course(race_id)
    panel_p = panel_path(race_id)
    tmap_p = terrain_map_path(race_id)
    out_dir = hitl_dir(race_id)
    manifest_p = out_dir / "EXPORT_MANIFEST.json"

    errors: list[str] = []
    warnings: list[str] = []

    if not panel_p.exists():
        errors.append(f"Panel missing: {panel_p} — run bootstrap_map_first_orphan.py --course {race_id}")
        for line in errors:
            print(f"FAIL {line}", file=sys.stderr)
        return 1

    tmap = load_terrain_map(tmap_p)
    panel = pd.read_parquet(panel_p)
    axis = resolve_axis_label(tmap, panel)
    rid = (tmap.get("corridor") or {}).get("race_id")

    print(f"=== {course.get('display_name')} HITL check ===")
    print(f"  race_id: {rid}")
    print(f"  axis:    {axis!r}")

    if axis.startswith("SUT_43"):
        errors.append("axis label is SUT_43 — check terrain map course_axis")
    if rid != race_id:
        errors.append(f"unexpected race_id {rid!r}")

    lat_all = pd.to_numeric(panel["latitude"], errors="coerce")
    lon_all = pd.to_numeric(panel["longitude"], errors="coerce")
    c_lat, c_lon = float(lat_all.mean()), float(lon_all.mean())
    print(f"  FIT GPS centroid: {c_lat:.5f}°N {c_lon:.5f}°E")

    km_end = float((tmap.get("corridor") or {}).get("km_end") or panel["course_km"].max())
    bad_chunks = 0
    for idx, lo, hi in _chunk_windows(km_end):
        clat, clon, n = _gps_window(panel, lo, hi)
        if n == 0 or math.isnan(clat):
            bad_chunks += 1
    if bad_chunks:
        warnings.append(f"{bad_chunks} chunk window(s) lack GPS samples")

    pngs = sorted(out_dir.glob("chunk_t*.png"))
    print(f"  OK GPS on all {len(_chunk_windows(km_end))} km windows" if not bad_chunks else f"  WARN {bad_chunks} windows missing GPS")
    print(f"  PNGs: {len(pngs)} in {out_dir.relative_to(_REPO)}")

    if strict and not manifest_p.exists():
        errors.append(f"EXPORT_MANIFEST.json missing: {manifest_p}")
    elif manifest_p.exists():
        meta = json.loads(manifest_p.read_text(encoding="utf-8"))
        print(f"  manifest: exported_at={meta.get('exported_at')}")

    for w in warnings:
        print(f"  WARN {w}")
    for e in errors:
        print(f"  FAIL {e}", file=sys.stderr)

    if errors:
        return 1
    print(f"\nOK {course.get('display_name')} HITL verified (trusting FIT GPS).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify orphan map-first HITL exports")
    parser.add_argument("--course", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    if args.all:
        targets = [c["race_id"] for c in list_orphan_courses()]
    elif args.course:
        targets = args.course
    else:
        parser.error("Pass --course RACE_ID or --all")

    rc = 0
    for race_id in targets:
        if verify_course(race_id, strict=args.strict):
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
