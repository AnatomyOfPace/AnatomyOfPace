#!/usr/bin/env python3
"""
HITL v2 majority-vote draft — per-stream NTI → S-class via ti_band, stacked per course_m.

Voter eligibility: all panel streams with telemetry at the metre (σ-gate optional).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "04_Python_Scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "04_Python_Scripts"))

from spatial.ti_draft_layer import (
    assign_surface_class_from_nti,
    run_length_encode_classes,
)
from spatial.terrain_map_gen import compute_nti

DEFAULT_MIN_RUN_M = 5
DEFAULT_ONTOLOGY_DIR = (
    _REPO_ROOT / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology"
)


def per_stream_nti_classes(
    panel: pd.DataFrame,
    *,
    session_type: str | None = "race",
) -> pd.DataFrame:
    """Per-metre NTI and ti_band S-class for each donor stream."""
    work = panel.copy()
    if session_type and "session_type" in work.columns:
        work = work[work["session_type"] == session_type]
    work["nti"] = compute_nti(work)
    work["stream_class"] = work["nti"].apply(assign_surface_class_from_nti)
    return work[
        ["course_m", "course_km", "donor_id", "nti", "stream_class"]
    ].sort_values(["course_m", "donor_id"])


def _majority_from_votes(votes: list[str]) -> tuple[str | None, dict[str, int], int, bool]:
    """Return (majority_class, vote_tally, vote_margin, is_tie)."""
    if not votes:
        return None, {}, 0, False
    tally = dict(Counter(votes))
    ranked = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
    top_cls, top_count = ranked[0]
    if len(ranked) > 1 and ranked[1][1] == top_count:
        return None, tally, top_count, True
    second = ranked[1][1] if len(ranked) > 1 else 0
    return top_cls, tally, top_count - second, False


def build_majority_vote_frame(
    panel: pd.DataFrame,
    km_lo: float,
    km_hi: float,
    *,
    session_type: str | None = "race",
    sigma_gate: bool = False,
    variance_threshold: float = 0.30,
) -> pd.DataFrame:
    """
    Per-metre majority vote across donor streams.

    When ``sigma_gate`` is False (default), every stream with data at the metre votes.
    """
    stream_df = per_stream_nti_classes(panel, session_type=session_type)
    mask = (stream_df["course_km"] >= km_lo) & (stream_df["course_km"] < km_hi)
    stream_df = stream_df.loc[mask]

    if sigma_gate:
        from spatial.hitl_nti_consistency import per_metre_nti_stats

        agg = per_metre_nti_stats(panel, session_type=session_type)
        agg = agg[(agg["course_km"] >= km_lo) & (agg["course_km"] < km_hi)]
        hot = set(
            agg.loc[
                (agg["nti_std"] >= variance_threshold) & (agg["n_athletes"] >= 2),
                "course_m",
            ].tolist()
        )
    else:
        hot = set()

    grid = (
        stream_df[["course_m", "course_km"]]
        .drop_duplicates(subset=["course_m"])
        .sort_values("course_m")
    )

    rows: list[dict[str, Any]] = []
    grouped = stream_df.groupby("course_m")
    for row in grid.itertuples(index=False):
        course_m = float(row.course_m)
        if course_m in hot:
            rows.append(
                {
                    "course_m": course_m,
                    "course_km": float(row.course_km),
                    "majority_class": None,
                    "vote_tally": "{}",
                    "n_voters": 0,
                    "vote_margin": 0,
                    "is_tie": False,
                    "sigma_gated": True,
                }
            )
            continue

        if course_m not in grouped.groups:
            rows.append(
                {
                    "course_m": course_m,
                    "course_km": float(row.course_km),
                    "majority_class": None,
                    "vote_tally": "{}",
                    "n_voters": 0,
                    "vote_margin": 0,
                    "is_tie": False,
                    "sigma_gated": False,
                }
            )
            continue

        sub = grouped.get_group(course_m)
        votes = sub["stream_class"].astype(str).tolist()
        majority, tally, margin, is_tie = _majority_from_votes(votes)
        rows.append(
            {
                "course_m": course_m,
                "course_km": float(row.course_km),
                "majority_class": majority,
                "vote_tally": json.dumps(tally, sort_keys=True),
                "n_voters": len(votes),
                "vote_margin": margin,
                "is_tie": is_tie,
                "sigma_gated": False,
            }
        )

    return pd.DataFrame(rows)


def majority_draft_segments(
    majority_df: pd.DataFrame,
    *,
    min_run_m: int = DEFAULT_MIN_RUN_M,
) -> list[dict[str, Any]]:
    """RLE majority_class → majority_draft_segments[]."""
    work = majority_df.copy()
    work["ti_draft_class"] = work["majority_class"].where(
        ~work["is_tie"] & work["majority_class"].notna(),
        other="deferred",
    )
    return run_length_encode_classes(work, class_col="ti_draft_class", min_run_m=min_run_m)


def majority_vote_metadata(
    *,
    km_lo: float,
    km_hi: float,
    donors: list[str],
    n_metres: int,
    n_segments: int,
    sigma_gate: bool,
) -> dict[str, Any]:
    return {
        "schema_version": "hitl_v2_majority_v1",
        "method": "per_stream_nti_ti_band_majority",
        "km_start": km_lo,
        "km_end": km_hi,
        "donors": donors,
        "n_metres": n_metres,
        "n_segments": n_segments,
        "sigma_gate": sigma_gate,
        "voter_eligibility": (
            "all streams with telemetry at metre"
            if not sigma_gate
            else f"exclude metres with nti_std>={0.30} and n_athletes>=2"
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def write_majority_vote_outputs(
    majority_df: pd.DataFrame,
    segments: list[dict[str, Any]],
    meta: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_ONTOLOGY_DIR,
    write_sidecar_to_map: dict[str, Any] | None = None,
    terrain_map_path: Path | None = None,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = output_dir / "hitl_v2_majority.parquet"
    json_path = output_dir / "hitl_v2_majority.json"

    majority_df.to_parquet(parquet_path, index=False)
    payload = {
        "meta": meta,
        "majority_draft_segments": segments,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if write_sidecar_to_map is not None and terrain_map_path is not None:
        updated = dict(write_sidecar_to_map)
        hitl = dict(updated.get("hitl") or {})
        hitl["hitl_v2_majority"] = meta
        hitl["majority_draft_segments"] = segments
        updated["hitl"] = hitl
        terrain_map_path.write_text(json.dumps(updated, indent=2), encoding="utf-8")

    return parquet_path, json_path


def build_and_write_majority_vote(
    panel: pd.DataFrame,
    *,
    km_lo: float,
    km_hi: float,
    output_dir: Path = DEFAULT_ONTOLOGY_DIR,
    min_run_m: int = DEFAULT_MIN_RUN_M,
    sigma_gate: bool = False,
) -> tuple[pd.DataFrame, list[dict[str, Any]], Path, Path]:
    majority_df = build_majority_vote_frame(
        panel, km_lo, km_hi, sigma_gate=sigma_gate
    )
    segments = majority_draft_segments(majority_df, min_run_m=min_run_m)
    donors = sorted(panel["donor_id"].unique().tolist())
    meta = majority_vote_metadata(
        km_lo=km_lo,
        km_hi=km_hi,
        donors=donors,
        n_metres=len(majority_df),
        n_segments=len(segments),
        sigma_gate=sigma_gate,
    )
    parquet_path, json_path = write_majority_vote_outputs(
        majority_df, segments, meta, output_dir=output_dir
    )
    return majority_df, segments, parquet_path, json_path
