"""Shared helpers for sparse operator-gold ML training and suggestion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.terrain_map_gen import aggregate_nti_by_course_m, compute_nti
from spatial.validation_dashboard import operator_gold_spans

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_PANEL = BASE_DIR / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "panel_1m.parquet"
DEFAULT_TERRAIN_MAP = BASE_DIR / "config" / "spatial_terrain_map_sut43.json"
DEFAULT_HMM_DRAFT = BASE_DIR / "07_ML_Models" / "terrain_hmm_sut43_draft_predictions.parquet"
TVERFJELL_PANEL = BASE_DIR / "03_Processed_Data" / "spatial" / "tverrfjell_course" / "panel_1m.parquet"
TVERFJELL_GOLD_OUTPUT = BASE_DIR / "03_Processed_Data" / "spatial" / "gold_training_set_tverrfjell.parquet"
KLEPP_RUNDE_PANEL = BASE_DIR / "03_Processed_Data" / "spatial" / "klepp_runde_course" / "panel_1m.parquet"
KLEPP_RUNDE_GOLD_OUTPUT = BASE_DIR / "03_Processed_Data" / "spatial" / "gold_training_set_klepp_runde.parquet"
GRAMSTAD_RUNDE_PANEL = BASE_DIR / "03_Processed_Data" / "spatial" / "gramstad_runde_course" / "panel_1m.parquet"
GRAMSTAD_RUNDE_GOLD_OUTPUT = BASE_DIR / "03_Processed_Data" / "spatial" / "gold_training_set_gramstad_runde.parquet"
VINJE_TERRENGLOP_PANEL = BASE_DIR / "03_Processed_Data" / "spatial" / "vinje_terrenglop_course" / "panel_1m.parquet"
VINJE_TERRENGLOP_GOLD_OUTPUT = BASE_DIR / "03_Processed_Data" / "spatial" / "gold_training_set_vinje_terrenglop.parquet"
STAVANGER_HALVMARATHON_PANEL = BASE_DIR / "03_Processed_Data" / "spatial" / "stavanger_halvmarathon_course" / "panel_1m.parquet"
STAVANGER_HALVMARATHON_GOLD_OUTPUT = BASE_DIR / "03_Processed_Data" / "spatial" / "gold_training_set_stavanger_halvmarathon.parquet"
SJOERSLOPET_PANEL = BASE_DIR / "03_Processed_Data" / "spatial" / "3_sjoerslopet_course" / "panel_1m.parquet"
SJOERSLOPET_GOLD_OUTPUT = BASE_DIR / "03_Processed_Data" / "spatial" / "gold_training_set_3_sjoerslopet.parquet"

SURFACE_CLASSES = ("S1", "S2", "S3", "S4", "S5", "S6")
FRICTION_TIERS = ("F0", "F1", "F2", "F3", "F4")

FEATURE_COLUMNS = (
    "consensus_nti",
    "nti_std",
    "nti_median",
    "ti_median",
    "ti_raw_median",
    "grade_pct_median",
    "speed_mps_median",
    "mechanical_kappa_median",
    "altitude_m",
    "cadence_spm_median",
    "pace_gap_flat_median",
    "hmm_confidence",
    "hmm_draft_class_ord",
)

HMM_CLASS_TO_ORD = {cls: i for i, cls in enumerate(SURFACE_CLASSES)}


def resolve_gold_training_defaults(terrain_map_path: Path) -> dict[str, Any]:
    """Derive panel/output/km window from terrain map race_id for non-SUT courses."""
    tmap = load_terrain_map(terrain_map_path)
    corridor = tmap.get("corridor") or {}
    race_id = str(corridor.get("race_id") or "")
    if race_id == "tverrfjell":
        km_end = float(corridor.get("km_end") or 23.549)
        return {
            "panel": TVERFJELL_PANEL,
            "output": TVERFJELL_GOLD_OUTPUT,
            "km_start": 0.0,
            "km_end": km_end,
            "hmm_draft": None,
        }
    if race_id == "klepp_runde":
        km_end = float(corridor.get("km_end") or 1.0)
        return {
            "panel": KLEPP_RUNDE_PANEL,
            "output": KLEPP_RUNDE_GOLD_OUTPUT,
            "km_start": 0.0,
            "km_end": km_end,
            "hmm_draft": None,
        }
    if race_id == "gramstad_runde":
        km_end = float(corridor.get("km_end") or 1.0)
        return {
            "panel": GRAMSTAD_RUNDE_PANEL,
            "output": GRAMSTAD_RUNDE_GOLD_OUTPUT,
            "km_start": 0.0,
            "km_end": km_end,
            "hmm_draft": None,
        }
    if race_id == "vinje_terrenglop":
        km_end = float(corridor.get("km_end") or 1.0)
        return {
            "panel": VINJE_TERRENGLOP_PANEL,
            "output": VINJE_TERRENGLOP_GOLD_OUTPUT,
            "km_start": 0.0,
            "km_end": km_end,
            "hmm_draft": None,
        }
    return {}


def _race_panel(panel: pd.DataFrame) -> pd.DataFrame:
    work = panel.copy()
    if "course_km" not in work.columns and "ref_chainage_m" in work.columns:
        work["course_km"] = work["ref_chainage_m"] / 1000.0
    if "course_m" not in work.columns and "ref_chainage_m" in work.columns:
        work["course_m"] = work["ref_chainage_m"]
    if "session_type" in work.columns:
        race = work[work["session_type"] == "race"]
        work = race if not race.empty else work
    return work.sort_values(["course_m", "donor_id"])


def _ensure_grade_pct_column(panel: pd.DataFrame) -> pd.DataFrame:
    """Populate grade_pct from grade or altitude diff when missing."""
    work = panel.copy()
    if "grade_pct" in work.columns and work["grade_pct"].notna().any():
        return work
    if "grade" in work.columns and work["grade"].notna().any():
        work["grade_pct"] = pd.to_numeric(work["grade"], errors="coerce")
        return work
    if "altitude_m" in work.columns:
        dalt = pd.to_numeric(work["altitude_m"], errors="coerce").diff()
        work["grade_pct"] = (100.0 * dalt).fillna(0.0)
    return work


def build_consensus_profile(panel: pd.DataFrame) -> pd.DataFrame:
    """Consensus TI + kinematic medians per course metre."""
    race = _race_panel(panel)
    race = _ensure_grade_pct_column(race)
    race = race.copy()
    if "ti" in race.columns:
        race["nti"] = compute_nti(race)
        consensus = aggregate_nti_by_course_m(race, use_consensus=True)
    else:
        consensus = pd.DataFrame()
    agg_spec: dict[str, tuple[str, str]] = {
        "course_km": ("course_km", "first"),
        "ti_median": ("ti", "median"),
        "ti_raw_median": ("ti_raw", "median"),
        "grade_pct_median": ("grade_pct", "median"),
        "speed_mps_median": ("speed_mps", "median"),
        "mechanical_kappa_median": ("mechanical_kappa", "median"),
        "altitude_m": ("altitude_m", "median"),
        "cadence_spm_median": ("cadence_spm", "median"),
        "pace_gap_flat_median": ("pace_gap_flat", "median"),
    }
    present = {k: v for k, v in agg_spec.items() if v[0] in race.columns}
    per_m = race.groupby("course_m", as_index=False).agg(**present)
    if consensus.empty:
        profile = per_m.copy()
        for col in ("consensus_nti", "nti_std", "nti_median"):
            profile[col] = np.nan
        return profile.sort_values("course_m").reset_index(drop=True)
    if "course_km" not in consensus.columns and "course_m" in consensus.columns:
        consensus = consensus.merge(per_m[["course_m", "course_km"]], on="course_m", how="left")
    profile = per_m.merge(
        consensus[["course_m", "consensus_nti", "nti_std", "nti_median"]],
        on="course_m",
        how="left",
    )
    return profile.sort_values("course_m").reset_index(drop=True)


def span_km_bounds(span: dict[str, Any]) -> tuple[float, float]:
    s0 = float(span.get("course_km_start", span.get("course_m_start", 0) / 1000.0))
    s1 = float(span.get("course_km_end", span.get("course_m_end", s0) / 1000.0))
    return s0, s1


def spans_overlap(km_start_a: float, km_end_a: float, km_start_b: float, km_end_b: float) -> bool:
    return km_start_a < km_end_b and km_start_b < km_end_a


def attach_gold_labels(frame: pd.DataFrame, gold_spans: list[dict[str, Any]]) -> pd.DataFrame:
    """Set label_surface, label_friction, is_labeled from operator gold spans."""
    work = frame.copy()
    work["label_surface"] = None
    work["label_friction"] = None
    work["is_labeled"] = False
    for span in gold_spans:
        km_start, km_end = span_km_bounds(span)
        mask = (work["course_km"] >= km_start) & (work["course_km"] < km_end)
        if not mask.any():
            continue
        work.loc[mask, "label_surface"] = span.get("surface_class")
        work.loc[mask, "label_friction"] = span.get("friction_tier")
        work.loc[mask, "is_labeled"] = True
    return work


def merge_hmm_features(profile: pd.DataFrame, hmm: pd.DataFrame) -> pd.DataFrame:
    if hmm.empty:
        profile = profile.copy()
        profile["draft_class"] = None
        profile["hmm_confidence"] = np.nan
        profile["hmm_draft_class_ord"] = np.nan
        return profile
    hmm_cols = ["course_m", "course_km", "draft_class", "hmm_confidence"]
    hmm_cols = [c for c in hmm_cols if c in hmm.columns]
    merged = profile.merge(hmm[hmm_cols].drop_duplicates("course_m"), on="course_m", how="left", suffixes=("", "_hmm"))
    if "course_km_hmm" in merged.columns:
        merged = merged.drop(columns=["course_km_hmm"])
    merged["hmm_draft_class_ord"] = merged["draft_class"].map(HMM_CLASS_TO_ORD)
    return merged


def load_panel_window(path: Path, km_lo: float, km_hi: float, *, buffer_km: float = 0.0) -> pd.DataFrame:
    lo = max(0.0, km_lo - buffer_km)
    hi = km_hi + buffer_km
    panel = pd.read_parquet(path)
    if "course_km" not in panel.columns and "ref_chainage_m" in panel.columns:
        panel["course_km"] = panel["ref_chainage_m"] / 1000.0
    return panel[(panel["course_km"] >= lo) & (panel["course_km"] <= hi)].copy()


def load_hmm_window(
    path: Path | None,
    km_lo: float,
    km_hi: float,
    *,
    buffer_km: float = 0.0,
) -> pd.DataFrame:
    if path is None or not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    lo = max(0.0, km_lo - buffer_km)
    hi = km_hi + buffer_km
    hmm = pd.read_parquet(path)
    return hmm[(hmm["course_km"] >= lo) & (hmm["course_km"] <= hi)].copy()


def build_training_frame(
    *,
    panel_path: Path = DEFAULT_PANEL,
    terrain_map_path: Path = DEFAULT_TERRAIN_MAP,
    extra_terrain_map_paths: list[Path] | None = None,
    hmm_path: Path | None = DEFAULT_HMM_DRAFT,
    km_lo: float | None = None,
    km_hi: float | None = None,
) -> pd.DataFrame:
    panel = pd.read_parquet(panel_path)
    if km_lo is not None and km_hi is not None:
        panel = load_panel_window(panel_path, km_lo, km_hi)
    profile = build_consensus_profile(panel)
    if km_lo is not None and km_hi is not None:
        profile = profile[(profile["course_km"] >= km_lo) & (profile["course_km"] < km_hi)].copy()
    if hmm_path is not None:
        hmm = load_hmm_window(
            hmm_path,
            km_lo or 0.0,
            km_hi or float(profile["course_km"].max()) + 0.001,
        )
    else:
        hmm = pd.DataFrame()
    frame = merge_hmm_features(profile, hmm)
    terrain_map = load_terrain_map(terrain_map_path)
    gold = list(operator_gold_spans(terrain_map))
    for extra_path in extra_terrain_map_paths or []:
        gold.extend(operator_gold_spans(load_terrain_map(extra_path)))
    frame = attach_gold_labels(frame, gold)
    return frame.sort_values("course_m").reset_index(drop=True)


def feature_matrix(df: pd.DataFrame, feature_cols: list[str] | tuple[str, ...] | None = None) -> pd.DataFrame:
    cols = list(feature_cols or FEATURE_COLUMNS)
    present = [c for c in cols if c in df.columns]
    return df[present].copy()
