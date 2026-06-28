"""
Unify raw `.fit` record columns into the ActivityFrame schema.

Wave 2 Phase 2a: column mapping, units, enhanced_* fallback, monotonic distance fix.
Course projection: fit_micro.course_project (Phase 2b).
"""

from __future__ import annotations

import pandas as pd

from fit_micro.activity_frame import ACTIVITY_FRAME_COLUMNS


def _prefer_enhanced(df: pd.DataFrame, base: str, enhanced: str) -> pd.Series:
    if enhanced in df.columns and df[enhanced].notna().any():
        return pd.to_numeric(df[enhanced], errors="coerce")
    return pd.to_numeric(df.get(base), errors="coerce")


def normalize_stream(df: pd.DataFrame, *, source: str = "fit") -> pd.DataFrame:
    """Map raw fitparse records to canonical ActivityFrame columns."""
    if df.empty:
        return pd.DataFrame(columns=ACTIVITY_FRAME_COLUMNS)

    out = pd.DataFrame(index=df.index)
    out["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    out["distance_m"] = pd.to_numeric(df.get("distance"), errors="coerce")
    out["latitude"] = pd.to_numeric(df.get("latitude"), errors="coerce")
    out["longitude"] = pd.to_numeric(df.get("longitude"), errors="coerce")
    out["altitude_m"] = _prefer_enhanced(df, "altitude", "enhanced_altitude")
    out["heart_rate"] = pd.to_numeric(df.get("heart_rate"), errors="coerce")
    out["cadence_spm"] = pd.to_numeric(df.get("cadence"), errors="coerce")
    out["speed_mps"] = _prefer_enhanced(df, "speed", "enhanced_speed")
    # fitparse exposes Garmin scaled units: mm, percent, mm, ms, watts
    out["vertical_oscillation_mm"] = pd.to_numeric(df.get("vertical_oscillation"), errors="coerce")
    out["vertical_ratio_pct"] = pd.to_numeric(df.get("vertical_ratio"), errors="coerce")
    step_mm = pd.to_numeric(df.get("step_length"), errors="coerce")
    out["step_length_m"] = step_mm / 1000.0
    out["stance_time_ms"] = pd.to_numeric(df.get("stance_time"), errors="coerce")
    out["power_w"] = pd.to_numeric(df.get("power"), errors="coerce")
    out["source"] = source

    out = out.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    out = out.drop_duplicates(subset=["timestamp"], keep="first")

    if out["distance_m"].notna().any():
        out["distance_m"] = out["distance_m"].cummax()

    t0 = out["timestamp"].iloc[0]
    out["elapsed_s"] = (out["timestamp"] - t0).dt.total_seconds()

    out["course_km"] = float("nan")
    out["grade"] = float("nan")

    return out[list(ACTIVITY_FRAME_COLUMNS)]
