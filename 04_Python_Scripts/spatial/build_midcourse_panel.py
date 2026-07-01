#!/usr/bin/env python3
"""
Build stream-axis panel slice for SUT_43 mid-course bridge km 8.0–22.0.

Phase F scaffold: closes the telemetry gap between Phase E start panel
(panel_start_* km 0.5–8.0) and Dale upstream panel (panel_* km 22–41).

Uses washed/aligned race streams on the SUT_43 course axis (activity_course_km
or course_km). Does not require extended reference_spine — stream-distance
course_km matches Phase E start ingest convention until full-lap spine rebuild.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/realign_subject_a_race.py   # Subject_A full-lap stitch (if missing)
    python3 04_Python_Scripts/spatial/build_midcourse_panel.py

    python3 04_Python_Scripts/spatial/build_midcourse_panel.py \\
        --km-start 8.0 --km-end 22.0 \\
        --output 03_Processed_Data/spatial/sut43_terrain_ontology/panel_midcourse_1m.parquet
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

from spatial.corridor_scope import (  # noqa: E402
    SUT43_CORRIDOR_ID,
    SUT43_MIDCOURSE_KM_END,
    SUT43_MIDCOURSE_KM_START,
)

# Mirror spatial_align.GRID_NUMERIC_COLS — avoid fit_micro import chain in cloud workspace.
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
    "mechanical_kappa",
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CORRIDOR_DIR = BASE_DIR / "03_Processed_Data" / "spatial" / SUT43_CORRIDOR_ID
DEFAULT_OUTPUT = DEFAULT_CORRIDOR_DIR / "panel_midcourse_1m.parquet"
DEFAULT_META = DEFAULT_CORRIDOR_DIR / "panel_midcourse_meta.json"

RACE_ACTIVITY_SPECS: list[tuple[str, str]] = [
    ("Subject_A", "SUT43_20260418"),
    ("Subject_B", "19000570862"),
]


def _resolve_course_km(frame: pd.DataFrame) -> pd.Series:
    """Prefer stream course km; fall back to activity_course_km on spine panels."""
    if "course_km" in frame.columns:
        km = pd.to_numeric(frame["course_km"], errors="coerce")
        if km.notna().any():
            return km
    if "activity_course_km" in frame.columns:
        return pd.to_numeric(frame["activity_course_km"], errors="coerce")
    raise ValueError("Aligned frame missing course_km / activity_course_km")


def _aligned_race_path(corridor_dir: Path, donor_id: str, activity_id: str) -> Path | None:
    """Prefer full-grid aligned race parquet; accept spine sidecar when it spans the window."""
    candidates = [
        corridor_dir / f"aligned_{donor_id}_{activity_id}_race.parquet",
        corridor_dir / f"aligned_{donor_id}_{activity_id}_race_spine.parquet",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _extract_race_window(
    path: Path,
    *,
    donor_id: str,
    activity_id: str,
    km_start: float,
    km_end: float,
) -> pd.DataFrame | None:
    frame = pd.read_parquet(path)
    km = _resolve_course_km(frame)
    mask = (km >= km_start - 1e-6) & (km < km_end - 1e-6)
    if not mask.any():
        return None

    sub = frame.loc[mask].copy()
    sub["course_km"] = km.loc[mask].to_numpy(dtype=float)
    sub["course_m"] = np.round(sub["course_km"] * 1000.0).astype(int)
    sub["donor_id"] = donor_id
    sub["activity_id"] = activity_id
    sub["session_type"] = "race"

    keep = ["course_m", "course_km", *GRID_NUMERIC_COLS, "donor_id", "activity_id", "session_type"]
    keep = [c for c in keep if c in sub.columns]
    return sub[keep].reset_index(drop=True)


def build_midcourse_panel(
    *,
    corridor_dir: Path,
    km_start: float,
    km_end: float,
    race_specs: list[tuple[str, str]] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    specs = race_specs or RACE_ACTIVITY_SPECS
    frames: list[pd.DataFrame] = []
    activity_meta: list[dict[str, Any]] = []

    for donor_id, activity_id in specs:
        path = _aligned_race_path(corridor_dir, donor_id, activity_id)
        if path is None:
            activity_meta.append(
                {
                    "donor_id": donor_id,
                    "activity_id": activity_id,
                    "status": "missing_aligned_parquet",
                }
            )
            continue

        slice_df = _extract_race_window(
            path,
            donor_id=donor_id,
            activity_id=activity_id,
            km_start=km_start,
            km_end=km_end,
        )
        if slice_df is None or slice_df.empty:
            activity_meta.append(
                {
                    "donor_id": donor_id,
                    "activity_id": activity_id,
                    "status": "no_rows_in_window",
                    "source": str(path.relative_to(BASE_DIR)),
                }
            )
            continue

        km = slice_df["course_km"]
        activity_meta.append(
            {
                "donor_id": donor_id,
                "activity_id": activity_id,
                "session_type": "race",
                "align_mode": "stream",
                "status": "ok",
                "source": str(path.relative_to(BASE_DIR)),
                "data_km_min": round(float(km.min()), 3),
                "data_km_max": round(float(km.max()), 3),
                "n_finite": int(km.notna().sum()),
            }
        )
        frames.append(slice_df)

    panel = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    window_m = int(round((km_end - km_start) * 1000))
    donors_ok = {m["donor_id"] for m in activity_meta if m.get("status") == "ok"}
    coverage_pct_any = 0.0
    if not panel.empty and window_m > 0:
        union_m = panel["course_m"].nunique()
        coverage_pct_any = round(100.0 * union_m / window_m, 2)

    meta: dict[str, Any] = {
        "phase": "F1_midcourse_bridge",
        "km_window": [km_start, km_end],
        "corridor_id": SUT43_CORRIDOR_ID,
        "activities": activity_meta,
        "donors_in_panel": sorted(donors_ok),
        "coverage_pct_any": coverage_pct_any,
        "note": (
            "Stream-axis race panel for mid-course HITL scaffold. "
            "Reproject to extended reference_spine after build_reference_spine.py --km-start 8 --km-end 41."
        ),
    }
    return panel, meta


def _gap_report(corridor_dir: Path, km_start: float, km_end: float) -> dict[str, Any]:
    """Summarize adjacent panel coverage for operator QC."""
    report: dict[str, Any] = {"km_gap": [km_start, km_end]}
    for label, path in (
        ("start_panel", corridor_dir / "panel_start_race_1m.parquet"),
        ("upstream_panel", corridor_dir / "panel_race_1m.parquet"),
    ):
        if not path.exists():
            report[label] = {"status": "missing"}
            continue
        df = pd.read_parquet(path, columns=["course_km"])
        km = pd.to_numeric(df["course_km"], errors="coerce")
        report[label] = {
            "km_min": round(float(km.min()), 3),
            "km_max": round(float(km.max()), 3),
            "seam_to_midcourse_km": round(float(km.max() if label == "start_panel" else km.min()), 3),
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build SUT_43 mid-course panel km 8–22.")
    parser.add_argument("--corridor-dir", type=Path, default=DEFAULT_CORRIDOR_DIR)
    parser.add_argument("--km-start", type=float, default=SUT43_MIDCOURSE_KM_START)
    parser.add_argument("--km-end", type=float, default=SUT43_MIDCOURSE_KM_END)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META)
    parser.add_argument("--no-race-sidecar", action="store_true", help="Skip panel_midcourse_race_1m.parquet sidecar")
    args = parser.parse_args()

    panel, meta = build_midcourse_panel(
        corridor_dir=args.corridor_dir,
        km_start=args.km_start,
        km_end=args.km_end,
    )
    meta["gap_report"] = _gap_report(args.corridor_dir, args.km_start, args.km_end)

    if panel.empty:
        print("ERROR: no race rows in window — check aligned race parquets and washed micro.", file=sys.stderr)
        args.meta.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(args.output, index=False)
    meta["panel"] = str(args.output.relative_to(BASE_DIR))
    meta["row_count"] = int(len(panel))
    args.meta.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    if not args.no_race_sidecar:
        race_path = args.output.with_name("panel_midcourse_race_1m.parquet")
        race = panel[panel["session_type"] == "race"] if "session_type" in panel.columns else panel
        race.to_parquet(race_path, index=False)
        meta["panel_race"] = str(race_path.relative_to(BASE_DIR))

    print(f"Wrote {args.output} ({len(panel)} rows, donors={meta['donors_in_panel']})")
    print(f"Coverage (union metres / window): {meta['coverage_pct_any']}%")
    print(f"Meta: {args.meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
