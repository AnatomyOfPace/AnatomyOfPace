"""
Shared donor intake utilities — privacy, paths, clinical IDs.

Used by Strava fetcher, form intake, and Kinematic_Scan pipeline.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "02_Raw_Data"
INBOX_DIR = RAW_DIR / "inbox" / "strava"
DONOR_DIR = RAW_DIR / "donors"

PRIVACY_CLIP_M = 500


def apply_privacy_clip(df: pd.DataFrame, clip_m: float = PRIVACY_CLIP_M) -> pd.DataFrame:
    """Remove first and last N metres from third-party telemetry (master_plan §7)."""
    if df.empty or "distance" not in df.columns:
        return df
    d_min, d_max = df["distance"].min(), df["distance"].max()
    return df[
        (df["distance"] >= d_min + clip_m) & (df["distance"] <= d_max - clip_m)
    ].copy()


def donor_fit_path(donor_id: str, activity_id: int | str, *, clipped: bool = True) -> Path:
    """
    Canonical path for external donor .fit files.

    clipped=True  → privacy-clipped copy used by analysis pipeline
    clipped=False → raw inbox copy (local only, gitignored)
    """
    root = DONOR_DIR if clipped else INBOX_DIR
    safe_id = donor_id.replace("/", "_")
    suffix = "" if clipped else "_raw"
    return root / safe_id / f"activity_{activity_id}{suffix}.fit"
