#!/usr/bin/env python3
"""
Reproject aligned panel activities onto Subject_A reference_spine_1m axis.

Maps each 1 m aligned sample to ref_chainage_m via GPS nearest-neighbour on the
canonical spine polyline (identity mapping for the spine source activity).
Preserves per-athlete stream labels as activity_course_km for audit.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/reproject_to_spine.py \\
        --manifest config/spatial_align_manifest_sut43.example.json

    python3 04_Python_Scripts/spatial/reproject_to_spine.py \\
        --manifest config/spatial_align_manifest_sut43.example.json \\
        --session-type race --validate-anchors
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

from spatial.build_reference_spine import DEFAULT_KINEMATIC_ANCHORS  # noqa: E402
from spatial.corridor_scope import SUT43_CORRIDOR_ID, SUT43_PRIMARY_KM_END, SUT43_PRIMARY_KM_START  # noqa: E402
from spatial.spatial_align import (  # noqa: E402
    aligned_parquet_path,
    load_manifest,
    spatial_output_dir,
    validate_session_type,
)
from spatial.trail_bridge import _haversine_m  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reference_spine_path(*, corridor_id: str = SUT43_CORRIDOR_ID) -> Path:
    return spatial_output_dir(corridor_id) / "reference_spine_1m.parquet"


def load_reference_spine(path: Path | None = None, *, corridor_id: str = SUT43_CORRIDOR_ID) -> pd.DataFrame:
    spine_path = path or reference_spine_path(corridor_id=corridor_id)
    if not spine_path.exists():
        raise FileNotFoundError(f"Reference spine missing: {spine_path}")
    spine = pd.read_parquet(spine_path)
    required = {"ref_chainage_m", "course_km"}
    missing = required - set(spine.columns)
    if missing:
        raise ValueError(f"Spine parquet missing columns: {sorted(missing)}")
    return spine.sort_values("ref_chainage_m").reset_index(drop=True)


def _prepare_spine_arrays(spine: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    chainage = pd.to_numeric(spine["ref_chainage_m"], errors="coerce").to_numpy(dtype=float)
    lat = pd.to_numeric(spine.get("latitude"), errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(spine.get("longitude"), errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(chainage) & np.isfinite(lat) & np.isfinite(lon)
    return chainage, lat, lon, valid


def nearest_ref_chainage_m(
    sample_lat: np.ndarray,
    sample_lon: np.ndarray,
    spine: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    """Nearest-neighbour GPS projection onto spine → ref_chainage_m and cross_track_m."""
    chainage, spine_lat, spine_lon, valid = _prepare_spine_arrays(spine)
    n = len(sample_lat)
    out_chainage = np.full(n, np.nan, dtype=float)
    out_cross = np.full(n, np.nan, dtype=float)

    if valid.sum() < 2:
        return out_chainage, out_cross

    slat = spine_lat[valid]
    slon = spine_lon[valid]
    sch = chainage[valid]

    sample_valid = np.isfinite(sample_lat) & np.isfinite(sample_lon)
    for i in np.where(sample_valid)[0]:
        dist = _haversine_m(
            np.array([sample_lat[i]]),
            np.array([sample_lon[i]]),
            slat,
            slon,
        )
        j = int(np.argmin(dist))
        out_chainage[i] = sch[j]
        out_cross[i] = float(dist[j])

    return out_chainage, out_cross


def is_canonical_spine_source(
    donor_id: str,
    activity_id: str,
    *,
    source_donor_id: str = "Subject_A",
    source_activity_id: str = "SUT43_20260418",
) -> bool:
    return donor_id == source_donor_id and str(activity_id) == str(source_activity_id)


def reproject_aligned_frame(
    frame: pd.DataFrame,
    spine: pd.DataFrame,
    *,
    donor_id: str,
    activity_id: str,
    session_type: str,
    subject_id: str | None = None,
    source_donor_id: str = "Subject_A",
    source_activity_id: str = "SUT43_20260418",
) -> pd.DataFrame:
    """Add ref_chainage_m; preserve stream course labels as activity_course_km."""
    out = frame.copy()
    if "course_m" in out.columns:
        out["activity_course_m"] = pd.to_numeric(out["course_m"], errors="coerce")
    elif "course_km" in out.columns:
        out["activity_course_m"] = pd.to_numeric(out["course_km"], errors="coerce") * 1000.0
    else:
        raise ValueError("Aligned frame lacks course_m / course_km")

    out["activity_course_km"] = out["activity_course_m"] / 1000.0
    out.drop(columns=[c for c in ("course_m", "course_km") if c in out.columns], inplace=True)

    if is_canonical_spine_source(
        donor_id,
        activity_id,
        source_donor_id=source_donor_id,
        source_activity_id=source_activity_id,
    ):
        out["ref_chainage_m"] = out["activity_course_m"].to_numpy(dtype=float)
        out["cross_track_m"] = 0.0
    else:
        lat = pd.to_numeric(out.get("latitude"), errors="coerce").to_numpy(dtype=float)
        lon = pd.to_numeric(out.get("longitude"), errors="coerce").to_numpy(dtype=float)
        ref_m, cross_m = nearest_ref_chainage_m(lat, lon, spine)
        out["ref_chainage_m"] = ref_m
        out["cross_track_m"] = cross_m

    out["donor_id"] = donor_id
    out["activity_id"] = str(activity_id)
    out["session_type"] = session_type
    out["subject_id"] = subject_id or donor_id
    return out


def is_spine_panel(panel: pd.DataFrame) -> bool:
    """True when panel rows carry ref_chainage_m (post reproject_to_spine)."""
    return "ref_chainage_m" in panel.columns


def subject_id_column(panel: pd.DataFrame) -> str:
    """Clinical subject key — prefer subject_id over donor_id when present."""
    return "subject_id" if "subject_id" in panel.columns else "donor_id"


def normalize_panel_axes(panel: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure course_km / course_m for downstream TRF and HITL consumers.

    On Subject_A race spine, ref_chainage_m equals activity_course_m and matches
    operator gold course_km_start/end (1:1 km mapping). HITL spans need no re-key.
    """
    work = panel.copy()
    if not is_spine_panel(work):
        return work
    ref_m = pd.to_numeric(work["ref_chainage_m"], errors="coerce")
    if "course_m" not in work.columns:
        work["course_m"] = ref_m
    if "course_km" not in work.columns:
        work["course_km"] = ref_m / 1000.0
    return work


def aligned_spine_parquet_path(
    donor_id: str,
    activity_id: str,
    *,
    corridor_id: str = SUT43_CORRIDOR_ID,
    session_type: str,
) -> Path:
    base = aligned_parquet_path(
        donor_id,
        activity_id,
        corridor_id=corridor_id,
        session_type=validate_session_type(session_type),
    )
    return base.with_name(f"{base.stem}_spine.parquet")


def reproject_aligned_activity(
    donor_id: str,
    activity_id: str,
    spine: pd.DataFrame,
    *,
    corridor_id: str = SUT43_CORRIDOR_ID,
    session_type: str = "race",
    subject_id: str | None = None,
    source_donor_id: str = "Subject_A",
    source_activity_id: str = "SUT43_20260418",
    write: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    session_type = validate_session_type(session_type)
    in_path = aligned_parquet_path(
        donor_id,
        activity_id,
        corridor_id=corridor_id,
        session_type=session_type,
    )
    if not in_path.exists():
        raise FileNotFoundError(f"Aligned parquet missing: {in_path}")

    frame = pd.read_parquet(in_path)
    reproj = reproject_aligned_frame(
        frame,
        spine,
        donor_id=donor_id,
        activity_id=activity_id,
        session_type=session_type,
        subject_id=subject_id,
        source_donor_id=source_donor_id,
        source_activity_id=source_activity_id,
    )

    meta: dict[str, Any] = {
        "donor_id": donor_id,
        "activity_id": str(activity_id),
        "subject_id": subject_id or donor_id,
        "session_type": session_type,
        "input_path": str(in_path.relative_to(BASE_DIR)),
        "n_rows": int(len(reproj)),
        "ref_chainage_m_min": float(reproj["ref_chainage_m"].min()),
        "ref_chainage_m_max": float(reproj["ref_chainage_m"].max()),
        "cross_track_m_median": round(float(reproj["cross_track_m"].median()), 2)
        if reproj["cross_track_m"].notna().any()
        else None,
        "canonical_spine_source": is_canonical_spine_source(
            donor_id,
            activity_id,
            source_donor_id=source_donor_id,
            source_activity_id=source_activity_id,
        ),
    }

    if write:
        out_path = aligned_spine_parquet_path(
            donor_id,
            activity_id,
            corridor_id=corridor_id,
            session_type=session_type,
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        reproj.to_parquet(out_path, index=False)
        meta["output_path"] = str(out_path.relative_to(BASE_DIR))

    return reproj, meta


def build_spine_panel(
    frames: list[pd.DataFrame],
    *,
    corridor_id: str = SUT43_CORRIDOR_ID,
    session_type: str,
    write: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not frames:
        return pd.DataFrame(), {"n_rows": 0}

    panel = pd.concat(frames, ignore_index=True)
    meta: dict[str, Any] = {
        "corridor_id": corridor_id,
        "session_type": session_type,
        "n_rows": int(len(panel)),
        "n_activities": panel.groupby(["donor_id", "activity_id"]).ngroups if not panel.empty else 0,
        "ref_chainage_m_range": [
            float(panel["ref_chainage_m"].min()),
            float(panel["ref_chainage_m"].max()),
        ],
    }

    if write:
        out_dir = spatial_output_dir(corridor_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"panel_{session_type}_1m_spine.parquet"
        panel.to_parquet(out_path, index=False)
        meta["panel_path"] = str(out_path.relative_to(BASE_DIR))

    return panel, meta


def validate_kinematic_anchors(
    panel: pd.DataFrame,
    anchors: list[dict[str, Any]],
    *,
    subjects: tuple[str, ...] = ("Subject_A", "Subject_B"),
) -> pd.DataFrame:
    """At each ref_chainage pin, report activity_course_km per subject and stream delta."""
    rows: list[dict[str, Any]] = []
    for anchor in anchors:
        ref_km = float(anchor["ref_chainage_km"])
        ref_m = ref_km * 1000.0
        anchor_id = anchor["anchor_id"]
        role = anchor.get("role", "")
        pin_offsets = anchor.get("pin_offset_m") or {}

        subject_km: dict[str, float | None] = {}
        for sid in subjects:
            sub = panel[panel["subject_id"] == sid] if "subject_id" in panel.columns else panel[
                panel["donor_id"] == sid
            ]
            if sub.empty:
                subject_km[sid] = None
                continue
            idx = (sub["ref_chainage_m"] - ref_m).abs().idxmin()
            subject_km[sid] = round(float(sub.loc[idx, "activity_course_km"]), 3)

        a_km = subject_km.get("Subject_A")
        b_km = subject_km.get("Subject_B")
        delta_m: float | None = None
        if a_km is not None and b_km is not None:
            delta_m = round((b_km - a_km) * 1000.0)

        rows.append(
            {
                "anchor_id": anchor_id,
                "role": role,
                "ref_chainage_km": ref_km,
                "Subject_A_activity_km": a_km,
                "Subject_B_activity_km": b_km,
                "stream_delta_m_B_vs_A": delta_m,
                "expected_delta_range_m": "282–390"
                if role == "crossing_order_knot"
                else "n/a",
                "Subject_A_pin_offset_m": pin_offsets.get("Subject_A"),
                "Subject_B_pin_offset_m": pin_offsets.get("Subject_B"),
            }
        )
    return pd.DataFrame(rows)


def reproject_from_manifest(
    manifest_path: Path,
    *,
    spine_path: Path | None = None,
    corridor_id: str | None = None,
    session_types: tuple[str, ...] = ("race",),
    write: bool = True,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    manifest = load_manifest(manifest_path)
    corridor_id = corridor_id or manifest.get("corridor_id", SUT43_CORRIDOR_ID)
    ref_cfg = manifest.get("reference_spine") or {}
    spine_file = spine_path
    if spine_file is None and ref_cfg.get("output_parquet"):
        spine_file = BASE_DIR / ref_cfg["output_parquet"]
    spine = load_reference_spine(spine_file, corridor_id=corridor_id)

    source_donor = ref_cfg.get("source_donor_id", "Subject_A")
    source_activity = ref_cfg.get("source_activity_id", "SUT43_20260418")
    anchors = ref_cfg.get("kinematic_anchors") or DEFAULT_KINEMATIC_ANCHORS

    activities = manifest.get("activities", [])
    reproj_frames: dict[str, list[pd.DataFrame]] = {st: [] for st in session_types}
    activity_meta: list[dict[str, Any]] = []

    for spec in activities:
        st = validate_session_type(spec.get("session_type", "race"))
        if st not in session_types:
            continue
        try:
            frame, meta = reproject_aligned_activity(
                spec["donor_id"],
                spec["activity_id"],
                spine,
                corridor_id=corridor_id,
                session_type=st,
                subject_id=spec.get("subject_id"),
                source_donor_id=source_donor,
                source_activity_id=source_activity,
                write=write,
            )
            reproj_frames[st].append(frame)
            activity_meta.append(meta)
        except FileNotFoundError as exc:
            activity_meta.append(
                {
                    "donor_id": spec["donor_id"],
                    "activity_id": spec["activity_id"],
                    "session_type": st,
                    "error": str(exc),
                }
            )

    panels: dict[str, pd.DataFrame] = {}
    panel_meta: dict[str, Any] = {}
    for st, frames in reproj_frames.items():
        if not frames:
            continue
        panel, pmeta = build_spine_panel(frames, corridor_id=corridor_id, session_type=st, write=write)
        panels[st] = panel
        panel_meta[st] = pmeta

    race_panel = panels.get("race", pd.DataFrame())
    anchor_table = (
        validate_kinematic_anchors(race_panel, anchors)
        if not race_panel.empty
        else pd.DataFrame()
    )

    run_meta: dict[str, Any] = {
        "schema_version": "reproject_spine_v0",
        "generated_at": _utc_now(),
        "corridor_id": corridor_id,
        "manifest": str(manifest_path.relative_to(BASE_DIR))
        if manifest_path.is_relative_to(BASE_DIR)
        else str(manifest_path),
        "spine_path": str((spine_file or reference_spine_path(corridor_id=corridor_id)).relative_to(BASE_DIR))
        if (spine_file or reference_spine_path(corridor_id=corridor_id)).is_relative_to(BASE_DIR)
        else str(spine_file or reference_spine_path(corridor_id=corridor_id)),
        "canonical_source": {"donor_id": source_donor, "activity_id": source_activity},
        "activities": activity_meta,
        "panels": panel_meta,
        "anchor_validation": anchor_table.to_dict(orient="records") if not anchor_table.empty else [],
    }

    if write:
        sidecar = spatial_output_dir(corridor_id) / "reproject_spine_meta.json"
        sidecar.write_text(json.dumps(run_meta, indent=2), encoding="utf-8")
        run_meta["meta_path"] = str(sidecar.relative_to(BASE_DIR))

    return panels, run_meta


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reproject aligned activities onto reference_spine_1m ref_chainage_m axis",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=BASE_DIR / "config" / "spatial_align_manifest_sut43.example.json",
    )
    parser.add_argument("--spine", type=Path, default=None, help="Override reference_spine_1m.parquet path")
    parser.add_argument("--corridor-id", default=None)
    parser.add_argument(
        "--session-type",
        choices=("race", "training", "all"),
        default="race",
        help="Which manifest activities to reproject (default race)",
    )
    parser.add_argument(
        "--validate-anchors",
        action="store_true",
        help="Print kinematic anchor validation table (default: always printed for race)",
    )
    parser.add_argument("--no-write", action="store_true", help="Dry run — no parquet output")
    args = parser.parse_args()

    manifest_path = args.manifest if args.manifest.is_absolute() else BASE_DIR / args.manifest
    session_types: tuple[str, ...]
    if args.session_type == "all":
        session_types = ("race", "training")
    else:
        session_types = (args.session_type,)

    panels, meta = reproject_from_manifest(
        manifest_path,
        spine_path=args.spine,
        corridor_id=args.corridor_id,
        session_types=session_types,
        write=not args.no_write,
    )

    for st, pmeta in meta.get("panels", {}).items():
        print(f"OK panel_{st}_1m_spine n={pmeta.get('n_rows', 0)} → {pmeta.get('panel_path', '(dry run)')}")

    for act in meta.get("activities", []):
        if "error" in act:
            print(f"SKIP {act['donor_id']} {act['activity_id']}: {act['error']}")
        else:
            print(
                f"OK {act['subject_id']} {act['activity_id']} "
                f"cross_track_median={act.get('cross_track_m_median')} → {act.get('output_path', '(dry run)')}"
            )

    anchor_rows = meta.get("anchor_validation", [])
    if anchor_rows and (args.validate_anchors or "race" in session_types):
        print("\nAnchor validation (activity_course_km at ref_chainage_m):")
        table = pd.DataFrame(anchor_rows)
        cols = [
            "anchor_id",
            "ref_chainage_km",
            "Subject_A_activity_km",
            "Subject_B_activity_km",
            "stream_delta_m_B_vs_A",
            "expected_delta_range_m",
        ]
        print(table[cols].to_string(index=False))

    if meta.get("meta_path"):
        print(f"\nOK meta → {meta['meta_path']}")


if __name__ == "__main__":
    main()
