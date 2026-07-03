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
from sklearn.metrics import accuracy_score, classification_report
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


def _make_classifier() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_depth=8,
        learning_rate=0.08,
        max_iter=200,
        random_state=RANDOM_STATE,
    )


def _fit_classifier(
    x: pd.DataFrame,
    y: pd.Series,
    *,
    sample_weight: np.ndarray | None = None,
) -> HistGradientBoostingClassifier:
    clf = _make_classifier()
    if sample_weight is not None:
        clf.fit(x, y, sample_weight=sample_weight)
    else:
        clf.fit(x, y)
    return clf


def _accuracy_report(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, Any]:
    report = classification_report(y_true, y_pred, output_dict=True, zero_division=0)
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "n": int(len(y_true)),
        "classification_report": report,
    }


def _per_source_accuracy(
    y_true: pd.Series,
    y_pred: np.ndarray,
    sources: pd.Series,
) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    aligned = sources.reindex(y_true.index)
    for anchor in sorted(aligned.dropna().unique()):
        mask = aligned == anchor
        if not mask.any():
            continue
        out[str(anchor)] = {
            "accuracy": float(accuracy_score(y_true[mask], y_pred[mask.to_numpy()])),
            "n": int(mask.sum()),
        }
    return out


def _source_holdout_eval(
    x: pd.DataFrame,
    y: pd.Series,
    sources: pd.Series,
    *,
    train_sources: set[str],
    test_sources: set[str],
    sample_weight: np.ndarray | None = None,
) -> dict[str, Any] | None:
    src = sources.reindex(x.index)
    train_mask = src.isin(train_sources)
    test_mask = src.isin(test_sources)
    if not train_mask.any() or not test_mask.any():
        return None
    w_train = sample_weight[train_mask.to_numpy()] if sample_weight is not None else None
    clf = _fit_classifier(x.loc[train_mask], y.loc[train_mask], sample_weight=w_train)
    y_pred = clf.predict(x.loc[test_mask])
    metrics = _accuracy_report(y.loc[test_mask], y_pred)
    metrics["train_sources"] = sorted(train_sources)
    metrics["test_sources"] = sorted(test_sources)
    metrics["n_train"] = int(train_mask.sum())
    return metrics


def _apply_source_weights(
    df: pd.DataFrame,
    weights: dict[str, float],
) -> pd.Series:
    base = pd.Series(1.0, index=df.index, dtype=float)
    if "source_anchor" not in df.columns or not weights:
        return base
    for anchor, mult in weights.items():
        mask = df["source_anchor"] == anchor
        base.loc[mask] *= float(mult)
    return base


def _parse_source_weight(spec: str) -> tuple[str, float]:
    if ":" not in spec:
        raise ValueError(f"Invalid --source-weight '{spec}'; expected SOURCE:WEIGHT")
    anchor, raw = spec.split(":", 1)
    anchor = anchor.strip()
    if not anchor:
        raise ValueError(f"Invalid --source-weight '{spec}'; empty source anchor")
    return anchor, float(raw)


def _train_classifier(
    x: pd.DataFrame,
    y: pd.Series,
    *,
    classes: tuple[str, ...],
    sample_weight: np.ndarray | None = None,
    sources: pd.Series | None = None,
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
    clf = _fit_classifier(x_train, y_train, sample_weight=w_train)
    y_pred = clf.predict(x_test)
    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    metrics: dict[str, Any] = {
        "n_train": int(len(x_train)),
        "n_test": int(len(x_test)),
        "classes": present_classes,
        "classification_report": report,
        "accuracy": float(report.get("accuracy", 0.0)),
    }
    if sources is not None:
        test_idx = y_test.index
        metrics["per_source_accuracy"] = _per_source_accuracy(
            y_test, y_pred, sources.reindex(test_idx)
        )
    return clf, metrics


def _filter_training_frame(
    df: pd.DataFrame,
    *,
    km_start: float | None,
    km_end: float | None,
    include_anchors: set[str] | None,
    exclude_anchors: set[str] | None,
) -> pd.DataFrame:
    out = df
    if km_start is not None:
        out = out[out["course_km"] >= km_start]
    if km_end is not None:
        out = out[out["course_km"] < km_end]
    if include_anchors is not None and "source_anchor" in out.columns:
        out = out[out["source_anchor"].isin(include_anchors)]
    if exclude_anchors is not None and "source_anchor" in out.columns:
        out = out[~out["source_anchor"].isin(exclude_anchors)]
    return out.reset_index(drop=True)


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
    parser.add_argument(
        "--source-weight",
        action="append",
        default=[],
        metavar="ANCHOR:WEIGHT",
        help="Per-source_anchor sample-weight multiplier (repeatable)",
    )
    parser.add_argument(
        "--no-source-holdout-eval",
        action="store_true",
        help="Skip source-stratified holdout evaluation",
    )
    parser.add_argument("--km-start", type=float, default=None, help="Keep rows with course_km >= bound")
    parser.add_argument("--km-end", type=float, default=None, help="Keep rows with course_km < bound")
    parser.add_argument(
        "--include-source-anchor",
        action="append",
        default=[],
        dest="include_source_anchors",
        help="Keep only listed source_anchor values (repeatable)",
    )
    parser.add_argument(
        "--exclude-source-anchor",
        action="append",
        default=[],
        dest="exclude_source_anchors",
        help="Drop listed source_anchor values (repeatable)",
    )
    parser.add_argument(
        "--sector-id",
        type=str,
        default=None,
        help="Sector label stored in metadata (e.g. start, bridge, downstream)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    training_paths = args.training_sets or [DEFAULT_TRAINING_SET]
    try:
        df, training_paths = _load_training_frames(training_paths)
    except FileNotFoundError:
        return 1
    include_anchors = set(args.include_source_anchors) if args.include_source_anchors else None
    exclude_anchors = set(args.exclude_source_anchors) if args.exclude_source_anchors else None
    df = _filter_training_frame(
        df,
        km_start=args.km_start,
        km_end=args.km_end,
        include_anchors=include_anchors,
        exclude_anchors=exclude_anchors,
    )
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
    source_weight_map: dict[str, float] = {}
    for spec in args.source_weight:
        anchor, mult = _parse_source_weight(spec)
        source_weight_map[anchor] = mult
    if source_weight_map:
        sample_weights *= _apply_source_weights(df, source_weight_map)
        print(f"Source weights: {source_weight_map}")

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
    labeled = df[df["is_labeled"]].copy()
    surf_sources = labeled.loc[x_surf.index, "source_anchor"] if "source_anchor" in labeled.columns else None
    fric_sources = labeled.loc[x_fric.index, "source_anchor"] if "source_anchor" in labeled.columns else None

    surface_clf, surface_metrics = _train_classifier(
        x_surf,
        y_surf,
        classes=SURFACE_CLASSES,
        sample_weight=w_surf,
        sources=surf_sources,
    )
    friction_clf, friction_metrics = _train_classifier(
        x_fric,
        y_fric,
        classes=FRICTION_TIERS,
        sample_weight=w_fric,
        sources=fric_sources,
    )

    source_holdout_eval: dict[str, Any] | None = None
    if not args.no_source_holdout_eval and surf_sources is not None:
        anchors = set(surf_sources.dropna().unique())
        if {"calibration_pool", "sut43", "start"}.issubset(anchors):
            cal_sut = {"calibration_pool", "sut43"}
            source_holdout_eval = {
                "train_cal_sut_test_start": {
                    "surface": _source_holdout_eval(
                        x_surf,
                        y_surf,
                        surf_sources,
                        train_sources=cal_sut,
                        test_sources={"start"},
                        sample_weight=w_surf,
                    ),
                    "friction": _source_holdout_eval(
                        x_fric,
                        y_fric,
                        fric_sources,
                        train_sources=cal_sut,
                        test_sources={"start"},
                        sample_weight=w_fric,
                    ),
                },
                "train_start_test_cal_sut": {
                    "surface": _source_holdout_eval(
                        x_surf,
                        y_surf,
                        surf_sources,
                        train_sources={"start"},
                        test_sources=cal_sut,
                        sample_weight=w_surf,
                    ),
                    "friction": _source_holdout_eval(
                        x_fric,
                        y_fric,
                        fric_sources,
                        train_sources={"start"},
                        test_sources=cal_sut,
                        sample_weight=w_fric,
                    ),
                },
            }

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
        "sector_id": args.sector_id,
        "km_filter": {"km_start": args.km_start, "km_end": args.km_end},
        "include_source_anchors": sorted(include_anchors) if include_anchors else None,
        "exclude_source_anchors": sorted(exclude_anchors) if exclude_anchors else None,
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
    if source_weight_map:
        metadata["source_weights"] = source_weight_map
    if source_holdout_eval:
        metadata["source_holdout_eval"] = source_holdout_eval
    if "source_anchor" in df.columns:
        metadata["source_anchor_counts"] = df["source_anchor"].value_counts().to_dict()
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
    if source_holdout_eval:
        cal_sut = source_holdout_eval.get("train_cal_sut_test_start", {})
        if cal_sut.get("surface"):
            print(
                "Source holdout (train cal+sut43 → test start): "
                f"surface={cal_sut['surface']['accuracy']:.3f} "
                f"friction={cal_sut['friction']['accuracy']:.3f}"
            )
        start_cal = source_holdout_eval.get("train_start_test_cal_sut", {})
        if start_cal.get("surface"):
            print(
                "Source holdout (train start → test cal+sut43): "
                f"surface={start_cal['surface']['accuracy']:.3f} "
                f"friction={start_cal['friction']['accuracy']:.3f}"
            )
    if surface_metrics.get("per_source_accuracy"):
        print("Per-source surface accuracy (random 80/20 holdout):")
        for anchor, row in sorted(surface_metrics["per_source_accuracy"].items()):
            print(f"  {anchor}: {row['accuracy']:.3f} (n={row['n']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
