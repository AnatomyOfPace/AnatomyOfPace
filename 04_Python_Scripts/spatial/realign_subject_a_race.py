#!/usr/bin/env python3
"""
Stitch Subject_A SUT_43 race alignment onto a full-lap stream grid (km 0.5–41).

Cloud-workspace scaffold when washed race micro is unavailable locally:
  - km 0.5–8.0  ← panel_start_race_1m (Phase E stream align)
  - km 8.001–21.999 ← linear interpolation between nearest finite anchors
  - km 22.0–41.0 ← aligned race spine (existing corridor_multi_fit output)

Production path still requires washed `.fit` micro + corridor_multi_fit on the
full lap; interpolated km 8–22 telemetry is explicitly flagged in sidecar meta.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/realign_subject_a_race.py

    python3 04_Python_Scripts/spatial/realign_subject_a_race.py --dry-run
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
    SUT43_FULL_KM_START,
    SUT43_MIDCOURSE_KM_END,
    SUT43_MIDCOURSE_KM_START,
)
from spatial.spatial_align import (  # noqa: E402
    GRID_NUMERIC_COLS,
    build_course_grid_m,
    compute_mechanical_kappa,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CORRIDOR_DIR = BASE_DIR / "03_Processed_Data" / "spatial" / SUT43_CORRIDOR_ID

DONOR_ID = "Subject_A"
ACTIVITY_ID = "SUT43_20260418"
SESSION_TYPE = "race"

KM_START = SUT43_FULL_KM_START
KM_END = 41.0
GAP_KM_LO = SUT43_MIDCOURSE_KM_START + 0.001
GAP_KM_HI = SUT43_MIDCOURSE_KM_END - 0.001
SPINE_KM_LO = SUT43_MIDCOURSE_KM_END


def _meta_path(corridor_dir: Path) -> Path:
    return corridor_dir / f"aligned_{DONOR_ID}_{ACTIVITY_ID}_race_realign_meta.json"


def _output_path(corridor_dir: Path) -> Path:
    return corridor_dir / f"aligned_{DONOR_ID}_{ACTIVITY_ID}_race.parquet"


def _start_panel_path(corridor_dir: Path) -> Path:
    return corridor_dir / "panel_start_race_1m.parquet"


def _spine_path(corridor_dir: Path) -> Path:
    return corridor_dir / f"aligned_{DONOR_ID}_{ACTIVITY_ID}_race_spine.parquet"


def _load_start_segment(path: Path) -> pd.DataFrame:
    panel = pd.read_parquet(path)
    sub = panel.loc[panel["donor_id"] == DONOR_ID].copy()
    if sub.empty:
        raise ValueError(f"No {DONOR_ID} rows in {path}")

    km = pd.to_numeric(sub["course_km"], errors="coerce")
    mask = (km >= KM_START - 1e-6) & (km <= SUT43_MIDCOURSE_KM_START + 1e-6)
    out = sub.loc[mask].copy()
    out["course_km"] = km.loc[mask].to_numpy(dtype=float)
    out["course_m"] = np.round(out["course_km"] * 1000.0).astype(float)
    return out.sort_values("course_m").reset_index(drop=True)


def _load_spine_segment(path: Path) -> pd.DataFrame:
    spine = pd.read_parquet(path)
    km = pd.to_numeric(spine["activity_course_km"], errors="coerce")
    mask = km >= SPINE_KM_LO - 1e-6
    out = spine.loc[mask].copy()
    out["course_km"] = km.loc[mask].to_numpy(dtype=float)
    out["course_m"] = np.round(out["course_km"] * 1000.0).astype(float)
    return out.sort_values("course_m").reset_index(drop=True)


def _best_anchor_row(frame: pd.DataFrame, *, km_col: str, prefer: str) -> pd.Series:
    """Pick the nearest row with finite telemetry for gap interpolation anchors."""
    numeric_cols = [c for c in GRID_NUMERIC_COLS if c in frame.columns]
    if not numeric_cols:
        raise ValueError("Frame has no numeric telemetry columns for anchoring")

    work = frame.copy()
    work["_km"] = pd.to_numeric(work[km_col], errors="coerce")
    work["_finite"] = work[numeric_cols].apply(pd.to_numeric, errors="coerce").notna().any(axis=1)
    finite = work.loc[work["_finite"]].sort_values("_km")
    if finite.empty:
        raise ValueError(f"No finite telemetry rows in {km_col} window")

    if prefer == "low":
        return finite.iloc[0]
    if prefer == "high":
        return finite.iloc[-1]
    raise ValueError(f"prefer must be 'low' or 'high', got {prefer!r}")


def _interpolate_gap(
    anchor_lo: pd.Series,
    anchor_hi: pd.Series,
    *,
    km_lo: float,
    km_hi: float,
) -> pd.DataFrame:
    grid_m = build_course_grid_m(GAP_KM_LO, GAP_KM_HI)
    grid_km = grid_m / 1000.0
    span = km_hi - km_lo
    if span <= 0:
        raise ValueError(f"Invalid anchor span: {km_lo}–{km_hi}")

    alpha = (grid_km - km_lo) / span
    out: dict[str, Any] = {"course_m": grid_m, "course_km": grid_km}

    for col in GRID_NUMERIC_COLS:
        if col not in anchor_lo.index and col not in anchor_hi.index:
            continue
        v_lo = pd.to_numeric(anchor_lo.get(col), errors="coerce")
        v_hi = pd.to_numeric(anchor_hi.get(col), errors="coerce")
        if pd.notna(v_lo) and pd.notna(v_hi):
            out[col] = v_lo + alpha * (v_hi - v_lo)
        else:
            out[col] = np.full(len(grid_m), np.nan)

    frame = pd.DataFrame(out)
    frame["mechanical_kappa"] = compute_mechanical_kappa(frame)
    return frame


def _harmonize_columns(frames: list[pd.DataFrame]) -> pd.DataFrame:
    keep = [
        "course_m",
        "course_km",
        *GRID_NUMERIC_COLS,
        "mechanical_kappa",
        "donor_id",
        "activity_id",
        "session_type",
    ]
    aligned: list[pd.DataFrame] = []
    for frame in frames:
        sub = frame.copy()
        sub["donor_id"] = DONOR_ID
        sub["activity_id"] = ACTIVITY_ID
        sub["session_type"] = SESSION_TYPE
        cols = [c for c in keep if c in sub.columns]
        aligned.append(sub[cols])

    out = pd.concat(aligned, ignore_index=True)
    out = out.sort_values("course_m").drop_duplicates(subset=["course_m"], keep="first")
    return out.reset_index(drop=True)


def realign_subject_a_race(
    *,
    corridor_dir: Path,
    dry_run: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    start_path = _start_panel_path(corridor_dir)
    spine_path = _spine_path(corridor_dir)
    if not start_path.exists():
        raise FileNotFoundError(f"Phase E start panel missing: {start_path}")
    if not spine_path.exists():
        raise FileNotFoundError(f"Race spine missing: {spine_path}")

    start_seg = _load_start_segment(start_path)
    spine_seg = _load_spine_segment(spine_path)

    anchor_lo = _best_anchor_row(start_seg, km_col="course_km", prefer="high")
    anchor_hi = _best_anchor_row(spine_seg, km_col="course_km", prefer="low")
    gap_seg = _interpolate_gap(
        anchor_lo,
        anchor_hi,
        km_lo=float(anchor_lo["course_km"]),
        km_hi=float(anchor_hi["course_km"]),
    )

    full = _harmonize_columns([start_seg, gap_seg, spine_seg])
    expected_m = int(round((KM_END - KM_START) * 1000)) + 1
    km = full["course_km"]
    meta: dict[str, Any] = {
        "donor_id": DONOR_ID,
        "activity_id": ACTIVITY_ID,
        "session_type": SESSION_TYPE,
        "align_mode": "stream_stitch_scaffold",
        "km_window": [KM_START, KM_END],
        "gap_km_interpolated": [GAP_KM_LO, GAP_KM_HI],
        "sources": {
            "start_segment": str(start_path.relative_to(BASE_DIR)),
            "spine_segment": str(spine_path.relative_to(BASE_DIR)),
        },
        "anchors": {
            "low_km": round(float(anchor_lo["course_km"]), 4),
            "high_km": round(float(anchor_hi["course_km"]), 4),
        },
        "row_count": int(len(full)),
        "expected_row_count": expected_m,
        "km_min": round(float(km.min()), 4),
        "km_max": round(float(km.max()), 4),
        "warning": (
            "km 8.001–21.999 telemetry is linearly interpolated between Phase E start "
            "and spine anchors — not operator gold. Replace via corridor_multi_fit "
            "after washed race micro is available."
        ),
    }

    if len(full) != expected_m:
        meta["row_count_mismatch"] = True

    if not dry_run:
        out_path = _output_path(corridor_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        full.to_parquet(out_path, index=False)
        meta["output"] = str(out_path.relative_to(BASE_DIR))
        _meta_path(corridor_dir).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    return full, meta


def main() -> int:
    parser = argparse.ArgumentParser(description="Stitch Subject_A full-lap race alignment.")
    parser.add_argument("--corridor-dir", type=Path, default=DEFAULT_CORRIDOR_DIR)
    parser.add_argument("--dry-run", action="store_true", help="Build frame without writing parquet")
    args = parser.parse_args()

    full, meta = realign_subject_a_race(corridor_dir=args.corridor_dir, dry_run=args.dry_run)
    action = "Built" if args.dry_run else "Wrote"
    target = meta.get("output", "(dry-run)")
    print(f"{action} {target} ({meta['row_count']} rows, km {meta['km_min']}–{meta['km_max']})")
    if meta.get("row_count_mismatch"):
        print("WARNING: row count does not match expected full-lap grid", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
