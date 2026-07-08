#!/usr/bin/env python3
"""
Phase A — multi-athlete spatial alignment on a unified 1 m course grid.

Ingests washed ActivityFrame Parquet (Wave 2 micro tier), snaps to organiser
GPX course axis (SUT_160), crops Dale CP → Paradisskaret Downhill end, and
resamples onto a shared distance grid. Supports race-day and training-tile
sessions per donor via session_type tag (v2.0).

Outputs:
  - Per-activity aligned Parquet under 03_Processed_Data/spatial/{corridor_id}/
  - Stacked panel Parquet (long format: donor_id, activity_id, session_type, course_m, …)
  - Split panels: panel_race_1m.parquet, panel_training_1m.parquet
  - Sidecar align_meta.json with corridor window and grid stats

Usage (from repo root):
    python3 04_Python_Scripts/spatial/spatial_align.py \\
        --donor Reference_Elite_D --activity 18159079828 \\
        --project-course --enrich-if-needed

    python3 04_Python_Scripts/spatial/spatial_align.py \\
        --manifest config/spatial_align_manifest.example.json
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from fit_micro.activity_frame import read_parquet, write_parquet  # noqa: E402
from fit_micro.course_project import (  # noqa: E402
    ORGANISER_GPX_DIR,
    RACE_GPX,
    load_gpx_course_km,
    project_course_km,
)
from fit_micro.ti_enrich import enrich_ti  # noqa: E402
from spatial.corridor_scope import (  # noqa: E402
    STRESS_TEST_CORRIDOR_ID,
    STRESS_TEST_RACE_ID,
    load_experiment_window,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SPATIAL_DIR = BASE_DIR / "03_Processed_Data" / "spatial"
DEFAULT_GPX = ORGANISER_GPX_DIR / RACE_GPX[STRESS_TEST_RACE_ID]
DEFAULT_STEP_M = 1.0
SessionType = Literal["race", "training"]
VALID_SESSION_TYPES: tuple[SessionType, ...] = ("race", "training")
DEFAULT_MAX_WORKERS = 4

# Columns interpolated onto the 1 m grid (numeric telemetry + derived metrics).
GRID_NUMERIC_COLS = (
    "altitude_m",
    "heart_rate",
    "cadence_spm",
    "speed_mps",
    "grade",
    "grade_pct",
    "pace_gap_flat",
    "pace_expected",
    "ti",
    "ti_raw",
    "latitude",
    "longitude",
    "vertical_oscillation_mm",
    "vertical_ratio_pct",
    "step_length_m",
    "stance_time_ms",
    "power_w",
)


def spatial_output_dir(corridor_id: str = STRESS_TEST_CORRIDOR_ID) -> Path:
    return SPATIAL_DIR / corridor_id


def aligned_parquet_path(
    donor_id: str,
    activity_id: str,
    *,
    corridor_id: str = STRESS_TEST_CORRIDOR_ID,
    session_type: SessionType | None = None,
) -> Path:
    safe_donor = donor_id.replace("/", "_")
    suffix = f"_{session_type}" if session_type else ""
    return spatial_output_dir(corridor_id) / f"aligned_{safe_donor}_{activity_id}{suffix}.parquet"


def validate_session_type(session_type: str) -> SessionType:
    if session_type not in VALID_SESSION_TYPES:
        raise ValueError(f"session_type must be one of {VALID_SESSION_TYPES}, got {session_type!r}")
    return session_type  # type: ignore[return-value]


def panel_parquet_path(*, corridor_id: str = STRESS_TEST_CORRIDOR_ID) -> Path:
    return spatial_output_dir(corridor_id) / "panel_1m.parquet"


def _resolve_course_km(frame: pd.DataFrame) -> pd.Series:
    if "course_km" in frame.columns and frame["course_km"].notna().any():
        return pd.to_numeric(frame["course_km"], errors="coerce")
    if "distance_m" in frame.columns:
        return pd.to_numeric(frame["distance_m"], errors="coerce") / 1000.0
    raise ValueError("Frame lacks course_km and distance_m")


def crop_corridor(
    frame: pd.DataFrame,
    km_start: float,
    km_end: float,
) -> pd.DataFrame:
    km = _resolve_course_km(frame)
    lo, hi = min(km_start, km_end), max(km_start, km_end)
    mask = (km >= lo) & (km <= hi)
    out = frame.loc[mask].copy()
    out["course_km"] = km.loc[mask].to_numpy()
    return out.reset_index(drop=True)


def build_course_grid_m(km_start: float, km_end: float, step_m: float = DEFAULT_STEP_M) -> np.ndarray:
    lo_m = min(km_start, km_end) * 1000.0
    hi_m = max(km_start, km_end) * 1000.0
    if hi_m <= lo_m:
        raise ValueError(f"Invalid corridor span: {km_start}–{km_end} km")
    # Inclusive upper bound at 1 m resolution.
    return np.arange(lo_m, hi_m + step_m * 0.5, step_m, dtype=float)


def resample_to_grid_1m(
    frame: pd.DataFrame,
    km_start: float,
    km_end: float,
    *,
    step_m: float = DEFAULT_STEP_M,
) -> pd.DataFrame:
    """
    Interpolate numeric telemetry onto a uniform course-distance grid (metres).

    Uses course_km as the independent axis. Duplicate km samples are collapsed
    by median before interpolation.
    """
    if frame.empty:
        raise ValueError("Cannot resample an empty frame")

    work = frame.copy()
    work["course_m"] = _resolve_course_km(work) * 1000.0
    work = work.sort_values("course_m")
    work = work.groupby("course_m", as_index=False).median(numeric_only=True)

    grid_m = build_course_grid_m(km_start, km_end, step_m=step_m)
    out: dict[str, Any] = {
        "course_m": grid_m,
        "course_km": grid_m / 1000.0,
    }

    x = work["course_m"].to_numpy(dtype=float)
    for col in GRID_NUMERIC_COLS:
        if col not in work.columns:
            continue
        y = pd.to_numeric(work[col], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(x) & np.isfinite(y)
        if valid.sum() < 2:
            out[col] = np.full(len(grid_m), np.nan)
            continue
        out[col] = np.interp(grid_m, x[valid], y[valid], left=np.nan, right=np.nan)

    return pd.DataFrame(out)


def compute_mechanical_kappa(frame: pd.DataFrame) -> pd.Series:
    """
    Mechanical braking proxy κ — grade magnitude × residual TI above unity.

    Full ceGAP-aware κ deferred to Phase B; scaffold uses Minetti TI residual.
    """
    grade_raw = frame.get("grade_pct", frame.get("grade"))
    if grade_raw is None:
        grade = pd.Series(0.0, index=frame.index)
    else:
        grade = pd.to_numeric(grade_raw, errors="coerce")
    if "ti" in frame.columns:
        ti = pd.to_numeric(frame["ti"], errors="coerce")
    else:
        ti = pd.Series(1.0, index=frame.index)
    residual = (ti - 1.0).clip(lower=0.0)
    return (grade.abs() / 100.0) * residual


def load_activity_frame(
    donor_id: str,
    activity_id: str,
    *,
    project_course: bool = False,
    enrich_if_needed: bool = False,
    race_id: str = STRESS_TEST_RACE_ID,
    gpx_path: Path | None = None,
    subject_id: str | None = None,
) -> pd.DataFrame:
    frame = read_parquet(donor_id, activity_id)

    if project_course or frame["course_km"].isna().all():
        frame = project_course_km(frame, race_id=race_id, gpx_path=gpx_path)

    if enrich_if_needed and "ti" not in frame.columns:
        frame, _ = enrich_ti(frame, subject_id=subject_id or donor_id)

    return frame


def align_activity(
    donor_id: str,
    activity_id: str,
    *,
    km_start: float | None = None,
    km_end: float | None = None,
    step_m: float = DEFAULT_STEP_M,
    project_course: bool = False,
    enrich_if_needed: bool = False,
    race_id: str = STRESS_TEST_RACE_ID,
    corridor_id: str = STRESS_TEST_CORRIDOR_ID,
    gpx_path: Path | None = None,
    subject_id: str | None = None,
    session_type: SessionType = "race",
    write: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Align one washed activity to the corridor 1 m grid."""
    session_type = validate_session_type(session_type)
    start, end, corridor_meta = load_experiment_window(
        race_id, km_start=km_start, km_end=km_end
    )
    corridor_meta["corridor_id"] = corridor_id

    frame = load_activity_frame(
        donor_id,
        activity_id,
        project_course=project_course,
        enrich_if_needed=enrich_if_needed,
        race_id=race_id,
        gpx_path=gpx_path,
        subject_id=subject_id,
    )
    cropped = crop_corridor(frame, start, end)
    grid = resample_to_grid_1m(cropped, start, end, step_m=step_m)
    grid["mechanical_kappa"] = compute_mechanical_kappa(grid)
    grid["donor_id"] = donor_id
    grid["activity_id"] = str(activity_id)
    grid["session_type"] = session_type

    meta: dict[str, Any] = {
        **corridor_meta,
        "donor_id": donor_id,
        "activity_id": str(activity_id),
        "session_type": session_type,
        "step_m": step_m,
        "n_grid": int(len(grid)),
        "n_source_samples": int(len(cropped)),
        "gpx_anchor": str(
            gpx_path
            or ORGANISER_GPX_DIR / RACE_GPX.get(race_id, RACE_GPX[STRESS_TEST_RACE_ID])
        ),
        "has_ti": bool(grid["ti"].notna().any()) if "ti" in grid.columns else False,
        "has_hr": bool(grid["heart_rate"].notna().any()) if "heart_rate" in grid.columns else False,
    }

    if write:
        out_path = aligned_parquet_path(donor_id, activity_id, corridor_id=corridor_id, session_type=session_type)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        grid.to_parquet(out_path, index=False)
        meta["output_path"] = str(out_path.relative_to(BASE_DIR))

    return grid, meta


def _align_activity_from_spec(
    spec: dict[str, Any],
    *,
    km_start: float | None,
    km_end: float | None,
    step_m: float,
    project_course: bool,
    enrich_if_needed: bool,
    race_id: str = STRESS_TEST_RACE_ID,
    corridor_id: str = STRESS_TEST_CORRIDOR_ID,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    session_type = validate_session_type(spec.get("session_type", "race"))
    return align_activity(
        spec["donor_id"],
        spec["activity_id"],
        km_start=km_start,
        km_end=km_end,
        step_m=step_m,
        project_course=project_course,
        enrich_if_needed=enrich_if_needed,
        race_id=race_id,
        corridor_id=corridor_id,
        subject_id=spec.get("subject_id"),
        session_type=session_type,
        write=True,
    )


def align_panel(
    activities: list[dict[str, Any]],
    *,
    km_start: float | None = None,
    km_end: float | None = None,
    step_m: float = DEFAULT_STEP_M,
    project_course: bool = False,
    enrich_if_needed: bool = False,
    race_id: str = STRESS_TEST_RACE_ID,
    corridor_id: str = STRESS_TEST_CORRIDOR_ID,
    write_panel: bool = True,
    max_workers: int = DEFAULT_MAX_WORKERS,
    async_batch: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Align multiple donor activities and stack into a long-format panel."""
    frames: list[pd.DataFrame] = []
    run_meta: list[dict[str, Any]] = []

    def _run(spec: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
        return _align_activity_from_spec(
            spec,
            km_start=km_start,
            km_end=km_end,
            step_m=step_m,
            project_course=project_course,
            enrich_if_needed=enrich_if_needed,
            race_id=race_id,
            corridor_id=corridor_id,
        )

    if async_batch and len(activities) > 1:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(activities))) as pool:
            futures = {pool.submit(_run, spec): spec for spec in activities}
            for fut in as_completed(futures):
                grid, meta = fut.result()
                frames.append(grid)
                run_meta.append(meta)
    else:
        for spec in activities:
            grid, meta = _run(spec)
            frames.append(grid)
            run_meta.append(meta)

    panel = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    _, _, corridor_meta = load_experiment_window(race_id, km_start=km_start, km_end=km_end)
    corridor_meta["corridor_id"] = corridor_id
    session_counts = (
        panel.groupby("session_type")["activity_id"].nunique().to_dict()
        if not panel.empty and "session_type" in panel.columns
        else {}
    )
    panel_meta: dict[str, Any] = {
        **corridor_meta,
        "step_m": step_m,
        "n_activities": len(activities),
        "session_type_counts": session_counts,
        "async_batch": async_batch,
        "activities": run_meta,
    }

    if write_panel and not panel.empty:
        path = panel_parquet_path(corridor_id=corridor_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        panel.to_parquet(path, index=False)
        panel_meta["panel_path"] = str(path.relative_to(BASE_DIR))

        # Split race vs training panels for downstream Phase B/C convenience.
        if "session_type" in panel.columns:
            for st in VALID_SESSION_TYPES:
                sub = panel[panel["session_type"] == st]
                if not sub.empty:
                    sub_path = path.with_name(f"panel_{st}_1m.parquet")
                    sub.to_parquet(sub_path, index=False)
                    panel_meta[f"panel_{st}_path"] = str(sub_path.relative_to(BASE_DIR))

        sidecar = path.with_name("align_meta.json")
        sidecar.write_text(json.dumps(panel_meta, indent=2), encoding="utf-8")
        panel_meta["meta_path"] = str(sidecar.relative_to(BASE_DIR))

    return panel, panel_meta


def load_manifest(path: Path) -> dict[str, Any]:
    """Load manifest envelope: corridor_id, race_id, activities[]."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"activities": payload}
    return payload


def load_manifest_activities(path: Path) -> list[dict[str, Any]]:
    return load_manifest(path).get("activities", [])


def gpx_elevation_profile(
    gpx_path: Path | None = None,
    km_start: float | None = None,
    km_end: float | None = None,
    race_id: str = STRESS_TEST_RACE_ID,
) -> pd.DataFrame:
    """Reference organiser GPX elevation on the corridor window (no athlete overlay)."""
    from fit_micro.course_project import RACE_GPX

    path = gpx_path or ORGANISER_GPX_DIR / RACE_GPX.get(race_id, RACE_GPX[STRESS_TEST_RACE_ID])
    course = load_gpx_course_km(path)
    start, end, _ = load_experiment_window(race_id, km_start=km_start, km_end=km_end)
    sub = course[(course["distance_km"] >= start) & (course["distance_km"] <= end)].copy()
    sub["course_m"] = sub["distance_km"] * 1000.0
    return sub.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase A — align micro Parquet onto SUT_160 1 m course grid",
    )
    parser.add_argument("--donor", help="Donor ID (e.g. Reference_Elite_D)")
    parser.add_argument("--activity", help="Activity ID (e.g. 18159079828)")
    parser.add_argument(
        "--manifest",
        type=Path,
        help="JSON manifest: activities[] with donor_id, activity_id, session_type (race|training)",
    )
    parser.add_argument(
        "--session-type",
        choices=VALID_SESSION_TYPES,
        default="race",
        help="Session tag for single --donor/--activity run (default race)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="Thread pool size for manifest batch ingest (default 4)",
    )
    parser.add_argument(
        "--no-async",
        action="store_true",
        help="Disable parallel manifest ingest",
    )
    parser.add_argument("--km-start", type=float, default=None, help="Corridor start km (default 140.0)")
    parser.add_argument("--km-end", type=float, default=None, help="Corridor end km (default 155.58)")
    parser.add_argument("--step-m", type=float, default=DEFAULT_STEP_M, help="Grid step metres (default 1)")
    parser.add_argument(
        "--project-course",
        action="store_true",
        help="GPX snap course_km before crop (required if Parquet lacks projection)",
    )
    parser.add_argument(
        "--enrich-if-needed",
        action="store_true",
        help="Run GAP/TI enrichment when ti column is missing",
    )
    parser.add_argument("--race", default=STRESS_TEST_RACE_ID)
    parser.add_argument(
        "--corridor-id",
        default=STRESS_TEST_CORRIDOR_ID,
        help="Output subdirectory under 03_Processed_Data/spatial/",
    )
    parser.add_argument("--gpx", type=Path, default=None, help="Override organiser GPX path")
    parser.add_argument("--subject", default=None, help="Anchor subject for TI enrichment")
    parser.add_argument(
        "--gpx-profile-only",
        action="store_true",
        help="Print GPX corridor elevation stats and exit (no athlete ingest)",
    )
    args = parser.parse_args()

    if args.gpx_profile_only:
        prof = gpx_elevation_profile(args.gpx, args.km_start, args.km_end, race_id=args.race)
        start, end, meta = load_experiment_window(args.race, km_start=args.km_start, km_end=args.km_end)
        gpx_name = (args.gpx or DEFAULT_GPX).name if args.race == STRESS_TEST_RACE_ID else f"race={args.race}"
        span_km = prof["distance_km"].max() - prof["distance_km"].min() if len(prof) else 0.0
        print(
            f"GPX corridor km {start:.2f}–{end:.2f}: "
            f"{len(prof)} track vertices, span {span_km:.2f} km ({gpx_name})"
        )
        print(json.dumps(meta, indent=2))
        return

    if args.manifest:
        manifest = load_manifest(args.manifest)
        from spatial.corridor_multi_fit import align_manifest_multi, manifest_needs_multi_fit

        if manifest_needs_multi_fit(manifest):
            panel, meta = align_manifest_multi(
                args.manifest,
                km_start=args.km_start,
                km_end=args.km_end,
                step_m=args.step_m,
                project_course=args.project_course,
                enrich_if_needed=args.enrich_if_needed,
            )
            counts = {
                st: sum(1 for a in meta.get("activities", []) if a.get("session_type") == st)
                for st in VALID_SESSION_TYPES
            }
            print(
                f"OK multi-fit panel n={len(panel)} → {meta.get('panel_path', '(not written)')} "
                f"(sessions: {counts})"
            )
            return

        activities = manifest.get("activities", [])
        race_id = manifest.get("race_id", args.race)
        corridor_id = manifest.get("corridor_id", STRESS_TEST_CORRIDOR_ID)
        km_start = args.km_start
        km_end = args.km_end
        if km_start is None and "km_analysis_window" in manifest:
            win = manifest["km_analysis_window"]
            km_start, km_end = float(win[0]), float(win[1])
        panel, meta = align_panel(
            activities,
            km_start=km_start,
            km_end=km_end,
            step_m=args.step_m,
            project_course=args.project_course,
            enrich_if_needed=args.enrich_if_needed,
            race_id=race_id,
            corridor_id=corridor_id,
            max_workers=args.max_workers,
            async_batch=not args.no_async,
        )
        counts = meta.get("session_type_counts", {})
        print(
            f"OK panel n={len(panel)} → {meta.get('panel_path', '(not written)')} "
            f"(sessions: {counts})"
        )
        return

    if not args.donor or not args.activity:
        parser.error("Provide --donor and --activity, or --manifest, or --gpx-profile-only")

    grid, meta = align_activity(
        args.donor,
        args.activity,
        km_start=args.km_start,
        km_end=args.km_end,
        step_m=args.step_m,
        project_course=args.project_course,
        enrich_if_needed=args.enrich_if_needed,
        race_id=args.race,
        corridor_id=args.corridor_id,
        gpx_path=args.gpx,
        subject_id=args.subject or args.donor,
        session_type=args.session_type,
    )
    print(f"OK n={len(grid)} grid → {meta.get('output_path')}")


if __name__ == "__main__":
    main()
