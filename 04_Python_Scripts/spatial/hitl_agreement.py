#!/usr/bin/env python3
"""
Agreement layer — compare HITL v1 effective vs v2 majority vote per course metre.

Tiers: gold, silver, bronze, review, abstain.
"""

from __future__ import annotations

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

from spatial.ti_draft_layer import run_length_encode_classes
from spatial.surface_ontology import SURFACE_CLASS_IDS

DEFAULT_MIN_RUN_M = 5
DEFAULT_ONTOLOGY_DIR = (
    _REPO_ROOT / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology"
)

TIER_GOLD = "gold"
TIER_SILVER = "silver"
TIER_BRONZE = "bronze"
TIER_REVIEW = "review"
TIER_ABSTAIN = "abstain"

ML_READY_TIERS = frozenset({TIER_GOLD, TIER_SILVER})


def _normalize_class(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return None
    s = str(value).strip()
    if not s or s == "unassigned":
        return None
    return s


def _is_strong_consensus(n_voters: int, vote_margin: int, is_tie: bool) -> bool:
    if is_tie or n_voters < 1:
        return False
    if vote_margin >= n_voters:
        return True
    return (vote_margin / n_voters) >= (2.0 / 3.0)


def agreement_tier_for_row(row: Any) -> str:
    """Assign agreement tier for one merged metre row."""
    if bool(getattr(row, "is_tie", False)):
        return TIER_ABSTAIN

    v1 = _normalize_class(getattr(row, "effective_class", None))
    v2 = _normalize_class(getattr(row, "majority_class", None))
    n_voters = int(getattr(row, "n_voters", 0))

    if v2 is None and n_voters == 0:
        return TIER_ABSTAIN

    if v1 is None or v2 is None:
        return TIER_REVIEW

    if v1 != v2:
        return TIER_REVIEW

    if n_voters >= 2:
        margin = int(getattr(row, "vote_margin", 0))
        tie = bool(getattr(row, "is_tie", False))
        if _is_strong_consensus(n_voters, margin, tie):
            return TIER_GOLD
        return TIER_SILVER

    if n_voters == 1:
        return TIER_BRONZE

    return TIER_REVIEW


def merge_v1_v2(
    v1_df: pd.DataFrame,
    v2_df: pd.DataFrame,
) -> pd.DataFrame:
    merged = v1_df.merge(
        v2_df[
            [
                "course_m",
                "majority_class",
                "vote_tally",
                "n_voters",
                "vote_margin",
                "is_tie",
            ]
        ],
        on="course_m",
        how="outer",
        suffixes=("", "_v2"),
    )
    merged = merged.sort_values("course_m").reset_index(drop=True)
    tiers = [agreement_tier_for_row(row) for row in merged.itertuples(index=False)]
    merged["agreement_tier"] = tiers
    merged["classes_match"] = merged.apply(
        lambda r: (
            _normalize_class(r.get("effective_class")) is not None
            and _normalize_class(r.get("majority_class")) is not None
            and _normalize_class(r.get("effective_class"))
            == _normalize_class(r.get("majority_class"))
        ),
        axis=1,
    )
    return merged


def cohens_kappa(y1: pd.Series, y2: pd.Series, labels: list[str] | None = None) -> float | None:
    """Cohen's κ for paired nominal labels (None/unassigned excluded)."""
    a = y1.astype(object).tolist()
    b = y2.astype(object).tolist()
    pairs = [
        (_normalize_class(x), _normalize_class(y))
        for x, y in zip(a, b)
        if _normalize_class(x) is not None and _normalize_class(y) is not None
    ]
    if not pairs:
        return None

    if labels is None:
        labels = sorted({p[0] for p in pairs} | {p[1] for p in pairs})

    n = len(pairs)
    conf: dict[tuple[str, str], int] = {}
    for x, y in pairs:
        conf[(x, y)] = conf.get((x, y), 0) + 1

    p_o = sum(conf.get((lbl, lbl), 0) for lbl in labels) / n
    p_e = 0.0
    for lbl in labels:
        row_sum = sum(conf.get((lbl, other), 0) for other in labels)
        col_sum = sum(conf.get((other, lbl), 0) for other in labels)
        p_e += (row_sum / n) * (col_sum / n)

    if abs(1.0 - p_e) < 1e-12:
        return 1.0 if abs(p_o - 1.0) < 1e-12 else 0.0
    return (p_o - p_e) / (1.0 - p_e)


def confusion_matrix_v1_v2(
    merged: pd.DataFrame,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    if labels is None:
        labels = list(SURFACE_CLASS_IDS) + ["unassigned"]

    matrix: dict[str, dict[str, int]] = {v1: {v2: 0 for v2 in labels} for v1 in labels}
    for row in merged.itertuples(index=False):
        v1 = _normalize_class(getattr(row, "effective_class", None)) or "unassigned"
        v2 = _normalize_class(getattr(row, "majority_class", None)) or "unassigned"
        if v1 not in matrix:
            matrix[v1] = {lbl: 0 for lbl in labels}
        if v2 not in matrix[v1]:
            matrix[v1][v2] = 0
        matrix[v1][v2] += 1
    return {"labels": labels, "counts": matrix}


def agreement_metrics(merged: pd.DataFrame) -> dict[str, Any]:
    tier_counts = merged["agreement_tier"].value_counts().to_dict()
    n_metres = len(merged)
    gold = int(tier_counts.get(TIER_GOLD, 0))
    silver = int(tier_counts.get(TIER_SILVER, 0))
    bronze = int(tier_counts.get(TIER_BRONZE, 0))
    review = int(tier_counts.get(TIER_REVIEW, 0))
    abstain = int(tier_counts.get(TIER_ABSTAIN, 0))
    n_match = gold + silver + bronze
    n_decided = n_metres - abstain
    agreement_pct = (100.0 * n_match / n_decided) if n_decided else 0.0

    kappa = cohens_kappa(merged["effective_class"], merged["majority_class"])

    return {
        "n_metres": n_metres,
        "n_decided_v2": n_decided,
        "n_match": n_match,
        "agreement_pct": round(agreement_pct, 2),
        "cohens_kappa": round(kappa, 4) if kappa is not None else None,
        "tier_counts": {str(k): int(v) for k, v in tier_counts.items()},
        "gold_metres": gold,
        "silver_metres": silver,
        "bronze_metres": bronze,
        "review_metres": review,
        "abstain_metres": abstain,
    }


def disagreement_spans(
    merged: pd.DataFrame,
    *,
    min_span_m: int = 5,
    tier: str = TIER_REVIEW,
) -> list[dict[str, Any]]:
    """RLE contiguous review-tier metres with v1/v2 class labels."""
    work = merged[merged["agreement_tier"] == tier].copy()
    if work.empty:
        return []

    work["ti_draft_class"] = work.apply(
        lambda r: f"{_normalize_class(r['effective_class']) or '∅'}"
        f"≠{_normalize_class(r['majority_class']) or '∅'}",
        axis=1,
    )
    return run_length_encode_classes(work, class_col="ti_draft_class", min_run_m=min_span_m)


def agreement_segments(
    merged: pd.DataFrame,
    *,
    min_run_m: int = DEFAULT_MIN_RUN_M,
    ml_ready_only: bool = True,
) -> list[dict[str, Any]]:
    """RLE segments for gold/silver (ML-ready) or all tiers."""
    work = merged.copy()
    if ml_ready_only:
        work = work[work["agreement_tier"].isin(ML_READY_TIERS)]
    if work.empty:
        return []

    records: list[dict[str, Any]] = []
    current_tier: str | None = None
    seg_start: float | None = None
    v1_cls: str | None = None

    for row in work.sort_values("course_m").itertuples(index=False):
        tier = str(row.agreement_tier)
        cm = float(row.course_m)
        eff = _normalize_class(row.effective_class)

        if tier != current_tier or eff != v1_cls:
            if current_tier is not None and seg_start is not None:
                records.append(
                    {
                        "course_m_start": seg_start,
                        "course_m_end": cm,
                        "course_km_start": seg_start / 1000.0,
                        "course_km_end": cm / 1000.0,
                        "agreement_tier": current_tier,
                        "effective_class": v1_cls,
                        "majority_class": _normalize_class(
                            work.loc[work["course_m"] == seg_start, "majority_class"].iloc[0]
                        ),
                    }
                )
            current_tier = tier
            seg_start = cm
            v1_cls = eff

    if current_tier is not None and seg_start is not None:
        last_m = float(work["course_m"].iloc[-1])
        records.append(
            {
                "course_m_start": seg_start,
                "course_m_end": last_m + 1.0,
                "course_km_start": seg_start / 1000.0,
                "course_km_end": (last_m + 1.0) / 1000.0,
                "agreement_tier": current_tier,
                "effective_class": v1_cls,
                "majority_class": _normalize_class(work.iloc[-1]["majority_class"]),
            }
        )

    if min_run_m <= 1 or not records:
        return records

    merged_segs: list[dict[str, Any]] = []
    for seg in records:
        length = float(seg["course_m_end"]) - float(seg["course_m_start"])
        if length >= min_run_m or not merged_segs:
            merged_segs.append(seg)
            continue
        prev = merged_segs[-1]
        prev["course_m_end"] = seg["course_m_end"]
        prev["course_km_end"] = seg["course_km_end"]
    return merged_segs


def operator_gold_spans_from_map(terrain_map: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not terrain_map:
        return []
    return list(terrain_map.get("hitl", {}).get("operator_gold_spans") or [])


def ml_label_class_for_row(row: Any) -> str | None:
    """Unified ML training label per metre."""
    if str(getattr(row, "gold_source", "") or "") == "operator":
        return _normalize_class(getattr(row, "operator_gold_class", None))
    if str(getattr(row, "agreement_tier", "")) == TIER_GOLD:
        return _normalize_class(getattr(row, "effective_class", None))
    return None


def attach_ml_label_class(merged: pd.DataFrame) -> pd.DataFrame:
    """Add ``ml_label_class`` column for ML training exports."""
    work = merged.copy()
    work["ml_label_class"] = [
        ml_label_class_for_row(row) for row in work.itertuples(index=False)
    ]
    return work


def apply_operator_gold_spans(
    merged: pd.DataFrame,
    spans: list[dict[str, Any]],
) -> pd.DataFrame:
    """Promote operator-gold course metres to tier gold regardless of v1/v2 match."""
    work = merged.copy()
    if "gold_source" not in work.columns:
        work["gold_source"] = None

    for span in spans:
        km_start = float(span["course_km_start"])
        km_end = float(span["course_km_end"])
        m_start = km_start * 1000.0
        m_end = km_end * 1000.0
        cls = _normalize_class(span.get("surface_class"))
        source = str(span.get("gold_source") or "operator")
        mask = (work["course_m"] >= m_start) & (work["course_m"] < m_end)
        if not mask.any():
            continue
        work.loc[mask, "agreement_tier"] = TIER_GOLD
        work.loc[mask, "gold_source"] = source
        if cls is not None:
            work.loc[mask, "operator_gold_class"] = cls

    return work


def build_agreement_layer(
    v1_df: pd.DataFrame,
    v2_df: pd.DataFrame,
    *,
    km_lo: float,
    km_hi: float,
    min_run_m: int = DEFAULT_MIN_RUN_M,
    terrain_map: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    merged = merge_v1_v2(v1_df, v2_df)
    operator_spans = operator_gold_spans_from_map(terrain_map)
    if operator_spans:
        merged = apply_operator_gold_spans(merged, operator_spans)
    merged = attach_ml_label_class(merged)
    metrics = agreement_metrics(merged)
    ml_counts = merged["ml_label_class"].value_counts(dropna=False).to_dict()
    metrics["ml_label_class_counts"] = {
        (str(k) if pd.notna(k) else "null"): int(v) for k, v in ml_counts.items()
    }
    segments = agreement_segments(merged, min_run_m=min_run_m, ml_ready_only=True)
    disagreements = disagreement_spans(merged, min_span_m=min_run_m)
    confusion = confusion_matrix_v1_v2(merged)

    report: dict[str, Any] = {
        "schema_version": "hitl_agreement_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "km_start": km_lo,
        "km_end": km_hi,
        "metrics": metrics,
        "confusion_matrix": confusion,
        "agreement_segments": segments,
        "disagreement_spans": disagreements[:50],
        "tier_definitions": {
            TIER_GOLD: "match + n_voters≥2 + unanimous or ≥2/3 vote strength; or hitl.operator_gold_spans[]",
            TIER_SILVER: "match + n_voters≥2",
            TIER_BRONZE: "match + n_voters=1",
            TIER_REVIEW: "v1 vs v2 class mismatch or missing class",
            TIER_ABSTAIN: "v2 tie or no voters",
        },
        "operator_gold_spans": operator_spans,
    }
    return merged, report


def write_agreement_outputs(
    merged: pd.DataFrame,
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_ONTOLOGY_DIR,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = output_dir / "hitl_agreement.parquet"
    json_path = output_dir / "hitl_agreement.json"
    merged.to_parquet(parquet_path, index=False)
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return parquet_path, json_path
