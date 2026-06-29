#!/usr/bin/env python3
"""
Training Residual Framework (TRF) — metre-level ΔTI and cell aggregation.

Computes athlete friction tax (ΔTI) against cohort or self-rolling baselines,
joins friction tier from terrain map HITL spans, and exports residual cell
reports per docs/training_residual_framework.md §4.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/compute_training_residual.py \\
        --subject Subject_A \\
        --terrain-map config/spatial_terrain_map_sut43.json \\
        --panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet

    python3 04_Python_Scripts/spatial/compute_training_residual.py \\
        --subject Subject_B \\
        --panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_race_1m_spine.parquet \\
        --baseline-mode cohort_median

    python3 04_Python_Scripts/spatial/compute_training_residual.py \\
        --cross-athlete \\
        --panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_race_1m_spine.parquet
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.corridor_scope import (  # noqa: E402
    SUT43_PRIMARY_KM_END,
    SUT43_PRIMARY_KM_START,
    SUT43_SECTOR_ID,
)
from spatial.locomotion_mode import (  # noqa: E402
    LocomotionThresholds,
    assign_grade_bin,
    classify_locomotion_mode,
    load_subject_kinematics_config,
    thresholds_for_subject,
)
from spatial.reproject_to_spine import (  # noqa: E402
    is_spine_panel,
    normalize_panel_axes,
    subject_id_column,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_PANEL = (
    BASE_DIR / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "panel_1m.parquet"
)
DEFAULT_SPINE_PANEL = (
    BASE_DIR
    / "03_Processed_Data"
    / "spatial"
    / "sut43_terrain_ontology"
    / "panel_race_1m_spine.parquet"
)
DEFAULT_TERRAIN_MAP = BASE_DIR / "config" / "spatial_terrain_map_sut43.json"
DEFAULT_KINEMATICS_CONFIG = BASE_DIR / "config" / "subject_kinematics.local.json"
DEFAULT_OUTPUT_DIR = (
    BASE_DIR / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology"
)

DEFAULT_DELTA_THRESHOLD = 0.15
MIN_CELL_METRES_FOR_TAGS = 200
SELF_ROLLING_WINDOW_M = 500

BaselineMode = Literal["cohort_median", "self_rolling"]

# S-class → primary friction tier (friction_index_spec.md §4).
S_TO_FRICTION_TIER: dict[str, str] = {
    "S1": "F0",
    "S2": "F1",
    "S3": "F2",
    "S4": "F3",
    "S5": "F4",
    "S6": "F4",
}
S_CLASS_AMBIGUOUS = frozenset({"S2", "S3", "S5"})

# TRF §4.1 training focus tag matrix (positive ΔTI interpretation).
TRAINING_FOCUS_TAGS: dict[tuple[str, str, str], list[str]] = {
    ("F1", "uphill", "hike"): ["uphill_power_hike_economy", "transition_run_to_hike"],
    ("F1", "uphill", "run"): ["uphill_climb_power"],
    ("F1", "flat", "run"): ["flat_trail_cadence", "easy_tread_economy"],
    ("F1", "downhill", "run"): ["downhill_relaxation", "overstriding_brake"],
    ("F2", "uphill", "hike"): ["uphill_power_hike_economy", "pole_technique"],
    ("F2", "flat", "run"): ["ankle_stabilisation", "push_off_stiffness"],
    ("F2", "downhill", "run"): ["eccentric_downhill_control"],
    ("F3", "uphill", "run"): ["technical_uphill_line", "root_rock_placement"],
    ("F3", "uphill", "hike"): ["steep_hike_technique", "hip_hinge_hike"],
    ("F3", "flat", "run"): ["cognitive_line_choice", "stride_frequency_technical"],
    ("F3", "downhill", "run"): [
        "steep_technical_downhill",
        "eccentric_downhill_control",
        "defensive_stride_ratio",
    ],
    ("F3", "downhill", "hike"): ["technical_descent_hike", "steep_technical_downhill"],
    ("F4", "uphill", "hike"): ["bog_extraction", "scree_balance", "accept_hike_pacing"],
    ("F4", "uphill", "run"): ["runnability_discipline", "hike_transition_timing"],
    ("F4", "flat", "hike"): ["bog_extraction", "scree_balance", "accept_hike_pacing"],
    ("F4", "flat", "run"): ["runnability_discipline", "hike_transition_timing"],
    ("F4", "downhill", "hike"): ["bog_extraction", "scree_balance", "accept_hike_pacing"],
    ("F4", "downhill", "run"): ["runnability_discipline", "hike_transition_timing"],
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_terrain_map(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_surface_class(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    text = str(value).strip().upper()
    if text.startswith("S") and len(text) == 2 and text[1].isdigit():
        return text
    return None


def _map_surface_to_friction(surface_class: str | None) -> tuple[str | None, bool]:
    """Return (friction_tier, is_ambiguous_s_map)."""
    if surface_class is None:
        return None, False
    tier = S_TO_FRICTION_TIER.get(surface_class)
    ambiguous = surface_class in S_CLASS_AMBIGUOUS
    return tier, ambiguous


def _collect_tier_spans(terrain_map: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge HITL span sources with priority (higher wins on overlap)."""
    hitl = terrain_map.get("hitl") or {}
    spans: list[dict[str, Any]] = []

    for span in hitl.get("friction_spans") or []:
        if span.get("friction_tier"):
            spans.append({**span, "_priority": 100, "_source": "friction_spans"})

    for span in hitl.get("operator_gold_spans") or []:
        if span.get("friction_tier"):
            spans.append({**span, "_priority": 90, "_source": "operator_gold_friction"})
        elif span.get("surface_class"):
            spans.append({**span, "_priority": 70, "_source": "operator_gold_surface"})

    for span in hitl.get("manual_overrides") or []:
        if span.get("friction_tier"):
            spans.append({**span, "_priority": 60, "_source": "manual_override_friction"})
        elif span.get("surface_class"):
            spans.append({**span, "_priority": 50, "_source": "manual_override_surface"})

    return spans


def _variance_gap_spans(terrain_map: dict[str, Any]) -> list[tuple[float, float]]:
    hitl = terrain_map.get("hitl") or {}
    out: list[tuple[float, float]] = []
    for gap in hitl.get("variance_gaps") or []:
        out.append((float(gap["course_km_start"]), float(gap["course_km_end"])))
    return out


def _trf_exclusion_spans(terrain_map: dict[str, Any]) -> list[dict[str, Any]]:
    hitl = terrain_map.get("hitl") or {}
    return list(hitl.get("trf_exclusions") or [])


def apply_trf_exclusions(
    df: pd.DataFrame,
    terrain_map: dict[str, Any],
    *,
    subject_id: str | None = None,
) -> pd.DataFrame:
    """
    Flag metres excluded from TRF aggregation per hitl.trf_exclusions[].

    subject_scope both: all subjects in window; Subject_A_only: Subject_A rows only.
    """
    work = df.copy()
    work["in_trf_exclusion"] = False
    work["trf_exclusion_type"] = pd.Series([None] * len(work), index=work.index, dtype="object")
    work["trf_exclusion_scope"] = pd.Series([None] * len(work), index=work.index, dtype="object")
    work["trf_exclusion_anchor_id"] = pd.Series([None] * len(work), index=work.index, dtype="object")

    km = pd.to_numeric(work["course_km"], errors="coerce")
    sid_col = "subject_id" if "subject_id" in work.columns else None

    for span in _trf_exclusion_spans(terrain_map):
        km0 = float(span["course_km_start"])
        km1 = float(span["course_km_end"])
        mask = (km >= km0) & (km < km1)
        scope = str(span.get("subject_scope") or "both")
        if scope == "Subject_A_only":
            if subject_id is not None and subject_id != "Subject_A":
                continue
            if sid_col:
                mask &= work[sid_col] == "Subject_A"
        if not mask.any():
            continue
        work.loc[mask, "in_trf_exclusion"] = True
        work.loc[mask, "trf_exclusion_type"] = span.get("exclusion_type")
        work.loc[mask, "trf_exclusion_scope"] = scope
        if span.get("anchor_id"):
            work.loc[mask, "trf_exclusion_anchor_id"] = span["anchor_id"]

    return work


def cross_athlete_exclusion_mask(
    paired: pd.DataFrame,
    terrain_map: dict[str, Any],
    *,
    subjects: tuple[str, ...] = ("Subject_A", "Subject_B"),
) -> pd.Series:
    """
    Metres to drop from paired cross-athlete TRF.

    Excludes both-scope windows and Subject_A-only asymmetry windows (gap artifact).
    """
    km = pd.to_numeric(paired["course_km"], errors="coerce")
    drop = pd.Series(False, index=paired.index)
    for span in _trf_exclusion_spans(terrain_map):
        km0 = float(span["course_km_start"])
        km1 = float(span["course_km_end"])
        in_window = (km >= km0) & (km < km1)
        scope = str(span.get("subject_scope") or "both")
        if scope in {"both", "Subject_A_only"}:
            drop |= in_window
    return drop


def trf_analysis_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Metres eligible for TRF cell aggregation and summary stats."""
    if "in_trf_exclusion" not in df.columns:
        return df
    return df.loc[~df["in_trf_exclusion"]].copy()


def resolve_friction_tiers(
    df: pd.DataFrame,
    terrain_map: dict[str, Any],
) -> pd.DataFrame:
    """
    Assign friction_tier, friction_tier_source, and per-metre residual_confidence.

    Uses operator friction_tier when present; otherwise maps S-class gold to F-tier.
    """
    work = df.copy()
    km = pd.to_numeric(work["course_km"], errors="coerce")
    n = len(work)

    tier = pd.Series([None] * n, index=work.index, dtype="object")
    source = pd.Series([None] * n, index=work.index, dtype="object")
    surface = pd.Series([None] * n, index=work.index, dtype="object")
    confidence = pd.Series("low", index=work.index, dtype="object")

    spans = sorted(
        _collect_tier_spans(terrain_map),
        key=lambda s: float(s.get("_priority", 0)),
    )

    for span in spans:
        km0 = float(span["course_km_start"])
        km1 = float(span["course_km_end"])
        mask = (km >= km0) & (km < km1)
        if not mask.any():
            continue

        explicit_tier = span.get("friction_tier")
        if explicit_tier:
            tier.loc[mask] = str(explicit_tier)
            source.loc[mask] = span["_source"]
            confidence.loc[mask] = "high"
        else:
            s_cls = _normalize_surface_class(span.get("surface_class"))
            if s_cls:
                mapped, ambiguous = _map_surface_to_friction(s_cls)
                if mapped:
                    tier.loc[mask] = mapped
                    source.loc[mask] = span["_source"]
                    surface.loc[mask] = s_cls
                    confidence.loc[mask] = "low" if ambiguous else "medium"

    for km0, km1 in _variance_gap_spans(terrain_map):
        mask = (km >= km0) & (km < km1)
        confidence.loc[mask] = "low"

    work["friction_tier"] = tier
    work["friction_tier_source"] = source
    work["surface_class_gold"] = surface
    work["residual_confidence"] = confidence
    work["in_variance_gap"] = False
    for km0, km1 in _variance_gap_spans(terrain_map):
        work.loc[(km >= km0) & (km < km1), "in_variance_gap"] = True

    return work


def compute_baseline_cohort_median(
    cohort: pd.DataFrame,
    target: pd.DataFrame,
) -> pd.Series:
    """
    Baseline TI per target row: median within friction_tier × grade_bin × mode.

    When friction_tier is null, falls back to grade_bin × mode cohort median (TRF §2).
    """
    work = cohort.copy()
    work["_ti"] = pd.to_numeric(work["ti"], errors="coerce")
    baselines: list[float] = []

    for _, row in target.iterrows():
        mask = pd.Series(True, index=work.index)
        mask &= work["grade_bin"] == row["grade_bin"]
        mask &= work["locomotion_mode"] == row["locomotion_mode"]
        if pd.notna(row.get("friction_tier")) and row["friction_tier"]:
            mask &= work["friction_tier"] == row["friction_tier"]
        subset = work.loc[mask, "_ti"].dropna()
        baselines.append(float(subset.median()) if len(subset) >= 3 else np.nan)

    return pd.Series(baselines, index=target.index)


def compute_baseline_self_rolling(
    athlete: pd.DataFrame,
    *,
    window_m: int = SELF_ROLLING_WINDOW_M,
) -> pd.Series:
    """Rolling median TI for same grade_bin × locomotion_mode within course window."""
    work = athlete.sort_values("course_m").copy()
    work["_ti"] = pd.to_numeric(work["ti"], errors="coerce")
    baselines = pd.Series(np.nan, index=work.index, dtype=float)

    for (grade_bin, mode), group in work.groupby(["grade_bin", "locomotion_mode"], observed=True):
        idx = group.index
        course_m = group["course_m"].values
        ti_vals = group["_ti"].values
        for i, row_idx in enumerate(idx):
            lo = course_m[i] - window_m / 2
            hi = course_m[i] + window_m / 2
            window_mask = (course_m >= lo) & (course_m <= hi) & (np.arange(len(course_m)) != i)
            window_ti = ti_vals[window_mask]
            window_ti = window_ti[~np.isnan(window_ti)]
            if len(window_ti) >= 5:
                baselines.loc[row_idx] = float(np.median(window_ti))

    return baselines.reindex(athlete.index)


def lookup_training_tags(
    friction_tier: str | None,
    grade_bin: str,
    locomotion_mode: str,
    delta_ti: float,
    *,
    delta_threshold: float = DEFAULT_DELTA_THRESHOLD,
) -> list[str]:
    if friction_tier == "F0":
        if delta_ti > delta_threshold:
            return ["qc_review"]
        if delta_ti < -delta_threshold:
            return ["efficiency_strength"]
        return []

    if delta_ti < -delta_threshold:
        return ["efficiency_strength"]
    if delta_ti <= delta_threshold:
        return []

    key = (str(friction_tier), grade_bin, locomotion_mode)
    tags = TRAINING_FOCUS_TAGS.get(key)
    if tags:
        return list(tags)
    if friction_tier == "F4":
        return ["bog_extraction", "scree_balance", "accept_hike_pacing"]
    return []


def aggregate_residual_cells(
    df: pd.DataFrame,
    *,
    subject_id: str,
    sector_id: str,
    delta_threshold: float,
    baseline_mode: str,
) -> list[dict[str, Any]]:
    """Aggregate metre-level residuals into TRF cell records (§4.4)."""
    session_delta = pd.to_numeric(df["delta_ti"], errors="coerce").dropna()
    cells: list[dict[str, Any]] = []

    group_cols = ["friction_tier", "grade_bin", "locomotion_mode"]
    for keys, group in df.groupby(group_cols, dropna=False, observed=True):
        tier_raw, grade, mode = keys
        tier = None if pd.isna(tier_raw) else str(tier_raw)
        n = len(group)
        if n == 0:
            continue
        delta = pd.to_numeric(group["delta_ti"], errors="coerce")
        ti = pd.to_numeric(group["ti"], errors="coerce")
        expected = pd.to_numeric(group["ti_expected"], errors="coerce")
        km = pd.to_numeric(group["course_km"], errors="coerce")

        delta_mean = float(delta.mean()) if delta.notna().any() else None
        delta_median = float(delta.median()) if delta.notna().any() else None
        pct_session = round(100.0 * n / len(df), 2)

        if delta_mean is not None and not session_delta.empty:
            pctile = float((session_delta <= delta_mean).mean())
        else:
            pctile = None

        conf_modes = group["residual_confidence"].mode()
        cell_confidence = str(conf_modes.iloc[0]) if len(conf_modes) else "low"
        if group["in_variance_gap"].any():
            cell_confidence = "low"

        tags: list[str] = []
        if delta_mean is not None and n >= MIN_CELL_METRES_FOR_TAGS:
            tags = lookup_training_tags(tier, grade, mode, delta_mean, delta_threshold=delta_threshold)
        overlay: list[str] = []
        if group["in_variance_gap"].mean() > 0.5:
            overlay.append("residual_confidence_low")

        tier_slug = str(tier) if tier else "unknown"
        segment_id = (
            f"sut43_{sector_id}_{tier_slug}_{grade}_{mode}_"
            f"km{km.min():.1f}_{km.max():.1f}"
        )

        cells.append(
            {
                "segment_id": segment_id,
                "course_km_start": round(float(km.min()), 3),
                "course_km_end": round(float(km.max()), 3),
                "friction_tier": tier,
                "grade_band": grade,
                "locomotion_mode": mode,
                "sector_id": sector_id,
                "ti_mean": round(float(ti.mean()), 4) if ti.notna().any() else None,
                "ti_expected": round(float(expected.mean()), 4) if expected.notna().any() else None,
                "delta_ti_mean": round(delta_mean, 4) if delta_mean is not None else None,
                "delta_ti_median": round(delta_median, 4) if delta_median is not None else None,
                "delta_ti_pctile_session": round(pctile, 3) if pctile is not None else None,
                "metre_count": int(n),
                "pct_of_session": pct_session,
                "impact_score": round(abs(delta_mean or 0.0) * n, 2),
                "training_focus_tags": tags,
                "overlay_tags": overlay,
                "residual_confidence": cell_confidence,
                "tpr_segment": None,
                "epr_vs_reference_elite_a": None,
            }
        )

    cells.sort(key=lambda c: c.get("impact_score") or 0.0, reverse=True)
    return cells


def _merge_fit_ti(
    work: pd.DataFrame,
    fit_ti_path: Path,
    *,
    subject_id: str,
) -> pd.DataFrame:
    """Optional FIT-derived TI overlay; spine panels join non-A subjects on stream course_m."""
    fit_ti = pd.read_parquet(fit_ti_path)
    sid_col = "donor_id" if "donor_id" in fit_ti.columns else subject_id_column(fit_ti)
    fit_ti = fit_ti[fit_ti[sid_col] == subject_id][["course_m", "ti"]].rename(columns={"ti": "ti_fit"})
    if is_spine_panel(work) and subject_id != "Subject_A" and "activity_course_m" in work.columns:
        work = work.merge(
            fit_ti,
            left_on="activity_course_m",
            right_on="course_m",
            how="left",
        )
    else:
        work = work.merge(fit_ti, on="course_m", how="left")
    work["ti"] = work["ti_fit"].combine_first(pd.to_numeric(work["ti"], errors="coerce"))
    return work.drop(columns=["ti_fit"], errors="ignore")


def build_subject_residual(
    panel: pd.DataFrame,
    terrain_map: dict[str, Any],
    *,
    subject_id: str,
    baseline_mode: BaselineMode,
    km_start: float,
    km_end: float,
    session_type: str = "race",
    fit_ti_path: Path | None = None,
    sector_id: str = SUT43_SECTOR_ID,
    locomotion_thresholds: LocomotionThresholds | None = None,
    kinematics_config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Build metre-level TRF frame for one subject."""
    panel = normalize_panel_axes(panel)
    sid_col = subject_id_column(panel)
    work = panel.copy()
    if session_type and "session_type" in work.columns:
        work = work[work["session_type"] == session_type]
    work = work[
        (work[sid_col] == subject_id)
        & (work["course_km"] >= km_start)
        & (work["course_km"] < km_end)
    ].sort_values("course_m")

    if work.empty:
        raise ValueError(f"No panel metres for {subject_id} in km {km_start}–{km_end}")

    if fit_ti_path and fit_ti_path.exists():
        work = _merge_fit_ti(work, fit_ti_path, subject_id=subject_id)

    work["ti"] = pd.to_numeric(work["ti"], errors="coerce")
    work["grade_bin"] = assign_grade_bin(work["grade_pct"])
    work = resolve_friction_tiers(work, terrain_map)
    if kinematics_config is None:
        kinematics_config = load_subject_kinematics_config()
    work["locomotion_mode"] = classify_locomotion_mode(
        work,
        subject_id=subject_id,
        kinematics_config=kinematics_config,
        thresholds=locomotion_thresholds,
    )

    cohort = panel.copy()
    if session_type and "session_type" in cohort.columns:
        cohort = cohort[cohort["session_type"] == session_type]
    cohort = cohort[(cohort["course_km"] >= km_start) & (cohort["course_km"] < km_end)].copy()
    cohort["ti"] = pd.to_numeric(cohort["ti"], errors="coerce")
    cohort["grade_bin"] = assign_grade_bin(cohort["grade_pct"])
    cohort = resolve_friction_tiers(cohort, terrain_map)
    if sid_col not in cohort.columns:
        cohort[sid_col] = subject_id
    cohort["locomotion_mode"] = classify_locomotion_mode(
        cohort,
        subject_id_col=sid_col,
        kinematics_config=kinematics_config,
        thresholds=locomotion_thresholds,
    )

    if baseline_mode == "cohort_median":
        work["ti_expected"] = compute_baseline_cohort_median(cohort, work)
    else:
        work["ti_expected"] = compute_baseline_self_rolling(work)

    work["delta_ti"] = work["ti"] - work["ti_expected"]
    work["subject_id"] = subject_id
    work["sector_id"] = sector_id
    work["baseline_mode"] = baseline_mode
    work = apply_trf_exclusions(work, terrain_map, subject_id=subject_id)
    return work


def export_outputs(
    df: pd.DataFrame,
    *,
    subject_id: str,
    output_dir: Path,
    sector_id: str,
    baseline_mode: str,
    delta_threshold: float,
    terrain_map_path: Path,
    panel_path: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = output_dir / f"training_residual_{subject_id}.parquet"
    json_path = output_dir / f"training_residual_report_{subject_id}.json"

    export_cols = [
        "course_m",
        "course_km",
        "ref_chainage_m",
        "activity_course_km",
        "subject_id",
        "sector_id",
        "ti",
        "ti_expected",
        "delta_ti",
        "grade_pct",
        "grade_bin",
        "locomotion_mode",
        "friction_tier",
        "friction_tier_source",
        "surface_class_gold",
        "residual_confidence",
        "in_variance_gap",
        "in_trf_exclusion",
        "trf_exclusion_type",
        "trf_exclusion_scope",
        "trf_exclusion_anchor_id",
        "cadence_spm",
        "speed_mps",
        "mechanical_kappa",
        "baseline_mode",
    ]
    present = [c for c in export_cols if c in df.columns]
    df[present].to_parquet(parquet_path, index=False)

    analysis_df = trf_analysis_frame(df)
    cells = aggregate_residual_cells(
        analysis_df,
        subject_id=subject_id,
        sector_id=sector_id,
        delta_threshold=delta_threshold,
        baseline_mode=baseline_mode,
    )
    tier_locked = df["friction_tier"].notna().sum()
    excluded = int(df["in_trf_exclusion"].sum()) if "in_trf_exclusion" in df.columns else 0
    report = {
        "schema_version": "training_residual_v0",
        "generated_at": _utc_now(),
        "subject_id": subject_id,
        "sector_id": sector_id,
        "baseline_mode": baseline_mode,
        "delta_ti_threshold": delta_threshold,
        "inputs": {
            "panel": str(panel_path.relative_to(BASE_DIR)),
            "terrain_map": str(terrain_map_path.relative_to(BASE_DIR)),
        },
        "summary": {
            "n_metres": int(len(df)),
            "n_metres_trf_eligible": int(len(analysis_df)),
            "n_metres_trf_excluded": excluded,
            "pct_friction_tier_assigned": round(100.0 * tier_locked / len(df), 2),
            "pct_variance_gap": round(100.0 * df["in_variance_gap"].mean(), 2),
            "pct_trf_excluded": round(100.0 * excluded / len(df), 2) if len(df) else 0.0,
            "pct_hike_mode": round(100.0 * (analysis_df["locomotion_mode"] == "hike").mean(), 2)
            if len(analysis_df)
            else 0.0,
            "mean_delta_ti": round(float(analysis_df["delta_ti"].mean()), 4)
            if len(analysis_df)
            else None,
        },
        "cells": cells,
        "top_cells_by_impact": cells[:5],
    }
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return parquet_path, json_path


def print_top_cells(cells: list[dict[str, Any]], subject_id: str, n: int = 5) -> None:
    print(f"\n=== Top {n} residual cells by |ΔTI| × metres — {subject_id} ===")
    for i, cell in enumerate(cells[:n], 1):
        tier_label = cell["friction_tier"] or "unknown"
        delta = cell["delta_ti_mean"]
        delta_str = f"{delta:+.3f}" if delta is not None else "n/a"
        print(
            f"  {i}. {tier_label} · {cell['grade_band']} · {cell['locomotion_mode']} | "
            f"ΔTI={delta_str} | n={cell['metre_count']} m | "
            f"impact={cell['impact_score']:.1f} | "
            f"tags={cell['training_focus_tags'] or '—'}"
        )


def build_cross_athlete_summary(
    panel: pd.DataFrame,
    terrain_map: dict[str, Any],
    *,
    subjects: tuple[str, ...] = ("Subject_A", "Subject_B"),
    baseline_mode: BaselineMode = "cohort_median",
    km_start: float = SUT43_PRIMARY_KM_START,
    km_end: float = SUT43_PRIMARY_KM_END,
    session_type: str = "race",
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    delta_threshold: float = DEFAULT_DELTA_THRESHOLD,
    terrain_map_path: Path = DEFAULT_TERRAIN_MAP,
    panel_path: Path = DEFAULT_SPINE_PANEL,
    locomotion_thresholds: LocomotionThresholds | None = None,
    kinematics_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Same-metre TRF on ref_chainage_m — paired ΔTI for cross-athlete validation (TRF §6 C3).
    """
    if not is_spine_panel(panel):
        raise ValueError("Cross-athlete TRF requires spine panel with ref_chainage_m")

    if kinematics_config is None:
        kinematics_config = load_subject_kinematics_config()

    per_subject: dict[str, pd.DataFrame] = {}
    reports: dict[str, dict[str, Any]] = {}
    for subject_id in subjects:
        fit_candidate = output_dir / f"fit_ti_clusters_{subject_id}.parquet"
        fit_ti_path = fit_candidate if fit_candidate.exists() else None
        df = build_subject_residual(
            panel,
            terrain_map,
            subject_id=subject_id,
            baseline_mode=baseline_mode,
            km_start=km_start,
            km_end=km_end,
            session_type=session_type,
            fit_ti_path=fit_ti_path,
            locomotion_thresholds=locomotion_thresholds,
            kinematics_config=kinematics_config,
        )
        per_subject[subject_id] = df
        _, json_path = export_outputs(
            df,
            subject_id=subject_id,
            output_dir=output_dir,
            sector_id=SUT43_SECTOR_ID,
            baseline_mode=baseline_mode,
            delta_threshold=delta_threshold,
            terrain_map_path=terrain_map_path,
            panel_path=panel_path,
        )
        reports[subject_id] = json.loads(json_path.read_text(encoding="utf-8"))

    join_cols = ["ref_chainage_m", "course_km"]
    a_df = per_subject[subjects[0]][join_cols + ["friction_tier", "grade_bin", "locomotion_mode", "ti", "ti_expected", "delta_ti"]].rename(
        columns={
            "friction_tier": f"friction_tier_{subjects[0]}",
            "grade_bin": f"grade_bin_{subjects[0]}",
            "locomotion_mode": f"locomotion_mode_{subjects[0]}",
            "ti": f"ti_{subjects[0]}",
            "ti_expected": f"ti_expected_{subjects[0]}",
            "delta_ti": f"delta_ti_{subjects[0]}",
        }
    )
    b_df = per_subject[subjects[1]][join_cols + ["friction_tier", "grade_bin", "locomotion_mode", "ti", "ti_expected", "delta_ti"]].rename(
        columns={
            "friction_tier": f"friction_tier_{subjects[1]}",
            "grade_bin": f"grade_bin_{subjects[1]}",
            "locomotion_mode": f"locomotion_mode_{subjects[1]}",
            "ti": f"ti_{subjects[1]}",
            "ti_expected": f"ti_expected_{subjects[1]}",
            "delta_ti": f"delta_ti_{subjects[1]}",
        }
    )
    paired = a_df.merge(b_df, on=join_cols, how="inner")
    paired["delta_ti_gap"] = paired[f"delta_ti_{subjects[0]}"] - paired[f"delta_ti_{subjects[1]}"]
    paired["ti_gap"] = paired[f"ti_{subjects[0]}"] - paired[f"ti_{subjects[1]}"]

    exclusion_mask = cross_athlete_exclusion_mask(paired, terrain_map, subjects=subjects)
    paired_eligible = paired.loc[~exclusion_mask]
    delta_gap = paired_eligible["delta_ti_gap"].dropna()
    ti_gap = paired_eligible["ti_gap"].dropna()
    summary = {
        "schema_version": "cross_athlete_trf_v0",
        "generated_at": _utc_now(),
        "subjects": list(subjects),
        "km_window": [km_start, km_end],
        "baseline_mode": baseline_mode,
        "axis": "ref_chainage_m",
        "inputs": {
            "panel": str(panel_path.relative_to(BASE_DIR)),
            "terrain_map": str(terrain_map_path.relative_to(BASE_DIR)),
        },
        "paired_metres": int(len(paired)),
        "paired_metres_trf_eligible": int(len(paired_eligible)),
        "paired_metres_trf_excluded": int(exclusion_mask.sum()),
        "trf_exclusions": _trf_exclusion_spans(terrain_map),
        "mean_delta_ti_gap": round(float(delta_gap.mean()), 4) if len(delta_gap) else None,
        "median_delta_ti_gap": round(float(delta_gap.median()), 4) if len(delta_gap) else None,
        "mean_abs_delta_ti_gap": round(float(delta_gap.abs().mean()), 4) if len(delta_gap) else None,
        "mean_ti_gap": round(float(ti_gap.mean()), 4) if len(ti_gap) else None,
        "pct_metres_a_higher_delta": round(
            100.0 * float((delta_gap > delta_threshold).mean()), 2
        )
        if len(delta_gap)
        else None,
        "per_subject": {
            sid: reports[sid]["summary"] for sid in subjects if sid in reports
        },
    }
    out_path = output_dir / "cross_athlete_trf_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["output_path"] = str(out_path.relative_to(BASE_DIR))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Training Residual Framework — ΔTI pipeline (Phase A–B)",
    )
    parser.add_argument("--subject", default=None, help="Clinical subject ID (Subject_A, Subject_B)")
    parser.add_argument(
        "--cross-athlete",
        action="store_true",
        help="Run same-metre paired TRF on ref_chainage_m (requires spine panel; Subject_A + Subject_B)",
    )
    parser.add_argument(
        "--terrain-map",
        type=Path,
        default=DEFAULT_TERRAIN_MAP,
        help="Terrain map JSON with HITL friction / gold spans",
    )
    parser.add_argument(
        "--panel",
        type=Path,
        default=DEFAULT_PANEL,
        help="Aligned 1 m panel parquet",
    )
    parser.add_argument(
        "--fit-ti",
        type=Path,
        default=None,
        help="Optional FIT-derived TI parquet (fit_ti_clusters_{subject}.parquet)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument(
        "--baseline-mode",
        choices=["cohort_median", "self_rolling"],
        default="cohort_median",
        help="Baseline TI source for ΔTI (default: cohort_median)",
    )
    parser.add_argument(
        "--delta-threshold",
        type=float,
        default=DEFAULT_DELTA_THRESHOLD,
        help="ΔTI threshold for training tag promotion (default: 0.15)",
    )
    parser.add_argument("--km-start", type=float, default=SUT43_PRIMARY_KM_START)
    parser.add_argument("--km-end", type=float, default=SUT43_PRIMARY_KM_END)
    parser.add_argument("--session-type", default="race")
    parser.add_argument(
        "--run-cadence-spm",
        type=float,
        default=None,
        help="Override run cadence threshold (default: 120 spm)",
    )
    parser.add_argument(
        "--kinematics-config",
        type=Path,
        default=DEFAULT_KINEMATICS_CONFIG,
        help="Subject locomotion thresholds JSON (default: config/subject_kinematics.local.json)",
    )
    args = parser.parse_args()

    if not args.cross_athlete and not args.subject:
        parser.error("--subject is required unless --cross-athlete is set")

    terrain_map_path = args.terrain_map if args.terrain_map.is_absolute() else BASE_DIR / args.terrain_map
    panel_path = args.panel if args.panel.is_absolute() else BASE_DIR / args.panel
    output_dir = args.output_dir if args.output_dir.is_absolute() else BASE_DIR / args.output_dir

    if not terrain_map_path.exists():
        raise FileNotFoundError(f"Terrain map not found: {terrain_map_path}")
    if not panel_path.exists():
        raise FileNotFoundError(f"Panel not found: {panel_path}")

    thresholds = None
    if args.run_cadence_spm is not None:
        base = thresholds_for_subject(load_subject_kinematics_config(), args.subject or "Subject_A")
        thresholds = LocomotionThresholds(
            run_cadence_min=args.run_cadence_spm,
            hike_cadence_max=base.hike_cadence_max,
        )

    kinematics_path = (
        args.kinematics_config
        if args.kinematics_config.is_absolute()
        else BASE_DIR / args.kinematics_config
    )
    kinematics_config = (
        load_subject_kinematics_config(str(kinematics_path))
        if kinematics_path.exists()
        else None
    )

    terrain_map = load_terrain_map(terrain_map_path)
    panel = normalize_panel_axes(pd.read_parquet(panel_path))

    if args.cross_athlete:
        summary = build_cross_athlete_summary(
            panel,
            terrain_map,
            baseline_mode=args.baseline_mode,
            km_start=args.km_start,
            km_end=args.km_end,
            session_type=args.session_type,
            output_dir=output_dir,
            delta_threshold=args.delta_threshold,
            terrain_map_path=terrain_map_path,
            panel_path=panel_path,
            locomotion_thresholds=thresholds,
            kinematics_config=kinematics_config,
        )
        print("\n=== Cross-athlete same-metre TRF (ref_chainage_m) ===")
        print(f"  paired metres: {summary['paired_metres']}")
        print(f"  TRF-eligible paired metres: {summary['paired_metres_trf_eligible']}")
        print(f"  TRF-excluded paired metres: {summary['paired_metres_trf_excluded']}")
        print(f"  mean ΔTI gap (A−B): {summary['mean_delta_ti_gap']:+.4f}")
        print(f"  mean |ΔTI gap|: {summary['mean_abs_delta_ti_gap']:.4f}")
        print(f"  mean TI gap (A−B): {summary['mean_ti_gap']:+.4f}")
        for sid, sub in summary.get("per_subject", {}).items():
            print(
                f"  {sid}: mean ΔTI={sub.get('mean_delta_ti'):+.4f} | "
                f"tier coverage={sub.get('pct_friction_tier_assigned')}%"
            )
        print(f"\nOK summary → {summary['output_path']}")
        return

    fit_ti_path = args.fit_ti
    if fit_ti_path is None:
        candidate = output_dir / f"fit_ti_clusters_{args.subject}.parquet"
        fit_ti_path = candidate if candidate.exists() else None
    elif not fit_ti_path.is_absolute():
        fit_ti_path = BASE_DIR / fit_ti_path

    residual_df = build_subject_residual(
        panel,
        terrain_map,
        subject_id=args.subject,
        baseline_mode=args.baseline_mode,
        km_start=args.km_start,
        km_end=args.km_end,
        session_type=args.session_type,
        fit_ti_path=fit_ti_path,
        locomotion_thresholds=thresholds,
        kinematics_config=kinematics_config,
    )

    parquet_path, json_path = export_outputs(
        residual_df,
        subject_id=args.subject,
        output_dir=output_dir,
        sector_id=SUT43_SECTOR_ID,
        baseline_mode=args.baseline_mode,
        delta_threshold=args.delta_threshold,
        terrain_map_path=terrain_map_path,
        panel_path=panel_path,
    )

    report = json.loads(json_path.read_text(encoding="utf-8"))
    print_top_cells(report["top_cells_by_impact"], args.subject)

    print(f"\nOK metre-level → {parquet_path.relative_to(BASE_DIR)}")
    print(f"OK cell report → {json_path.relative_to(BASE_DIR)}")
    print(
        f"   tier coverage: {report['summary']['pct_friction_tier_assigned']:.1f}% | "
        f"variance gap: {report['summary']['pct_variance_gap']:.1f}% | "
        f"hike mode: {report['summary']['pct_hike_mode']:.1f}%"
    )


if __name__ == "__main__":
    main()
