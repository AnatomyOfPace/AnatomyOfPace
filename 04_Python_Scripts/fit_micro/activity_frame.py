"""
Canonical ActivityFrame schema and Parquet I/O for the micro tier.

Output: 03_Processed_Data/micro/{donor_id}/activity_{activity_id}.parquet
Sidecar: 03_Processed_Data/micro/{donor_id}/activity_{activity_id}.meta.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent
MICRO_DIR = BASE_DIR / "03_Processed_Data" / "micro"

PARSER_VERSION = "wave2_v1"

ACTIVITY_FRAME_COLUMNS = (
    "timestamp",
    "elapsed_s",
    "distance_m",
    "course_km",
    "latitude",
    "longitude",
    "altitude_m",
    "heart_rate",
    "cadence_spm",
    "speed_mps",
    "grade",
    "vertical_oscillation_mm",
    "vertical_ratio_pct",
    "step_length_m",
    "stance_time_ms",
    "power_w",
    "source",
)


def micro_parquet_path(donor_id: str, activity_id: str | int) -> Path:
    safe_id = donor_id.replace("/", "_")
    return MICRO_DIR / safe_id / f"activity_{activity_id}.parquet"


def micro_meta_path(donor_id: str, activity_id: str | int) -> Path:
    safe_id = donor_id.replace("/", "_")
    return MICRO_DIR / safe_id / f"activity_{activity_id}.meta.json"


def write_parquet(
    frame: pd.DataFrame,
    donor_id: str,
    activity_id: str | int,
    *,
    meta: dict[str, Any] | None = None,
) -> Path:
    """Write ActivityFrame to Parquet; optional sidecar metadata."""
    path = micro_parquet_path(donor_id, activity_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    if meta is not None:
        write_meta_json(donor_id, activity_id, meta)
    return path


def read_parquet(donor_id: str, activity_id: str | int) -> pd.DataFrame:
    path = micro_parquet_path(donor_id, activity_id)
    if not path.exists():
        raise FileNotFoundError(f"ActivityFrame not found: {path}")
    return pd.read_parquet(path)


def write_meta_json(donor_id: str, activity_id: str | int, meta: dict[str, Any]) -> Path:
    path = micro_meta_path(donor_id, activity_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"parser_version": PARSER_VERSION, **meta}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
