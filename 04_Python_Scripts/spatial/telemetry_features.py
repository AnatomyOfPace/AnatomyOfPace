"""Rolling telemetry features for O₂ clustering and anchor export (no sklearn)."""

from __future__ import annotations

import numpy as np
import pandas as pd

ROLLING_WINDOW_M = 60
WALK_SPEED_THRESHOLD_MPS = 1.2


def add_rolling_features(
    frame: pd.DataFrame,
    *,
    distance_col: str = "course_m",
    window_m: int = ROLLING_WINDOW_M,
) -> pd.DataFrame:
    """Rolling means/stds and walk fraction on a 1 m distance grid."""
    work = frame.sort_values(distance_col).copy()
    idx = work.index
    win = max(1, int(window_m))

    for col, out_mean, out_std in (
        ("ti", "ti_mean", "ti_std"),
        ("speed", "speed_mean", None),
        ("pace_residual", "pace_residual_mean", None),
    ):
        if col not in work.columns:
            continue
        series = pd.to_numeric(work[col], errors="coerce")
        work[out_mean] = series.rolling(win, min_periods=max(1, win // 3)).mean()
        if out_std:
            work[out_std] = series.rolling(win, min_periods=max(1, win // 3)).std()

    if "speed" in work.columns:
        walk = (pd.to_numeric(work["speed"], errors="coerce") < WALK_SPEED_THRESHOLD_MPS).astype(float)
        work["walk_fraction"] = walk.rolling(win, min_periods=max(1, win // 3)).mean()
    else:
        work["walk_fraction"] = np.nan

    return work.loc[idx].reset_index(drop=True)
