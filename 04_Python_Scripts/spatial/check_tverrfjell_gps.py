#!/usr/bin/env python3
"""
QC: Tverrfjell FIT GPS vs SUT_43 organiser corridor (cross-track distance).

Confirms the Tier-0 loop is off-axis from SUT_43 even when geographically nearby.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/check_tverrfjell_gps.py

    python3 04_Python_Scripts/spatial/check_tverrfjell_gps.py \\
        --micro 03_Processed_Data/micro/Subject_A/activity_Tverrfjell_20260704.parquet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "04_Python_Scripts") not in sys.path:
    sys.path.insert(0, str(_REPO / "04_Python_Scripts"))

from fit_micro.course_project import load_gpx_course_km, resolve_gpx_path  # noqa: E402

DEFAULT_MICRO = (
    _REPO / "03_Processed_Data" / "micro" / "Subject_A" / "activity_Tverrfjell_20260704.parquet"
)
SUT43_GPX = _REPO / "02_Raw_Data" / "organiser_gpx" / "COURSE_SUT43_official_2027.gpx"


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
    return float(2 * r * np.arcsin(np.sqrt(np.clip(a, 0, 1))))


def _nearest_gpx_distance_m(
    lats: np.ndarray,
    lons: np.ndarray,
    course: pd.DataFrame,
    *,
    sample_step: int = 5,
) -> tuple[float, float, float]:
    """Min cross-track distance from each GPS sample to SUT GPX (vertex NN proxy)."""
    work = course.sort_values("distance_km")
    clat = work["latitude"].to_numpy(dtype=float)
    clon = work["longitude"].to_numpy(dtype=float)
    dists: list[float] = []
    for lat, lon in zip(lats[::sample_step], lons[::sample_step]):
        if not np.isfinite(lat) or not np.isfinite(lon):
            continue
        cos_lat = np.cos(np.radians(lat))
        dlat = (clat - lat) * 111_320.0
        dlon = (clon - lon) * cos_lat * 111_320.0
        dists.append(float(np.sqrt(dlat * dlat + dlon * dlon).min()))
    if not dists:
        return float("nan"), float("nan"), float("nan")
    arr = np.array(dists)
    return float(np.median(arr)), float(np.percentile(arr, 90)), float(arr.max())


def main() -> int:
    parser = argparse.ArgumentParser(description="Tverrfjell GPS vs SUT_43 corridor QC")
    parser.add_argument("--micro", type=Path, default=DEFAULT_MICRO)
    parser.add_argument("--gpx", type=Path, default=SUT43_GPX)
    parser.add_argument("--pass-m", type=float, default=30.0, help="Cross-track pass threshold (m)")
    args = parser.parse_args()

    micro_path = args.micro if args.micro.is_absolute() else _REPO / args.micro
    if not micro_path.exists():
        print(f"Micro parquet not found: {micro_path}", file=sys.stderr)
        return 1

    df = pd.read_parquet(micro_path)
    lat = pd.to_numeric(df["latitude"], errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(df["longitude"], errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(lat) & np.isfinite(lon)
    alt = pd.to_numeric(df.get("altitude_m"), errors="coerce")

    print("=== Tverrfjell activity GPS ===")
    print(f"  file: {micro_path.relative_to(_REPO)}")
    meta_path = micro_path.with_name(micro_path.stem + ".meta.json")
    if meta_path.exists():
        import json

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        print(f"  race_id (wash): {meta.get('race_id')}")
    print(f"  samples: {valid.sum()} / {len(df)}")
    print(f"  lat:  {lat[valid].min():.6f} – {lat[valid].max():.6f}")
    print(f"  lon:  {lon[valid].min():.6f} – {lon[valid].max():.6f}")
    print(f"  centroid: {lat[valid].mean():.6f}, {lon[valid].mean():.6f}")
    if alt is not None and alt.notna().any():
        print(f"  altitude m: {alt.min():.0f} – {alt.max():.0f}")
    print(f"  stream course_km: 0 – {df['course_km'].max():.3f} (FIT distance — NOT SUT km)")

    gpx_path = args.gpx if args.gpx.is_absolute() else _REPO / args.gpx
    if not gpx_path.exists():
        gpx_path = resolve_gpx_path("SUT_43")
    if gpx_path is None or not Path(gpx_path).exists():
        print("\n(SUT_43 GPX not found — place organiser GPX locally for cross-track QC)")
        print("  Expected: 02_Raw_Data/organiser_gpx/COURSE_SUT43_official_2027.gpx")
        return 0

    course = load_gpx_course_km(Path(gpx_path))
    med, p90, mx = _nearest_gpx_distance_m(lat[valid], lon[valid], course)
    print("\n=== vs SUT_43 organiser GPX ===")
    print(f"  gpx: {Path(gpx_path).relative_to(_REPO) if Path(gpx_path).is_relative_to(_REPO) else gpx_path}")
    print(f"  cross_track median: {med:.1f} m")
    print(f"  cross_track p90:    {p90:.1f} m")
    print(f"  cross_track max:    {mx:.1f} m")
    on_corridor = med <= args.pass_m
    print(f"  on_corridor (median ≤ {args.pass_m:.0f} m): {'YES — unexpected for local loop' if on_corridor else 'NO — off SUT tread (expected)'}")

    print("\n=== pipeline note ===")
    print("  Tverrfjell uses stream_distance course axis (race_id=tverrfjell).")
    print("  panel course_km is loop stream metres — never write into SUT_43 terrain maps.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
