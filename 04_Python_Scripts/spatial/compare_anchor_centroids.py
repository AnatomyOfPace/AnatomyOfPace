#!/usr/bin/env python3
"""
Pool O₂ anchor windows and compare feature centroids (overall + grade-stratified).

Memo 19: clusters are behavioral families, not O₁ gold. Anchors calibrate centroid
separation — poles off (road) vs mixed (LFI) vs scramble (Selvikstakken).

Usage (from repo root):
    python3 04_Python_Scripts/spatial/compare_anchor_centroids.py
    python3 04_Python_Scripts/spatial/compare_anchor_centroids.py --chart
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.build_telemetry_clusters import CLUSTER_FEATURE_COLUMNS  # noqa: E402
from spatial.build_anchor_features import load_manifest  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_MANIFEST = BASE_DIR / "config" / "anchor_runs_manifest.json"
DEFAULT_ANCHOR_DIR = BASE_DIR / "03_Processed_Data" / "spatial" / "anchor_features"
DEFAULT_CSV = BASE_DIR / "03_Processed_Data" / "spatial" / "anchor_centroid_qc_summary.csv"
DEFAULT_JSON = BASE_DIR / "03_Processed_Data" / "spatial" / "anchor_centroid_qc_summary.json"
DEFAULT_VIZ = BASE_DIR / "06_Visualizations" / "anchor_centroid_qc.png"

QC_FEATURES = (
    "ti",
    "grade_pct",
    "speed",
    "pace_residual",
    "walk_fraction",
    "scramble_fraction",
    "ti_mean",
    "speed_mean",
    "pace_residual_mean",
)

GRADE_BINS = ("flat", "uphill", "downhill")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_meta(run: dict) -> dict:
    expected = run.get("expected") or {}
    return {
        "anchor_id": run.get("anchor_id"),
        "display_name": run.get("display_name"),
        "o2_signature": run.get("o2_signature"),
        "o2_role": run.get("o2_role"),
        "pole_policy": run.get("pole_policy", "unknown"),
        "substrate_class_o1": expected.get("substrate_o1"),
        "friction_tier_o1": expected.get("friction_o1"),
        "effort_tier": expected.get("effort"),
    }


def load_anchor_frames(
    manifest: dict,
    anchor_dir: Path,
) -> tuple[pd.DataFrame, dict[str, dict]]:
    """Load all calibration-set anchor parquets; return pooled frame + per-run meta."""
    anchor_ids = manifest.get("calibration_set", {}).get("anchor_runs", [])
    runs_by_id = {r["anchor_id"]: r for r in manifest.get("runs", []) if r.get("anchor_id")}
    frames: list[pd.DataFrame] = []
    meta: dict[str, dict] = {}

    for anchor_id in anchor_ids:
        path = anchor_dir / f"anchor_features_{anchor_id}.parquet"
        if not path.exists():
            print(f"  missing parquet: {path}", file=sys.stderr)
            continue
        df = pd.read_parquet(path)
        run = runs_by_id.get(anchor_id, {})
        meta[anchor_id] = _run_meta(run)
        frames.append(df)

    if not frames:
        return pd.DataFrame(), meta
    pooled = pd.concat(frames, ignore_index=True)
    return pooled, meta


def _centroid_row(
    frame: pd.DataFrame,
    *,
    anchor_id: str,
    grade_bin: str | None,
    meta: dict,
) -> dict:
    row: dict = {
        "anchor_id": anchor_id,
        "grade_bin": grade_bin or "all",
        "n_metres": len(frame),
        **meta,
    }
    for col in QC_FEATURES:
        if col not in frame.columns:
            continue
        vals = pd.to_numeric(frame[col], errors="coerce")
        row[f"{col}_median"] = float(vals.median()) if vals.notna().any() else np.nan
        row[f"{col}_mean"] = float(vals.mean()) if vals.notna().any() else np.nan
        row[f"{col}_p25"] = float(vals.quantile(0.25)) if vals.notna().any() else np.nan
        row[f"{col}_p75"] = float(vals.quantile(0.75)) if vals.notna().any() else np.nan
    return row


def build_centroid_table(
    pooled: pd.DataFrame,
    meta_by_anchor: dict[str, dict],
    *,
    grade_stratified: bool,
) -> pd.DataFrame:
    rows: list[dict] = []
    for anchor_id, grp in pooled.groupby("anchor_id", observed=True):
        m = meta_by_anchor.get(str(anchor_id), {})
        rows.append(_centroid_row(grp, anchor_id=str(anchor_id), grade_bin=None, meta=m))
        if grade_stratified and "grade_bin" in grp.columns:
            for gb in GRADE_BINS:
                sub = grp[grp["grade_bin"] == gb]
                if sub.empty:
                    continue
                rows.append(_centroid_row(sub, anchor_id=str(anchor_id), grade_bin=gb, meta=m))
    return pd.DataFrame(rows)


def build_pooled_centroids(pooled: pd.DataFrame, *, grade_stratified: bool) -> pd.DataFrame:
    """Cross-anchor pooled centroids (behavioral family baselines)."""
    meta = {"anchor_id": "pooled", "display_name": "Pooled anchors", "o2_signature": "mixed"}
    rows: list[dict] = []
    rows.append(_centroid_row(pooled, anchor_id="pooled", grade_bin=None, meta=meta))
    if grade_stratified and "grade_bin" in pooled.columns:
        for gb in GRADE_BINS:
            sub = pooled[pooled["grade_bin"] == gb]
            if sub.empty:
                continue
            rows.append(_centroid_row(sub, anchor_id="pooled", grade_bin=gb, meta=meta))
    return pd.DataFrame(rows)


def centroid_distance_matrix(summary: pd.DataFrame) -> pd.DataFrame:
    """Pairwise Euclidean distance on standardized overall centroids (ti, speed, grade, locomotion)."""
    overall = summary[summary["grade_bin"] == "all"].copy()
    dist_cols = [c for c in overall.columns if c.endswith("_median") and any(c.startswith(f) for f in QC_FEATURES[:6])]
    if not dist_cols or overall.empty:
        return pd.DataFrame()

    mat = overall[dist_cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    mu = np.nanmean(mat, axis=0)
    sigma = np.nanstd(mat, axis=0)
    sigma[sigma == 0] = 1.0
    z = (mat - mu) / sigma
    ids = overall["anchor_id"].astype(str).tolist()
    n = len(ids)
    dist = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            diff = z[i] - z[j]
            dist[i, j] = float(np.sqrt(np.nansum(diff**2)))
    return pd.DataFrame(dist, index=ids, columns=ids)


def print_console_report(summary: pd.DataFrame, distances: pd.DataFrame) -> None:
    overall = summary[summary["grade_bin"] == "all"].sort_values("ti_median")
    print("\n=== O₂ anchor centroid QC (overall) ===")
    show_cols = [
        "anchor_id",
        "pole_policy",
        "o2_signature",
        "n_metres",
        "ti_median",
        "speed_median",
        "grade_pct_median",
        "walk_fraction_median",
        "scramble_fraction_median",
    ]
    show_cols = [c for c in show_cols if c in overall.columns]
    print(overall[show_cols].to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    print("\n--- Grade-stratified TI medians ---")
    strat = summary[summary["grade_bin"] != "all"]
    if strat.empty:
        print("  (no grade bins)")
    else:
        pivot = strat.pivot_table(index="anchor_id", columns="grade_bin", values="ti_median", aggfunc="first")
        print(pivot.to_string(float_format=lambda x: f"{x:.3f}"))

    if not distances.empty:
        print("\n--- Centroid distance matrix (standardized feature space) ---")
        print(distances.round(2).to_string())


def write_chart(summary: pd.DataFrame, out_path: Path) -> None:
    import matplotlib.pyplot as plt

    overall = summary[summary["grade_bin"] == "all"].sort_values("ti_median")
    if overall.empty:
        return

    pole_colors = {"off": "#2ecc71", "mixed": "#e67e22", "on_mixed": "#9b59b6"}
    colors = [pole_colors.get(str(p), "#95a5a6") for p in overall["pole_policy"]]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    ax = axes[0]
    x = np.arange(len(overall))
    ax.bar(x, overall["ti_median"], color=colors, edgecolor="black", linewidth=0.5)
    ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.8, label="TI null (1.0)")
    ax.set_xticks(x)
    ax.set_xticklabels(overall["anchor_id"], rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("TI median")
    ax.set_title("O₂ anchor TI centroids")
    ax.legend(loc="upper left", fontsize=8)

    ax2 = axes[1]
    width = 0.35
    wf = overall.get("walk_fraction_median", pd.Series(0, index=overall.index)).fillna(0)
    sf = overall.get("scramble_fraction_median", pd.Series(0, index=overall.index)).fillna(0)
    ax2.bar(x - width / 2, wf, width, label="walk_fraction", color="#3498db", alpha=0.85)
    ax2.bar(x + width / 2, sf, width, label="scramble_fraction", color="#e74c3c", alpha=0.85)
    ax2.set_xticks(x)
    ax2.set_xticklabels(overall["anchor_id"], rotation=35, ha="right", fontsize=8)
    ax2.set_ylabel("Rolling fraction (median)")
    ax2.set_title("Locomotion mix centroids")
    ax2.legend(loc="upper right", fontsize=8)

    fig.suptitle("Anchor centroid QC — behavioral O₂ families (not O₁ gold)", fontsize=10)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote chart {out_path}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare O₂ anchor feature centroids.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--anchor-dir", type=Path, default=DEFAULT_ANCHOR_DIR)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--no-grade-stratified", action="store_true")
    parser.add_argument("--chart", action="store_true", help="Write PNG to 06_Visualizations/")
    parser.add_argument("--chart-path", type=Path, default=DEFAULT_VIZ)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.manifest.exists():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        return 1

    manifest = load_manifest(args.manifest)
    pooled, meta_by_anchor = load_anchor_frames(manifest, args.anchor_dir)
    if pooled.empty:
        print("No anchor parquets found.", file=sys.stderr)
        return 1

    grade_stratified = not args.no_grade_stratified
    per_anchor = build_centroid_table(pooled, meta_by_anchor, grade_stratified=grade_stratified)
    pooled_rows = build_pooled_centroids(pooled, grade_stratified=grade_stratified)
    summary = pd.concat([per_anchor, pooled_rows], ignore_index=True)
    distances = centroid_distance_matrix(per_anchor)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.output_csv, index=False)

    payload = {
        "generated_at": _utc_now(),
        "n_anchors": int(per_anchor[per_anchor["grade_bin"] == "all"]["anchor_id"].nunique()),
        "n_metres_pooled": int(len(pooled)),
        "cluster_feature_columns_ref": list(CLUSTER_FEATURE_COLUMNS),
        "qc_features": list(QC_FEATURES),
        "centroid_distance_matrix": distances.round(4).to_dict() if not distances.empty else {},
        "output_csv": str(args.output_csv),
    }
    args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print_console_report(per_anchor, distances)
    print(f"\nWrote {args.output_csv} ({len(summary)} rows)")
    print(f"Wrote {args.output_json}")

    if args.chart:
        try:
            write_chart(per_anchor, args.chart_path)
        except ImportError:
            print("matplotlib not available — chart skipped", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
