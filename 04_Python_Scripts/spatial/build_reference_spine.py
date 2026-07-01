#!/usr/bin/env python3
"""
Build Subject_A canonical reference spine for SUT_43 cross-athlete alignment.

Default manifest window: km 8.0–41.0 (extended mid-course bridge through gramstad_band).
Gramstad-only rebuild: `--km-start 29 --km-end 41`.

Exports a 1 m grid with ref_chainage_m from Subject_A SUT43_20260418 race GPS,
resolves kinematic anchor stream-km per athlete, and scaffolds cross_track_m
projection for panel activities.

See docs/hitl_dashboard_runbook.md § Cross-athlete alignment caveat.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/build_reference_spine.py

    python3 04_Python_Scripts/spatial/build_reference_spine.py \\
        --manifest config/spatial_align_manifest_sut43.example.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from fit_micro.activity_frame import read_parquet  # noqa: E402
from spatial.corridor_scope import (  # noqa: E402
    SUT43_CORRIDOR_ID,
    SUT43_PRIMARY_KM_END,
    SUT43_PRIMARY_KM_START,
    SUT43_REFERENCE_SPINE_KM_END,
    SUT43_REFERENCE_SPINE_KM_START,
    SUT43_SECTOR_ID,
)
from spatial.spatial_align import (  # noqa: E402
    DEFAULT_STEP_M,
    aligned_parquet_path,
    build_course_grid_m,
    spatial_output_dir,
)
from spatial.trail_bridge import _haversine_m  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Validated pins — UTM zone 32N (EPSG:25832). ref_chainage_km on Subject_A spine.
DEFAULT_KINEMATIC_ANCHORS: list[dict[str, Any]] = [
    {
        "anchor_id": "food_cp",
        "display_name": "Gramstad food CP",
        "role": "crossing_order_knot",
        "ref_chainage_km": 30.52,
        "utm_epsg": 25832,
        "utm_e": 316090.14,
        "utm_n": 6531722.07,
        "elevation_m": 209.4,
    },
    {
        "anchor_id": "drink_cp",
        "display_name": "Gramstad drink CP",
        "role": "crossing_order_knot",
        "ref_chainage_km": 34.64,
        "utm_epsg": 25832,
        "utm_e": 315494.2,
        "utm_n": 6531475.5,
        "elevation_m": 161.3,
        "note": "Stop centroid UTM; gravel-entry pin at E 315526.13 N 6531456.32",
    },
    {
        "anchor_id": "paradisskaret_stile",
        "display_name": "Paradisskaret stile (gjerdeklyver)",
        "role": "crossing_order_knot",
        "crossing_order": "Subject_B_before_Subject_A",
        "ref_chainage_km": 39.135,
        "utm_epsg": 25832,
        "utm_e": 315959.62,
        "utm_n": 6530127.48,
        "elevation_m": 38.2,
    },
    {
        "anchor_id": "stile_31",
        "display_name": "STILE-31 (gramstad bedrock co-wait)",
        "role": "behavioral_exclusion_only",
        "ref_chainage_km": 31.16,
        "utm_epsg": 25832,
        "utm_e": 316408.72,
        "utm_n": 6531320.04,
        "elevation_m": 286.0,
        "note": "Behavioral TRF exclusion — not a crossing-order knot",
    },
]

SPINE_EXPORT_COLS = (
    "ref_chainage_m",
    "course_km",
    "latitude",
    "longitude",
    "altitude_m",
    "grade_pct",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utm_to_wgs84(e: float, n: float, epsg: int = 25832) -> tuple[float, float]:
    try:
        from pyproj import Transformer

        t = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
        lon, lat = t.transform(e, n)
        return float(lat), float(lon)
    except ImportError:
        return float("nan"), float("nan")


def load_canonical_spine_frame(
    *,
    donor_id: str = "Subject_A",
    activity_id: str = "SUT43_20260418",
    corridor_id: str = SUT43_CORRIDOR_ID,
    km_start: float = SUT43_PRIMARY_KM_START,
    km_end: float = SUT43_PRIMARY_KM_END,
) -> pd.DataFrame:
    """Load aligned Subject_A race grid as spine source."""
    path = aligned_parquet_path(donor_id, activity_id, corridor_id=corridor_id, session_type="race")
    if not path.exists():
        raise FileNotFoundError(f"Canonical spine source missing: {path}")
    df = pd.read_parquet(path)
    mask = (df["course_km"] >= km_start) & (df["course_km"] < km_end)
    return df.loc[mask].sort_values("course_m").reset_index(drop=True)


def build_reference_spine_1m(
    spine_source: pd.DataFrame,
    *,
    km_start: float = SUT43_PRIMARY_KM_START,
    km_end: float = SUT43_PRIMARY_KM_END,
    step_m: float = DEFAULT_STEP_M,
) -> pd.DataFrame:
    """1 m grid with ref_chainage_m = Subject_A course_m on gramstad_band."""
    grid_m = build_course_grid_m(km_start, km_end, step_m=step_m)
    out = pd.DataFrame({"ref_chainage_m": grid_m, "course_km": grid_m / 1000.0})

    src = spine_source.copy()
    src["course_m"] = pd.to_numeric(src["course_m"], errors="coerce")
    src = src.sort_values("course_m").groupby("course_m", as_index=False).median(numeric_only=True)
    x = src["course_m"].to_numpy(dtype=float)

    for col in ("latitude", "longitude", "altitude_m", "grade_pct"):
        if col not in src.columns:
            continue
        y = pd.to_numeric(src[col], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(x) & np.isfinite(y)
        if valid.sum() < 2:
            out[col] = np.nan
            continue
        out[col] = np.interp(grid_m, x[valid], y[valid], left=np.nan, right=np.nan)

    return out


def _resolve_course_km(frame: pd.DataFrame) -> pd.Series:
    if "course_km" in frame.columns and frame["course_km"].notna().any():
        return pd.to_numeric(frame["course_km"], errors="coerce")
    if "distance_m" in frame.columns:
        return pd.to_numeric(frame["distance_m"], errors="coerce") / 1000.0
    raise ValueError("Frame lacks course_km and distance_m")


def nearest_stream_km_at_pin(
    frame: pd.DataFrame,
    *,
    lat: float,
    lon: float,
    ref_km_hint: float | None = None,
) -> dict[str, float | None]:
    """Nearest sample stream km and geodesic offset to UTM pin."""
    lat_col = pd.to_numeric(frame.get("latitude"), errors="coerce")
    lon_col = pd.to_numeric(frame.get("longitude"), errors="coerce")
    km = _resolve_course_km(frame)

    if lat_col.notna().sum() >= 3 and lon_col.notna().sum() >= 3 and np.isfinite(lat):
        dist_m = _haversine_m(
            lat_col.to_numpy(dtype=float),
            lon_col.to_numpy(dtype=float),
            np.full(len(frame), lat),
            np.full(len(frame), lon),
        )
        idx = int(np.nanargmin(dist_m))
        return {
            "stream_km": round(float(km.iloc[idx]), 3),
            "pin_offset_m": round(float(dist_m[idx]), 1),
        }

    if ref_km_hint is not None:
        idx = int((km - ref_km_hint).abs().idxmin())
        return {"stream_km": round(float(km.iloc[idx]), 3), "pin_offset_m": None}

    return {"stream_km": None, "pin_offset_m": None}


def resolve_anchor_stream_km(
    anchors: list[dict[str, Any]],
    athletes: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Attach per-athlete stream_km at each kinematic pin."""
    resolved: list[dict[str, Any]] = []
    for anchor in anchors:
        rec = dict(anchor)
        lat, lon = _utm_to_wgs84(
            float(anchor["utm_e"]),
            float(anchor["utm_n"]),
            int(anchor.get("utm_epsg", 25832)),
        )
        rec["wgs84"] = {"latitude": lat, "longitude": lon}
        stream_km: dict[str, float | None] = {}
        pin_offset_m: dict[str, float | None] = {}
        for athlete in athletes:
            sid = athlete["subject_id"]
            try:
                frame = read_parquet(athlete["donor_id"], athlete["activity_id"])
            except FileNotFoundError:
                stream_km[sid] = None
                pin_offset_m[sid] = None
                continue
            hit = nearest_stream_km_at_pin(
                frame,
                lat=lat,
                lon=lon,
                ref_km_hint=float(anchor.get("ref_chainage_km", 0)),
            )
            stream_km[sid] = hit["stream_km"]
            pin_offset_m[sid] = hit["pin_offset_m"]

        rec["stream_km"] = stream_km
        rec["pin_offset_m"] = pin_offset_m
        a_km = stream_km.get("Subject_A")
        b_km = stream_km.get("Subject_B")
        if a_km is not None and b_km is not None:
            rec["stream_km_delta_m"] = {"Subject_B_vs_A": round((b_km - a_km) * 1000.0)}
        resolved.append(rec)
    return resolved


def project_activity_cross_track(
    spine: pd.DataFrame,
    frame: pd.DataFrame,
    *,
    subject_id: str,
    activity_id: str,
) -> dict[str, Any]:
    """Scaffold: median cross-track offset vs Subject_A spine polyline."""
    lat = pd.to_numeric(spine["latitude"], errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(spine["longitude"], errors="coerce").to_numpy(dtype=float)
    valid_spine = np.isfinite(lat) & np.isfinite(lon)
    if valid_spine.sum() < 2:
        return {
            "subject_id": subject_id,
            "activity_id": activity_id,
            "cross_track_m_median": None,
            "cross_track_m_p95": None,
            "n_samples": 0,
        }

    alat = pd.to_numeric(frame.get("latitude"), errors="coerce").to_numpy(dtype=float)
    alon = pd.to_numeric(frame.get("longitude"), errors="coerce").to_numpy(dtype=float)
    sample_valid = np.isfinite(alat) & np.isfinite(alon)
    if sample_valid.sum() == 0:
        return {
            "subject_id": subject_id,
            "activity_id": activity_id,
            "cross_track_m_median": None,
            "cross_track_m_p95": None,
            "n_samples": 0,
        }

    spine_lat = lat[valid_spine]
    spine_lon = lon[valid_spine]
    dists: list[float] = []
    for i in np.where(sample_valid)[0]:
        d = _haversine_m(
            np.array([alat[i]]),
            np.array([alon[i]]),
            spine_lat,
            spine_lon,
        )
        dists.append(float(np.nanmin(d)))

    if not dists:
        return {
            "subject_id": subject_id,
            "activity_id": activity_id,
            "cross_track_m_median": None,
            "cross_track_m_p95": None,
            "n_samples": 0,
        }

    arr = np.array(dists)
    return {
        "subject_id": subject_id,
        "activity_id": activity_id,
        "cross_track_m_median": round(float(np.median(arr)), 1),
        "cross_track_m_p95": round(float(np.percentile(arr, 95)), 1),
        "n_samples": int(len(arr)),
    }


def build_reference_spine(
    *,
    manifest_path: Path | None = None,
    corridor_id: str = SUT43_CORRIDOR_ID,
    km_start: float | None = None,
    km_end: float | None = None,
    step_m: float = DEFAULT_STEP_M,
    source_donor_id: str = "Subject_A",
    source_activity_id: str = "SUT43_20260418",
    anchors: list[dict[str, Any]] | None = None,
    output_dir: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build spine parquet + sidecar meta."""
    out_dir = output_dir or spatial_output_dir(corridor_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {}
    ref_km_start = km_start
    ref_km_end = km_end
    if manifest_path and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        ref_cfg = manifest.get("reference_spine") or {}
        km_win = ref_cfg.get("km_window") or manifest.get("km_analysis_window")
        if km_win and len(km_win) == 2:
            if ref_km_start is None:
                ref_km_start = float(km_win[0])
            if ref_km_end is None:
                ref_km_end = float(km_win[1])
        source_donor_id = ref_cfg.get("source_donor_id", source_donor_id)
        source_activity_id = ref_cfg.get("source_activity_id", source_activity_id)
        if ref_cfg.get("kinematic_anchors"):
            anchors = ref_cfg["kinematic_anchors"]

    if ref_km_start is None:
        ref_km_start = SUT43_REFERENCE_SPINE_KM_START
    if ref_km_end is None:
        ref_km_end = SUT43_REFERENCE_SPINE_KM_END

    anchor_list = anchors or DEFAULT_KINEMATIC_ANCHORS
    spine_src = load_canonical_spine_frame(
        donor_id=source_donor_id,
        activity_id=source_activity_id,
        corridor_id=corridor_id,
        km_start=ref_km_start,
        km_end=ref_km_end,
    )
    spine = build_reference_spine_1m(spine_src, km_start=ref_km_start, km_end=ref_km_end, step_m=step_m)

    race_athletes = [
        {
            "donor_id": a["donor_id"],
            "activity_id": a["activity_id"],
            "subject_id": a.get("subject_id", a["donor_id"]),
        }
        for a in manifest.get("activities", [])
        if a.get("session_type") == "race"
    ] or [
        {"donor_id": "Subject_A", "activity_id": "SUT43_20260418", "subject_id": "Subject_A"},
        {"donor_id": "Subject_B", "activity_id": "19000570862", "subject_id": "Subject_B"},
    ]

    resolved_anchors = resolve_anchor_stream_km(anchor_list, race_athletes)

    cross_track: list[dict[str, Any]] = []
    for athlete in race_athletes:
        if athlete["donor_id"] == source_donor_id and athlete["activity_id"] == source_activity_id:
            cross_track.append(
                {
                    "subject_id": athlete["subject_id"],
                    "activity_id": athlete["activity_id"],
                    "cross_track_m_median": 0.0,
                    "cross_track_m_p95": 0.0,
                    "n_samples": int(len(spine)),
                    "note": "canonical spine source",
                }
            )
            continue
        try:
            frame = read_parquet(athlete["donor_id"], athlete["activity_id"])
            km = _resolve_course_km(frame)
            mask = (km >= ref_km_start) & (km < ref_km_end)
            cross_track.append(
                project_activity_cross_track(
                    spine,
                    frame.loc[mask],
                    subject_id=athlete["subject_id"],
                    activity_id=athlete["activity_id"],
                )
            )
        except FileNotFoundError:
            cross_track.append(
                {
                    "subject_id": athlete["subject_id"],
                    "activity_id": athlete["activity_id"],
                    "cross_track_m_median": None,
                    "cross_track_m_p95": None,
                    "n_samples": 0,
                    "error": "washed parquet missing",
                }
            )

    parquet_path = out_dir / "reference_spine_1m.parquet"
    spine.to_parquet(parquet_path, index=False)

    meta: dict[str, Any] = {
        "schema_version": "reference_spine_v0",
        "generated_at": _utc_now(),
        "corridor_id": corridor_id,
        "sector_id": SUT43_SECTOR_ID,
        "km_window": [ref_km_start, ref_km_end],
        "step_m": step_m,
        "canonical_source": {
            "donor_id": source_donor_id,
            "activity_id": source_activity_id,
            "session_type": "race",
        },
        "n_metres": int(len(spine)),
        "output_parquet": str(parquet_path.relative_to(BASE_DIR)),
        "kinematic_anchors": resolved_anchors,
        "cross_track_summary": cross_track,
        "usage": (
            "Join activities on ref_chainage_m after reprojecting stream samples. "
            "Use kinematic_anchors.stream_km for per-athlete km labels at validated pins. "
            "Defer cross-athlete same-metre TRF until all panel rows carry ref_chainage_m."
        ),
    }
    meta_path = out_dir / "reference_spine_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    meta["meta_path"] = str(meta_path.relative_to(BASE_DIR))
    return spine, meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Subject_A reference spine for gramstad_band")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=BASE_DIR / "config" / "spatial_align_manifest_sut43.example.json",
    )
    parser.add_argument("--corridor-id", default=SUT43_CORRIDOR_ID)
    parser.add_argument("--km-start", type=float, default=None, help="Spine km start (manifest default if omitted)")
    parser.add_argument("--km-end", type=float, default=None, help="Spine km end (manifest default if omitted)")
    parser.add_argument("--step-m", type=float, default=DEFAULT_STEP_M)
    args = parser.parse_args()

    manifest_path = args.manifest if args.manifest.is_absolute() else BASE_DIR / args.manifest
    spine, meta = build_reference_spine(
        manifest_path=manifest_path,
        corridor_id=args.corridor_id,
        km_start=args.km_start,
        km_end=args.km_end,
        step_m=args.step_m,
    )
    print(f"OK reference spine n={len(spine)} → {meta['output_parquet']}")
    print(f"OK meta → {meta['meta_path']}")
    for anchor in meta["kinematic_anchors"]:
        sk = anchor.get("stream_km", {})
        delta = anchor.get("stream_km_delta_m", {})
        d_str = f" Δ={delta.get('Subject_B_vs_A')} m" if delta else ""
        print(
            f"   {anchor['anchor_id']} ({anchor['role']}): "
            f"A={sk.get('Subject_A')} B={sk.get('Subject_B')}{d_str}"
        )


if __name__ == "__main__":
    main()
