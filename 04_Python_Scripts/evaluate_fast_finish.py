#!/usr/bin/env python3
"""Evaluate Sunday fast-finish compliance against a private local blueprint.

Reads:
  - washed micro Parquet (03_Processed_Data/micro/...)
  - config/training_blueprint.local.json (gitignored)
  - config/session_metadata.local.json (gitignored)

Writes (optional):
  - training_compliance.local.db session_summaries (gitignored)

Does not touch anatomy_macro.db. Personal nutrition / body-mass anchors are
never required for pace evaluation and are never written to public paths.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
MICRO_DIR = BASE_DIR / "03_Processed_Data" / "micro"
DEFAULT_BLUEPRINT = BASE_DIR / "config" / "training_blueprint.local.json"
DEFAULT_SESSION_META = BASE_DIR / "config" / "session_metadata.local.json"
DEFAULT_COMPLIANCE_DB = BASE_DIR / "training_compliance.local.db"
MACRO_DB = BASE_DIR / "05_Macro_Database" / "anatomy_macro.db"


@dataclass
class FastFinishResult:
    activity_id: str
    subject_id: str
    session_type: str
    week_id: str | None
    stream_distance_km: float
    fast_finish_km: float
    window_start_km: float
    window_end_km: float
    median_pace_min_per_km: float | None
    target_pace_min_per_km: float
    pace_delta_sec_per_km: float | None
    cardiac_drift_bpm: float | None
    compliance_score: float
    held_target: bool
    skipped_reason: str | None = None


def pace_str_to_min_per_km(value: str | float | int) -> float:
    """Parse '4:44' or numeric minutes-per-km into float minutes."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if ":" in text:
        minutes, seconds = text.split(":", 1)
        return float(minutes) + float(seconds) / 60.0
    return float(text)


def min_per_km_to_mps(pace_min_per_km: float) -> float:
    if pace_min_per_km <= 0:
        raise ValueError("pace_min_per_km must be positive")
    return 1000.0 / (pace_min_per_km * 60.0)


def mps_to_min_per_km(speed_mps: float) -> float | None:
    if speed_mps is None or not math.isfinite(speed_mps) or speed_mps <= 0:
        return None
    return 1000.0 / (speed_mps * 60.0)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing local config: {path}. Copy the matching *.local.example.json "
            "to a gitignored *.local.json first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_fast_finish_km(
    blueprint: dict[str, Any],
    *,
    month_key: str | None,
    is_recovery_week: bool,
) -> float | None:
    sunday = blueprint.get("week_matrix", {}).get("sunday", {})
    ff = sunday.get("fast_finish") or {}
    if not ff.get("enabled", True):
        return None
    if is_recovery_week and (ff.get("recovery_week") or {}).get("drop_fast_finish", True):
        return None

    progression = ff.get("progression_by_month") or {}
    if month_key and month_key in progression:
        band = progression[month_key]
        lo = float(band.get("fast_finish_km_min", band.get("fast_finish_km", 2.0)))
        hi = float(band.get("fast_finish_km_max", lo))
        return (lo + hi) / 2.0

    return float(ff.get("default_fast_finish_km", 2.0))


def micro_path(donor_id: str, activity_id: str) -> Path:
    safe = donor_id.replace("/", "_")
    return MICRO_DIR / safe / f"activity_{activity_id}.parquet"


def stream_km_series(frame: pd.DataFrame) -> pd.Series:
    if "course_km" in frame.columns and frame["course_km"].notna().any():
        km = pd.to_numeric(frame["course_km"], errors="coerce")
        if km.notna().any():
            return km
    if "distance_m" not in frame.columns:
        raise ValueError("ActivityFrame missing distance_m / course_km")
    return pd.to_numeric(frame["distance_m"], errors="coerce") / 1000.0


def compute_cardiac_drift_bpm(window: pd.DataFrame) -> float | None:
    if "heart_rate" not in window.columns or "speed_mps" not in window.columns:
        return None
    hr = pd.to_numeric(window["heart_rate"], errors="coerce")
    spd = pd.to_numeric(window["speed_mps"], errors="coerce")
    valid = window.assign(_hr=hr, _spd=spd).dropna(subset=["_hr", "_spd"])
    if len(valid) < 20:
        return None
    # Stable-speed mask: within 10% of median speed
    med_spd = float(valid["_spd"].median())
    if med_spd <= 0:
        return None
    stable = valid[(valid["_spd"] >= 0.9 * med_spd) & (valid["_spd"] <= 1.1 * med_spd)]
    if len(stable) < 20:
        return None
    third = max(len(stable) // 3, 1)
    early = float(stable["_hr"].iloc[:third].mean())
    late = float(stable["_hr"].iloc[-third:].mean())
    return late - early


def score_fast_finish(
    *,
    median_pace: float | None,
    target_pace: float,
    tolerance_sec_per_km: float,
    cardiac_drift_bpm: float | None,
) -> tuple[float, bool, float | None]:
    if median_pace is None:
        return 0.0, False, None
    delta_sec = (median_pace - target_pace) * 60.0
    # Pace component: 100 at exact target; linear down to 0 at 3× tolerance slow
    pace_score = max(0.0, 100.0 - max(0.0, delta_sec) * (100.0 / (3.0 * tolerance_sec_per_km)))
    # Slight bonus if faster than target (capped)
    if delta_sec < 0:
        pace_score = min(100.0, 100.0 + min(5.0, -delta_sec))
    held = delta_sec <= tolerance_sec_per_km

    drift_penalty = 0.0
    if cardiac_drift_bpm is not None and cardiac_drift_bpm > 8.0:
        drift_penalty = min(15.0, (cardiac_drift_bpm - 8.0) * 1.5)

    score = max(0.0, min(100.0, pace_score - drift_penalty))
    return score, held, delta_sec


def evaluate_activity(
    frame: pd.DataFrame,
    *,
    activity_id: str,
    blueprint: dict[str, Any],
    session_meta: dict[str, Any],
) -> FastFinishResult:
    subject_id = str(
        session_meta.get("subject_id")
        or blueprint.get("subject_id")
        or "Subject_A"
    )
    session_type = str(session_meta.get("session_type", "unknown"))
    week_id = session_meta.get("week_id")
    is_recovery = bool(session_meta.get("is_recovery_week", False))
    month_key = session_meta.get("month_key")

    sunday = blueprint.get("week_matrix", {}).get("sunday", {})
    ff = sunday.get("fast_finish") or {}
    target_pace = pace_str_to_min_per_km(ff.get("target_pace_min_per_km", "4:44"))
    tolerance = float(ff.get("tolerance_sec_per_km", 5.0))

    km = stream_km_series(frame)
    end_km = float(np.nanmax(km.to_numpy(dtype=float)))
    start_stream = float(np.nanmin(km.to_numpy(dtype=float)))
    stream_distance_km = max(0.0, end_km - start_stream)

    finish_km = resolve_fast_finish_km(
        blueprint, month_key=month_key, is_recovery_week=is_recovery
    )
    if finish_km is None:
        return FastFinishResult(
            activity_id=activity_id,
            subject_id=subject_id,
            session_type=session_type,
            week_id=week_id,
            stream_distance_km=stream_distance_km,
            fast_finish_km=0.0,
            window_start_km=end_km,
            window_end_km=end_km,
            median_pace_min_per_km=None,
            target_pace_min_per_km=target_pace,
            pace_delta_sec_per_km=None,
            cardiac_drift_bpm=None,
            compliance_score=0.0,
            held_target=False,
            skipped_reason="fast_finish_disabled_or_recovery_week",
        )

    if session_type != "sunday_simulator":
        return FastFinishResult(
            activity_id=activity_id,
            subject_id=subject_id,
            session_type=session_type,
            week_id=week_id,
            stream_distance_km=stream_distance_km,
            fast_finish_km=finish_km,
            window_start_km=end_km,
            window_end_km=end_km,
            median_pace_min_per_km=None,
            target_pace_min_per_km=target_pace,
            pace_delta_sec_per_km=None,
            cardiac_drift_bpm=None,
            compliance_score=0.0,
            held_target=False,
            skipped_reason=f"session_type_not_sunday_simulator:{session_type}",
        )

    window_start = max(start_stream, end_km - finish_km)
    mask = (km >= window_start) & (km <= end_km)
    window = frame.loc[mask].copy()
    if window.empty:
        return FastFinishResult(
            activity_id=activity_id,
            subject_id=subject_id,
            session_type=session_type,
            week_id=week_id,
            stream_distance_km=stream_distance_km,
            fast_finish_km=finish_km,
            window_start_km=window_start,
            window_end_km=end_km,
            median_pace_min_per_km=None,
            target_pace_min_per_km=target_pace,
            pace_delta_sec_per_km=None,
            cardiac_drift_bpm=None,
            compliance_score=0.0,
            held_target=False,
            skipped_reason="empty_fast_finish_window",
        )

    speed = pd.to_numeric(window.get("speed_mps"), errors="coerce")
    if speed is None or speed.notna().sum() == 0:
        # Derive from distance/time if needed
        if "elapsed_s" in window.columns and "distance_m" in window.columns:
            d = pd.to_numeric(window["distance_m"], errors="coerce").diff()
            t = pd.to_numeric(window["elapsed_s"], errors="coerce").diff()
            speed = d / t.replace(0, np.nan)
        else:
            speed = pd.Series(np.nan, index=window.index)

    median_speed = float(speed.replace([np.inf, -np.inf], np.nan).median())
    median_pace = mps_to_min_per_km(median_speed)
    drift = compute_cardiac_drift_bpm(window)
    score, held, delta_sec = score_fast_finish(
        median_pace=median_pace,
        target_pace=target_pace,
        tolerance_sec_per_km=tolerance,
        cardiac_drift_bpm=drift,
    )

    return FastFinishResult(
        activity_id=activity_id,
        subject_id=subject_id,
        session_type=session_type,
        week_id=week_id,
        stream_distance_km=stream_distance_km,
        fast_finish_km=finish_km,
        window_start_km=window_start,
        window_end_km=end_km,
        median_pace_min_per_km=median_pace,
        target_pace_min_per_km=target_pace,
        pace_delta_sec_per_km=delta_sec,
        cardiac_drift_bpm=drift,
        compliance_score=score,
        held_target=held,
        skipped_reason=None,
    )


def write_session_summary(db_path: Path, result: FastFinishResult) -> None:
    resolved = db_path.resolve()
    if resolved == MACRO_DB.resolve() or "anatomy_macro" in resolved.name:
        raise SystemExit("Refusing to write compliance into anatomy_macro.db")
    if not resolved.exists():
        raise FileNotFoundError(
            f"Compliance DB missing: {resolved}. Run init_training_compliance_local.py first."
        )

    payload = asdict(result)
    conn = sqlite3.connect(resolved)
    try:
        conn.execute(
            """
            INSERT INTO session_summaries (
                activity_id, subject_id, session_type, week_id,
                stream_distance_km, fast_finish_km, median_pace_min_per_km,
                target_pace_min_per_km, pace_delta_sec_per_km, cardiac_drift_bpm,
                compliance_score, held_target, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(activity_id) DO UPDATE SET
                subject_id=excluded.subject_id,
                session_type=excluded.session_type,
                week_id=excluded.week_id,
                stream_distance_km=excluded.stream_distance_km,
                fast_finish_km=excluded.fast_finish_km,
                median_pace_min_per_km=excluded.median_pace_min_per_km,
                target_pace_min_per_km=excluded.target_pace_min_per_km,
                pace_delta_sec_per_km=excluded.pace_delta_sec_per_km,
                cardiac_drift_bpm=excluded.cardiac_drift_bpm,
                compliance_score=excluded.compliance_score,
                held_target=excluded.held_target,
                details_json=excluded.details_json,
                created_at=datetime('now')
            """,
            (
                result.activity_id,
                result.subject_id,
                result.session_type,
                result.week_id,
                result.stream_distance_km,
                result.fast_finish_km,
                result.median_pace_min_per_km,
                result.target_pace_min_per_km,
                result.pace_delta_sec_per_km,
                result.cardiac_drift_bpm,
                result.compliance_score,
                1 if result.held_target else 0,
                json.dumps(payload),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def format_pace(min_per_km: float | None) -> str:
    if min_per_km is None or not math.isfinite(min_per_km):
        return "n/a"
    total_sec = int(round(min_per_km * 60.0))
    return f"{total_sec // 60}:{total_sec % 60:02d}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score Sunday fast-finish vs private local blueprint (meso only)."
    )
    parser.add_argument("--activity-id", required=True, help="Washed micro activity_id")
    parser.add_argument(
        "--donor-id",
        default=None,
        help="Micro donor folder (default: session metadata / blueprint subject_id)",
    )
    parser.add_argument("--blueprint", type=Path, default=DEFAULT_BLUEPRINT)
    parser.add_argument("--session-meta", type=Path, default=DEFAULT_SESSION_META)
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="Upsert result into training_compliance.local.db",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_COMPLIANCE_DB)
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path for machine-readable result (keep under gitignored local dirs)",
    )
    args = parser.parse_args(argv)

    blueprint = load_json(args.blueprint)
    meta_root = load_json(args.session_meta)
    activities = meta_root.get("activities") or {}
    if args.activity_id not in activities:
        raise SystemExit(
            f"activity_id {args.activity_id!r} not in {args.session_meta}. "
            "Tag the session in session_metadata.local.json first."
        )
    session_meta = {
        "subject_id": meta_root.get("subject_id", blueprint.get("subject_id")),
        **activities[args.activity_id],
    }
    donor_id = args.donor_id or meta_root.get("donor_id") or session_meta.get("subject_id")
    path = micro_path(str(donor_id), args.activity_id)
    if not path.exists():
        raise SystemExit(f"Micro Parquet not found: {path}")

    frame = pd.read_parquet(path)
    result = evaluate_activity(
        frame,
        activity_id=args.activity_id,
        blueprint=blueprint,
        session_meta=session_meta,
    )

    print("fast_finish_evaluation")
    print(f"  activity_id:        {result.activity_id}")
    print(f"  subject_id:         {result.subject_id}")
    print(f"  session_type:       {result.session_type}")
    print(f"  stream_distance_km: {result.stream_distance_km:.2f}")
    print(f"  fast_finish_km:     {result.fast_finish_km:.2f}")
    print(
        f"  window_km:          {result.window_start_km:.2f} → {result.window_end_km:.2f}"
    )
    print(f"  median_pace:        {format_pace(result.median_pace_min_per_km)} min/km")
    print(f"  target_pace:        {format_pace(result.target_pace_min_per_km)} min/km")
    if result.pace_delta_sec_per_km is not None:
        print(f"  pace_delta_s/km:    {result.pace_delta_sec_per_km:+.1f}")
    if result.cardiac_drift_bpm is not None:
        print(f"  cardiac_drift_bpm:  {result.cardiac_drift_bpm:+.1f}")
    print(f"  compliance_score:   {result.compliance_score:.1f}")
    print(f"  held_target:        {result.held_target}")
    if result.skipped_reason:
        print(f"  skipped_reason:     {result.skipped_reason}")

    if args.write_db:
        write_session_summary(args.db, result)
        print(f"  wrote_local_db:     {args.db}")

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8"
        )
        print(f"  wrote_json:         {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
