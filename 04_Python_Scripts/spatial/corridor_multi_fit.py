#!/usr/bin/env python3
"""
Multi-fit corridor ingest — partial overlap, reverse traversal, GPS bridge dispatch.

Extends Phase A spatial_align with per-activity align_mode so lab athletes can
contribute SUT_43 race streams and partial training tiles onto the SUT_160
Dale–Alsvik corridor axis (km 140–155.58) without a full SUT_160 race file.

Align modes (per activity or manifest default_align_mode):
  gpx    — organiser GPX snap (spatial_align.load_activity_frame + crop)
  bridge — GPS NN snap to target race GPX (trail_bridge.project_samples_to_target)
  stream — stream distance_m / 1000 (no GPX); supports direction flip for reverse laps

Usage (from repo root):
    python3 04_Python_Scripts/spatial/corridor_multi_fit.py \\
        --manifest config/spatial_align_manifest_dale_alsvik.example.json

    python3 04_Python_Scripts/spatial/corridor_multi_fit.py --discover
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from fit_micro.activity_frame import MICRO_DIR, read_parquet  # noqa: E402
from fit_micro.course_project import project_course_km  # noqa: E402
from spatial.corridor_scope import (  # noqa: E402
    STRESS_TEST_CORRIDOR_ID,
    STRESS_TEST_RACE_ID,
    load_experiment_window,
)
from spatial.spatial_align import (  # noqa: E402
    DEFAULT_STEP_M,
    align_activity,
    aligned_parquet_path,
    compute_mechanical_kappa,
    crop_corridor,
    load_manifest,
    load_manifest_activities,
    panel_parquet_path,
    resample_to_grid_1m,
    validate_session_type,
)
from spatial.trail_bridge import (  # noqa: E402
    BRIDGE_VERSION,
    DEFAULT_MATCH_RADIUS_M,
    project_samples_to_target,
    resolve_gpx,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent

AlignMode = Literal["gpx", "bridge", "stream"]
Direction = Literal["auto", "forward", "reverse"]
VALID_ALIGN_MODES: tuple[AlignMode, ...] = ("gpx", "bridge", "stream")
VALID_DIRECTIONS: tuple[Direction, ...] = ("auto", "forward", "reverse")


def validate_align_mode(mode: str) -> AlignMode:
    if mode not in VALID_ALIGN_MODES:
        raise ValueError(f"align_mode must be one of {VALID_ALIGN_MODES}, got {mode!r}")
    return mode  # type: ignore[return-value]


def validate_direction(direction: str) -> Direction:
    if direction not in VALID_DIRECTIONS:
        raise ValueError(f"direction must be one of {VALID_DIRECTIONS}, got {direction!r}")
    return direction  # type: ignore[return-value]


def _time_ordered_course_km(
    frame: pd.DataFrame,
    course_km_col: str = "course_km",
) -> np.ndarray:
    """Course km sorted by elapsed time (or row order)."""
    km = pd.to_numeric(frame[course_km_col], errors="coerce").to_numpy(dtype=float)
    if "elapsed_s" in frame.columns:
        t = pd.to_numeric(frame["elapsed_s"], errors="coerce").to_numpy(dtype=float)
        order = np.argsort(t, kind="stable")
        return km[order]
    return km


def detect_traversal_direction(
    frame: pd.DataFrame,
    *,
    course_km_col: str = "course_km",
    min_samples: int = 20,
    min_delta_km: float = 0.05,
) -> str:
    """
    Infer forward vs reverse traversal from time-ordered course_km trend.

    GPS-projected km is position-based; reverse runs still map to valid course_km.
    Detection tags metadata and drives stream-axis flips when align_mode=stream.
    """
    km_series = _time_ordered_course_km(frame, course_km_col)
    valid = np.isfinite(km_series)
    if valid.sum() < min_samples:
        return "forward"
    km = km_series[valid]
    delta = float(km[-1] - km[0])
    if abs(delta) < min_delta_km:
        return "forward"
    return "reverse" if delta < 0 else "forward"


def flip_stream_axis(
    frame: pd.DataFrame,
    km_lo: float,
    km_hi: float,
    *,
    course_km_col: str = "course_km",
) -> pd.DataFrame:
    """Mirror stream-distance course_km within corridor bounds (reverse lap)."""
    out = frame.copy()
    km = pd.to_numeric(out[course_km_col], errors="coerce")
    lo, hi = min(km_lo, km_hi), max(km_lo, km_hi)
    out[course_km_col] = lo + hi - km
    return out


def canonicalize_course_axis(
    frame: pd.DataFrame,
    km_lo: float,
    km_hi: float,
    *,
    direction: Direction = "auto",
    align_mode: AlignMode = "gpx",
    course_km_col: str = "course_km",
) -> tuple[pd.DataFrame, str]:
    """
    Resolve traversal direction; flip stream axis when required.

    GPS modes (gpx, bridge): position-based km — no flip; direction is metadata only.
    Stream mode + reverse: mirror course_km within corridor window.
    """
    resolved = detect_traversal_direction(frame, course_km_col=course_km_col) if direction == "auto" else direction
    if align_mode == "stream" and resolved == "reverse":
        return flip_stream_axis(frame, km_lo, km_hi, course_km_col=course_km_col), resolved
    return frame, resolved


def compute_overlap_stats(
    frame: pd.DataFrame,
    km_lo: float,
    km_hi: float,
    *,
    course_km_col: str = "course_km",
) -> dict[str, Any]:
    """Actual data extent inside corridor window and coverage fraction."""
    lo, hi = min(km_lo, km_hi), max(km_lo, km_hi)
    span_m = (hi - lo) * 1000.0
    km = pd.to_numeric(frame.get(course_km_col), errors="coerce")
    in_win = km.notna() & (km >= lo) & (km <= hi)
    if not in_win.any():
        return {
            "overlap_km_start": None,
            "overlap_km_end": None,
            "overlap_span_km": 0.0,
            "coverage_fraction": 0.0,
            "n_overlap_samples": 0,
        }
    sub = km.loc[in_win]
    overlap_lo = float(sub.min())
    overlap_hi = float(sub.max())
    overlap_m = max(0.0, (overlap_hi - overlap_lo) * 1000.0)
    coverage = float(overlap_m / span_m) if span_m > 0 else 0.0
    return {
        "overlap_km_start": overlap_lo,
        "overlap_km_end": overlap_hi,
        "overlap_span_km": round(overlap_hi - overlap_lo, 3),
        "coverage_fraction": round(min(1.0, coverage), 4),
        "n_overlap_samples": int(in_win.sum()),
    }


def resolve_activity_spec(
    spec: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Merge per-activity fields with manifest-level defaults."""
    merged = dict(spec)
    for key in (
        "align_mode",
        "direction",
        "bridge_target_race",
        "bridge_source_race",
        "match_radius_m",
        "race_id",
        "subject_id",
        "session_type",
        "project_course",
    ):
        if key not in merged and key in manifest:
            merged[key] = manifest[key]
    if "align_mode" not in merged:
        merged["align_mode"] = manifest.get("default_align_mode", "gpx")
    if "direction" not in merged:
        merged["direction"] = manifest.get("default_direction", "auto")
    if "match_radius_m" not in merged:
        merged["match_radius_m"] = manifest.get("match_radius_m", DEFAULT_MATCH_RADIUS_M)
    if "bridge_target_race" not in merged:
        merged["bridge_target_race"] = manifest.get("bridge_target_race", STRESS_TEST_RACE_ID)
    return merged


def resolve_project_course(
    resolved: dict[str, Any],
    *,
    cli_project_course: bool = False,
) -> bool:
    """
    Per-activity course projection flag.

    Defaults: stream → True, gpx → False (pre-projected tiles keep course_km).
    Explicit manifest ``project_course`` wins. CLI ``--project-course`` enables
    projection for stream activities only — it does not re-snap GPX tiles.
    """
    if "project_course" in resolved:
        return bool(resolved["project_course"])
    align_mode = validate_align_mode(resolved.get("align_mode", "gpx"))
    if align_mode == "gpx":
        return False
    if align_mode == "stream":
        return True
    return cli_project_course


def _prepare_stream_frame(
    donor_id: str,
    activity_id: str,
    *,
    race_id: str,
    km_lo: float,
    km_hi: float,
    direction: Direction,
) -> tuple[pd.DataFrame, str]:
    frame = read_parquet(donor_id, activity_id)
    if "course_km" not in frame.columns or frame["course_km"].isna().all():
        frame = project_course_km(frame, race_id=race_id)
    frame, resolved_dir = canonicalize_course_axis(
        frame, km_lo, km_hi, direction=direction, align_mode="stream"
    )
    return frame, resolved_dir


def _prepare_bridge_frame(
    donor_id: str,
    activity_id: str,
    *,
    target_race: str,
    target_km: tuple[float, float],
    match_radius_m: float,
    km_lo: float,
    km_hi: float,
    direction: Direction,
) -> tuple[pd.DataFrame, str]:
    frame = read_parquet(donor_id, activity_id)
    projected = project_samples_to_target(
        frame,
        target_race,
        target_km=target_km,
        match_radius_m=match_radius_m,
    )
    # Widen to full corridor crop — bridge filter may be tighter than analysis window.
    cropped = crop_corridor(projected, km_lo, km_hi)
    resolved_dir = (
        detect_traversal_direction(cropped)
        if direction == "auto"
        else validate_direction(direction)
    )
    return cropped, resolved_dir


def align_activity_multi(
    spec: dict[str, Any],
    manifest: dict[str, Any],
    *,
    km_start: float,
    km_end: float,
    step_m: float = DEFAULT_STEP_M,
    project_course: bool = False,
    enrich_if_needed: bool = False,
    race_id: str = STRESS_TEST_RACE_ID,
    corridor_id: str = STRESS_TEST_CORRIDOR_ID,
    gpx_path: Path | None = None,
    write: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Align one manifest activity with multi-fit dispatch (gpx | bridge | stream)."""
    resolved = resolve_activity_spec(spec, manifest)
    align_mode = validate_align_mode(resolved["align_mode"])
    direction = validate_direction(resolved.get("direction", "auto"))
    session_type = validate_session_type(resolved.get("session_type", "race"))
    donor_id = resolved["donor_id"]
    activity_id = str(resolved["activity_id"])
    km_lo, km_hi = min(km_start, km_end), max(km_start, km_end)
    activity_project_course = resolve_project_course(
        resolved, cli_project_course=project_course
    )

    if align_mode == "gpx":
        grid, meta = align_activity(
            donor_id,
            activity_id,
            km_start=km_start,
            km_end=km_end,
            step_m=step_m,
            project_course=activity_project_course,
            enrich_if_needed=enrich_if_needed,
            race_id=resolved.get("race_id", race_id),
            corridor_id=corridor_id,
            gpx_path=gpx_path,
            subject_id=resolved.get("subject_id"),
            session_type=session_type,
            write=False,
        )
        _, trav_dir = canonicalize_course_axis(
            grid, km_lo, km_hi, direction=direction, align_mode="gpx"
        )
        overlap = compute_overlap_stats(grid, km_lo, km_hi)
    elif align_mode == "bridge":
        target_race = resolved["bridge_target_race"]
        match_radius_m = float(resolved["match_radius_m"])
        target_km = tuple(resolved.get("target_km", manifest.get("bridge_target_km", [km_lo, km_hi])))
        if len(target_km) != 2:
            raise ValueError(f"target_km must be [lo, hi], got {target_km!r}")
        cropped, trav_dir = _prepare_bridge_frame(
            donor_id,
            activity_id,
            target_race=target_race,
            target_km=(float(target_km[0]), float(target_km[1])),
            match_radius_m=match_radius_m,
            km_lo=km_lo,
            km_hi=km_hi,
            direction=direction,
        )
        grid = resample_to_grid_1m(cropped, km_lo, km_hi, step_m=step_m)
        grid["mechanical_kappa"] = compute_mechanical_kappa(grid)
        grid["donor_id"] = donor_id
        grid["activity_id"] = activity_id
        grid["session_type"] = session_type
        grid["bridge_mode"] = True
        grid["bridge_target_race"] = target_race
        grid["bridge_version"] = BRIDGE_VERSION
        overlap = compute_overlap_stats(cropped, km_lo, km_hi)
        meta = {
            "donor_id": donor_id,
            "activity_id": activity_id,
            "session_type": session_type,
            "align_mode": align_mode,
            "n_grid": int(len(grid)),
            "n_source_samples": int(len(cropped)),
            "gpx_target": str(Path(resolve_gpx(target_race)).relative_to(BASE_DIR)),
            "match_radius_m": match_radius_m,
        }
    else:  # stream
        stream_race = resolved.get("race_id", manifest.get("stream_race_id", "SUT_43"))
        frame, trav_dir = _prepare_stream_frame(
            donor_id,
            activity_id,
            race_id=stream_race,
            km_lo=km_lo,
            km_hi=km_hi,
            direction=direction,
        )
        cropped = crop_corridor(frame, km_lo, km_hi)
        grid = resample_to_grid_1m(cropped, km_lo, km_hi, step_m=step_m)
        grid["mechanical_kappa"] = compute_mechanical_kappa(grid)
        grid["donor_id"] = donor_id
        grid["activity_id"] = activity_id
        grid["session_type"] = session_type
        overlap = compute_overlap_stats(cropped, km_lo, km_hi)
        meta = {
            "donor_id": donor_id,
            "activity_id": activity_id,
            "session_type": session_type,
            "align_mode": align_mode,
            "stream_race_id": stream_race,
            "n_grid": int(len(grid)),
            "n_source_samples": int(len(cropped)),
        }

    meta.update(
        {
            "corridor_id": corridor_id,
            "align_mode": align_mode,
            "project_course": activity_project_course,
            "traversal_direction": trav_dir,
            "direction_requested": direction,
            "step_m": step_m,
            "km_start": km_lo,
            "km_end": km_hi,
            **overlap,
        }
    )

    if write:
        out_path = aligned_parquet_path(
            donor_id, activity_id, corridor_id=corridor_id, session_type=session_type
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        grid.to_parquet(out_path, index=False)
        meta["output_path"] = str(out_path.relative_to(BASE_DIR))

    return grid, meta


def align_manifest_multi(
    manifest_path: Path,
    *,
    km_start: float | None = None,
    km_end: float | None = None,
    step_m: float = DEFAULT_STEP_M,
    project_course: bool = False,
    enrich_if_needed: bool = False,
    write_panel: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Align all activities in a multi-fit manifest; stack panel + sidecar."""
    manifest = load_manifest(manifest_path)
    activities = load_manifest_activities(manifest_path)
    race_id = manifest.get("race_id", STRESS_TEST_RACE_ID)
    corridor_id = manifest.get("corridor_id", STRESS_TEST_CORRIDOR_ID)

    if km_start is None and "km_analysis_window" in manifest:
        win = manifest["km_analysis_window"]
        km_start, km_end = float(win[0]), float(win[1])
    start, end, corridor_meta = load_experiment_window(
        race_id, km_start=km_start, km_end=km_end
    )

    frames: list[pd.DataFrame] = []
    run_meta: list[dict[str, Any]] = []
    for spec in activities:
        grid, meta = align_activity_multi(
            spec,
            manifest,
            km_start=start,
            km_end=end,
            step_m=step_m,
            project_course=project_course,
            enrich_if_needed=enrich_if_needed,
            race_id=race_id,
            corridor_id=corridor_id,
            write=True,
        )
        frames.append(grid)
        run_meta.append(meta)

    panel = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    panel_meta: dict[str, Any] = {
        **corridor_meta,
        "corridor_id": corridor_id,
        "multi_fit": True,
        "default_align_mode": manifest.get("default_align_mode"),
        "step_m": step_m,
        "n_activities": len(activities),
        "activities": run_meta,
    }

    if write_panel and not panel.empty:
        path = panel_parquet_path(corridor_id=corridor_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        panel.to_parquet(path, index=False)
        panel_meta["panel_path"] = str(path.relative_to(BASE_DIR))
        for st in ("race", "training"):
            sub = panel[panel["session_type"] == st] if "session_type" in panel.columns else pd.DataFrame()
            if not sub.empty:
                sub_path = path.with_name(f"panel_{st}_1m.parquet")
                sub.to_parquet(sub_path, index=False)
                panel_meta[f"panel_{st}_path"] = str(sub_path.relative_to(BASE_DIR))
        sidecar = path.with_name("align_meta.json")
        sidecar.write_text(json.dumps(panel_meta, indent=2), encoding="utf-8")
        panel_meta["meta_path"] = str(sidecar.relative_to(BASE_DIR))

    return panel, panel_meta


def discover_washed_activities(
    *,
    donors: list[str] | None = None,
    micro_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Scan washed micro Parquet tier for ingest candidates.

    Returns donor_id, activity_id, parquet path, and byte size — no personal names.
    """
    root = micro_dir or MICRO_DIR
    out: list[dict[str, Any]] = []
    if not root.exists():
        return out
    for donor_dir in sorted(root.iterdir()):
        if not donor_dir.is_dir():
            continue
        donor_id = donor_dir.name
        if donors and donor_id not in donors:
            continue
        for path in sorted(donor_dir.glob("activity_*.parquet")):
            activity_id = path.stem.replace("activity_", "", 1)
            out.append(
                {
                    "donor_id": donor_id,
                    "activity_id": activity_id,
                    "parquet_path": str(path.relative_to(BASE_DIR)),
                    "size_bytes": path.stat().st_size,
                }
            )
    return out


def manifest_needs_multi_fit(manifest: dict[str, Any]) -> bool:
    """True when manifest opts into multi-fit dispatch."""
    if manifest.get("multi_fit"):
        return True
    if manifest.get("default_align_mode") and manifest["default_align_mode"] != "gpx":
        return True
    for spec in manifest.get("activities", []):
        if spec.get("align_mode") and spec["align_mode"] != "gpx":
            return True
        if spec.get("direction") and spec["direction"] != "auto":
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-fit Dale–Alsvik corridor ingest")
    parser.add_argument("--manifest", type=Path, help="Multi-fit manifest JSON")
    parser.add_argument("--discover", action="store_true", help="List washed micro Parquet activities")
    parser.add_argument("--donor", action="append", help="Filter --discover to donor id(s)")
    parser.add_argument("--km-start", type=float, default=None)
    parser.add_argument("--km-end", type=float, default=None)
    parser.add_argument("--step-m", type=float, default=DEFAULT_STEP_M)
    parser.add_argument("--project-course", action="store_true")
    parser.add_argument("--enrich-if-needed", action="store_true")
    args = parser.parse_args()

    if args.discover:
        rows = discover_washed_activities(donors=args.donor)
        print(json.dumps(rows, indent=2))
        return 0

    if not args.manifest:
        parser.error("Provide --manifest or --discover")

    panel, meta = align_manifest_multi(
        args.manifest,
        km_start=args.km_start,
        km_end=args.km_end,
        step_m=args.step_m,
        project_course=args.project_course,
        enrich_if_needed=args.enrich_if_needed,
    )
    print(
        f"OK multi-fit panel n={len(panel)} → {meta.get('panel_path', '(not written)')} "
        f"activities={meta.get('n_activities')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
