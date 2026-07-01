#!/usr/bin/env python3
"""
HMM draft pre-computation scaffold for terrain surface classification.

Trains on operator-gold spans (km 22–34: upstream + gramstad_band), applies
Viterbi smoothing with spatial transition penalties, and emits **draft** class
predictions for management-by-exception triage. Does **not** replace operator gold.

Extended predict window km 8–41 when midcourse feature parquet is present.

Usage (from repo root):
    python3 07_ML_Models/train_terrain_hmm.py --dry-run

    python3 07_ML_Models/train_terrain_hmm.py \\
        --predict-km-start 29 --predict-km-end 41 \\
        --output 07_ML_Models/terrain_hmm_sut43_draft_predictions.parquet
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import LabelEncoder

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "04_Python_Scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "04_Python_Scripts"))

from spatial.corridor_scope import (
    SUT43_FULL_KM_END,
    SUT43_MIDCOURSE_KM_START,
    SUT43_PRIMARY_KM_END,
    SUT43_PRIMARY_KM_START,
    SUT43_UPSTREAM_KM_END,
    SUT43_UPSTREAM_KM_START,
)
from spatial.hitl_agreement import apply_operator_gold_spans, operator_gold_spans_from_map
from spatial.spatial_hitl_overlay import load_terrain_map

DEFAULT_GRAMSTAD_MAP = _REPO_ROOT / "config" / "spatial_terrain_map_sut43.json"
DEFAULT_UPSTREAM_MAP = _REPO_ROOT / "config" / "spatial_terrain_map_sut43_upstream.json"
DEFAULT_GRAMSTAD_FEATURES = (
    _REPO_ROOT / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "ml_features_1m.parquet"
)
DEFAULT_UPSTREAM_FEATURES = (
    _REPO_ROOT
    / "03_Processed_Data"
    / "spatial"
    / "sut43_terrain_ontology"
    / "upstream_draft"
    / "ml_features_1m.parquet"
)
DEFAULT_MIDCOURSE_FEATURES = (
    _REPO_ROOT
    / "03_Processed_Data"
    / "spatial"
    / "sut43_terrain_ontology"
    / "midcourse_draft"
    / "ml_features_1m.parquet"
)
DEFAULT_OUTPUT = _REPO_ROOT / "07_ML_Models" / "terrain_hmm_sut43_draft_predictions.parquet"
DEFAULT_DIAGNOSTICS = _REPO_ROOT / "07_ML_Models" / "terrain_hmm_sut43_diagnostics.json"

ML_CLASSES = ("S1", "S2", "S3", "S4", "S5", "S6")
HMM_FEATURE_COLS = (
    "speed_median",
    "grade_pct_median",
    "cadence_median",
    "consensus_nti",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def merged_operator_gold_spans(
    upstream_map: dict[str, Any],
    gramstad_map: dict[str, Any],
) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    spans.extend(operator_gold_spans_from_map(upstream_map))
    spans.extend(operator_gold_spans_from_map(gramstad_map))
    return spans


def load_merged_features(
    upstream_features_path: Path,
    gramstad_features_path: Path,
    *,
    midcourse_features_path: Path | None = None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in (midcourse_features_path, upstream_features_path, gramstad_features_path):
        if path is None or not path.exists():
            continue
        frames.append(pd.read_parquet(path))
    if not frames:
        raise FileNotFoundError("No feature parquets found for HMM ingest")
    merged = pd.concat(frames, ignore_index=True)
    merged = merged.sort_values("course_m").drop_duplicates("course_m", keep="last")
    return merged.reset_index(drop=True)


def gold_labels_from_spans(
    features: pd.DataFrame,
    spans: list[dict[str, Any]],
) -> pd.DataFrame:
    """Attach ml_label_class from operator_gold_spans onto feature grid."""
    base = features[["course_m", "course_km"]].copy()
    base["agreement_tier"] = None
    base["gold_source"] = None
    base["operator_gold_class"] = None
    labeled = apply_operator_gold_spans(base, spans)
    labeled["ml_label_class"] = labeled["operator_gold_class"]
    return labeled


def _available_feature_cols(df: pd.DataFrame) -> list[str]:
    cols = [c for c in HMM_FEATURE_COLS if c in df.columns]
    if not cols:
        raise ValueError(f"No HMM feature columns found; expected subset of {HMM_FEATURE_COLS}")
    return cols


def build_transition_log_probs(
    classes: list[str],
    *,
    stay_log_prob: float = -0.05,
    switch_log_prob: float = -2.5,
) -> np.ndarray:
    """Strong diagonal — penalize class switches (spatial continuity)."""
    n = len(classes)
    mat = np.full((n, n), switch_log_prob, dtype=float)
    np.fill_diagonal(mat, stay_log_prob)
    return mat


def viterbi_decode(
    log_emissions: np.ndarray,
    transition_log_probs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Viterbi over T time steps × K hidden states.

    log_emissions: (T, K) log P(obs_t | state_k)
    transition_log_probs: (K, K) log P(state_j | state_i)
    """
    t_steps, n_states = log_emissions.shape
    dp = np.full((t_steps, n_states), -np.inf)
    backptr = np.zeros((t_steps, n_states), dtype=int)

    dp[0] = log_emissions[0]
    for t in range(1, t_steps):
        for j in range(n_states):
            scores = dp[t - 1] + transition_log_probs[:, j]
            backptr[t, j] = int(np.argmax(scores))
            dp[t, j] = scores[backptr[t, j]] + log_emissions[t, j]

    path = np.zeros(t_steps, dtype=int)
    path[-1] = int(np.argmax(dp[-1]))
    conf = np.exp(dp[-1, path[-1]] - np.max(dp[-1]))  # rough terminal confidence
    for t in range(t_steps - 2, -1, -1):
        path[t] = backptr[t + 1, path[t + 1]]
    return path, np.full(t_steps, conf, dtype=float)


def _run_length_segment_lengths(classes: np.ndarray) -> list[int]:
    if len(classes) == 0:
        return []
    lengths: list[int] = []
    run = 1
    for i in range(1, len(classes)):
        if classes[i] == classes[i - 1]:
            run += 1
        else:
            lengths.append(run)
            run = 1
    lengths.append(run)
    return lengths


def evaluate_oversmoothing_gates(
    draft: pd.DataFrame,
    features: pd.DataFrame,
    *,
    predict_km_start: float,
    predict_km_end: float,
    mvl_min_m: float = 15.0,
    s56_ti_spike_tolerance: float = 0.10,
    switches_per_km_min: float = 2.0,
    switches_per_km_max: float = 8.0,
    technical_km_windows: list[tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """
    Over-smoothing acceptance gates (Strategic Command 2026-06-29):
    - MVL >= 15 m (minimum viable segment length after Viterbi)
    - S5/S6 draft calls land within 10% of local TI p90 spike
    - Technical chunks: 2–8 class switches per km
    """
    merged = draft.merge(
        features[["course_m", "ti_median"]].drop_duplicates("course_m"),
        on="course_m",
        how="left",
    )
    classes = merged["draft_class"].astype(str).to_numpy()
    segment_lengths = _run_length_segment_lengths(classes)
    mvl_m = float(min(segment_lengths)) if segment_lengths else 0.0

    ti = pd.to_numeric(merged["ti_median"], errors="coerce")
    ti_p90 = float(ti.quantile(0.90)) if ti.notna().any() else float("nan")
    s56_mask = merged["draft_class"].isin(["S5", "S6"])
    if s56_mask.any() and np.isfinite(ti_p90) and ti_p90 > 0:
        s56_ti = ti[s56_mask]
        within_tol = ((s56_ti - ti_p90).abs() / ti_p90) <= s56_ti_spike_tolerance
        s56_within_pct = float(within_tol.mean())
    else:
        s56_within_pct = 1.0

    if technical_km_windows is None:
        technical_km_windows = [(29.0, 34.0), (36.5, 38.5)]

    switch_reports: list[dict[str, Any]] = []
    for win_lo, win_hi in technical_km_windows:
        win = merged[(merged["course_km"] >= win_lo) & (merged["course_km"] < win_hi)]
        if win.empty:
            continue
        n_switches = int((win["draft_class"] != win["draft_class"].shift()).sum() - 1)
        span_km = max(win_hi - win_lo, 1e-6)
        switches_per_km = n_switches / span_km
        switch_reports.append(
            {
                "km_window": [win_lo, win_hi],
                "switches": n_switches,
                "switches_per_km": round(switches_per_km, 3),
                "pass": switches_per_km_min <= switches_per_km <= switches_per_km_max,
            }
        )

    gates = {
        "mvl_m": round(mvl_m, 1),
        "mvl_pass": mvl_m >= mvl_min_m,
        "mvl_min_required_m": mvl_min_m,
        "s56_within_spike_pct": round(s56_within_pct, 4),
        "s56_spike_tolerance": s56_ti_spike_tolerance,
        "s56_pass": s56_within_pct >= (1.0 - s56_ti_spike_tolerance) or not s56_mask.any(),
        "technical_switch_windows": switch_reports,
        "switches_pass": all(r["pass"] for r in switch_reports) if switch_reports else True,
    }
    gates["all_pass"] = bool(gates["mvl_pass"] and gates["s56_pass"] and gates["switches_pass"])
    return gates


def train_hmm_draft(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    train_km_start: float,
    train_km_end: float,
    predict_km_start: float,
    predict_km_end: float,
    transition_stay: float = -0.05,
    transition_switch: float = -2.5,
    random_state: int = 42,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    merged = features.merge(labels[["course_m", "ml_label_class"]], on="course_m", how="left")
    feature_cols = _available_feature_cols(merged)

    train = merged[
        (merged["course_km"] >= train_km_start)
        & (merged["course_km"] < train_km_end)
        & merged["ml_label_class"].isin(ML_CLASSES)
    ].copy()
    predict = merged[
        (merged["course_km"] >= predict_km_start) & (merged["course_km"] < predict_km_end)
    ].copy()

    if train.empty:
        raise ValueError(
            f"No operator-gold training rows in km {train_km_start}–{train_km_end}. "
            "Check terrain map operator_gold_spans[] and feature parquets."
        )
    if predict.empty:
        raise ValueError(f"No prediction rows in km {predict_km_start}–{predict_km_end}")

    le = LabelEncoder()
    le.fit(list(ML_CLASSES))
    y_train = le.transform(train["ml_label_class"].astype(str))
    clf = HistGradientBoostingClassifier(
        class_weight="balanced",
        random_state=random_state,
        max_iter=150,
    )
    X_train = train[feature_cols].fillna(train[feature_cols].median(numeric_only=True))
    clf.fit(X_train, y_train)

    X_pred = predict[feature_cols].fillna(train[feature_cols].median(numeric_only=True))
    proba = clf.predict_proba(X_pred)
    class_order = np.array([str(c) for c in le.classes_])
    proba_aligned = np.full((len(predict), len(class_order)), 1.0 / len(class_order))
    for i, enc_label in enumerate(clf.classes_):
        cls = str(le.inverse_transform([enc_label])[0])
        j = int(np.where(class_order == cls)[0][0])
        proba_aligned[:, j] = proba[:, i]

    eps = 1e-12
    log_emissions = np.log(np.clip(proba_aligned, eps, 1.0))
    transition = build_transition_log_probs(
        list(class_order),
        stay_log_prob=transition_stay,
        switch_log_prob=transition_switch,
    )
    path_idx, path_conf = viterbi_decode(log_emissions, transition)
    pred_classes = le.inverse_transform(path_idx)
    max_proba = proba_aligned.max(axis=1)

    out = predict[["course_m", "course_km"]].copy()
    out["draft_class"] = pred_classes
    out["hmm_confidence"] = max_proba
    out["viterbi_score"] = path_conf
    out["is_draft"] = True
    out["gold_source"] = "hmm_draft"
    out["generated_at"] = _utc_now()

    oversmoothing = evaluate_oversmoothing_gates(
        out,
        merged,
        predict_km_start=predict_km_start,
        predict_km_end=predict_km_end,
    )

    diagnostics: dict[str, Any] = {
        "schema_version": "terrain_hmm_draft_v0",
        "generated_at": _utc_now(),
        "train_km": [train_km_start, train_km_end],
        "predict_km": [predict_km_start, predict_km_end],
        "n_train_rows": int(len(train)),
        "n_predict_rows": int(len(out)),
        "feature_columns": feature_cols,
        "class_distribution_train": train["ml_label_class"].value_counts().to_dict(),
        "class_distribution_draft": out["draft_class"].value_counts().to_dict(),
        "mean_hmm_confidence": float(out["hmm_confidence"].mean()),
        "transition_stay_log_prob": transition_stay,
        "transition_switch_log_prob": transition_switch,
        "oversmoothing_gates": oversmoothing,
        "note": "Draft predictions only — operator gold spans remain authoritative.",
    }
    return out, diagnostics


def main() -> None:
    parser = argparse.ArgumentParser(description="HMM draft terrain classifier scaffold")
    parser.add_argument("--upstream-map", type=Path, default=DEFAULT_UPSTREAM_MAP)
    parser.add_argument("--gramstad-map", type=Path, default=DEFAULT_GRAMSTAD_MAP)
    parser.add_argument("--upstream-features", type=Path, default=DEFAULT_UPSTREAM_FEATURES)
    parser.add_argument("--gramstad-features", type=Path, default=DEFAULT_GRAMSTAD_FEATURES)
    parser.add_argument("--midcourse-features", type=Path, default=DEFAULT_MIDCOURSE_FEATURES)
    parser.add_argument("--train-km-start", type=float, default=SUT43_UPSTREAM_KM_START)
    parser.add_argument("--train-km-end", type=float, default=34.0)
    parser.add_argument("--predict-km-start", type=float, default=SUT43_MIDCOURSE_KM_START)
    parser.add_argument("--predict-km-end", type=float, default=SUT43_FULL_KM_END)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--diagnostics", type=Path, default=DEFAULT_DIAGNOSTICS)
    parser.add_argument("--dry-run", action="store_true", help="Train/predict without writing files")
    args = parser.parse_args()

    upstream_map = load_terrain_map(args.upstream_map)
    gramstad_map = load_terrain_map(args.gramstad_map)
    spans = merged_operator_gold_spans(upstream_map, gramstad_map)
    print(f"Operator gold spans: {len(spans)} (upstream + gramstad maps)")

    features = load_merged_features(
        args.upstream_features,
        args.gramstad_features,
        midcourse_features_path=args.midcourse_features,
    )
    labels = gold_labels_from_spans(features, spans)
    n_gold = int(
        labels[
            (labels["course_km"] >= args.train_km_start)
            & (labels["course_km"] < args.train_km_end)
            & labels["ml_label_class"].notna()
        ].shape[0]
    )
    print(f"Gold-labelled metres (train window): {n_gold}")

    draft, diagnostics = train_hmm_draft(
        features,
        labels,
        train_km_start=args.train_km_start,
        train_km_end=args.train_km_end,
        predict_km_start=args.predict_km_start,
        predict_km_end=args.predict_km_end,
    )

    print(f"Draft predictions: {len(draft)} rows, km {args.predict_km_start}–{args.predict_km_end}")
    print(f"Mean HMM confidence: {diagnostics['mean_hmm_confidence']:.3f}")
    print(f"Draft class counts: {diagnostics['class_distribution_draft']}")
    gates = diagnostics.get("oversmoothing_gates", {})
    if gates:
        print(
            f"Over-smoothing gates: MVL={gates.get('mvl_m')}m "
            f"({'PASS' if gates.get('mvl_pass') else 'FAIL'}) · "
            f"S5/S6 spike={gates.get('s56_within_spike_pct', 0):.2%} "
            f"({'PASS' if gates.get('s56_pass') else 'FAIL'}) · "
            f"switches={'PASS' if gates.get('switches_pass') else 'FAIL'} · "
            f"ALL={'PASS' if gates.get('all_pass') else 'FAIL'}"
        )

    if args.dry_run:
        print("Dry-run — no files written.")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    draft.to_parquet(args.output, index=False)
    args.diagnostics.write_text(json.dumps(diagnostics, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"Wrote {args.diagnostics}")


if __name__ == "__main__":
    main()
