#!/usr/bin/env python3
"""
Per-metre ML feature matrix for gramstad_band terrain classification.

Aggregates panel telemetry, consensus NTI, per-athlete TI deltas, and v2 vote
columns into one row per course_m for km 29–41.
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

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "04_Python_Scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "04_Python_Scripts"))

from spatial.corridor_scope import SUT43_PRIMARY_KM_END, SUT43_PRIMARY_KM_START
from spatial.terrain_map_gen import consensus_nti_at_course_m

DEFAULT_PANEL = (
    _REPO_ROOT / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "panel_1m.parquet"
)
DEFAULT_MAJORITY = (
    _REPO_ROOT / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "hitl_v2_majority.parquet"
)
DEFAULT_OUTPUT = (
    _REPO_ROOT
    / "03_Processed_Data"
    / "spatial"
    / "sut43_terrain_ontology"
    / "ml_features_1m.parquet"
)

# Rolling pace-irregularity windows (metres, 1 m grid, centered).
PACE_IRREGULARITY_WINDOWS_M = (25, 100, 250)
# Walk/stop guard — windows whose min speed falls below this get NaN jerk stats.
WALK_SPEED_THRESHOLD_MPS = 0.5


def _resolve_panel_km(panel: pd.DataFrame) -> pd.Series:
    if "course_km" in panel.columns and panel["course_km"].notna().any():
        return pd.to_numeric(panel["course_km"], errors="coerce")
    if "ref_chainage_m" in panel.columns:
        return pd.to_numeric(panel["ref_chainage_m"], errors="coerce") / 1000.0
    if "activity_course_km" in panel.columns:
        return pd.to_numeric(panel["activity_course_km"], errors="coerce")
    raise ValueError("Panel lacks course_km / ref_chainage_m / activity_course_km")


def _filter_panel(
    panel: pd.DataFrame,
    *,
    km_lo: float,
    km_hi: float,
    session_type: str | None = "race",
) -> pd.DataFrame:
    work = panel.copy()
    if session_type and "session_type" in work.columns:
        work = work[work["session_type"] == session_type]
    km = _resolve_panel_km(work)
    work = work.assign(course_km=km)
    if "course_m" not in work.columns:
        work = work.assign(course_m=np.round(work["course_km"] * 1000.0))
    else:
        work["course_m"] = pd.to_numeric(work["course_m"], errors="coerce")
        missing = work["course_m"].isna()
        if missing.any():
            work.loc[missing, "course_m"] = np.round(work.loc[missing, "course_km"] * 1000.0)
    return work[(work["course_km"] >= km_lo) & (work["course_km"] < km_hi)].copy()


def _iqr(series: pd.Series) -> float:
    q1, q3 = series.quantile([0.25, 0.75])
    return float(q3 - q1)


def _per_athlete_pace_irregularity(panel: pd.DataFrame) -> pd.DataFrame:
    """
    Multi-scale pace irregularity per athlete, aggregated to median + IQR.

    Per athlete (rolling, centered, 1 m grid):
      - speed_std_w
      - speed_mean_abs_delta_w  (exported as speed_jerk_* — mean |Δspeed|)
      - pace_gap_flat_std_w     (optional, when column present)

    Guard: when rolling min(speed) < WALK_SPEED_THRESHOLD_MPS, jerk stats → NaN
    (avoids walk/stop segments polluting irregularity signal).
    """
    work = panel.sort_values(["donor_id", "course_m"]).copy()
    has_pace_gap = "pace_gap_flat" in work.columns
    stat_frames: list[pd.DataFrame] = []

    for donor, grp in work.groupby("donor_id", sort=True):
        g = grp.sort_values("course_m").reset_index(drop=True)
        course_m = g["course_m"].to_numpy(dtype=float)
        speed = g["speed_mps"].astype(float)
        abs_delta = speed.diff().abs()

        donor_stats: dict[str, np.ndarray] = {"course_m": course_m}
        for window_m in PACE_IRREGULARITY_WINDOWS_M:
            tag = f"{window_m}m"
            roll = speed.rolling(window=window_m, center=True, min_periods=max(3, window_m // 4))
            speed_std = roll.std()
            speed_jerk = abs_delta.rolling(
                window=window_m, center=True, min_periods=max(3, window_m // 4)
            ).mean()
            min_speed = roll.min()
            walk_mask = min_speed < WALK_SPEED_THRESHOLD_MPS
            speed_std = speed_std.where(~walk_mask)
            speed_jerk = speed_jerk.where(~walk_mask)
            donor_stats[f"speed_std_{tag}"] = speed_std.to_numpy()
            donor_stats[f"speed_jerk_{tag}"] = speed_jerk.to_numpy()

            if has_pace_gap:
                pace_gap = g["pace_gap_flat"].astype(float)
                pg_std = pace_gap.rolling(
                    window=window_m, center=True, min_periods=max(3, window_m // 4)
                ).std()
                pg_std = pg_std.where(~walk_mask)
                donor_stats[f"pace_gap_flat_std_{tag}"] = pg_std.to_numpy()

        stat_frames.append(pd.DataFrame(donor_stats))

    long = pd.concat(stat_frames, ignore_index=True)
    value_cols = [c for c in long.columns if c != "course_m"]
    agg_rows: list[dict[str, Any]] = []
    for course_m, grp in long.groupby("course_m", sort=True):
        row: dict[str, Any] = {"course_m": float(course_m)}
        for col in value_cols:
            vals = grp[col].dropna()
            base = col
            row[f"{base}_median"] = float(vals.median()) if len(vals) else np.nan
            row[f"{base}_iqr"] = _iqr(vals) if len(vals) >= 2 else np.nan
        agg_rows.append(row)
    return pd.DataFrame(agg_rows)


def _per_athlete_ti_deltas(panel: pd.DataFrame) -> pd.DataFrame:
    """TI minus cross-athlete median TI at each course_m."""
    med = panel.groupby(["course_m", "donor_id"], as_index=False)["ti"].median()
    pivot = med.pivot(index="course_m", columns="donor_id", values="ti")
    panel_median = pivot.median(axis=1, skipna=True)
    out = pd.DataFrame({"course_m": pivot.index.astype(float)})
    for donor in sorted(pivot.columns):
        col = f"ti_delta_{donor}"
        out[col] = (pivot[donor] - panel_median).to_numpy()
    return out


def build_ml_feature_matrix(
    panel: pd.DataFrame,
    majority_df: pd.DataFrame,
    *,
    km_lo: float = SUT43_PRIMARY_KM_START,
    km_hi: float = SUT43_PRIMARY_KM_END,
    session_type: str | None = "race",
) -> pd.DataFrame:
    """One row per course_m with telemetry + vote features (no HR)."""
    work = _filter_panel(panel, km_lo=km_lo, km_hi=km_hi, session_type=session_type)
    if work.empty:
        raise ValueError(f"No panel rows in km {km_lo}–{km_hi}")

    nti_df = consensus_nti_at_course_m(work)
    telemetry = work.groupby("course_m", as_index=False).agg(
        course_km=("course_km", "first"),
        ti_median=("ti", "median"),
        ti_raw_median=("ti_raw", "median"),
        grade_pct_median=("grade_pct", "median"),
        mechanical_kappa_median=("mechanical_kappa", "median"),
        altitude_m=("altitude_m", "median"),
        cadence_median=("cadence_spm", "median"),
        speed_median=("speed_mps", "median"),
        pace_gap_flat_median=("pace_gap_flat", "median"),
        heart_rate_median=("heart_rate", "median"),
        vertical_oscillation_mm_median=("vertical_oscillation_mm", "median"),
        step_length_m_median=("step_length_m", "median"),
        stance_time_ms_median=("stance_time_ms", "median"),
        power_w_median=("power_w", "median"),
    )
    ti_delta = _per_athlete_ti_deltas(work)
    pace_irreg = _per_athlete_pace_irregularity(work)

    maj = majority_df[
        (majority_df["course_km"] >= km_lo) & (majority_df["course_km"] < km_hi)
    ][
        [
            "course_m",
            "n_voters",
            "vote_margin",
            "is_tie",
            "majority_class",
            "vote_tally",
        ]
    ].copy()
    maj["is_tie"] = maj["is_tie"].astype(bool)

    features = telemetry.merge(nti_df, on="course_m", how="left", suffixes=("", "_nti"))
    if "course_km_nti" in features.columns:
        features = features.drop(columns=["course_km_nti"])
    features = features.merge(ti_delta, on="course_m", how="left")
    features = features.merge(pace_irreg, on="course_m", how="left")
    features = features.merge(maj, on="course_m", how="left")
    features = features.sort_values("course_m").reset_index(drop=True)
    return features


def write_ml_features(
    features: pd.DataFrame,
    *,
    output_path: Path,
    meta: dict[str, Any] | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(output_path, index=False)
    if meta is not None:
        json_path = output_path.with_suffix(".json")
        json_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build per-metre ML feature matrix (gramstad_band)")
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--majority", type=Path, default=DEFAULT_MAJORITY)
    parser.add_argument("--km-start", type=float, default=SUT43_PRIMARY_KM_START)
    parser.add_argument("--km-end", type=float, default=SUT43_PRIMARY_KM_END)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    panel_path = args.panel if args.panel.is_absolute() else _REPO_ROOT / args.panel
    maj_path = args.majority if args.majority.is_absolute() else _REPO_ROOT / args.majority
    out_path = args.output if args.output.is_absolute() else _REPO_ROOT / args.output

    panel = pd.read_parquet(panel_path)
    majority_df = pd.read_parquet(maj_path)
    features = build_ml_feature_matrix(
        panel,
        majority_df,
        km_lo=args.km_start,
        km_hi=args.km_end,
    )
    meta = {
        "schema_version": "terrain_ml_features_v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "km_start": args.km_start,
        "km_end": args.km_end,
        "n_metres": len(features),
        "feature_columns": [c for c in features.columns if c not in ("course_m", "course_km")],
        "pace_irregularity_windows_m": list(PACE_IRREGULARITY_WINDOWS_M),
        "walk_speed_guard_mps": WALK_SPEED_THRESHOLD_MPS,
        "walk_guard_policy": "NaN jerk/irregularity stats when rolling min(speed) < threshold",
        "fit_telemetry": [
            "heart_rate_median",
            "vertical_oscillation_mm_median",
            "step_length_m_median",
            "stance_time_ms_median",
            "power_w_median",
        ],
        "note": "HR and running dynamics included when present in FIT-washed panel.",
    }
    write_ml_features(features, output_path=out_path, meta=meta)
    rel = out_path.relative_to(_REPO_ROOT)
    print(f"OK ml features → {rel} ({len(features)} rows, {len(features.columns)} cols)")


if __name__ == "__main__":
    main()
