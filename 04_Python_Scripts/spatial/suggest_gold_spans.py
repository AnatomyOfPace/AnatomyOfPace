#!/usr/bin/env python3
"""
Propose terrain/friction lock spans for operator agree/disagree review.

Engines:
  hmm — HMM draft S-class runs + consensus TI → friction tier (legacy heuristic)
  ml  — trained gold suggester on labeled metres; gaps + revision flags

Usage (from repo root):
    python3 04_Python_Scripts/spatial/suggest_gold_spans.py \\
        --engine ml --mode gaps-only \\
        --km-start 37 --km-end 38 \\
        --model 07_ML_Models/spatial/gold_suggester_v0.joblib \\
        --output 03_Processed_Data/spatial/suggested_locks_sut43.csv

    python3 04_Python_Scripts/spatial/suggest_gold_spans.py \\
        --engine ml --mode all \\
        --km-start 8 --km-end 22 \\
        --sector-routing \\
        --output 03_Processed_Data/spatial/suggested_locks_bridge.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Literal

import joblib
import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.gold_training_common import build_training_frame
from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.terrain_map_gen import aggregate_nti_by_course_m, compute_nti

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_PANEL = BASE_DIR / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "panel_1m.parquet"
DEFAULT_TERRAIN_MAP = BASE_DIR / "config" / "spatial_terrain_map_sut43.json"
DEFAULT_TRIAGE_QUEUE = (
    BASE_DIR
    / "03_Processed_Data"
    / "spatial"
    / "sut43_terrain_ontology"
    / "ground_truth_review"
    / "triage_queue_sut43.csv"
)
DEFAULT_HMM_DRAFT = BASE_DIR / "07_ML_Models" / "terrain_hmm_sut43_draft_predictions.parquet"
DEFAULT_OUTPUT = BASE_DIR / "03_Processed_Data" / "spatial" / "suggested_locks_sut43.csv"
DEFAULT_MODEL = BASE_DIR / "07_ML_Models" / "spatial" / "gold_suggester_v0.joblib"
DEFAULT_ROUTING_MANIFEST = BASE_DIR / "config" / "gold_suggester_routing.json"

SuggestMode = Literal["gaps-only", "revise", "all"]
SuggestEngine = Literal["hmm", "ml"]

# friction_index_spec.md §3 — overlapping bands; pick tier whose centre is nearest when multiple match.
FRICTION_TI_BANDS: list[tuple[str, float, float]] = [
    ("F0", 0.85, 1.15),
    ("F1", 0.90, 1.20),
    ("F2", 1.05, 1.45),
    ("F3", 1.40, 1.80),
    ("F4", 1.80, 4.50),
]
FRICTION_TIER_CENTRES = {t: (lo + hi) / 2.0 for t, lo, hi in FRICTION_TI_BANDS}

MIN_SPAN_KM = 0.05  # 50 m contiguous run
HMM_HIGH_P = 0.85
HMM_MED_P = 0.70
NTI_HIGH_STD = 0.20
NTI_MED_STD = 0.30

HMM_OUTPUT_COLUMNS = [
    "chunk_id",
    "km_start",
    "km_end",
    "surface_class",
    "friction_tier",
    "confidence",
    "ti_median",
    "hmm_p_median",
    "rationale",
]

ML_OUTPUT_COLUMNS = [
    "action",
    "chunk_id",
    "km_start",
    "km_end",
    "surface_class",
    "friction_tier",
    "confidence",
    "gold_surface",
    "gold_friction",
    "surface_proba",
    "friction_proba",
    "rationale",
]

REVISE_PROBA_THRESHOLD = 0.55
ROAD_LIKE_SURFACE_CLASSES = frozenset({"S1", "S2"})
VARIANCE_GAP_SUPPRESS_NOTE = "suppressed: variance_gap gps_disturbance"
LOCKED_MONO_CLASS_NOTE = "operator_locked_mono: ML revise suppressed"


def operator_gold_spans(terrain_map: dict[str, Any]) -> list[dict[str, Any]]:
    return list(terrain_map.get("hitl", {}).get("operator_gold_spans") or [])


def variance_gap_spans(terrain_map: dict[str, Any]) -> list[tuple[float, float]]:
    hitl = terrain_map.get("hitl") or {}
    return [
        (float(gap["course_km_start"]), float(gap["course_km_end"]))
        for gap in (hitl.get("variance_gaps") or [])
    ]


def overlaps_variance_gap(
    km_start: float,
    km_end: float,
    gaps: list[tuple[float, float]],
) -> bool:
    return any(spans_overlap(km_start, km_end, g0, g1) for g0, g1 in gaps)


def _gold_span_overlaps_variance_gap(
    gold_span: dict[str, Any],
    gaps: list[tuple[float, float]],
) -> bool:
    s0, s1 = span_km_bounds(gold_span)
    return overlaps_variance_gap(s0, s1, gaps)


def _revise_on_variance_gap_gold(
    row: dict[str, Any],
    gold_spans: list[dict[str, Any]],
    gaps: list[tuple[float, float]],
) -> bool:
    """REVISE on operator gold that contains a variance_gap (GPS seed artefact)."""
    km_start = float(row["km_start"])
    km_end = float(row["km_end"])
    for span in gold_spans:
        s0, s1 = span_km_bounds(span)
        if not spans_overlap(km_start, km_end, s0, s1):
            continue
        if _gold_span_overlaps_variance_gap(span, gaps):
            return True
    return False


def operator_gold_surface_classes(terrain_map: dict[str, Any]) -> set[str]:
    classes = {
        str(span.get("surface_class", "")).strip().upper()
        for span in operator_gold_spans(terrain_map)
    }
    return {c for c in classes if c}


def is_operator_locked_mono_class(terrain_map: dict[str, Any]) -> bool:
    """True when HITL is locked and every operator span shares one surface class."""
    hitl = terrain_map.get("hitl") or {}
    if str(hitl.get("status", "")).lower() != "locked":
        return False
    classes = operator_gold_surface_classes(terrain_map)
    return len(classes) == 1


def apply_locked_mono_class_suppression(
    rows: list[dict[str, Any]],
    terrain_map: dict[str, Any],
    *,
    gold_spans: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Drop ML REVISE on locked mono-class operator gold; spurious surface noise only."""
    if not is_operator_locked_mono_class(terrain_map):
        return rows
    return [row for row in rows if str(row.get("action", "")) != "REVISE"]


def suggest_ml_keep_locked_operator(
    gold_spans: list[dict[str, Any]],
    km_lo: float,
    km_hi: float,
    *,
    chunk_id: str,
) -> list[dict[str, Any]]:
    """Force KEEP for operator spans when locked mono-class band (no ML agreement gate)."""
    rows: list[dict[str, Any]] = []
    for span in gold_spans:
        s0, s1 = span_km_bounds(span)
        if s1 <= km_lo or s0 >= km_hi:
            continue
        win_lo = max(s0, km_lo)
        win_hi = min(s1, km_hi)
        gold_s = str(span.get("surface_class", ""))
        gold_f = str(span.get("friction_tier", ""))
        rows.append(
            {
                "action": "KEEP",
                "chunk_id": chunk_id,
                "km_start": round(win_lo, 3),
                "km_end": round(win_hi, 3),
                "surface_class": gold_s,
                "friction_tier": gold_f,
                "confidence": "HIGH",
                "gold_surface": gold_s,
                "gold_friction": gold_f,
                "surface_proba": "",
                "friction_proba": "",
                "rationale": (
                    f"Operator locked mono-class {gold_s}; "
                    f"ML revise path skipped ({LOCKED_MONO_CLASS_NOTE})"
                ),
            }
        )
    return rows


def apply_variance_gap_suppression(
    rows: list[dict[str, Any]],
    gaps: list[tuple[float, float]],
    *,
    gold_spans: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Drop REVISE on variance_gap windows or parent gold; downgrade overlapping NEW."""
    if not gaps:
        return rows
    kept: list[dict[str, Any]] = []
    gold_spans = gold_spans or []
    for row in rows:
        action = str(row.get("action", ""))
        if action not in ("REVISE", "NEW"):
            kept.append(row)
            continue
        km_start = float(row["km_start"])
        km_end = float(row["km_end"])
        direct = overlaps_variance_gap(km_start, km_end, gaps)
        on_gap_gold = action == "REVISE" and _revise_on_variance_gap_gold(row, gold_spans, gaps)
        if not direct and not on_gap_gold:
            kept.append(row)
            continue
        if action == "REVISE":
            continue
        row = dict(row)
        row["confidence"] = "LOW"
        row["rationale"] = f"{row['rationale']}; {VARIANCE_GAP_SUPPRESS_NOTE}"
        kept.append(row)
    return kept


def operator_gold_class_at_km(terrain_map: dict[str, Any], km: float) -> str | None:
    for span in operator_gold_spans(terrain_map):
        s0, s1 = span_km_bounds(span)
        if s0 <= km < s1:
            return str(span.get("surface_class", "")).strip().upper() or None
    return None


def spans_overlap(km_start_a: float, km_end_a: float, km_start_b: float, km_end_b: float) -> bool:
    return km_start_a < km_end_b and km_start_b < km_end_a


def span_km_bounds(span: dict[str, Any]) -> tuple[float, float]:
    s0 = float(span.get("course_km_start", span.get("course_m_start", 0) / 1000.0))
    s1 = float(span.get("course_km_end", span.get("course_m_end", s0) / 1000.0))
    return s0, s1


def find_overlapping_gold_spans(
    existing_spans: list[dict[str, Any]],
    km_start: float,
    km_end: float,
) -> list[dict[str, Any]]:
    return [
        span
        for span in existing_spans
        if spans_overlap(km_start, km_end, *span_km_bounds(span))
    ]


def _race_panel(panel: pd.DataFrame) -> pd.DataFrame:
    work = panel.copy()
    if "course_km" not in work.columns and "ref_chainage_m" in work.columns:
        work["course_km"] = work["ref_chainage_m"] / 1000.0
    if "course_m" not in work.columns and "ref_chainage_m" in work.columns:
        work["course_m"] = work["ref_chainage_m"]
    if "session_type" in work.columns:
        work = work[work["session_type"] == "race"]
    return work.sort_values(["course_m", "donor_id"])


def build_consensus_profile(panel: pd.DataFrame) -> pd.DataFrame:
    """Consensus TI + NTI σ per course metre (mirrors hitl_annotator_app, no Streamlit)."""
    race = _race_panel(panel)
    race = race.copy()
    race["nti"] = compute_nti(race)
    consensus = aggregate_nti_by_course_m(race, use_consensus=True)
    per_m_aggs: dict[str, tuple[str, str]] = {
        "course_km": ("course_km", "first"),
        "ti_median": ("ti", "median"),
        "ti_raw_median": ("ti_raw", "median"),
    }
    per_m = race.groupby("course_m", as_index=False).agg(**per_m_aggs)
    if "course_km" not in consensus.columns and "course_m" in consensus.columns:
        consensus = consensus.merge(per_m[["course_m", "course_km"]], on="course_m", how="left")
    profile = per_m.merge(
        consensus[["course_m", "consensus_nti", "nti_std", "nti_median"]],
        on="course_m",
        how="left",
    )
    return profile.sort_values("course_m").reset_index(drop=True)


def ungolded_intervals(
    km_lo: float,
    km_hi: float,
    gold_spans: list[dict[str, Any]],
) -> list[tuple[float, float]]:
    """Subtract operator gold from [km_lo, km_hi]; return uncovered intervals."""
    free: list[tuple[float, float]] = [(km_lo, km_hi)]
    for span in gold_spans:
        s0, s1 = span_km_bounds(span)
        next_free: list[tuple[float, float]] = []
        for a, b in free:
            if s1 <= a or s0 >= b:
                next_free.append((a, b))
                continue
            if a < s0:
                next_free.append((a, s0))
            if s1 < b:
                next_free.append((s1, b))
        free = next_free
    return [(a, b) for a, b in free if (b - a) >= 1e-6]


def ti_to_friction_tier(ti_median: float) -> str:
    """Map consensus TI median to F-tier using friction_index_spec.md §3 bands."""
    if not np.isfinite(ti_median):
        return "F2"
    matching = [t for t, lo, hi in FRICTION_TI_BANDS if lo <= ti_median <= hi]
    if matching:
        return min(matching, key=lambda t: abs(ti_median - FRICTION_TIER_CENTRES[t]))
    return min(FRICTION_TI_BANDS, key=lambda row: abs(ti_median - FRICTION_TIER_CENTRES[row[0]]))[0]


def assign_confidence(hmm_p_median: float, nti_std_median: float | None) -> str:
    nti = float(nti_std_median) if nti_std_median is not None and np.isfinite(nti_std_median) else 0.0
    if hmm_p_median >= HMM_HIGH_P and nti <= NTI_HIGH_STD:
        return "HIGH"
    if hmm_p_median >= HMM_MED_P and nti <= NTI_MED_STD:
        return "MED"
    return "LOW"


def hmm_class_runs(
    hmm: pd.DataFrame,
    km_lo: float,
    km_hi: float,
    *,
    min_span_km: float = MIN_SPAN_KM,
) -> list[dict[str, Any]]:
    """Contiguous HMM draft_class runs within [km_lo, km_hi), merged, min span filter."""
    if hmm.empty or "draft_class" not in hmm.columns:
        return []
    win = hmm[(hmm["course_km"] >= km_lo) & (hmm["course_km"] < km_hi)].copy()
    if win.empty:
        return []
    win = win.sort_values("course_km")
    runs: list[dict[str, Any]] = []
    cur_cls = str(win.iloc[0]["draft_class"])
    start_km = float(win.iloc[0]["course_km"])
    p_vals = [float(win.iloc[0].get("hmm_confidence", np.nan))]
    for _, row in win.iloc[1:].iterrows():
        cls = str(row["draft_class"])
        if cls != cur_cls:
            end_km = float(row["course_km"])
            runs.append(
                {
                    "km_start": start_km,
                    "km_end": end_km,
                    "surface_class": cur_cls,
                    "hmm_p_values": list(p_vals),
                }
            )
            cur_cls = cls
            start_km = end_km
            p_vals = []
        p_vals.append(float(row.get("hmm_confidence", np.nan)))
    last_km = float(win.iloc[-1]["course_km"]) + 0.001
    runs.append(
        {
            "km_start": start_km,
            "km_end": last_km,
            "surface_class": cur_cls,
            "hmm_p_values": list(p_vals),
        }
    )
    return [r for r in runs if (r["km_end"] - r["km_start"]) >= min_span_km - 1e-9]


def _median_finite(values: list[float] | pd.Series | np.ndarray) -> float:
    arr = np.asarray(values, dtype=float)
    finite = arr[np.isfinite(arr)]
    return float(np.median(finite)) if finite.size else float("nan")


def _profile_window_stats(
    profile: pd.DataFrame,
    km_start: float,
    km_end: float,
) -> tuple[float, float | None]:
    ti_col = "ti_median" if "ti_median" in profile.columns else "ti_raw_median"
    win = profile[(profile["course_km"] >= km_start) & (profile["course_km"] < km_end)]
    if win.empty:
        return float("nan"), None
    ti_med = _median_finite(win[ti_col].to_numpy())
    nti_std_med = None
    if "nti_std" in win.columns:
        nti_std_med = _median_finite(win["nti_std"].to_numpy())
        if not np.isfinite(nti_std_med):
            nti_std_med = None
    return ti_med, nti_std_med


def _gold_adjacency_note(
    km_start: float,
    km_end: float,
    gold_spans: list[dict[str, Any]],
    *,
    margin_km: float = 0.05,
) -> str:
    """One-line note when suggestion sits next to existing gold."""
    for span in gold_spans:
        s0, s1 = span_km_bounds(span)
        if abs(km_start - s1) <= margin_km or abs(km_end - s0) <= margin_km:
            sc = span.get("surface_class", "?")
            ft = span.get("friction_tier", "?")
            return f"adjacent gold {sc}/{ft} km {s0:.3f}–{s1:.3f}"
    overlaps = find_overlapping_gold_spans(gold_spans, km_start, km_end)
    if overlaps:
        span = overlaps[0]
        s0, s1 = span_km_bounds(span)
        sc = span.get("surface_class", "?")
        ft = span.get("friction_tier", "?")
        return f"overlaps gold {sc}/{ft} km {s0:.3f}–{s1:.3f}"
    return "no gold overlap"


def build_rationale(
    *,
    surface_class: str,
    friction_tier: str,
    hmm_p_median: float,
    ti_median: float,
    nti_std_median: float | None,
    gold_note: str,
) -> str:
    parts = [
        f"HMM {surface_class} p={hmm_p_median:.2f}",
        f"TI_med={ti_median:.2f}→{friction_tier}",
    ]
    if nti_std_median is not None and np.isfinite(nti_std_median):
        parts.append(f"nti_σ={nti_std_median:.2f}")
    parts.append(gold_note)
    return "; ".join(parts)


def suggest_for_chunk(
    chunk_id: str,
    km_lo: float,
    km_hi: float,
    *,
    profile: pd.DataFrame,
    hmm: pd.DataFrame,
    gold_spans: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for interval_lo, interval_hi in ungolded_intervals(km_lo, km_hi, gold_spans):
        for run in hmm_class_runs(hmm, interval_lo, interval_hi):
            km_start = float(run["km_start"])
            km_end = float(run["km_end"])
            if find_overlapping_gold_spans(gold_spans, km_start, km_end):
                continue
            ti_median, nti_std_med = _profile_window_stats(profile, km_start, km_end)
            hmm_p_median = _median_finite(run["hmm_p_values"])
            if not np.isfinite(hmm_p_median):
                hmm_p_median = 0.0
            friction_tier = ti_to_friction_tier(ti_median)
            confidence = assign_confidence(hmm_p_median, nti_std_med)
            gold_note = _gold_adjacency_note(km_start, km_end, gold_spans)
            suggestions.append(
                {
                    "chunk_id": chunk_id,
                    "km_start": round(km_start, 3),
                    "km_end": round(km_end, 3),
                    "surface_class": run["surface_class"],
                    "friction_tier": friction_tier,
                    "confidence": confidence,
                    "ti_median": round(ti_median, 3) if np.isfinite(ti_median) else "",
                    "hmm_p_median": round(hmm_p_median, 3),
                    "rationale": build_rationale(
                        surface_class=run["surface_class"],
                        friction_tier=friction_tier,
                        hmm_p_median=hmm_p_median,
                        ti_median=ti_median if np.isfinite(ti_median) else float("nan"),
                        nti_std_median=nti_std_med,
                        gold_note=gold_note,
                    ),
                }
            )
    return suggestions


def load_panel_window(path: Path, km_lo: float, km_hi: float, *, buffer_km: float = 0.5) -> pd.DataFrame:
    lo = max(0.0, km_lo - buffer_km)
    hi = km_hi + buffer_km
    panel = pd.read_parquet(path)
    if "course_km" not in panel.columns and "ref_chainage_m" in panel.columns:
        panel["course_km"] = panel["ref_chainage_m"] / 1000.0
    return panel[(panel["course_km"] >= lo) & (panel["course_km"] <= hi)].copy()


def load_hmm_window(path: Path, km_lo: float, km_hi: float, *, buffer_km: float = 0.5) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    lo = max(0.0, km_lo - buffer_km)
    hi = km_hi + buffer_km
    hmm = pd.read_parquet(path)
    return hmm[(hmm["course_km"] >= lo) & (hmm["course_km"] <= hi)].copy()


def draft_gold_disagreement_pct(
    hmm: pd.DataFrame,
    gold_spans: list[dict[str, Any]],
    km_lo: float,
    km_hi: float,
) -> float | None:
    """Share (0–100) of window metres where HMM draft S-class != operator gold S-class."""
    if hmm.empty or "draft_class" not in hmm.columns or not gold_spans:
        return None
    win = hmm[(hmm["course_km"] >= km_lo) & (hmm["course_km"] < km_hi)]
    if win.empty:
        return None
    disagree = compared = 0
    terrain_stub = {"hitl": {"operator_gold_spans": gold_spans}}
    for _, row in win.iterrows():
        km = float(row["course_km"])
        gold = operator_gold_class_at_km(terrain_stub, km)
        if gold is None:
            continue
        compared += 1
        if str(row["draft_class"]) != gold:
            disagree += 1
    if compared == 0:
        return None
    return 100.0 * disagree / compared


def _prepare_features(df: pd.DataFrame, bundle: dict[str, Any]) -> pd.DataFrame:
    feature_cols = bundle["feature_columns"]
    medians = bundle.get("feature_medians") or {}
    x = df.reindex(columns=feature_cols).copy()
    for col in feature_cols:
        if x[col].dtype == object:
            x[col] = pd.to_numeric(x[col], errors="coerce")
        fill = medians.get(col, np.nan)
        x[col] = x[col].fillna(fill)
    return x


def _predict_bundle(frame: pd.DataFrame, bundle: dict[str, Any]) -> pd.DataFrame:
    x = _prepare_features(frame, bundle)
    surf_clf = bundle["surface_model"]
    fric_clf = bundle["friction_model"]
    surf_pred = surf_clf.predict(x)
    fric_pred = fric_clf.predict(x)
    surf_proba = surf_clf.predict_proba(x).max(axis=1)
    fric_proba = fric_clf.predict_proba(x).max(axis=1)
    out = frame.copy()
    out["pred_surface"] = surf_pred
    out["pred_friction"] = fric_pred
    out["surface_proba"] = surf_proba
    out["friction_proba"] = fric_proba
    out["pred_confidence"] = np.minimum(surf_proba, fric_proba)
    return out


def _confidence_label(proba: float) -> str:
    if proba >= 0.85:
        return "HIGH"
    if proba >= 0.65:
        return "MED"
    return "LOW"


def _label_runs(
    df: pd.DataFrame,
    *,
    label_cols: tuple[str, str],
    min_span_km: float,
) -> list[tuple[float, float, str, str]]:
    """Contiguous runs where both label columns match."""
    if df.empty:
        return []
    col_s, col_f = label_cols
    runs: list[tuple[float, float, str, str]] = []
    cur_s = str(df.iloc[0][col_s])
    cur_f = str(df.iloc[0][col_f])
    start_km = float(df.iloc[0]["course_km"])
    for _, row in df.iloc[1:].iterrows():
        s_cls = str(row[col_s])
        f_tier = str(row[col_f])
        if s_cls != cur_s or f_tier != cur_f:
            end_km = float(row["course_km"])
            if (end_km - start_km) >= min_span_km - 1e-9:
                runs.append((start_km, end_km, cur_s, cur_f))
            cur_s, cur_f = s_cls, f_tier
            start_km = end_km
    end_km = float(df.iloc[-1]["course_km"]) + 0.001
    if (end_km - start_km) >= min_span_km - 1e-9:
        runs.append((start_km, end_km, cur_s, cur_f))
    return runs


def suggest_ml_gaps(
    predicted: pd.DataFrame,
    gold_spans: list[dict[str, Any]],
    km_lo: float,
    km_hi: float,
    *,
    chunk_id: str,
    min_span_km: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    unlabeled = predicted[~predicted["is_labeled"]].copy()
    for gap_lo, gap_hi in ungolded_intervals(km_lo, km_hi, gold_spans):
        gap_df = unlabeled[(unlabeled["course_km"] >= gap_lo) & (unlabeled["course_km"] < gap_hi)]
        for start_km, end_km, surf, fric in _label_runs(
            gap_df.sort_values("course_km"),
            label_cols=("pred_surface", "pred_friction"),
            min_span_km=min_span_km,
        ):
            win = gap_df[(gap_df["course_km"] >= start_km) & (gap_df["course_km"] < end_km)]
            conf_proba = float(win["pred_confidence"].median()) if not win.empty else 0.0
            rows.append(
                {
                    "action": "NEW",
                    "chunk_id": chunk_id,
                    "km_start": round(start_km, 3),
                    "km_end": round(end_km, 3),
                    "surface_class": surf,
                    "friction_tier": fric,
                    "confidence": _confidence_label(conf_proba),
                    "gold_surface": "",
                    "gold_friction": "",
                    "surface_proba": round(float(win["surface_proba"].median()), 3),
                    "friction_proba": round(float(win["friction_proba"].median()), 3),
                    "rationale": f"ML gap fill {surf}/{fric} p={conf_proba:.2f}; unlabeled interval",
                }
            )
    return rows


def suggest_ml_revise(
    predicted: pd.DataFrame,
    gold_spans: list[dict[str, Any]],
    km_lo: float,
    km_hi: float,
    *,
    chunk_id: str,
    min_span_km: float,
    proba_threshold: float = REVISE_PROBA_THRESHOLD,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for span in gold_spans:
        s0, s1 = span_km_bounds(span)
        if s1 <= km_lo or s0 >= km_hi:
            continue
        win_lo = max(s0, km_lo)
        win_hi = min(s1, km_hi)
        win = predicted[(predicted["course_km"] >= win_lo) & (predicted["course_km"] < win_hi)]
        if win.empty:
            continue
        gold_s = str(span.get("surface_class", ""))
        gold_f = str(span.get("friction_tier", ""))
        disagree = (win["pred_surface"] != gold_s) | (win["pred_friction"] != gold_f)
        if not disagree.any():
            continue
        disagree_df = win[disagree]
        for start_km, end_km, surf, fric in _label_runs(
            disagree_df.sort_values("course_km"),
            label_cols=("pred_surface", "pred_friction"),
            min_span_km=min_span_km,
        ):
            sub = disagree_df[(disagree_df["course_km"] >= start_km) & (disagree_df["course_km"] < end_km)]
            conf_proba = float(sub["pred_confidence"].median())
            if conf_proba < proba_threshold:
                continue
            rows.append(
                {
                    "action": "REVISE",
                    "chunk_id": chunk_id,
                    "km_start": round(start_km, 3),
                    "km_end": round(end_km, 3),
                    "surface_class": surf,
                    "friction_tier": fric,
                    "confidence": _confidence_label(conf_proba),
                    "gold_surface": gold_s,
                    "gold_friction": gold_f,
                    "surface_proba": round(float(sub["surface_proba"].median()), 3),
                    "friction_proba": round(float(sub["friction_proba"].median()), 3),
                    "rationale": (
                        f"ML revise {gold_s}/{gold_f}→{surf}/{fric} "
                        f"p={conf_proba:.2f}; model disagrees with operator gold"
                    ),
                }
            )
    return rows


def suggest_ml_keep_summary(
    predicted: pd.DataFrame,
    gold_spans: list[dict[str, Any]],
    km_lo: float,
    km_hi: float,
    *,
    chunk_id: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for span in gold_spans:
        s0, s1 = span_km_bounds(span)
        if s1 <= km_lo or s0 >= km_hi:
            continue
        win_lo = max(s0, km_lo)
        win_hi = min(s1, km_hi)
        win = predicted[(predicted["course_km"] >= win_lo) & (predicted["course_km"] < win_hi)]
        if win.empty:
            continue
        gold_s = str(span.get("surface_class", ""))
        gold_f = str(span.get("friction_tier", ""))
        agree = (win["pred_surface"] == gold_s) & (win["pred_friction"] == gold_f)
        if agree.mean() < 0.9:
            continue
        conf_proba = float(win.loc[agree, "pred_confidence"].median()) if agree.any() else 0.0
        rows.append(
            {
                "action": "KEEP",
                "chunk_id": chunk_id,
                "km_start": round(win_lo, 3),
                "km_end": round(win_hi, 3),
                "surface_class": gold_s,
                "friction_tier": gold_f,
                "confidence": _confidence_label(conf_proba),
                "gold_surface": gold_s,
                "gold_friction": gold_f,
                "surface_proba": round(float(win["surface_proba"].median()), 3),
                "friction_proba": round(float(win["friction_proba"].median()), 3),
                "rationale": f"ML agrees with operator gold {gold_s}/{gold_f} ({100*agree.mean():.0f}% metres)",
            }
        )
    return rows


def _predict_bundle_routed(
    frame: pd.DataFrame,
    routes,
    cache,
) -> pd.DataFrame:
    from spatial.gold_suggester_routing import predict_frame_routed

    return predict_frame_routed(frame, routes, cache=cache)


def resolve_windows(args: argparse.Namespace) -> list[tuple[str, float, float]]:
    """Return (chunk_id, km_lo, km_hi) windows for suggestion."""
    if args.km_start is not None and args.km_end is not None:
        chunk_id = args.chunk or "course_window"
        return [(chunk_id, float(args.km_start), float(args.km_end))]
    if not args.triage_queue.exists():
        raise FileNotFoundError(f"Triage queue not found: {args.triage_queue}")
    triage = pd.read_csv(args.triage_queue)
    if args.chunk:
        triage = triage[triage["chunk_id"] == args.chunk]
    elif str(args.queue).upper() != "ALL":
        triage = triage[triage["queue"] == str(args.queue).upper()]
    if triage.empty:
        return []
    sort_col = "RPS" if "RPS" in triage.columns else triage.columns[0]
    windows: list[tuple[str, float, float]] = []
    for _, row in triage.sort_values(sort_col, ascending=False).iterrows():
        windows.append((str(row["chunk_id"]), float(row["km_start"]), float(row["km_end"])))
    return windows


def run_ml_suggest(args: argparse.Namespace) -> pd.DataFrame:
    use_routing = bool(getattr(args, "sector_routing", False))
    routes = None
    model_cache = None
    bundle = None
    if use_routing:
        from spatial.gold_suggester_routing import SectorModelCache, load_routing_manifest

        manifest = getattr(args, "routing_manifest", None) or DEFAULT_ROUTING_MANIFEST
        routes = load_routing_manifest(manifest)
        model_cache = SectorModelCache(routes)
    else:
        if not args.model.exists():
            raise FileNotFoundError(f"Model not found: {args.model}")
        bundle = joblib.load(args.model)
    windows = resolve_windows(args)
    if not windows:
        raise ValueError("No km windows to process (set --km-start/--km-end or triage filters)")

    terrain_map = load_terrain_map(args.terrain_map)
    gold_spans = operator_gold_spans(terrain_map)
    variance_gaps = variance_gap_spans(terrain_map)
    locked_mono = is_operator_locked_mono_class(terrain_map)
    all_rows: list[dict[str, Any]] = []
    mode: SuggestMode = args.mode
    for chunk_id, km_lo, km_hi in windows:
        frame = build_training_frame(
            panel_path=args.panel,
            terrain_map_path=args.terrain_map,
            hmm_path=args.hmm_draft,
            km_lo=km_lo,
            km_hi=km_hi,
        )
        predicted = (
            _predict_bundle_routed(frame, routes, model_cache)
            if use_routing
            else _predict_bundle(frame, bundle)
        )
        if mode in ("gaps-only", "all"):
            all_rows.extend(
                suggest_ml_gaps(
                    predicted,
                    gold_spans,
                    km_lo,
                    km_hi,
                    chunk_id=chunk_id,
                    min_span_km=MIN_SPAN_KM,
                )
            )
        if mode in ("revise", "all") and not locked_mono:
            all_rows.extend(
                suggest_ml_revise(
                    predicted,
                    gold_spans,
                    km_lo,
                    km_hi,
                    chunk_id=chunk_id,
                    min_span_km=MIN_SPAN_KM,
                    proba_threshold=float(args.revise_threshold),
                )
            )
        if mode == "all":
            if locked_mono:
                all_rows.extend(
                    suggest_ml_keep_locked_operator(
                        gold_spans,
                        km_lo,
                        km_hi,
                        chunk_id=chunk_id,
                    )
                )
            else:
                all_rows.extend(
                    suggest_ml_keep_summary(
                        predicted,
                        gold_spans,
                        km_lo,
                        km_hi,
                        chunk_id=chunk_id,
                    )
                )
    all_rows = apply_locked_mono_class_suppression(all_rows, terrain_map, gold_spans=gold_spans)
    all_rows = apply_variance_gap_suppression(all_rows, variance_gaps, gold_spans=gold_spans)
    return pd.DataFrame(all_rows, columns=ML_OUTPUT_COLUMNS)


def run_hmm_suggest(args: argparse.Namespace) -> pd.DataFrame:
    windows = resolve_windows(args)
    if not windows:
        raise ValueError("No triage chunks match filter")
    terrain_map = load_terrain_map(args.terrain_map)
    gold_spans = operator_gold_spans(terrain_map)
    all_rows: list[dict[str, Any]] = []
    for chunk_id, km_lo, km_hi in windows:
        panel = load_panel_window(args.panel, km_lo, km_hi)
        profile = build_consensus_profile(panel)
        hmm = load_hmm_window(args.hmm_draft, km_lo, km_hi)
        all_rows.extend(
            suggest_for_chunk(
                chunk_id,
                km_lo,
                km_hi,
                profile=profile,
                hmm=hmm,
                gold_spans=gold_spans,
            )
        )
    return pd.DataFrame(all_rows, columns=HMM_OUTPUT_COLUMNS)


def run_self_test() -> None:
    """Synthetic pipeline check — no production files required."""
    mono_map = {
        "hitl": {
            "status": "locked",
            "operator_gold_spans": [
                {"course_km_start": 41.0, "course_km_end": 41.6, "surface_class": "S1", "friction_tier": "F0"},
                {"course_km_start": 41.6, "course_km_end": 42.5, "surface_class": "S1", "friction_tier": "F0"},
            ],
        }
    }
    assert is_operator_locked_mono_class(mono_map)
    multi_map = {
        "hitl": {
            "status": "locked",
            "operator_gold_spans": [
                {"course_km_start": 0.5, "course_km_end": 1.0, "surface_class": "S1", "friction_tier": "F0"},
                {"course_km_start": 1.0, "course_km_end": 2.0, "surface_class": "S4", "friction_tier": "F3"},
            ],
        }
    }
    assert not is_operator_locked_mono_class(multi_map)
    revise_rows = [
        {
            "action": "REVISE",
            "km_start": 41.0,
            "km_end": 41.6,
            "surface_class": "S2",
            "friction_tier": "F1",
            "rationale": "ML revise",
        }
    ]
    suppressed = apply_locked_mono_class_suppression(revise_rows, mono_map)
    assert suppressed == [], "locked mono-class should drop REVISE rows"
    keep_rows = suggest_ml_keep_locked_operator(
        operator_gold_spans(mono_map),
        41.0,
        42.5,
        chunk_id="chunk_selftest",
    )
    assert len(keep_rows) == 2
    assert all(r["action"] == "KEEP" for r in keep_rows)

    hmm_rows = []
    profile_rows = []
    for i in range(120):
        km = 37.0 + i * 0.001
        cls = "S4" if i >= 50 else "S3"
        p = 0.88 if cls == "S4" else 0.72
        ti = 1.55 if cls == "S4" else 1.25
        hmm_rows.append({"course_km": km, "draft_class": cls, "hmm_confidence": p})
        profile_rows.append({"course_m": int(km * 1000), "course_km": km, "ti_median": ti, "nti_std": 0.12})
    hmm = pd.DataFrame(hmm_rows)
    profile = pd.DataFrame(profile_rows)
    gold = [{"course_km_start": 37.0, "course_km_end": 37.05, "surface_class": "S3", "friction_tier": "F2"}]
    rows = suggest_for_chunk("chunk_selftest", 37.0, 37.12, profile=profile, hmm=hmm, gold_spans=gold)
    assert rows, "self-test expected at least one suggestion"
    assert rows[0]["surface_class"] == "S4"
    print("self_test: OK")
    print(pd.DataFrame(rows).to_string(index=False))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Propose HITL gold lock spans (HMM heuristic or ML suggester).")
    parser.add_argument("--engine", choices=("hmm", "ml"), default="hmm", help="Suggestion engine")
    parser.add_argument(
        "--mode",
        choices=("gaps-only", "revise", "all"),
        default="gaps-only",
        help="ML mode: fill gaps, flag revisions, or both (+ KEEP summary)",
    )
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="ML model joblib (engine=ml, ignored with --sector-routing)")
    parser.add_argument(
        "--sector-routing",
        action="store_true",
        help="Route predictions by course km using config/gold_suggester_routing.json sector models",
    )
    parser.add_argument(
        "--routing-manifest",
        type=Path,
        default=DEFAULT_ROUTING_MANIFEST,
        help="Sector routing manifest (used with --sector-routing)",
    )
    parser.add_argument("--revise-threshold", type=float, default=REVISE_PROBA_THRESHOLD)
    parser.add_argument("--km-start", type=float, default=None, help="Course-wide window start (inclusive)")
    parser.add_argument("--km-end", type=float, default=None, help="Course-wide window end (exclusive)")
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--terrain-map", type=Path, default=DEFAULT_TERRAIN_MAP)
    parser.add_argument("--triage-queue", type=Path, default=DEFAULT_TRIAGE_QUEUE)
    parser.add_argument("--hmm-draft", type=Path, default=DEFAULT_HMM_DRAFT)
    parser.add_argument(
        "--no-hmm-draft",
        action="store_true",
        help="Skip HMM draft merge (map-first courses without SUT_43 HMM parquet)",
    )
    parser.add_argument("--queue", type=str, default="RED", help="Triage queue filter (RED/YELLOW/GREEN/ALL)")
    parser.add_argument("--chunk", type=str, default=None, help="Single chunk_id e.g. chunk_08")
    parser.add_argument("--min-span-m", type=float, default=50.0, help="Minimum contiguous run (metres)")
    parser.add_argument(
        "--surface-filter",
        type=str,
        default=None,
        help="Comma-separated S-classes to keep (e.g. S1,S2)",
    )
    parser.add_argument(
        "--road-like",
        action="store_true",
        help="Shortcut for --surface-filter S1,S2 (map-visible asphalt and gravel)",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--print-sample", action="store_true", help="Print suggestions to stdout")
    parser.add_argument("--self-test", action="store_true", help="Run synthetic pipeline check")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        run_self_test()
        return 0
    global MIN_SPAN_KM
    MIN_SPAN_KM = max(0.001, float(args.min_span_m) / 1000.0)
    hmm_path: Path | None = None if args.no_hmm_draft else args.hmm_draft
    args.hmm_draft = hmm_path  # type: ignore[misc]

    if args.engine == "ml" and not args.sector_routing and not args.model.exists():
        print(f"Model not found: {args.model}", file=sys.stderr)
        return 1

    if not args.panel.exists():
        print(f"Panel not found: {args.panel}", file=sys.stderr)
        return 1
    if not args.terrain_map.exists():
        print(f"Terrain map not found: {args.terrain_map}", file=sys.stderr)
        return 1

    surface_filter: set[str] | None = None
    if args.road_like:
        surface_filter = set(ROAD_LIKE_SURFACE_CLASSES)
    elif args.surface_filter:
        surface_filter = {part.strip().upper() for part in args.surface_filter.split(",") if part.strip()}

    try:
        if args.engine == "ml":
            out_df = run_ml_suggest(args)
        else:
            if args.km_start is None and args.km_end is None and not args.triage_queue.exists():
                print(f"Triage queue not found: {args.triage_queue}", file=sys.stderr)
                return 1
            out_df = run_hmm_suggest(args)
        if surface_filter and not out_df.empty:
            allowed = set(surface_filter)
            out_df = out_df[out_df["surface_class"].astype(str).str.upper().isin(allowed)].reset_index(drop=True)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.output, index=False)

    print(f"Wrote {len(out_df)} suggestion(s) → {args.output} (engine={args.engine})")
    if args.print_sample or args.chunk or (args.km_start is not None and args.km_end is not None):
        sample = out_df.head(20)
        if not sample.empty:
            print(sample.to_string(index=False))
        else:
            print("(no suggestions — window may be fully golded or model abstains)")
            terrain_map = load_terrain_map(args.terrain_map)
            gold_spans = operator_gold_spans(terrain_map)
            try:
                windows = resolve_windows(args)
            except FileNotFoundError:
                windows = []
            for chunk_id, km_lo, km_hi in windows:
                gaps = ungolded_intervals(km_lo, km_hi, gold_spans)
                ungolded_km = sum(b - a for a, b in gaps)
                hmm = load_hmm_window(args.hmm_draft, km_lo, km_hi)
                disagree = draft_gold_disagreement_pct(hmm, gold_spans, km_lo, km_hi)
                msg = f"  {chunk_id} km {km_lo:.1f}–{km_hi:.1f}: ungolded={ungolded_km:.3f} km"
                if disagree is not None:
                    msg += f"; HMM vs gold disagree={disagree:.1f}%"
                print(msg)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
