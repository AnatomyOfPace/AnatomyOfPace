#!/usr/bin/env python3
"""
Per-athlete FIT kinematic clustering with post-hoc TI rank sorting.

MVP pilot: cluster 1 m aligned race telemetry independently per donor, then
relabel cluster IDs 0..k-1 by ascending mean TI (cluster_ti_rank). Intended as
HITL friction hints — clusters reflect physiology/kinematics, not surface class.

Outputs:
  - fit_ti_clusters_{donor}.parquet — per-metre cluster_id + cluster_ti_rank
  - fit_ti_cluster_comparison.json — cross-athlete spatial overlap stats
  - PNG strip charts under 06_Visualizations/sut43_fit_clusters/

Usage (from repo root):
    python3 04_Python_Scripts/spatial/fit_ti_cluster_pilot.py
    python3 04_Python_Scripts/spatial/fit_ti_cluster_pilot.py --k 6 --method gmm
    python3 04_Python_Scripts/spatial/fit_ti_cluster_pilot.py --km-start 29 --km-end 41
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "04_Python_Scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "04_Python_Scripts"))

from spatial.corridor_scope import (  # noqa: E402
    SUT43_PRIMARY_KM_END,
    SUT43_PRIMARY_KM_START,
)
DEFAULT_PANEL = (
    _REPO_ROOT / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "panel_1m.parquet"
)
DEFAULT_OUTPUT_DIR = (
    _REPO_ROOT / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology"
)
DEFAULT_VIZ_DIR = _REPO_ROOT / "06_Visualizations" / "sut43_fit_clusters"

DEFAULT_DONORS = ("Subject_A", "Subject_B")
DEFAULT_K = 6
ClusterMethod = Literal["gmm", "kmeans"]

# Kinematic / grade features for clustering (TI excluded by default — used for rank sort).
DEFAULT_FEATURE_COLS = (
    "grade_pct",
    "speed_mps",
    "cadence_spm",
    "heart_rate",
    "altitude_m",
    "power_w",
    "vertical_oscillation_mm",
    "step_length_m",
    "stance_time_ms",
    "mechanical_kappa",
    "pace_gap_flat",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def filter_donor_window(
    panel: pd.DataFrame,
    donor_id: str,
    *,
    km_start: float,
    km_end: float,
    session_type: str = "race",
) -> pd.DataFrame:
    work = panel[panel["donor_id"] == donor_id].copy()
    if session_type and "session_type" in work.columns:
        work = work[work["session_type"] == session_type]
    return work[(work["course_km"] >= km_start) & (work["course_km"] < km_end)].sort_values("course_m")


def available_feature_cols(df: pd.DataFrame, candidates: tuple[str, ...]) -> list[str]:
    cols: list[str] = []
    for c in candidates:
        if c not in df.columns:
            continue
        if pd.to_numeric(df[c], errors="coerce").notna().sum() >= 10:
            cols.append(c)
    return cols


def build_feature_matrix(
    df: pd.DataFrame,
    feature_cols: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Return (X standardized, valid_row_mask). Rows with any NaN in features are dropped."""
    raw = df[feature_cols].apply(pd.to_numeric, errors="coerce")
    valid = raw.notna().all(axis=1).to_numpy()
    if valid.sum() == 0:
        return np.empty((0, len(feature_cols))), valid

    X = raw.loc[valid].to_numpy(dtype=float)
    mu = X.mean(axis=0)
    sigma = X.std(axis=0)
    sigma[sigma == 0] = 1.0
    X_std = (X - mu) / sigma
    return X_std, valid


def fit_multivariate_clusters(
    X: np.ndarray,
    *,
    n_clusters: int,
    method: ClusterMethod,
    random_state: int = 42,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Fit GMM or KMeans on standardized multi-column feature matrix."""
    fit_meta: dict[str, Any] = {"method": method, "n_clusters": n_clusters, "n_features": X.shape[1]}
    n_samples, _ = X.shape

    if n_samples < n_clusters:
        fit_meta["fallback"] = "insufficient_samples"
        return np.full(n_samples, -1, dtype=int), fit_meta

    try:
        if method == "gmm":
            from sklearn.mixture import GaussianMixture

            model = GaussianMixture(
                n_components=n_clusters,
                random_state=random_state,
                covariance_type="full",
                reg_covar=1e-5,
            )
            model.fit(X)
            labels = model.predict(X)
            fit_meta["bic"] = float(model.bic(X))
        else:
            from sklearn.cluster import KMeans

            model = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
            labels = model.fit_predict(X)
            fit_meta["inertia"] = float(model.inertia_)

        fit_meta["cluster_counts"] = {int(k): int((labels == k).sum()) for k in range(n_clusters)}
        return labels, fit_meta

    except ImportError:
        # Fallback: 1-D quantile bin on first column
        fit_meta["fallback"] = "sklearn_missing"
        col0 = X[:, 0]
        quantiles = np.linspace(0, 1, n_clusters + 1)
        edges = np.quantile(col0, quantiles)
        labels = np.digitize(col0, edges[1:-1], right=True)
        fit_meta["cluster_counts"] = {int(k): int((labels == k).sum()) for k in range(n_clusters)}
        return labels, fit_meta


def rank_clusters_by_ti(
    df: pd.DataFrame,
    cluster_ids: np.ndarray,
    *,
    ti_col: str = "ti",
    n_clusters: int,
) -> tuple[dict[int, int], pd.DataFrame]:
    """
    Map raw cluster_id -> cluster_ti_rank (0 = lowest mean TI, k-1 = highest).

    Returns (rank_map, summary_df with mean/median TI per cluster).
    """
    work = df.copy()
    work["_cluster_id"] = cluster_ids
    work["_ti"] = pd.to_numeric(work.get(ti_col), errors="coerce")

    summary_rows: list[dict[str, Any]] = []
    for cid in range(n_clusters):
        mask = work["_cluster_id"] == cid
        ti_vals = work.loc[mask, "_ti"].dropna()
        summary_rows.append(
            {
                "cluster_id": cid,
                "n_metres": int(mask.sum()),
                "mean_ti": float(ti_vals.mean()) if len(ti_vals) else np.nan,
                "median_ti": float(ti_vals.median()) if len(ti_vals) else np.nan,
                "std_ti": float(ti_vals.std(ddof=0)) if len(ti_vals) > 1 else 0.0,
            }
        )
    summary = pd.DataFrame(summary_rows)
    summary = summary.sort_values("mean_ti", na_position="last").reset_index(drop=True)
    summary["cluster_ti_rank"] = range(len(summary))

    rank_map = {
        int(row.cluster_id): int(row.cluster_ti_rank)
        for row in summary.itertuples(index=False)
    }
    return rank_map, summary


def cluster_donor(
    panel: pd.DataFrame,
    donor_id: str,
    *,
    km_start: float,
    km_end: float,
    n_clusters: int,
    method: ClusterMethod,
    feature_cols: list[str],
    random_state: int = 42,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Run independent clustering for one donor; return labelled rows + metadata."""
    df = filter_donor_window(panel, donor_id, km_start=km_start, km_end=km_end)
    meta: dict[str, Any] = {
        "donor_id": donor_id,
        "km_start": km_start,
        "km_end": km_end,
        "n_rows_window": len(df),
        "feature_cols": feature_cols,
    }

    if df.empty:
        meta["error"] = "empty_window"
        return pd.DataFrame(), meta

    X, valid = build_feature_matrix(df, feature_cols)
    meta["n_valid_for_fit"] = int(valid.sum())
    meta["valid_fraction"] = round(float(valid.sum()) / len(df), 4) if len(df) else 0.0

    labels_full = np.full(len(df), -1, dtype=int)
    if valid.sum() >= n_clusters:
        labels_valid, fit_meta = fit_multivariate_clusters(
            X, n_clusters=n_clusters, method=method, random_state=random_state
        )
        labels_full[valid] = labels_valid
        meta["fit"] = fit_meta
    else:
        meta["fit"] = {"fallback": "insufficient_valid_rows", "n_valid": int(valid.sum())}

    rank_map, cluster_summary = rank_clusters_by_ti(df, labels_full, n_clusters=n_clusters)
    meta["cluster_summary"] = cluster_summary.to_dict(orient="records")
    meta["rank_map"] = {str(k): v for k, v in rank_map.items()}

    out = df[["course_m", "course_km", "ti", "ti_raw"]].copy()
    out["donor_id"] = donor_id
    out["cluster_id"] = labels_full
    out["cluster_ti_rank"] = [rank_map.get(int(c), -1) if c >= 0 else -1 for c in labels_full]

    for c in feature_cols:
        if c in df.columns:
            out[c] = df[c].values

    return out, meta


def compare_cross_athlete(
    a: pd.DataFrame,
    b: pd.DataFrame,
    *,
    n_clusters: int,
    high_rank_threshold: int | None = None,
) -> dict[str, Any]:
    """Compare TI-sorted cluster ranks at shared course_m grid points."""
    if a.empty or b.empty:
        return {"error": "missing_donor_output"}

    merged = a[["course_m", "cluster_ti_rank", "ti"]].merge(
        b[["course_m", "cluster_ti_rank", "ti"]],
        on="course_m",
        suffixes=("_a", "_b"),
        how="inner",
    )
    both_labelled = merged[
        (merged["cluster_ti_rank_a"] >= 0) & (merged["cluster_ti_rank_b"] >= 0)
    ].copy()

    report: dict[str, Any] = {
        "n_shared_metres": int(len(merged)),
        "n_both_labelled": int(len(both_labelled)),
    }

    if both_labelled.empty:
        report["note"] = "No overlapping labelled metres for comparison."
        return report

    rank_a = both_labelled["cluster_ti_rank_a"].to_numpy()
    rank_b = both_labelled["cluster_ti_rank_b"].to_numpy()

    exact_match = float((rank_a == rank_b).mean())
    abs_diff = np.abs(rank_a - rank_b)
    report["exact_rank_match_rate"] = round(exact_match, 4)
    report["mean_abs_rank_diff"] = round(float(abs_diff.mean()), 4)
    report["median_abs_rank_diff"] = round(float(np.median(abs_diff)), 4)

    if len(both_labelled) >= 3:
        rho, pval = stats.spearmanr(rank_a, rank_b)
        report["spearman_rank_correlation"] = round(float(rho), 4)
        report["spearman_p_value"] = round(float(pval), 6)

    hi = high_rank_threshold if high_rank_threshold is not None else max(0, n_clusters - 2)
    high_a = rank_a >= hi
    high_b = rank_b >= hi
    union = high_a | high_b
    if union.any():
        overlap = (high_a & high_b).sum()
        report["high_ti_rank_threshold"] = hi
        report["high_ti_spatial_jaccard"] = round(float(overlap / union.sum()), 4)
        report["high_ti_both_fraction"] = round(float(overlap / len(both_labelled)), 4)

    # TI correlation at shared metres (sanity — independent of cluster fit)
    ti_a = both_labelled["ti_a"].dropna()
    ti_b = both_labelled["ti_b"].dropna()
    common_idx = ti_a.index.intersection(ti_b.index)
    if len(common_idx) >= 3:
        rho_ti, _ = stats.spearmanr(
            both_labelled.loc[common_idx, "ti_a"],
            both_labelled.loc[common_idx, "ti_b"],
        )
        report["ti_spearman_at_shared_metres"] = round(float(rho_ti), 4)

    return report


def render_strip_chart(
    df: pd.DataFrame,
    donor_id: str,
    *,
    n_clusters: int,
    output_path: Path,
    km_start: float,
    km_end: float,
) -> None:
    """Simple course_km vs cluster_ti_rank strip (colored by rank)."""
    work = df[df["cluster_ti_rank"] >= 0].copy()
    if work.empty:
        return

    fig, axes = plt.subplots(2, 1, figsize=(14, 5), sharex=True, height_ratios=[1, 1.2])
    cmap = plt.get_cmap("viridis", n_clusters)

    ax0, ax1 = axes
    ax0.plot(work["course_km"], work["ti"], color="#888888", linewidth=0.6, alpha=0.8)
    ax0.set_ylabel("TI")
    ax0.set_title(f"{donor_id} — TI + TI-ranked clusters (km {km_start:.0f}–{km_end:.0f})")
    ax0.grid(True, alpha=0.25)

    ranks = work["cluster_ti_rank"].astype(int)
    colors = [cmap(r / max(n_clusters - 1, 1)) for r in ranks]
    ax1.scatter(work["course_km"], ranks, c=colors, s=2, marker="|", linewidths=0.5)
    ax1.set_yticks(range(n_clusters))
    ax1.set_ylabel("cluster_ti_rank\n(0=low TI … high)")
    ax1.set_xlabel("course_km")
    ax1.grid(True, alpha=0.25)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def render_comparison_chart(
    a: pd.DataFrame,
    b: pd.DataFrame,
    *,
    n_clusters: int,
    output_path: Path,
    km_start: float,
    km_end: float,
) -> None:
    """Overlay both donors' cluster_ti_rank on shared course axis."""
    merged = a[["course_m", "course_km", "cluster_ti_rank"]].merge(
        b[["course_m", "cluster_ti_rank"]],
        on="course_m",
        suffixes=("_a", "_b"),
        how="inner",
    )
    merged = merged[(merged["cluster_ti_rank_a"] >= 0) & (merged["cluster_ti_rank_b"] >= 0)]
    if merged.empty:
        return

    fig, ax = plt.subplots(figsize=(14, 4))
    ax.plot(
        merged["course_km"],
        merged["cluster_ti_rank_a"],
        label="Subject_A",
        linewidth=0.8,
        alpha=0.85,
    )
    ax.plot(
        merged["course_km"],
        merged["cluster_ti_rank_b"],
        label="Subject_B",
        linewidth=0.8,
        alpha=0.85,
    )
    ax.set_yticks(range(n_clusters))
    ax.set_ylabel("cluster_ti_rank")
    ax.set_xlabel("course_km")
    ax.set_title(f"Cross-athlete TI-ranked clusters (km {km_start:.0f}–{km_end:.0f})")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Per-athlete FIT clustering with TI rank sorting.")
    p.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--viz-dir", type=Path, default=DEFAULT_VIZ_DIR)
    p.add_argument("--donors", nargs="+", default=list(DEFAULT_DONORS))
    p.add_argument("--km-start", type=float, default=SUT43_PRIMARY_KM_START)
    p.add_argument("--km-end", type=float, default=SUT43_PRIMARY_KM_END)
    p.add_argument("--n-clusters", type=int, default=DEFAULT_K, dest="n_clusters")
    p.add_argument("--method", choices=("gmm", "kmeans"), default="gmm")
    p.add_argument("--include-ti-in-features", action="store_true")
    p.add_argument("--no-viz", action="store_true")
    p.add_argument("--random-state", type=int, default=42)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    panel = pd.read_parquet(args.panel)

    feature_candidates = list(DEFAULT_FEATURE_COLS)
    if args.include_ti_in_features:
        feature_candidates = ["ti", "ti_raw", *feature_candidates]

    # Resolve features from full panel (union of donor coverage)
    feature_cols = available_feature_cols(panel, tuple(feature_candidates))
    if not feature_cols:
        print("ERROR: No usable feature columns found.", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    donor_outputs: dict[str, pd.DataFrame] = {}
    run_meta: dict[str, Any] = {
        "generated_at": _utc_now(),
        "panel": str(args.panel),
        "km_window": [args.km_start, args.km_end],
        "n_clusters": args.n_clusters,
        "method": args.method,
        "feature_cols": feature_cols,
        "include_ti_in_features": args.include_ti_in_features,
        "donors": {},
    }

    for donor_id in args.donors:
        out, meta = cluster_donor(
            panel,
            donor_id,
            km_start=args.km_start,
            km_end=args.km_end,
            n_clusters=args.n_clusters,
            method=args.method,
            feature_cols=feature_cols,
            random_state=args.random_state,
        )
        run_meta["donors"][donor_id] = meta

        if out.empty:
            print(f"WARN: No output for {donor_id}", file=sys.stderr)
            continue

        parquet_path = args.output_dir / f"fit_ti_clusters_{donor_id}.parquet"
        out.to_parquet(parquet_path, index=False)
        donor_outputs[donor_id] = out
        print(f"Wrote {parquet_path} ({len(out)} rows)")

        if not args.no_viz:
            render_strip_chart(
                out,
                donor_id,
                n_clusters=args.n_clusters,
                output_path=args.viz_dir / f"{donor_id}_ti_rank_strip.png",
                km_start=args.km_start,
                km_end=args.km_end,
            )

    if "Subject_A" in donor_outputs and "Subject_B" in donor_outputs:
        comparison = compare_cross_athlete(
            donor_outputs["Subject_A"],
            donor_outputs["Subject_B"],
            n_clusters=args.n_clusters,
        )
        run_meta["cross_athlete_comparison"] = comparison

        comp_path = args.output_dir / "fit_ti_cluster_comparison.json"
        comp_path.write_text(json.dumps(run_meta, indent=2), encoding="utf-8")
        print(f"Wrote {comp_path}")

        if not args.no_viz:
            render_comparison_chart(
                donor_outputs["Subject_A"],
                donor_outputs["Subject_B"],
                n_clusters=args.n_clusters,
                output_path=args.viz_dir / "cross_athlete_ti_rank_overlay.png",
                km_start=args.km_start,
                km_end=args.km_end,
            )
            print(f"Wrote charts under {args.viz_dir}")
    else:
        summary_path = args.output_dir / "fit_ti_cluster_comparison.json"
        summary_path.write_text(json.dumps(run_meta, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
