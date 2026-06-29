"""
Locomotion mode classifier for Training Residual Framework (TRF).

Interim rules per docs/training_residual_framework.md §3.3:
  - run: cadence at or above threshold AND speed above hike cutoff (unless F4)
  - hike: low cadence, slow speed, steep uphill, or F4 friction tier

Defaults are conservative for trail telemetry with sparse cadence. Athlete-specific
thresholds may be supplied via config/subject_kinematics.local.json (gitignored).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

LocomotionMode = Literal["run", "hike"]

# TRF §3.2 grade band boundaries (percent).
GRADE_UPHILL_MIN_PCT = 3.0
GRADE_DOWNHILL_MAX_PCT = -3.0

# Interim cadence / speed defaults (documented in module docstring).
# Trail-ultra panel speeds cluster ~1.3–2.0 m/s at race effort; hike cutoff is
# walk-equivalent, not GAP-normalized jog pace.
DEFAULT_RUN_CADENCE_SPM = 120.0
DEFAULT_HIKE_SPEED_MPS = 1.25
DEFAULT_RUN_SPEED_MPS = 1.35
DEFAULT_STEEP_UPHIKE_GRADE_PCT = 8.0
MIN_VALID_CADENCE_SPM = 40.0


@dataclass(frozen=True)
class LocomotionThresholds:
    """Athlete-calibrated or default locomotion detection thresholds."""

    run_cadence_spm: float = DEFAULT_RUN_CADENCE_SPM
    hike_speed_mps: float = DEFAULT_HIKE_SPEED_MPS
    run_speed_mps: float = DEFAULT_RUN_SPEED_MPS
    steep_uphill_grade_pct: float = DEFAULT_STEEP_UPHIKE_GRADE_PCT


def athlete_locomotion_thresholds(
    df: pd.DataFrame,
    *,
    cadence_col: str = "cadence_spm",
    speed_col: str = "speed_mps",
    overrides: LocomotionThresholds | None = None,
) -> LocomotionThresholds:
    """
    Derive session-adaptive cadence threshold from valid telemetry.

    Uses the 40th percentile of non-zero cadence (bounded 90–140 spm) when
    at least 100 valid samples exist; otherwise falls back to defaults.
    """
    base = overrides or LocomotionThresholds()
    cadence = pd.to_numeric(df.get(cadence_col), errors="coerce")
    valid = cadence.notna() & (cadence >= MIN_VALID_CADENCE_SPM)
    if valid.sum() >= 100:
        p40 = float(cadence.loc[valid].quantile(0.40))
        run_cadence = float(np.clip(p40, 90.0, 140.0))
    else:
        run_cadence = base.run_cadence_spm
    return LocomotionThresholds(
        run_cadence_spm=run_cadence,
        hike_speed_mps=base.hike_speed_mps,
        run_speed_mps=base.run_speed_mps,
        steep_uphill_grade_pct=base.steep_uphill_grade_pct,
    )


def assign_grade_bin(grade_pct: pd.Series | np.ndarray) -> pd.Series:
    """
    Bin grade_pct into uphill / flat / downhill per TRF §3.2.

    Boundaries: uphill > +3%, flat −3% to +3%, downhill < −3%.
    """
    grade = pd.to_numeric(grade_pct, errors="coerce")
    out = pd.Series("flat", index=grade.index, dtype="object")
    out.loc[grade > GRADE_UPHILL_MIN_PCT] = "uphill"
    out.loc[grade < GRADE_DOWNHILL_MAX_PCT] = "downhill"
    return out


def classify_locomotion_mode(
    df: pd.DataFrame,
    *,
    grade_col: str = "grade_pct",
    cadence_col: str = "cadence_spm",
    speed_col: str = "speed_mps",
    friction_tier_col: str | None = "friction_tier",
    thresholds: LocomotionThresholds | None = None,
) -> pd.Series:
    """
    Per-metre run / hike classification.

    Priority order:
      1. F4 friction tier → hike
      2. Steep uphill (+8% default) with cadence below run threshold → hike
      3. Cadence below run threshold OR speed below hike cutoff → hike
      4. Otherwise → run
    """
    th = thresholds or LocomotionThresholds()
    grade = pd.to_numeric(df.get(grade_col, 0), errors="coerce").fillna(0.0)
    cadence = pd.to_numeric(df.get(cadence_col), errors="coerce")
    speed = pd.to_numeric(df.get(speed_col), errors="coerce")

    mode = pd.Series("run", index=df.index, dtype="object")

    if friction_tier_col and friction_tier_col in df.columns:
        f4 = df[friction_tier_col].astype(str) == "F4"
        mode.loc[f4] = "hike"

    valid_cadence = cadence.notna() & (cadence >= MIN_VALID_CADENCE_SPM)
    low_cadence = valid_cadence & (cadence < th.run_cadence_spm)
    slow_speed = speed.notna() & (speed < th.hike_speed_mps)
    run_speed = speed.notna() & (speed >= th.run_speed_mps)
    steep_up = grade >= th.steep_uphill_grade_pct

    # Cadence-led hike when telemetry is present.
    hike_mask = low_cadence | (steep_up & low_cadence)

    # Speed-led hike when cadence is missing — do not treat zero cadence as low cadence.
    missing_cadence = ~valid_cadence
    hike_mask |= missing_cadence & slow_speed
    hike_mask |= missing_cadence & steep_up & ~run_speed

    # Explicit slow shuffle regardless of cadence availability.
    hike_mask |= slow_speed & ~run_speed

    mode.loc[hike_mask & (mode != "hike")] = "hike"
    return mode
