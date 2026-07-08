#!/usr/bin/env python3
"""
Verify Stavanger Halvmarathon O₁ asphalt-anchor HITL export — axis, GPS, PNG count.

Map-first FIT stream axis km 0–21.38 — not SUT_43 organiser GPX.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/verify_stavanger_halvmarathon_hitl_exports.py
    python3 04_Python_Scripts/spatial/verify_stavanger_halvmarathon_hitl_exports.py --strict
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

from spatial.spatial_hitl_overlay import load_terrain_map  # noqa: E402
from spatial.validation_dashboard import resolve_axis_label  # noqa: E402

PANEL = _REPO / "03_Processed_Data" / "spatial" / "stavanger_halvmarathon_course" / "panel_1m.parquet"
TERRAIN_MAP = _REPO / "config" / "spatial_terrain_map_stavanger_halvmarathon.json"
OUT_DIR = _REPO / "06_Visualizations" / "stavanger_halvmarathon_hitl"
MANIFEST = OUT_DIR / "EXPORT_MANIFEST.json"

ROGALAND_LAT_MIN = 58.75
ROGALAND_LAT_MAX = 59.10
ROGALAND_LON_MIN = 5.50
ROGALAND_LON_MAX = 5.95
USKEDALEN_LAT_MIN = 59.0


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Stavanger Halvmarathon HITL export")
    parser.add_argument("--strict", action="store_true", help="Fail when PNG count mismatches km_end")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []

    if not PANEL.exists():
        errors.append(
            f"Panel missing: {PANEL} — rebuild via corridor_multi_fit.py "
            "(config/spatial_align_manifest_stavanger_halvmarathon.json)"
        )
        for line in errors:
            print(f"FAIL {line}", file=sys.stderr)
        return 1

    tmap = load_terrain_map(TERRAIN_MAP)
    panel = pd.read_parquet(PANEL)
    axis = resolve_axis_label(tmap, panel)
    race_id = (tmap.get("corridor") or {}).get("race_id")

    print("=== Stavanger Halvmarathon HITL check (O₁ asphalt anchor) ===")
    print(f"  race_id: {race_id}")
    print(f"  axis:    {axis!r}")

    if axis.startswith("SUT_43"):
        errors.append("axis label is SUT_43 — use map-first stream axis")
    if race_id != "stavanger_halvmarathon":
        errors.append(f"unexpected race_id {race_id!r}")

    lat_all = pd.to_numeric(panel["latitude"], errors="coerce")
    lon_all = pd.to_numeric(panel["longitude"], errors="coerce")
    valid = lat_all.notna() & lon_all.notna()
    if not valid.any():
        errors.append("panel has no valid GPS — check FIT wash")
    else:
        c_lat, c_lon = float(lat_all[valid].mean()), float(lon_all[valid].mean())
        print(f"  FIT GPS centroid: {c_lat:.5f}°N {c_lon:.5f}°E")
        if c_lat >= USKEDALEN_LAT_MIN:
            errors.append(f"centroid {c_lat:.4f}°N looks like Uskedalen — not Stavanger/Rogaland")
        if not (ROGALAND_LAT_MIN <= c_lat <= ROGALAND_LAT_MAX):
            warnings.append(f"centroid lat {c_lat:.4f} outside expected Rogaland band")
        if not (ROGALAND_LON_MIN <= c_lon <= ROGALAND_LON_MAX):
            warnings.append(f"centroid lon {c_lon:.4f} outside expected Rogaland band")

    km_end = float((tmap.get("corridor") or {}).get("km_end") or panel["course_km"].max())
    no_gps: list[str] = []
    for idx, km_lo, km_hi in _chunk_windows(km_end):
        clat, clon, n = _gps_window(panel, km_lo, km_hi)
        if not math.isfinite(clat) or n == 0:
            no_gps.append(f"chunk {idx:02d} km {km_lo:.0f}-{km_hi:.1f}: no GPS")
        elif clat >= USKEDALEN_LAT_MIN:
            no_gps.append(
                f"chunk {idx:02d} km {km_lo:.0f}-{km_hi:.1f}: {clat:.4f}°N — Uskedalen (wrong course)"
            )

    if no_gps:
        errors.extend(no_gps)
    else:
        print(f"  OK GPS on all {len(_chunk_windows(km_end))} km windows")

    pngs = sorted(OUT_DIR.glob("chunk_t*.png"))
    expected = len(_chunk_windows(km_end))
    print(f"  PNGs: {len(pngs)} (expected ~{expected}) in {OUT_DIR.relative_to(_REPO)}")
    if args.strict and len(pngs) < expected:
        errors.append(f"expected at least {expected} chunk PNGs, found {len(pngs)}")

    if MANIFEST.exists():
        meta = json.loads(MANIFEST.read_text(encoding="utf-8"))
        print(f"  manifest: exported_at={meta.get('exported_at')}")

    for w in warnings:
        print(f"WARN {w}")
    for e in errors:
        print(f"FAIL {e}", file=sys.stderr)

    if errors:
        return 1
    print("\nOK Stavanger Halvmarathon HITL verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
