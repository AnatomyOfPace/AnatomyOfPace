#!/usr/bin/env python3
"""
Verify Klepp Runde HITL PNG folder uses Uskedalen FIT GPS.

Klepp is a very local place name in Uskedalen (~59.9°N, ~5.9°E) — not Klepp
municipality in Rogaland/Jæren (~58.77°N, ~5.63°E).

Usage (from repo root):
    python3 04_Python_Scripts/spatial/verify_klepp_runde_hitl_exports.py
    python3 04_Python_Scripts/spatial/verify_klepp_runde_hitl_exports.py --strict
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

PANEL = _REPO / "03_Processed_Data" / "spatial" / "klepp_runde_course" / "panel_1m.parquet"
TERRAIN_MAP = _REPO / "config" / "spatial_terrain_map_klepp_runde.json"
OUT_DIR = _REPO / "06_Visualizations" / "klepp_runde_hitl"
MANIFEST = OUT_DIR / "EXPORT_MANIFEST.json"

# Uskedalen band — Klepp Runde local loop (near Tverrfjell).
USKEDALEN_LAT_MIN = 59.86
USKEDALEN_LAT_MAX = 59.95
USKEDALEN_LON_MIN = 5.88
USKEDALEN_LON_MAX = 6.02
# Rogaland homonym — wrong course if centroid lands here.
ROGALAND_KLEPP_LAT_MAX = 59.0


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
    parser = argparse.ArgumentParser(description="Verify Klepp Runde HITL export geography")
    parser.add_argument("--strict", action="store_true", help="Fail if EXPORT_MANIFEST.json missing")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []

    if not PANEL.exists():
        errors.append(f"Panel missing: {PANEL} — run bootstrap_klepp_runde_course.py")
        for line in errors:
            print(f"FAIL {line}", file=sys.stderr)
        return 1

    tmap = load_terrain_map(TERRAIN_MAP)
    panel = pd.read_parquet(PANEL)
    axis = resolve_axis_label(tmap, panel)
    race_id = (tmap.get("corridor") or {}).get("race_id")

    print("=== Klepp Runde HITL geography check ===")
    print(f"  race_id: {race_id}")
    print(f"  axis:    {axis!r}")

    if axis.startswith("SUT_43"):
        errors.append("axis label is SUT_43 — check terrain map course_axis")
    if race_id != "klepp_runde":
        errors.append(f"unexpected race_id {race_id!r}")

    lat_all = pd.to_numeric(panel["latitude"], errors="coerce")
    lon_all = pd.to_numeric(panel["longitude"], errors="coerce")
    c_lat, c_lon = float(lat_all.mean()), float(lon_all.mean())
    print(f"  panel centroid: {c_lat:.5f}°N {c_lon:.5f}°E")

    if c_lat < ROGALAND_KLEPP_LAT_MAX:
        errors.append(
            f"panel centroid {c_lat:.4f}°N looks like Rogaland Jæren "
            "(Klepp municipality homonym — not Uskedalen Klepp)"
        )
    if not (USKEDALEN_LAT_MIN <= c_lat <= USKEDALEN_LAT_MAX):
        warnings.append(f"panel centroid lat {c_lat:.4f} outside expected Uskedalen Klepp band")
    if not (USKEDALEN_LON_MIN <= c_lon <= USKEDALEN_LON_MAX):
        warnings.append(f"panel centroid lon {c_lon:.4f} outside expected Uskedalen Klepp band")

    km_end = float((tmap.get("corridor") or {}).get("km_end") or panel["course_km"].max())
    bad_chunks: list[str] = []
    for idx, km_lo, km_hi in _chunk_windows(km_end):
        clat, clon, _n = _gps_window(panel, km_lo, km_hi)
        if not math.isfinite(clat):
            bad_chunks.append(f"chunk {idx:02d} km {km_lo:.0f}-{km_hi:.1f}: no GPS")
            continue
        if clat < ROGALAND_KLEPP_LAT_MAX:
            bad_chunks.append(
                f"chunk {idx:02d} km {km_lo:.0f}-{km_hi:.1f}: "
                f"{clat:.4f}°N — Rogaland Jæren (wrong course)"
            )

    if bad_chunks:
        errors.extend(bad_chunks)
    else:
        print(f"  OK all {len(_chunk_windows(km_end))} chunk GPS windows in Uskedalen Klepp band")

    pngs = sorted(OUT_DIR.glob("chunk_t*.png"))
    print(f"  PNGs: {len(pngs)} in {OUT_DIR.relative_to(_REPO)}")

    if MANIFEST.exists():
        meta = json.loads(MANIFEST.read_text(encoding="utf-8"))
        print(f"  manifest: exported_at={meta.get('exported_at')} basemap={meta.get('basemap')}")
    elif args.strict:
        errors.append(f"missing {MANIFEST.relative_to(_REPO)} — re-run export_hitl_chunks_klepp_runde.sh")

    for w in warnings:
        print(f"WARN {w}")
    for e in errors:
        print(f"FAIL {e}", file=sys.stderr)

    if errors:
        print("\nRemedy:", file=sys.stderr)
        print("  ./04_Python_Scripts/spatial/bootstrap_klepp_runde_course.py --fit <your.fit>", file=sys.stderr)
        print("  ./04_Python_Scripts/spatial/export_hitl_chunks_klepp_runde.sh", file=sys.stderr)
        return 1

    print("\nOK Klepp Runde HITL geography verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
