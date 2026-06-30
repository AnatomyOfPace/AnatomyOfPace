#!/usr/bin/env python3
"""
Grade-stratified telemetry clustering (O₂) with empirical O₁ bridge table.

Builds per-metre cluster assignments from panel consensus features and optional
operator gold mapping P(S, F | cluster).

Usage (from repo root):
    python3 04_Python_Scripts/spatial/build_telemetry_clusters.py \\
        --km-start 23 --km-end 24 \\
        --terrain-map config/spatial_terrain_map_sut43_upstream.json

    python3 04_Python_Scripts/spatial/build_telemetry_clusters.py \\
        --km-start 38.4 --km-end 39.14 \\
        --terrain-map config/spatial_terrain_map_sut43.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.gold_training_common import (  # noqa: E402
    DEFAULT_HMM_DRAFT,
    DEFAULT_PANEL,
    DEFAULT_TERRAIN_MAP,
    SURFACE_CLASSES,
    attach_gold_labels,
    build_consensus_profile,
    merge_hmm_features,
)
from spatial.locomotion_mode import assign_grade_bin  # noqa: E402
from spatial.spatial_hitl_overlay import load_terrain_map  # noqa: E402
from spatial.validation_dashboard import operator_gold_spans  # noqa: E402

try:
    import hdbscan  # type: ignore

    _HAS_HDBSCAN = True
except ImportError:
    hdbscan = None  # type: ignore
    _HAS_HDBSCAN = False

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUTPUT = BASE_DIR / "03_Processed_Data" / "spatial" / "telemetry_clusters_sut43.parquet"
DEFAULT_MAPPING = BASE_DIR / "03_Processed_Data" / "spatial" / "cluster_to_gold_mapping.csv"

from spatial.telemetry_features import (  # noqa: E402
    ROLLING_WINDOW_M,
    WALK_SPEED_THRESHOLD_MPS,
    add_rolling_features,
)

CLUSTER_FEATURE_COLUMNS = (
    "ti",
    "grade_pct",
    "speed",
    "pace_expected",
    "nti_std",
    "ti_mean",
    "ti_std",
    "speed_mean",
    "pace_residual_mean",
    "walk_fraction",
)

GRADE_BINS = ("flat", "uphill", "downhill")


def _race_panel(panel: pd.DataFrame) -> pd.DataFrame:
    work = panel.copy()
    if "course_km" not in work.columns and "ref_chainage_m" in work.columns:
        work["course_km"] = work["ref_chainage_m"] / 1000.0
    if "course_m" not in work.columns and "ref_chainage_m" in work.columns:
        work["course_m"] = work["ref_chainage_m"]
    if "session_type" in work.columns:
        work = work[work["session_type"] == "race"]
    return work.sort_values(["course_m", "donor_id"])


def enrich_profile(panel: pd.DataFrame, profile: pd.DataFrame) -> pd.DataFrame:
    """Attach per-metre TI, speed, pace, and cross-athlete NTI σ."""
    work = profile.copy()
    work = work.rename(
        columns={
            "ti_median": "ti",
            "grade_pct_median": "grade_pct",
            "speed_mps_median": "speed",
            "pace_gap_flat_median": "pace_residual",
        }
    )
    race = _race_panel(panel)
    if "pace_expected" in race.columns:
        pace = race.groupby("course_m", as_index=False).agg(pace_expected=("pace_expected", "median"))
        work = work.merge(pace, on="course_m", how="left")
    if "pace_residual" not in work.columns or work["pace_residual"].isna().all():
        if "ti" in work.columns:
            work["pace_residual"] = work["ti"] - 1.0
        elif "pace_gap_flat_median" in profile.columns:
            work["pace_residual"] = profile["pace_gap_flat_median"]
    if "nti_std" not in work.columns:
        work["nti_std"] = np.nan
    return work.sort_values("course_m").reset_index(drop=True)


def _feature_matrix(frame: pd.DataFrame, cols: tuple[str, ...]) -> tuple[np.ndarray, list[str]]:
    present = [c for c in cols if c in frame.columns]
    mat = frame[present].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    return mat, present


def _fit_gmm(x: np.ndarray, n_components: int, seed: int) -> np.ndarray:
    n = len(x)
    k = max(1, min(n_components, n))
    if k == 1 or n < 2:
        return np.zeros(n, dtype=int)
    scaler = StandardScaler()
    xs = scaler.fit_transform(x)
    gmm = GaussianMixture(n_components=k, random_state=seed, n_init=3, max_iter=200)
    gmm.fit(xs)
    return gmm.predict(xs)


def _fit_hdbscan(x: np.ndarray) -> np.ndarray:
    if not _HAS_HDBSCAN or len(x) < 5:
        return _fit_gmm(x, 2, 42)
    scaler = StandardScaler()
    xs = scaler.fit_transform(x)
    labels = hdbscan.HDBSCAN(min_cluster_size=max(5, len(x) // 20)).fit_predict(xs)
    # Remap noise (-1) to its own id block
    noise = labels == -1
    if noise.any():
        labels = labels.astype(int)
        labels[noise] = labels.max() + 1 if (labels >= 0).any() else 0
    return labels


def assign_clusters(
    frame: pd.DataFrame,
    *,
    method: str,
    n_components: int,
    grade_stratified: bool,
    seed: int,
) -> pd.Series:
    """Return cluster_id series; grade-stratified fits separate models per bin."""
    labels = pd.Series(-1, index=frame.index, dtype=int)
    offset = 0
    groups = frame.groupby("grade_bin", observed=True) if grade_stratified and "grade_bin" in frame.columns else [(None, frame)]

    for _key, group in groups:
        if group.empty:
            continue
        x, _cols = _feature_matrix(group, CLUSTER_FEATURE_COLUMNS)
        valid = np.isfinite(x).all(axis=1)
        if valid.sum() < 2:
            local = np.zeros(len(group), dtype=int)
        elif method == "hdbscan":
            local = _fit_hdbscan(x[valid])
        else:
            local = _fit_gmm(x[valid], n_components, seed)
        out = np.full(len(group), -1, dtype=int)
        out[np.where(valid)[0]] = local + offset
        if (~valid).any():
            fallback = int(local.max()) + offset if len(local) else offset
            out[~valid] = fallback
        labels.loc[group.index] = out
        offset = int(labels.max()) + 1

    return labels


def build_cluster_gold_mapping(labeled: pd.DataFrame) -> pd.DataFrame:
    """Empirical P(S | cluster) and dominant S/F from operator gold metres."""
    rows: list[dict] = []
    gold = labeled[labeled["is_labeled"]].copy()
    if gold.empty:
        return pd.DataFrame()

    for cluster_id, grp in gold.groupby("cluster_id", observed=True):
        n = len(grp)
        surf_counts = grp["label_surface"].value_counts(dropna=True)
        fric_counts = grp["label_friction"].value_counts(dropna=True)
        dominant_s = surf_counts.index[0] if len(surf_counts) else None
        dominant_f = fric_counts.index[0] if len(fric_counts) else None
        row: dict = {
            "cluster_id": int(cluster_id),
            "dominant_surface": dominant_s,
            "dominant_friction": dominant_f,
            "n_metres": n,
        }
        for s in SURFACE_CLASSES:
            row[f"P({s})"] = float((grp["label_surface"] == s).sum() / n)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("cluster_id").reset_index(drop=True)


def build_cluster_frame(
    *,
    panel_path: Path,
    terrain_map_path: Path,
    hmm_path: Path,
    km_lo: float,
    km_hi: float,
    method: str,
    n_components: int,
    grade_stratified: bool,
    window_m: int,
    seed: int,
) -> pd.DataFrame:
    panel = pd.read_parquet(panel_path)
    if "course_km" not in panel.columns and "ref_chainage_m" in panel.columns:
        panel["course_km"] = panel["ref_chainage_m"] / 1000.0
    panel = panel[(panel["course_km"] >= km_lo) & (panel["course_km"] < km_hi)].copy()

    profile = build_consensus_profile(panel)
    profile = profile[(profile["course_km"] >= km_lo) & (profile["course_km"] < km_hi)].copy()
    frame = enrich_profile(panel, profile)
    frame = add_rolling_features(frame, window_m=window_m)
    frame["grade_bin"] = assign_grade_bin(frame["grade_pct"])

    hmm = pd.read_parquet(hmm_path) if hmm_path.exists() else pd.DataFrame()
    if not hmm.empty:
        hmm = hmm[(hmm["course_km"] >= km_lo) & (hmm["course_km"] < km_hi)]
    frame = merge_hmm_features(frame, hmm)

    terrain_map = load_terrain_map(terrain_map_path)
    gold = operator_gold_spans(terrain_map)
    frame = attach_gold_labels(frame, gold)

    frame["cluster_id"] = assign_clusters(
        frame,
        method=method,
        n_components=n_components,
        grade_stratified=grade_stratified,
        seed=seed,
    )
    return frame.sort_values("course_m").reset_index(drop=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build O₂ telemetry clusters with O₁ bridge table.")
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--terrain-map", type=Path, default=DEFAULT_TERRAIN_MAP)
    parser.add_argument("--hmm-draft", type=Path, default=DEFAULT_HMM_DRAFT)
    parser.add_argument("--km-start", type=float, required=True)
    parser.add_argument("--km-end", type=float, required=True)
    parser.add_argument("--method", choices=("gmm", "hdbscan"), default="gmm")
    parser.add_argument("--n-components", type=int, default=6, help="GMM components per grade bin")
    parser.add_argument("--no-grade-stratified", action="store_true", help="Cluster entire window without grade bins")
    parser.add_argument("--window-m", type=int, default=ROLLING_WINDOW_M)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--mapping-output", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--summary-json", type=Path, default=None)
    return parser.parse_args(argv)


def _print_summary(frame: pd.DataFrame, mapping: pd.DataFrame, km_lo: float, km_hi: float) -> None:
    print(f"\n=== Telemetry clusters km {km_lo}–{km_hi} ===")
    counts = frame["cluster_id"].value_counts().sort_index()
    print("Cluster counts:")
    for cid, n in counts.items():
        gb = frame.loc[frame["cluster_id"] == cid, "grade_bin"].mode()
        gb_s = gb.iloc[0] if len(gb) else "?"
        ti_m = frame.loc[frame["cluster_id"] == cid, "ti"].median()
        wf = frame.loc[frame["cluster_id"] == cid, "walk_fraction"].median()
        print(f"  cluster {cid:3d}: n={n:4d}  grade_bin~{gb_s}  ti_med={ti_m:.3f}  walk_frac={wf:.2f}")

    labeled = int(frame["is_labeled"].sum())
    print(f"Labeled metres: {labeled} / {len(frame)}")
    if not mapping.empty:
        print("\nGold mapping (cluster → dominant S/F):")
        show = mapping[["cluster_id", "dominant_surface", "dominant_friction", "n_metres"]].copy()
        p_cols = [c for c in mapping.columns if c.startswith("P(")]
        if p_cols:
            show["P_surface_top"] = mapping[p_cols].max(axis=1).round(3)
        print(show.to_string(index=False))
    else:
        print("\nNo operator gold in window — mapping table skipped.")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.method == "hdbscan" and not _HAS_HDBSCAN:
        print("hdbscan not installed; falling back to gmm", file=sys.stderr)
        args.method = "gmm"

    if not args.panel.exists():
        print(f"Panel not found: {args.panel}", file=sys.stderr)
        return 1
    if not args.terrain_map.exists():
        print(f"Terrain map not found: {args.terrain_map}", file=sys.stderr)
        return 1

    frame = build_cluster_frame(
        panel_path=args.panel,
        terrain_map_path=args.terrain_map,
        hmm_path=args.hmm_draft,
        km_lo=args.km_start,
        km_hi=args.km_end,
        method=args.method,
        n_components=args.n_components,
        grade_stratified=not args.no_grade_stratified,
        window_m=args.window_m,
        seed=args.seed,
    )

    export_cols = [
        "course_m",
        "course_km",
        "cluster_id",
        "grade_bin",
        *CLUSTER_FEATURE_COLUMNS,
        "label_surface",
        "label_friction",
        "is_labeled",
    ]
    export_cols = [c for c in export_cols if c in frame.columns]
    out = frame[export_cols].copy()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.output, index=False)

    mapping = build_cluster_gold_mapping(frame)
    if not mapping.empty:
        args.mapping_output.parent.mkdir(parents=True, exist_ok=True)
        mapping.to_csv(args.mapping_output, index=False)

    _print_summary(frame, mapping, args.km_start, args.km_end)

    if args.summary_json:
        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "km_start": args.km_start,
            "km_end": args.km_end,
            "method": args.method,
            "n_metres": len(out),
            "n_clusters": int(out["cluster_id"].nunique()),
            "n_labeled": int(out["is_labeled"].sum()) if "is_labeled" in out.columns else 0,
            "cluster_counts": out["cluster_id"].value_counts().sort_index().to_dict(),
            "output": str(args.output),
            "mapping_output": str(args.mapping_output) if not mapping.empty else None,
        }
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\nWrote {args.output} ({len(out)} rows)")
    if not mapping.empty:
        print(f"Wrote {args.mapping_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
