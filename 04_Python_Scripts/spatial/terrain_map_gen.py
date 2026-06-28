#!/usr/bin/env python3
"""
Phase B — terrain map generation via GMM clustering on consensus NTI.

Reads aligned 1 m panel Parquet (Phase A), filters race sessions, computes
IQR-trimmed consensus NTI per grid cell, fits GMM (default) or K-means,
maps clusters to S1–S6 ontology, and writes config/spatial_terrain_map.json
(machine draft — HITL override in Phase D).

Outputs:
  - spatial_terrain_map.json — per-metre surface class + cluster metadata
  - mechanical_kappa profile (from aligned race panel)
  - fatigue_delta_ti summary (reference vs panel athletes)
  - calibration_credibility_index scalar + breakdown

Usage:
    python3 04_Python_Scripts/spatial/terrain_map_gen.py \\
        --panel 03_Processed_Data/spatial/dale_to_paradisskaret_stress_test/panel_1m.parquet

    python3 04_Python_Scripts/spatial/terrain_map_gen.py \\
        --aligned-glob '03_Processed_Data/spatial/dale_to_paradisskaret_stress_test/aligned_*.parquet'
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.corridor_scope import STRESS_TEST_CORRIDOR_ID, load_stress_test_window
from spatial.surface_ontology import (
    SURFACE_CLASS_SPECS,
    SURFACE_ONTOLOGY_VERSION,
    map_cluster_to_surface_class,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_TERRAIN_MAP_PATH = BASE_DIR / "config" / "spatial_terrain_map.json"
DEFAULT_N_CLUSTERS = 6
ClusterMethod = Literal["gmm", "kmeans"]


def compute_nti(
    panel: pd.DataFrame,
    *,
    grade_col: str = "grade_pct",
    ti_col: str = "ti",
) -> pd.Series:
    """
    Normalized Terrain Index — residual TI after grade-bin median subtraction.

    Interim proxy until full Baseline TI matrix exists: NTI ≈ TI / median(TI | grade bin).
    """
    work = panel.copy()
    ti = pd.to_numeric(work.get(ti_col), errors="coerce")
    grade = pd.to_numeric(work.get(grade_col, work.get("grade", 0)), errors="coerce")
    if ti.isna().all():
        return pd.Series(np.nan, index=work.index)

    bins = pd.cut(grade, bins=[-np.inf, -10, -3, 3, 10, np.inf], labels=False)
    work["_grade_bin"] = bins
    bin_median = work.groupby("_grade_bin", observed=True)[ti_col].transform("median")
    nti = ti / bin_median.replace(0, np.nan)
    return nti.replace([np.inf, -np.inf], np.nan)


def consensus_nti_at_course_m(
    panel: pd.DataFrame,
    *,
    grade_col: str = "grade_pct",
    ti_col: str = "ti",
    outlier_iqr: float = 1.5,
) -> pd.DataFrame:
    """
    Robust consensus NTI per course_m across athletes.

    Per metre: compute NTI per donor, trim cross-athlete outliers via IQR fence,
    then take the median as consensus_nti. Also emits nti_std on the trimmed set.
    """
    work = panel.copy()
    work["nti"] = compute_nti(work, grade_col=grade_col, ti_col=ti_col)

    rows: list[dict[str, Any]] = []
    for course_m, group in work.groupby("course_m", sort=True):
        nti_vals = group["nti"].dropna()
        if nti_vals.empty:
            continue
        q1, q3 = nti_vals.quantile(0.25), nti_vals.quantile(0.75)
        iqr = q3 - q1
        lo, hi = q1 - outlier_iqr * iqr, q3 + outlier_iqr * iqr
        trimmed = nti_vals[(nti_vals >= lo) & (nti_vals <= hi)]
        if trimmed.empty:
            trimmed = nti_vals
        rows.append(
            {
                "course_m": float(course_m),
                "course_km": float(course_m) / 1000.0,
                "consensus_nti": float(trimmed.median()),
                "nti_median": float(nti_vals.median()),
                "nti_mean": float(nti_vals.mean()),
                "nti_std": float(trimmed.std(ddof=0)) if len(trimmed) > 1 else 0.0,
                "n_athletes": int(group["donor_id"].nunique()),
                "n_trimmed": int(len(trimmed)),
            }
        )
    return pd.DataFrame(rows)


def aggregate_nti_by_course_m(
    panel: pd.DataFrame,
    *,
    reference_donor: str | None = None,
    use_consensus: bool = True,
) -> pd.DataFrame:
    """
    Median/consensus NTI across athletes at each course_m.

    When use_consensus=True (default), applies IQR-trimmed robust median (consensus_nti).
  """
    if use_consensus:
        agg = consensus_nti_at_course_m(panel)
        if reference_donor:
            ref = panel[panel["donor_id"] == reference_donor].copy()
            if not ref.empty:
                ref["nti"] = compute_nti(ref)
                ref_med = ref.groupby("course_m", as_index=False)["nti"].median()
                ref_med = ref_med.rename(columns={"nti": "nti_reference"})
                agg = agg.merge(ref_med, on="course_m", how="left")
        if "ti_median" not in agg.columns:
            ti_agg = panel.groupby("course_m", as_index=False).agg(
                ti_median=("ti", "median"),
                grade_pct_median=("grade_pct", "median"),
            )
            agg = agg.merge(ti_agg, on="course_m", how="left")
        return agg

    work = panel.copy()
    work["nti"] = compute_nti(work)

    if reference_donor:
        ref = work[work["donor_id"] == reference_donor].copy()
        if not ref.empty:
            ref_med = ref.groupby("course_m", as_index=False)["nti"].median()
            ref_med = ref_med.rename(columns={"nti": "nti_reference"})
            agg = work.groupby("course_m", as_index=False).agg(
                nti_median=("nti", "median"),
                nti_mean=("nti", "mean"),
                nti_std=("nti", "std"),
                ti_median=("ti", "median"),
                grade_pct_median=("grade_pct", "median"),
                n_athletes=("donor_id", "nunique"),
            )
            return agg.merge(ref_med, on="course_m", how="left")

    return work.groupby("course_m", as_index=False).agg(
        nti_median=("nti", "median"),
        nti_mean=("nti", "mean"),
        nti_std=("nti", "std"),
        ti_median=("ti", "median"),
        grade_pct_median=("grade_pct", "median"),
        n_athletes=("donor_id", "nunique"),
    )


def fit_surface_clusters(
    feature_df: pd.DataFrame,
    *,
    feature_col: str = "consensus_nti",
    n_clusters: int = DEFAULT_N_CLUSTERS,
    method: ClusterMethod = "gmm",
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """
    Cluster aggregated NTI along the corridor.

    Returns (labels, centroids, fit_meta). Falls back to equal-width bins if
    sklearn is unavailable or sample count is too small.
    """
    x = feature_df[feature_col].to_numpy(dtype=float)
    valid = np.isfinite(x)
    labels = np.full(len(x), -1, dtype=int)
    fit_meta: dict[str, Any] = {"method": method, "n_clusters": n_clusters, "fallback": None}

    if valid.sum() < n_clusters:
        fit_meta["fallback"] = "insufficient_samples"
        return labels, np.array([]), fit_meta

    X = x[valid].reshape(-1, 1)

    try:
        if method == "gmm":
            from sklearn.mixture import GaussianMixture

            model = GaussianMixture(
                n_components=n_clusters,
                random_state=random_state,
                covariance_type="full",
            )
            model.fit(X)
            pred = model.predict(X)
            centroids = model.means_.ravel()
            fit_meta["bic"] = float(model.bic(X))
        else:
            from sklearn.cluster import KMeans

            model = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
            pred = model.fit_predict(X)
            centroids = model.cluster_centers_.ravel()
            fit_meta["inertia"] = float(model.inertia_)

        labels[valid] = pred
        fit_meta["centroids"] = centroids.tolist()
        return labels, centroids, fit_meta

    except ImportError:
        fit_meta["fallback"] = "sklearn_missing"
        quantiles = np.linspace(0, 1, n_clusters + 1)
        edges = np.quantile(X.ravel(), quantiles)
        pred = np.digitize(X.ravel(), edges[1:-1], right=True)
        labels[valid] = pred
        centroids = np.array([X[pred == k].mean() if (pred == k).any() else np.nan for k in range(n_clusters)])
        fit_meta["centroids"] = centroids.tolist()
        return labels, centroids, fit_meta


def _race_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Phase B clusters race-day telemetry only; training tiles feed Phase C."""
    if "session_type" in panel.columns:
        race = panel[panel["session_type"] == "race"]
        if not race.empty:
            return race
    return panel


def build_terrain_map(
    panel: pd.DataFrame,
    *,
    reference_donor: str | None = "Reference_Elite_D",
    n_clusters: int = DEFAULT_N_CLUSTERS,
    method: ClusterMethod = "gmm",
) -> dict[str, Any]:
    """Produce spatial_terrain_map.json payload from aligned panel (race sessions)."""
    race_panel = _race_panel(panel)
    start, end, corridor_meta = load_stress_test_window()
    agg = aggregate_nti_by_course_m(race_panel, reference_donor=reference_donor, use_consensus=True)
    cluster_col = "consensus_nti" if "consensus_nti" in agg.columns else "nti_median"
    labels, centroids, fit_meta = fit_surface_clusters(
        agg,
        feature_col=cluster_col,
        n_clusters=n_clusters,
        method=method,
    )

    cluster_to_class: dict[int, str] = {}
    if len(centroids):
        cluster_to_class = map_cluster_to_surface_class(centroids, ordered=True)

    segments: list[dict[str, Any]] = []
    agg = agg.copy()
    agg["cluster_id"] = labels
    agg["surface_class"] = agg["cluster_id"].map(lambda c: cluster_to_class.get(int(c), "S2"))

    # Run-length encode surface_class along course_m for compact JSON.
    agg = agg.sort_values("course_m")
    current_class = None
    seg_start: float | None = None
    for row in agg.itertuples(index=False):
        cls = row.surface_class if row.cluster_id >= 0 else "S2"
        cm = float(row.course_m)
        if cls != current_class:
            if current_class is not None and seg_start is not None:
                segments.append(
                    {
                        "course_m_start": seg_start,
                        "course_m_end": cm,
                        "course_km_start": seg_start / 1000.0,
                        "course_km_end": cm / 1000.0,
                        "surface_class": current_class,
                        "source": "cluster",
                    }
                )
            current_class = cls
            seg_start = cm
    if current_class is not None and seg_start is not None:
        last_m = float(agg["course_m"].iloc[-1])
        segments.append(
            {
                "course_m_start": seg_start,
                "course_m_end": last_m + 1.0,
                "course_km_start": seg_start / 1000.0,
                "course_km_end": (last_m + 1.0) / 1000.0,
                "surface_class": current_class,
                "source": "cluster",
            }
        )

    kappa = race_panel.groupby("course_m", as_index=False)["mechanical_kappa"].median()
    fatigue = compute_fatigue_delta_ti(race_panel, reference_donor=reference_donor)
    credibility = compute_calibration_credibility_index(race_panel, agg, fit_meta)

    return {
        "schema_version": "spatial_terrain_map_v0",
        "ontology_version": SURFACE_ONTOLOGY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corridor": corridor_meta,
        "clustering": {
            **fit_meta,
            "feature_col": cluster_col,
            "consensus_method": "iqr_trimmed_median",
            "cluster_to_surface_class": {str(k): v for k, v in cluster_to_class.items()},
            "surface_class_specs": {
                cid: {
                    "label": spec.label,
                    "ti_target": spec.ti_target,
                    "ti_band": list(spec.ti_band),
                    "master_plan_classes": list(spec.master_plan_classes),
                }
                for cid, spec in SURFACE_CLASS_SPECS.items()
            },
        },
        "segments": segments,
        "grid_summary": {
            "n_course_m": int(len(agg)),
            "consensus_nti_range": [
                float(agg[cluster_col].min(skipna=True)),
                float(agg[cluster_col].max(skipna=True)),
            ],
            "nti_median_range": [
                float(agg["nti_median"].min(skipna=True)) if "nti_median" in agg.columns else None,
                float(agg["nti_median"].max(skipna=True)) if "nti_median" in agg.columns else None,
            ],
        },
        "mechanical_kappa_profile": {
            "course_m": kappa["course_m"].tolist(),
            "kappa_median": kappa["mechanical_kappa"].tolist(),
        },
        "fatigue_delta_ti": fatigue,
        "calibration_credibility_index": credibility,
        "hitl": {
            "status": "draft",
            "manual_overrides": [],
        },
    }


def compute_fatigue_delta_ti(
    panel: pd.DataFrame,
    *,
    reference_donor: str | None = None,
) -> dict[str, Any]:
    """ΔTI heatmap summary — panel median minus reference donor per course_m."""
    work = panel.copy()
    if "ti" not in work.columns or work["ti"].isna().all():
        return {"status": "missing_ti", "delta_by_course_m": []}

    med = work.groupby(["course_m", "donor_id"], as_index=False)["ti"].median()
    pivot = med.pivot(index="course_m", columns="donor_id", values="ti")
    panel_median = pivot.median(axis=1, skipna=True)

    out: dict[str, Any] = {"status": "ok", "delta_by_course_m": []}
    if reference_donor and reference_donor in pivot.columns:
        delta = panel_median - pivot[reference_donor]
        out["reference_donor"] = reference_donor
        out["delta_by_course_m"] = [
            {"course_m": float(cm), "delta_ti": float(d)}
            for cm, d in delta.dropna().items()
        ]
        out["mean_abs_delta_ti"] = float(delta.abs().mean(skipna=True))
    else:
        out["reference_donor"] = None
        out["note"] = "Reference donor TI not in panel — per-athlete spread only"
        out["ti_spread_by_course_m"] = [
            {"course_m": float(cm), "ti_std": float(row.std(skipna=True))}
            for cm, row in pivot.iterrows()
            if row.notna().sum() >= 2
        ]
    return out


def compute_calibration_credibility_index(
    panel: pd.DataFrame,
    agg: pd.DataFrame,
    fit_meta: dict[str, Any],
) -> dict[str, Any]:
    """
    Composite credibility score in [0, 1] for automated ontology draft.

    Weights: athlete coverage, TI availability, cluster stability, NTI variance.
    """
    n_athletes = panel["donor_id"].nunique() if "donor_id" in panel.columns else 0
    ti_cov = float(panel["ti"].notna().mean()) if "ti" in panel.columns else 0.0
    athlete_score = min(n_athletes / 3.0, 1.0)
    ti_score = ti_cov
    cluster_score = 0.0 if fit_meta.get("fallback") else 1.0
    nti_std = float(agg["nti_std"].median(skipna=True)) if "nti_std" in agg.columns else np.nan
    variance_score = 1.0 if not np.isfinite(nti_std) else float(np.clip(1.0 - nti_std / 2.0, 0.0, 1.0))

    weights = (0.35, 0.30, 0.20, 0.15)
    components = {
        "athlete_coverage": athlete_score,
        "ti_coverage": ti_score,
        "cluster_fit": cluster_score,
        "nti_stability": variance_score,
    }
    index = sum(w * components[k] for w, k in zip(weights, components))
    return {
        "index": round(index, 4),
        "components": components,
        "n_athletes": int(n_athletes),
    }


def write_terrain_map(payload: dict[str, Any], path: Path | None = None) -> Path:
    out = path or DEFAULT_TERRAIN_MAP_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def load_panel(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def load_aligned_glob(pattern: str) -> pd.DataFrame:
    paths = sorted(Path(BASE_DIR).glob(pattern))
    if not paths:
        raise FileNotFoundError(f"No aligned Parquet matched: {pattern}")
    frames = [pd.read_parquet(p) for p in paths]
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase B — NTI clustering → S1–S6 terrain map")
    parser.add_argument("--panel", type=Path, help="Stacked panel_1m.parquet from Phase A")
    parser.add_argument(
        "--aligned-glob",
        default=None,
        help="Glob under repo root for aligned_*.parquet (alternative to --panel)",
    )
    parser.add_argument("--reference-donor", default="Reference_Elite_D")
    parser.add_argument("--n-clusters", type=int, default=DEFAULT_N_CLUSTERS)
    parser.add_argument("--method", choices=("gmm", "kmeans"), default="gmm",
                        help="Clustering method (default gmm — preferred)")
    parser.add_argument("--output", type=Path, default=DEFAULT_TERRAIN_MAP_PATH)
    args = parser.parse_args()

    if args.panel:
        panel = load_panel(args.panel if args.panel.is_absolute() else BASE_DIR / args.panel)
    elif args.aligned_glob:
        panel = load_aligned_glob(args.aligned_glob)
    else:
        default_panel = (
            BASE_DIR
            / "03_Processed_Data"
            / "spatial"
            / STRESS_TEST_CORRIDOR_ID
            / "panel_1m.parquet"
        )
        if not default_panel.exists():
            parser.error("Provide --panel or --aligned-glob; default panel not found")
        panel = load_panel(default_panel)

    payload = build_terrain_map(
        panel,
        reference_donor=args.reference_donor,
        n_clusters=args.n_clusters,
        method=args.method,
    )
    out = write_terrain_map(payload, args.output if args.output.is_absolute() else BASE_DIR / args.output)
    cci = payload["calibration_credibility_index"]["index"]
    print(f"OK terrain map → {out.relative_to(BASE_DIR)} (credibility={cci:.3f}, segments={len(payload['segments'])})")


if __name__ == "__main__":
    main()
