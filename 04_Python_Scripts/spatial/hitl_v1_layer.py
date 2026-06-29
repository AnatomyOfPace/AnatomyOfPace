#!/usr/bin/env python3
"""
HITL v1 effective class layer — per-metre authoritative assignment from terrain map.

Priority (highest wins): lock > active guidance (non-deferred) > accept-draft
(draft_preservation policy + GMM) > GMM cluster draft > unassigned.

Does not mutate terrain map JSON or HITL entries.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "04_Python_Scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "04_Python_Scripts"))

from spatial.validation_dashboard import (
    _class_is_accept_draft_on_span,
    _class_is_no_input_on_span,
    _segment_km_bounds,
    cluster_segments,
    draft_preservation_policies,
    guidance_overrides as manual_guidance_overrides,
    load_terrain_map,
    manual_overrides_by_mode,
)

SOURCE_LOCK = "lock"
SOURCE_GUIDANCE = "guidance"
SOURCE_ACCEPT_DRAFT = "accept_draft"
SOURCE_GMM_CLUSTER = "gmm_cluster"
SOURCE_UNASSIGNED = "unassigned"

DEFAULT_ONTOLOGY_DIR = (
    _REPO_ROOT / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology"
)


def _gmm_class_at_km(segments: list[dict[str, Any]], km: float) -> str | None:
    for seg in segments:
        s0, s1 = _segment_km_bounds(seg)
        if s0 <= km < s1 or (km >= s1 and abs(km - s1) < 1e-6):
            return str(seg.get("surface_class", "S2"))
    return None


def _override_class_at_km(
    overrides: list[dict[str, Any]],
    km: float,
) -> str | None:
    for ov in overrides:
        km0 = float(ov["course_km_start"])
        km1 = float(ov["course_km_end"])
        if km0 <= km < km1 or (km >= km1 and abs(km - km1) < 1e-6):
            return str(ov.get("surface_class", "S2"))
    return None


def effective_class_at_km(
    km: float,
    terrain_map: dict[str, Any],
    *,
    segments: list[dict[str, Any]] | None = None,
    policies: list[dict[str, Any]] | None = None,
    lock_overrides: list[dict[str, Any]] | None = None,
    guidance_overrides: list[dict[str, Any]] | None = None,
) -> tuple[str | None, str]:
    """Return (effective_class, source_layer) for one course km."""
    segments = segments if segments is not None else cluster_segments(terrain_map)
    policies = policies if policies is not None else draft_preservation_policies(terrain_map)
    lock_overrides = (
        lock_overrides
        if lock_overrides is not None
        else manual_overrides_by_mode(terrain_map, "lock")
    )
    guidance_overrides = (
        guidance_overrides
        if guidance_overrides is not None
        else manual_guidance_overrides(terrain_map)
    )

    lock_cls = _override_class_at_km(lock_overrides, km)
    if lock_cls is not None:
        return lock_cls, SOURCE_LOCK

    guidance_cls = _override_class_at_km(guidance_overrides, km)
    if guidance_cls is not None:
        return guidance_cls, SOURCE_GUIDANCE

    gmm_cls = _gmm_class_at_km(segments, km)
    if gmm_cls is None:
        return None, SOURCE_UNASSIGNED

    eps = 1e-6
    if policies and _class_is_no_input_on_span(km, km + eps, gmm_cls, policies):
        return None, SOURCE_UNASSIGNED

    if policies and _class_is_accept_draft_on_span(km, km + eps, gmm_cls, policies):
        return gmm_cls, SOURCE_ACCEPT_DRAFT

    return gmm_cls, SOURCE_GMM_CLUSTER


def shared_metre_grid(
    panel: pd.DataFrame,
    km_lo: float,
    km_hi: float,
) -> pd.DataFrame:
    """One row per course_m in [km_lo, km_hi)."""
    work = panel.sort_values("course_m")
    mask = (work["course_km"] >= km_lo) & (work["course_km"] < km_hi)
    grid = work.loc[mask, ["course_m", "course_km"]].drop_duplicates(subset=["course_m"])
    return grid.sort_values("course_m").reset_index(drop=True)


def build_hitl_v1_effective(
    terrain_map: dict[str, Any],
    panel: pd.DataFrame,
    km_lo: float,
    km_hi: float,
) -> pd.DataFrame:
    """Per-metre HITL v1 effective class on the shared panel grid."""
    grid = shared_metre_grid(panel, km_lo, km_hi)
    segments = cluster_segments(terrain_map)
    policies = draft_preservation_policies(terrain_map)
    lock_ovs = manual_overrides_by_mode(terrain_map, "lock")
    guidance_ovs = manual_guidance_overrides(terrain_map)

    classes: list[str | None] = []
    sources: list[str] = []
    for row in grid.itertuples(index=False):
        km = float(row.course_km)
        cls, src = effective_class_at_km(
            km,
            terrain_map,
            segments=segments,
            policies=policies,
            lock_overrides=lock_ovs,
            guidance_overrides=guidance_ovs,
        )
        classes.append(cls)
        sources.append(src)

    out = grid.copy()
    out["effective_class"] = classes
    out["source_layer"] = sources
    return out


def hitl_v1_metadata(
    *,
    km_lo: float,
    km_hi: float,
    n_metres: int,
    source_counts: dict[str, int],
) -> dict[str, Any]:
    return {
        "schema_version": "hitl_v1_effective_v1",
        "km_start": km_lo,
        "km_end": km_hi,
        "n_metres": n_metres,
        "priority": [
            SOURCE_LOCK,
            SOURCE_GUIDANCE,
            SOURCE_ACCEPT_DRAFT,
            SOURCE_GMM_CLUSTER,
            SOURCE_UNASSIGNED,
        ],
        "source_layer_counts": source_counts,
    }


def write_hitl_v1_effective(
    df: pd.DataFrame,
    *,
    parquet_path: Path,
    json_path: Path | None = None,
    meta: dict[str, Any] | None = None,
) -> tuple[Path, Path | None]:
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(parquet_path, index=False)
    written_json: Path | None = None
    if json_path is not None and meta is not None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"meta": meta, "records": df.to_dict(orient="records")}
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written_json = json_path
    return parquet_path, written_json


def build_and_write_hitl_v1(
    terrain_map: dict[str, Any],
    panel: pd.DataFrame,
    *,
    km_lo: float,
    km_hi: float,
    output_dir: Path = DEFAULT_ONTOLOGY_DIR,
) -> tuple[pd.DataFrame, Path]:
    df = build_hitl_v1_effective(terrain_map, panel, km_lo, km_hi)
    source_counts = df["source_layer"].value_counts().to_dict()
    meta = hitl_v1_metadata(
        km_lo=km_lo,
        km_hi=km_hi,
        n_metres=len(df),
        source_counts={str(k): int(v) for k, v in source_counts.items()},
    )
    parquet_path = output_dir / "hitl_v1_effective.parquet"
    write_hitl_v1_effective(df, parquet_path=parquet_path, meta=meta)
    return df, parquet_path
