#!/usr/bin/env python3
"""
Train sparse-gold suggester models (surface S-class + friction F-tier).

Reads labeled metres from build_gold_training_set export; saves joblib bundle + metadata.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/train_gold_suggester.py \\
        --training-set 03_Processed_Data/spatial/gold_training_set_sut43.parquet

    python3 04_Python_Scripts/spatial/train_gold_suggester.py \\
        --training-set 03_Processed_Data/spatial/gold_training_set_stavanger_halvmarathon.parquet \\
        --training-set 03_Processed_Data/spatial/gold_training_set_sunderunde.parquet \\
        --training-set 03_Processed_Data/spatial/gold_training_set_3_sjoerslopet.parquet
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.gold_training_common import FEATURE_COLUMNS, FRICTION_TIERS, SURFACE_CLASSES

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_TRAINING_SET = BASE_DIR / "03_Processed_Data" / "spatial" / "gold_training_set_sut43.parquet"
DEFAULT_MODEL_DIR = BASE_DIR / "07_ML_Models" / "spatial"
DEFAULT_MODEL_PATH = DEFAULT_MODEL_DIR / "gold_suggester_v0.joblib"
DEFAULT_METADATA_PATH = DEFAULT_MODEL_DIR / "gold_suggester_v0_metadata.json"

MIN_LABELED_METRES = 200
RANDOM_STATE = 42


def _prepare_xy(
    df: pd.DataFrame,
    feature_cols: list[str],
    label_col: str,
    *,
    sample_weights: pd.Series | None = None,
) -> tuple[pd.DataFrame, pd.Series, np.ndarray | None]:
    labeled = df[df["is_labeled"] & df[label_col].notna()].copy()
    x = labeled[feature_cols].copy()
    for col in feature_cols:
        if x[col].dtype == object:
            x[col] = pd.to_numeric(x[col], errors="coerce")
    medians = x.median(numeric_only=True)
    x = x.fillna(medians)
    y = labeled[label_col].astype(str)
    weights = None
    if sample_weights is not None:
        weights = sample_weights.reindex(labeled.index).fillna(1.0).to_numpy(dtype=float)
    return x, y, weights


def _active_feature_columns(df: pd.DataFrame, feature_cols: list[str]) -> list[str]:
    """Keep columns with ≥2 distinct values after median imputation on labeled rows."""
    labeled = df[df["is_labeled"]].copy()
    active: list[str] = []
    for col in feature_cols:
        if col not in labeled.columns:
            continue
        series = pd.to_numeric(labeled[col], errors="coerce")
        filled = series.fillna(series.median())
        if filled.nunique(dropna=True) >= 2:
            active.append(col)
    return active


def _train_classifier(
    x: pd.DataFrame,
    y: pd.Series,
    *,
    classes: tuple[str, ...],
    sample_weight: np.ndarray | None = None,
) -> tuple[HistGradientBoostingClassifier, dict[str, Any]]:
    present_classes = sorted(set(y.unique()) & set(classes))
    if len(present_classes) < 2:
        raise ValueError(f"Need ≥2 classes for training; got {present_classes}")

    stratify = y if y.value_counts().min() >= 2 else None
    split_kwargs: dict[str, Any] = {
        "test_size": 0.2,
        "random_state": RANDOM_STATE,
        "stratify": stratify,
    }
    if sample_weight is not None:
        x_train, x_test, y_train, y_test, w_train, _w_test = train_test_split(
            x,
            y,
            sample_weight,
            **split_kwargs,
        )
    else:
        x_train, x_test, y_train, y_test = train_test_split(x, y, **split_kwargs)
        w_train = None
    clf = HistGradientBoostingClassifier(
        max_depth=8,
        learning_rate=0.08,
        max_iter=200,
        random_state=RANDOM_STATE,
    )
    if w_train is not None:
        clf.fit(x_train, y_train, sample_weight=w_train)
    else:
        clf.fit(x_train, y_train)
    y_pred = clf.predict(x_test)
    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    metrics: dict[str, Any] = {
        "n_train": int(len(x_train)),
        "n_test": int(len(x_test)),
        "classes": present_classes,
        "classification_report": report,
        "accuracy": float(report.get("accuracy", 0.0)),
    }
    return clf, metrics


def _load_training_frames(paths: list[Path]) -> tuple[pd.DataFrame, list[Path]]:
    frames: list[pd.DataFrame] = []
    loaded: list[Path] = []
    for path in paths:
        if not path.exists():
            print(f"Training set not found: {path}", file=sys.stderr)
            raise FileNotFoundError(path)
        frames.append(pd.read_parquet(path))
        loaded.append(path)
    if len(frames) == 1:
        return frames[0], loaded
    return pd.concat(frames, ignore_index=True), loaded


def _load_negative_set(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_parquet(path)


def _apply_negative_weights(
    df: pd.DataFrame,
    negatives: pd.DataFrame,
    *,
    boost: float,
) -> pd.Series:
    """Elevate sample_weight on labeled metres overlapping harvested negative spans."""
    weights = pd.Series(1.0, index=df.index, dtype=float)
    if negatives.empty or boost <= 1.0:
        return weights
    labeled = df["is_labeled"] & df["label_surface"].notna() & df["label_friction"].notna()
    km = df["course_km"]
    for _, neg in negatives.iterrows():
        km_start = float(neg["course_km_start"])
        km_end = float(neg["course_km_end"])
        mask = labeled & (km >= km_start) & (km < km_end)
        weights.loc[mask] = np.maximum(weights.loc[mask], boost)
    return weights


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train gold span suggester (surface + friction).")
    parser.add_argument(
        "--training-set",
        type=Path,
        action="append",
        dest="training_sets",
        help="Training parquet (repeatable; defaults to SUT43 export)",
    )
    parser.add_argument("--model-out", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--metadata-out", type=Path, default=DEFAULT_METADATA_PATH)
    parser.add_argument("--min-labeled", type=int, default=MIN_LABELED_METRES)
    parser.add_argument(
        "--negative-set",
        type=Path,
        default=None,
        help="Harvested negative spans parquet (boosts gold-label weight in overlap windows)",
    )
    parser.add_argument(
        "--negative-weight",
        type=float,
        default=3.0,
        help="Sample-weight multiplier for metres overlapping negative spans",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    training_paths = args.training_sets or [DEFAULT_TRAINING_SET]
    try:
        df, training_paths = _load_training_frames(training_paths)
    except FileNotFoundError:
        return 1
    labeled_n = int(df["is_labeled"].sum())
    if labeled_n < args.min_labeled:
        print(
            f"Insufficient labeled metres: {labeled_n} < {args.min_labeled}. "
            "Annotate more gold spans before training.",
            file=sys.stderr,
        )
        return 1

    feature_cols = _active_feature_columns(df, [c for c in FEATURE_COLUMNS if c in df.columns])
    if not feature_cols:
        print("No usable feature columns found in training set.", file=sys.stderr)
        return 1
    dropped = sorted(set(FEATURE_COLUMNS) & set(df.columns) - set(feature_cols))
    if dropped:
        print(f"Dropped inactive features: {', '.join(dropped)}")

    negatives_meta: dict[str, Any] | None = None
    sample_weights = pd.Series(1.0, index=df.index, dtype=float)
    if args.negative_set:
        try:
            negatives = _load_negative_set(args.negative_set)
        except FileNotFoundError:
            print(f"Negative set not found: {args.negative_set}", file=sys.stderr)
            return 1
        sample_weights = _apply_negative_weights(df, negatives, boost=args.negative_weight)
        boosted_n = int((sample_weights > 1.0).sum())
        negatives_meta = {
            "negative_set": str(args.negative_set),
            "negative_spans": len(negatives),
            "negative_weight": args.negative_weight,
            "boosted_metres": boosted_n,
            "reject_reason_counts": negatives["reject_reason"].value_counts(dropna=False).to_dict()
            if "reject_reason" in negatives.columns
            else {},
        }
        print(
            f"Negative reinforcement: {len(negatives)} span(s), "
            f"{boosted_n} metre(s) at weight×{args.negative_weight}"
        )

    x_surf, y_surf, w_surf = _prepare_xy(df, feature_cols, "label_surface", sample_weights=sample_weights)
    x_fric, y_fric, w_fric = _prepare_xy(df, feature_cols, "label_friction", sample_weights=sample_weights)

    surface_clf, surface_metrics = _train_classifier(
        x_surf, y_surf, classes=SURFACE_CLASSES, sample_weight=w_surf
    )
    friction_clf, friction_metrics = _train_classifier(
        x_fric, y_fric, classes=FRICTION_TIERS, sample_weight=w_fric
    )

    feature_medians = df[feature_cols].median(numeric_only=True).to_dict()
    bundle = {
        "surface_model": surface_clf,
        "friction_model": friction_clf,
        "feature_columns": feature_cols,
        "feature_medians": feature_medians,
        "surface_classes": list(SURFACE_CLASSES),
        "friction_tiers": list(FRICTION_TIERS),
        "schema_version": "gold_suggester_v0",
    }

    args.model_out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, args.model_out)

    metadata = {
        "schema_version": "gold_suggester_v0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "training_set": str(training_paths[0]) if len(training_paths) == 1 else None,
        "training_sets": [str(p) for p in training_paths],
        "labeled_metres": labeled_n,
        "total_metres": len(df),
        "feature_columns": feature_cols,
        "dropped_features": dropped,
        "surface_metrics": surface_metrics,
        "friction_metrics": friction_metrics,
        "model_path": str(args.model_out),
    }
    if negatives_meta:
        metadata["negative_reinforcement"] = negatives_meta
    args.metadata_out.parent.mkdir(parents=True, exist_ok=True)
    args.metadata_out.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    print(f"Saved model → {args.model_out}")
    print(f"Metadata → {args.metadata_out}")
    print(
        f"Surface holdout accuracy: {surface_metrics['accuracy']:.3f} "
        f"(n_train={surface_metrics['n_train']}, n_test={surface_metrics['n_test']})"
    )
    print(
        f"Friction holdout accuracy: {friction_metrics['accuracy']:.3f} "
        f"(n_train={friction_metrics['n_train']}, n_test={friction_metrics['n_test']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
