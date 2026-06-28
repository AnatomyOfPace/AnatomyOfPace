"""
Garmin `.fit` record-message ingest — raw DataFrame from fitparse.

Wave 2 Phase 2a: extraction only; normalization lives in stream_normalize.py.
"""

from __future__ import annotations

from pathlib import Path

import fitparse
import pandas as pd

RECORD_FIELDS = (
    "timestamp",
    "position_lat",
    "position_long",
    "distance",
    "heart_rate",
    "altitude",
    "enhanced_altitude",
    "cadence",
    "speed",
    "enhanced_speed",
    # Running dynamics (Garmin HRM-Pro / compatible footpod — optional per record)
    "vertical_oscillation",
    "vertical_ratio",
    "step_length",
    "stance_time",
    "stance_time_percent",
    "power",
)

_SEMICIRCLE_SCALE = 180.0 / (2**31)


def parse_fit(path: str | Path) -> pd.DataFrame:
    """Parse Garmin `.fit` record messages into a raw DataFrame."""
    fit_path = Path(path)
    if not fit_path.exists():
        raise FileNotFoundError(f"FIT file not found: {fit_path}")

    fit = fitparse.FitFile(str(fit_path))
    rows = []
    for record in fit.get_messages("record"):
        values = record.get_values()
        rows.append({field: values.get(field) for field in RECORD_FIELDS})

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    if "position_lat" in df.columns:
        df["latitude"] = pd.to_numeric(df["position_lat"], errors="coerce") * _SEMICIRCLE_SCALE
    if "position_long" in df.columns:
        df["longitude"] = pd.to_numeric(df["position_long"], errors="coerce") * _SEMICIRCLE_SCALE

    return df
