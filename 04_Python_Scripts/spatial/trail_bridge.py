#!/usr/bin/env python3
"""
GPS Trail Anchor Bridge — project source-race telemetry onto a target organiser GPX axis.

Use case: SUT_43 race streams (Subject_A/B) → SUT_160 1 m grid in Gramstad/Dale overlap
without full SUT_160 race files for lab athletes.

See docs/memos/13_gps_trail_bridge_sut43_sut160_gramstad_20260626.local.md.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/trail_bridge.py --build-lut-only

    python3 04_Python_Scripts/spatial/trail_bridge.py \\
        --trail-bridge SUT_43:SUT_160 \\
        --manifest config/spatial_align_manifest_sut43.example.json \\
        --corridor-id gramstad_trail_bridge
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from fit_micro.activity_frame import read_parquet  # noqa: E402
from fit_micro.course_project import (  # noqa: E402
    ORGANISER_GPX_DIR,
    RACE_GPX,
    load_gpx_course_km,
    _nearest_track_km_batch,
)
from spatial.spatial_align import (  # noqa: E402
    DEFAULT_STEP_M,
    GRID_NUMERIC_COLS,
    compute_mechanical_kappa,
    load_manifest_activities,
    resample_to_grid_1m,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SPATIAL_DIR = BASE_DIR / "03_Processed_Data" / "spatial"

# Locked overlap (memo 13) — operator QC 2026-06-26.
DEFAULT_BRIDGE_PAIR = ("SUT_43", "SUT_160")
DEFAULT_SOURCE_KM = (22.0, 34.2)
DEFAULT_TARGET_KM = (140.0, 152.0)
DEFAULT_GEO_BBOX = (58.87487, 58.90986, 5.77947, 5.82101)  # lat_lo, lat_hi, lon_lo, lon_hi
DEFAULT_MATCH_RADIUS_M = 30.0
DEFAULT_LUT_SPACING_M = 25.0
DEFAULT_CORRIDOR_ID = "gramstad_trail_bridge"
BRIDGE_VERSION = "2026-06-26-gramstad-v0"


def _haversine_m(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    r = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def parse_bridge_pair(spec: str) -> tuple[str, str]:
    if ":" not in spec:
        raise ValueError(f"Expected SOURCE:TARGET, got {spec!r}")
    source, target = spec.split(":", 1)
    return source.strip(), target.strip()


def parse_float_pair(spec: str) -> tuple[float, float]:
    parts = [p.strip() for p in spec.split(",")]
    if len(parts) != 2:
        raise ValueError(f"Expected lo,hi — got {spec!r}")
    return float(parts[0]), float(parts[1])


def parse_geo_bbox(spec: str) -> tuple[float, float, float, float]:
    parts = [float(p.strip()) for p in spec.split(",")]
    if len(parts) != 4:
        raise ValueError(f"Expected lat_lo,lat_hi,lon_lo,lon_hi — got {spec!r}")
    return parts[0], parts[1], parts[2], parts[3]


def resolve_gpx(race_id: str) -> Path:
    fname = RACE_GPX.get(race_id)
    if not fname:
        raise KeyError(f"No organiser GPX registered for {race_id!r}")
    path = ORGANISER_GPX_DIR / fname
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def _resample_course_segment(
    course: pd.DataFrame,
    km_start: float,
    km_end: float,
    spacing_m: float,
) -> pd.DataFrame:
    lo, hi = min(km_start, km_end), max(km_start, km_end)
    seg = course[(course["distance_km"] >= lo) & (course["distance_km"] <= hi)].copy()
    if len(seg) < 2:
        raise ValueError(f"Insufficient GPX vertices in km {lo}–{hi}")
    dist_m = seg["distance_km"].to_numpy(dtype=float) * 1000.0
    new_dist = np.arange(dist_m[0], dist_m[-1], spacing_m)
    if new_dist[-1] < dist_m[-1] - 1e-3:
        new_dist = np.append(new_dist, dist_m[-1])
    lat = np.interp(new_dist, dist_m, seg["latitude"].to_numpy(dtype=float))
    lon = np.interp(new_dist, dist_m, seg["longitude"].to_numpy(dtype=float))
    return pd.DataFrame(
        {
            "source_km": new_dist / 1000.0,
            "latitude": lat,
            "longitude": lon,
        }
    )


def build_bridge_lut(
    source_race: str,
    target_race: str,
    *,
    source_km: tuple[float, float] = DEFAULT_SOURCE_KM,
    target_km: tuple[float, float] = DEFAULT_TARGET_KM,
    spacing_m: float = DEFAULT_LUT_SPACING_M,
    match_radius_m: float = DEFAULT_MATCH_RADIUS_M,
) -> pd.DataFrame:
    """
    Resample source organiser GPX in overlap band; NN-map each point to target GPX course_km.
    """
    source_course = load_gpx_course_km(resolve_gpx(source_race))
    target_course = load_gpx_course_km(resolve_gpx(target_race))
    t_lo, t_hi = target_km

    lut = _resample_course_segment(source_course, *source_km, spacing_m)
    target_km_at = _nearest_track_km_batch(
        target_course,
        lut["latitude"].to_numpy(dtype=float),
        lut["longitude"].to_numpy(dtype=float),
    )
    lut["target_km"] = target_km_at
    lut["source_race"] = source_race
    lut["target_race"] = target_race

    # Horizontal offset at mapped target vertex.
    tgt = target_course.sort_values("distance_km")
    clat = tgt["latitude"].to_numpy(dtype=float)
    clon = tgt["longitude"].to_numpy(dtype=float)
    ckm = tgt["distance_km"].to_numpy(dtype=float)
    offsets: list[float] = []
    for lat, lon, tkm in zip(lut["latitude"], lut["longitude"], lut["target_km"], strict=True):
        if not np.isfinite(tkm):
            offsets.append(np.nan)
            continue
        i = int(np.argmin(np.abs(ckm - tkm)))
        offsets.append(float(_haversine_m(np.array([lat]), np.array([lon]), np.array([clat[i]]), np.array([clon[i]]))[0]))
    lut["offset_m"] = offsets

    in_window = (lut["target_km"] >= t_lo) & (lut["target_km"] <= t_hi)
    in_radius = lut["offset_m"] <= match_radius_m
    lut["in_bridge_window"] = in_window & in_radius
    return lut.reset_index(drop=True)


def project_samples_to_target(
    frame: pd.DataFrame,
    target_race: str,
    *,
    target_km: tuple[float, float] = DEFAULT_TARGET_KM,
    match_radius_m: float = DEFAULT_MATCH_RADIUS_M,
) -> pd.DataFrame:
    """NN-snap activity GPS to target organiser GPX; filter to bridge window."""
    if not {"latitude", "longitude"}.issubset(frame.columns):
        raise ValueError("Frame requires latitude and longitude for trail bridge projection")

    target_course = load_gpx_course_km(resolve_gpx(target_race))
    lats = pd.to_numeric(frame["latitude"], errors="coerce").to_numpy(dtype=float)
    lons = pd.to_numeric(frame["longitude"], errors="coerce").to_numpy(dtype=float)
    target_km_at = _nearest_track_km_batch(target_course, lats, lons)

    out = frame.copy()
    out["course_km"] = target_km_at
    out["bridge_mode"] = True
    out["bridge_target_race"] = target_race
    out["bridge_version"] = BRIDGE_VERSION

    # Offset from nearest target GPX vertex.
    tgt = target_course.sort_values("distance_km")
    clat = tgt["latitude"].to_numpy(dtype=float)
    clon = tgt["longitude"].to_numpy(dtype=float)
    ckm = tgt["distance_km"].to_numpy(dtype=float)
    offsets = np.full(len(out), np.nan)
    valid = np.isfinite(lats) & np.isfinite(lons) & np.isfinite(target_km_at)
    for idx in np.where(valid)[0]:
        tkm = float(target_km_at[idx])
        i = int(np.argmin(np.abs(ckm - tkm)))
        offsets[idx] = float(
            _haversine_m(
                np.array([lats[idx]]),
                np.array([lons[idx]]),
                np.array([clat[i]]),
                np.array([clon[i]]),
            )[0]
        )
    out["bridge_offset_m"] = offsets

    t_lo, t_hi = target_km
    mask = (
        valid
        & (out["course_km"] >= t_lo)
        & (out["course_km"] <= t_hi)
        & (out["bridge_offset_m"] <= match_radius_m)
    )
    return out.loc[mask].reset_index(drop=True)


def bridge_align_activity(
    donor_id: str,
    activity_id: str,
    *,
    source_race: str = DEFAULT_BRIDGE_PAIR[0],
    target_race: str = DEFAULT_BRIDGE_PAIR[1],
    target_km: tuple[float, float] = DEFAULT_TARGET_KM,
    match_radius_m: float = DEFAULT_MATCH_RADIUS_M,
    step_m: float = DEFAULT_STEP_M,
    corridor_id: str = DEFAULT_CORRIDOR_ID,
    session_type: str = "race",
    write: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Project washed Parquet via GPS bridge, resample onto target 1 m grid."""
    frame = read_parquet(donor_id, activity_id)
    projected = project_samples_to_target(
        frame,
        target_race,
        target_km=target_km,
        match_radius_m=match_radius_m,
    )
    t_lo, t_hi = target_km
    grid = resample_to_grid_1m(projected, t_lo, t_hi, step_m=step_m)
    grid["mechanical_kappa"] = compute_mechanical_kappa(grid)
    grid["donor_id"] = donor_id
    grid["activity_id"] = str(activity_id)
    grid["session_type"] = session_type
    grid["bridge_mode"] = True
    grid["bridge_source_race"] = source_race
    grid["bridge_target_race"] = target_race
    grid["bridge_version"] = BRIDGE_VERSION

    meta: dict[str, Any] = {
        "corridor_id": corridor_id,
        "bridge_pair": f"{source_race}:{target_race}",
        "bridge_version": BRIDGE_VERSION,
        "target_km_start": t_lo,
        "target_km_end": t_hi,
        "match_radius_m": match_radius_m,
        "step_m": step_m,
        "donor_id": donor_id,
        "activity_id": str(activity_id),
        "session_type": session_type,
        "n_grid": int(len(grid)),
        "n_source_samples": int(len(projected)),
        "n_input_samples": int(len(frame)),
        "gpx_target": str(resolve_gpx(target_race)),
        "has_ti": bool(grid["ti"].notna().any()) if "ti" in grid.columns else False,
        "has_hr": bool(grid["heart_rate"].notna().any()) if "heart_rate" in grid.columns else False,
        "mean_bridge_offset_m": float(projected["bridge_offset_m"].mean()) if len(projected) else None,
    }

    if write:
        out_dir = SPATIAL_DIR / corridor_id
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_donor = donor_id.replace("/", "_")
        out_path = out_dir / f"aligned_{safe_donor}_{activity_id}_bridged.parquet"
        grid.to_parquet(out_path, index=False)
        meta["output_path"] = str(out_path.relative_to(BASE_DIR))

    return grid, meta


def bridge_panel_from_manifest(
    manifest_path: Path,
    *,
    source_race: str,
    target_race: str,
    target_km: tuple[float, float],
    match_radius_m: float,
    step_m: float,
    corridor_id: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    activities = load_manifest_activities(manifest_path)
    frames: list[pd.DataFrame] = []
    run_meta: list[dict[str, Any]] = []
    for spec in activities:
        grid, meta = bridge_align_activity(
            spec["donor_id"],
            spec["activity_id"],
            source_race=source_race,
            target_race=target_race,
            target_km=target_km,
            match_radius_m=match_radius_m,
            step_m=step_m,
            corridor_id=corridor_id,
            session_type=spec.get("session_type", "race"),
        )
        frames.append(grid)
        run_meta.append(meta)

    panel = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    out_dir = SPATIAL_DIR / corridor_id
    out_dir.mkdir(parents=True, exist_ok=True)

    panel_meta: dict[str, Any] = {
        "corridor_id": corridor_id,
        "bridge_pair": f"{source_race}:{target_race}",
        "bridge_version": BRIDGE_VERSION,
        "target_km_start": target_km[0],
        "target_km_end": target_km[1],
        "match_radius_m": match_radius_m,
        "step_m": step_m,
        "n_activities": len(activities),
        "activities": run_meta,
    }

    if not panel.empty:
        panel_path = out_dir / "panel_bridged_1m.parquet"
        panel.to_parquet(panel_path, index=False)
        panel_meta["panel_path"] = str(panel_path.relative_to(BASE_DIR))
        sidecar = out_dir / "align_meta.json"
        sidecar.write_text(json.dumps(panel_meta, indent=2), encoding="utf-8")
        panel_meta["meta_path"] = str(sidecar.relative_to(BASE_DIR))

    return panel, panel_meta


def main() -> int:
    parser = argparse.ArgumentParser(description="GPS Trail Anchor Bridge (SUT_43 → SUT_160)")
    parser.add_argument(
        "--trail-bridge",
        default=f"{DEFAULT_BRIDGE_PAIR[0]}:{DEFAULT_BRIDGE_PAIR[1]}",
        help="SOURCE:TARGET race ids (default SUT_43:SUT_160)",
    )
    parser.add_argument("--sut43-km", default=f"{DEFAULT_SOURCE_KM[0]},{DEFAULT_SOURCE_KM[1]}")
    parser.add_argument("--sut160-km", default=f"{DEFAULT_TARGET_KM[0]},{DEFAULT_TARGET_KM[1]}")
    parser.add_argument("--geo-window", default=",".join(str(v) for v in DEFAULT_GEO_BBOX))
    parser.add_argument("--match-radius-m", type=float, default=DEFAULT_MATCH_RADIUS_M)
    parser.add_argument("--lut-spacing-m", type=float, default=DEFAULT_LUT_SPACING_M)
    parser.add_argument("--step-m", type=float, default=DEFAULT_STEP_M)
    parser.add_argument("--corridor-id", default=DEFAULT_CORRIDOR_ID)
    parser.add_argument("--manifest", type=Path, help="Activity manifest (same schema as spatial_align)")
    parser.add_argument("--donor", help="Single donor id")
    parser.add_argument("--activity", help="Single activity id")
    parser.add_argument(
        "--build-lut-only",
        action="store_true",
        help="Write bridge LUT Parquet and exit",
    )
    args = parser.parse_args()

    source_race, target_race = parse_bridge_pair(args.trail_bridge)
    source_km = parse_float_pair(args.sut43_km)
    target_km = parse_float_pair(args.sut160_km)
    geo_bbox = parse_geo_bbox(args.geo_window)

    lut = build_bridge_lut(
        source_race,
        target_race,
        source_km=source_km,
        target_km=target_km,
        spacing_m=args.lut_spacing_m,
        match_radius_m=args.match_radius_m,
    )

    if args.build_lut_only or (not args.manifest and not (args.donor and args.activity)):
        out_dir = SPATIAL_DIR / args.corridor_id
        out_dir.mkdir(parents=True, exist_ok=True)
        lut_name = f"bridge_lut_{source_race.lower()}_{target_race.lower()}.parquet"
        lut_path = out_dir / lut_name
        lut.to_parquet(lut_path, index=False)
        n_in = int(lut["in_bridge_window"].sum())
        print(
            f"LUT n={len(lut)} in_window={n_in} "
            f"source {source_km[0]}–{source_km[1]} → target {target_km[0]}–{target_km[1]} "
            f"→ {lut_path.relative_to(BASE_DIR)}"
        )
        if args.build_lut_only:
            return 0

    if args.manifest:
        panel, meta = bridge_panel_from_manifest(
            args.manifest,
            source_race=source_race,
            target_race=target_race,
            target_km=target_km,
            match_radius_m=args.match_radius_m,
            step_m=args.step_m,
            corridor_id=args.corridor_id,
        )
        print(f"OK bridged panel n={len(panel)} → {meta.get('panel_path', '(empty)')}")
        return 0

    if args.donor and args.activity:
        grid, meta = bridge_align_activity(
            args.donor,
            args.activity,
            source_race=source_race,
            target_race=target_race,
            target_km=target_km,
            match_radius_m=args.match_radius_m,
            step_m=args.step_m,
            corridor_id=args.corridor_id,
        )
        print(f"OK n={len(grid)} grid → {meta.get('output_path')}")
        return 0

    parser.error("Provide --manifest, or --donor + --activity, or --build-lut-only")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
