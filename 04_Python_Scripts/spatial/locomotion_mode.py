"""
Locomotion mode classifier for Training Residual Framework (TRF).

Strategic Command memo 2026-06-29 — four-gate per-metre run / hike classification
must run **before** ΔTI residualization to suppress uphill power-hike false
positives on easy F1–F2 tread (docs/training_residual_framework.md §3.3).

Gate order:
  1. **F4 override** — friction_tier F4 → hike (walk / scramble authority)
  2. **Cadence hard limits** — hike if cadence ≤ hike_cadence_max;
     run if cadence ≥ run_cadence_min
  3. **Speed × grade grey zones** — uphill (grade > threshold AND speed < max)
     or downhill (grade < threshold AND speed < max) → hike
  4. **Default** — run

Athlete-specific thresholds load from ``config/subject_kinematics.local.json``
(gitignored). Template: ``config/subject_kinematics.local.example.json``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import pandas as pd

LocomotionMode = Literal["run", "hike"]

# TRF §3.2 grade band boundaries (percent).
GRADE_UPHILL_MIN_PCT = 3.0
GRADE_DOWNHILL_MAX_PCT = -3.0

DEFAULT_RUN_CADENCE_MIN = 145.0
DEFAULT_HIKE_CADENCE_MAX = 130.0
DEFAULT_GREY_UPHILL_GRADE_PCT = 5.0
DEFAULT_GREY_UPHILL_SPEED_MAX_MPS = 1.5
DEFAULT_GREY_DOWNHILL_GRADE_PCT = -5.0
DEFAULT_GREY_DOWNHILL_SPEED_MAX_MPS = 1.8
MIN_VALID_CADENCE_SPM = 40.0

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KINEMATICS_PATH = _REPO_ROOT / "config" / "subject_kinematics.local.json"


@dataclass(frozen=True)
class GreyZoneSpec:
    grade_threshold_pct: float
    speed_max_ms: float


@dataclass(frozen=True)
class SubjectKinematics:
    """Per-athlete four-gate locomotion thresholds."""

    run_cadence_min: float = DEFAULT_RUN_CADENCE_MIN
    hike_cadence_max: float = DEFAULT_HIKE_CADENCE_MAX
    grey_zone_uphill: GreyZoneSpec = GreyZoneSpec(
        DEFAULT_GREY_UPHILL_GRADE_PCT,
        DEFAULT_GREY_UPHILL_SPEED_MAX_MPS,
    )
    grey_zone_downhill: GreyZoneSpec = GreyZoneSpec(
        DEFAULT_GREY_DOWNHILL_GRADE_PCT,
        DEFAULT_GREY_DOWNHILL_SPEED_MAX_MPS,
    )


# Backward-compatible alias for TRF CLI overrides.
LocomotionThresholds = SubjectKinematics


def _parse_grey_zone(block: dict[str, Any] | None, *, uphill: bool) -> GreyZoneSpec:
    if not block:
        if uphill:
            return GreyZoneSpec(DEFAULT_GREY_UPHILL_GRADE_PCT, DEFAULT_GREY_UPHILL_SPEED_MAX_MPS)
        return GreyZoneSpec(DEFAULT_GREY_DOWNHILL_GRADE_PCT, DEFAULT_GREY_DOWNHILL_SPEED_MAX_MPS)
    return GreyZoneSpec(
        float(block.get("grade_threshold_pct", DEFAULT_GREY_UPHILL_GRADE_PCT if uphill else DEFAULT_GREY_DOWNHILL_GRADE_PCT)),
        float(block.get("speed_max_ms", DEFAULT_GREY_UPHILL_SPEED_MAX_MPS if uphill else DEFAULT_GREY_DOWNHILL_SPEED_MAX_MPS)),
    )


def _kinematics_from_mapping(data: dict[str, Any]) -> SubjectKinematics:
    return SubjectKinematics(
        run_cadence_min=float(data.get("run_cadence_min", DEFAULT_RUN_CADENCE_MIN)),
        hike_cadence_max=float(data.get("hike_cadence_max", DEFAULT_HIKE_CADENCE_MAX)),
        grey_zone_uphill=_parse_grey_zone(data.get("grey_zone_uphill"), uphill=True),
        grey_zone_downhill=_parse_grey_zone(data.get("grey_zone_downhill"), uphill=False),
    )


@lru_cache(maxsize=4)
def load_subject_kinematics_config(path: str | None = None) -> dict[str, Any]:
    """
    Load gitignored subject kinematics registry.

    Returns empty dict when the file is missing; callers fall back to module defaults.
    """
    cfg_path = Path(path) if path else DEFAULT_KINEMATICS_PATH
    if not cfg_path.is_absolute():
        cfg_path = _REPO_ROOT / cfg_path
    if not cfg_path.exists():
        return {}
    with cfg_path.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    return {k: v for k, v in raw.items() if not str(k).startswith("_")}


def thresholds_for_subject(
    config: dict[str, Any] | None,
    subject_id: str,
    *,
    overrides: SubjectKinematics | None = None,
) -> SubjectKinematics:
    """Resolve per-subject thresholds from config with CLI/runtime overrides."""
    base = overrides or SubjectKinematics()
    if not config:
        return base
    block = config.get(subject_id)
    if not block:
        return base
    parsed = _kinematics_from_mapping(block)
    return replace(
        base,
        run_cadence_min=parsed.run_cadence_min,
        hike_cadence_max=parsed.hike_cadence_max,
        grey_zone_uphill=parsed.grey_zone_uphill,
        grey_zone_downhill=parsed.grey_zone_downhill,
    )


def athlete_locomotion_thresholds(
    df: pd.DataFrame,
    *,
    subject_id: str | None = None,
    kinematics_config: dict[str, Any] | None = None,
    overrides: SubjectKinematics | None = None,
    **_kwargs: Any,
) -> SubjectKinematics:
    """Return JSON-backed thresholds for one subject (session slice ignored)."""
    if subject_id and kinematics_config is not None:
        return thresholds_for_subject(kinematics_config, subject_id, overrides=overrides)
    return overrides or SubjectKinematics()


def assign_grade_bin(grade_pct: pd.Series | pd.Index) -> pd.Series:
    """
    Bin grade_pct into uphill / flat / downhill per TRF §3.2.

    Boundaries: uphill > +3%, flat −3% to +3%, downhill < −3%.
    """
    grade = pd.to_numeric(grade_pct, errors="coerce")
    out = pd.Series("flat", index=grade.index, dtype="object")
    out.loc[grade > GRADE_UPHILL_MIN_PCT] = "uphill"
    out.loc[grade < GRADE_DOWNHILL_MAX_PCT] = "downhill"
    return out


def _classify_gate_slice(
    grade: pd.Series,
    cadence: pd.Series,
    speed: pd.Series,
    friction_tier: pd.Series | None,
    th: SubjectKinematics,
) -> pd.Series:
    """Apply four-gate logic on aligned series sharing one threshold set."""
    mode = pd.Series("run", index=grade.index, dtype="object")

    # Gate 1 — F4 override
    if friction_tier is not None:
        mode.loc[friction_tier.astype(str) == "F4"] = "hike"

    valid_cadence = cadence.notna() & (cadence >= MIN_VALID_CADENCE_SPM)

    # Gate 2 — cadence hard limits
    hard_hike = valid_cadence & (cadence <= th.hike_cadence_max)
    mode.loc[hard_hike] = "hike"

    hard_run = valid_cadence & (cadence >= th.run_cadence_min)
    mode.loc[hard_run & (mode != "hike")] = "run"

    # Gate 3 — speed × grade grey zones (ambiguous cadence or missing cadence)
    grey_eligible = mode == "run"
    uphill_grey = (
        grey_eligible
        & (grade > th.grey_zone_uphill.grade_threshold_pct)
        & speed.notna()
        & (speed < th.grey_zone_uphill.speed_max_ms)
    )
    downhill_grey = (
        grey_eligible
        & (grade < th.grey_zone_downhill.grade_threshold_pct)
        & speed.notna()
        & (speed < th.grey_zone_downhill.speed_max_ms)
    )
    mode.loc[uphill_grey | downhill_grey] = "hike"

    # Gate 4 — default run (already "run" where not hike)
    return mode


def classify_locomotion_mode(
    df: pd.DataFrame,
    *,
    grade_col: str = "grade_pct",
    cadence_col: str = "cadence_spm",
    speed_col: str = "speed_mps",
    friction_tier_col: str | None = "friction_tier",
    subject_id_col: str | None = None,
    subject_id: str | None = None,
    kinematics_config: dict[str, Any] | None = None,
    thresholds: SubjectKinematics | None = None,
) -> pd.Series:
    """
    Per-metre run / hike classification via four-gate logic.

    When ``subject_id`` or ``subject_id_col`` plus ``kinematics_config`` are set,
    thresholds resolve per athlete (Subject_A, Subject_B, …).
    """
    grade_raw = df[grade_col] if grade_col in df.columns else df.get("grade_pct", df.get("grade"))
    if grade_raw is None or isinstance(grade_raw, (int, float)):
        grade = pd.Series(0.0, index=df.index, dtype=float)
    else:
        grade = pd.to_numeric(grade_raw, errors="coerce").fillna(0.0)
    cadence = pd.to_numeric(df[cadence_col], errors="coerce") if cadence_col in df.columns else pd.Series(index=df.index, dtype=float)
    speed = pd.to_numeric(df[speed_col], errors="coerce") if speed_col in df.columns else pd.Series(index=df.index, dtype=float)
    friction = df[friction_tier_col] if friction_tier_col and friction_tier_col in df.columns else None

    if thresholds is not None:
        return _classify_gate_slice(grade, cadence, speed, friction, thresholds)

    if subject_id and kinematics_config is not None:
        th = thresholds_for_subject(kinematics_config, subject_id)
        return _classify_gate_slice(grade, cadence, speed, friction, th)

    sid_col = subject_id_col
    if sid_col is None and "subject_id" in df.columns:
        sid_col = "subject_id"
    if sid_col and sid_col in df.columns and kinematics_config is not None:
        mode = pd.Series("run", index=df.index, dtype="object")
        for sid in df[sid_col].dropna().unique():
            mask = df[sid_col] == sid
            th = thresholds_for_subject(kinematics_config, str(sid))
            mode.loc[mask] = _classify_gate_slice(
                grade.loc[mask],
                cadence.loc[mask],
                speed.loc[mask],
                friction.loc[mask] if friction is not None else None,
                th,
            )
        return mode

    return _classify_gate_slice(grade, cadence, speed, friction, SubjectKinematics())


def _ensure_grade_pct(work: pd.DataFrame) -> pd.DataFrame:
    """Derive grade_pct from altitude when the panel lacks a populated grade column."""
    if "grade_pct" in work.columns and work["grade_pct"].notna().any():
        return work
    if "grade" in work.columns and work["grade"].notna().any():
        out = work.copy()
        if "grade_pct" not in out.columns:
            out["grade_pct"] = pd.to_numeric(out["grade"], errors="coerce")
        return out
    if "altitude_m" not in work.columns:
        return work
    out = work.copy()
    dalt = pd.to_numeric(out["altitude_m"], errors="coerce").diff()
    out["grade_pct"] = (100.0 * dalt).fillna(0.0)
    return out


def tag_panel_locomotion(
    panel: pd.DataFrame,
    terrain_map: dict[str, Any],
    *,
    kinematics_config: dict[str, Any] | None = None,
    session_type: str | None = "race",
) -> pd.DataFrame:
    """Attach friction_tier and locomotion_mode per panel row."""
    import sys

    repo = Path(__file__).resolve().parents[2]
    scripts = repo / "04_Python_Scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))

    from spatial.compute_training_residual import resolve_friction_tiers  # noqa: WPS433
    from spatial.reproject_to_spine import normalize_panel_axes, subject_id_column  # noqa: WPS433

    work = normalize_panel_axes(panel.copy())
    if session_type and "session_type" in work.columns:
        filtered = work[work["session_type"] == session_type]
        if not filtered.empty:
            work = filtered
    work = _ensure_grade_pct(work)
    work = resolve_friction_tiers(work, terrain_map)
    if kinematics_config is None:
        kinematics_config = load_subject_kinematics_config()
    sid_col = subject_id_column(work)
    work["locomotion_mode"] = classify_locomotion_mode(
        work,
        subject_id_col=sid_col,
        kinematics_config=kinematics_config,
    )
    return work


def _cli_main() -> None:
    import argparse
    import json
    import sys

    repo = Path(__file__).resolve().parents[2]
    if str(repo / "04_Python_Scripts") not in sys.path:
        sys.path.insert(0, str(repo / "04_Python_Scripts"))

    parser = argparse.ArgumentParser(
        description="Re-tag panel metres with four-gate run/hike locomotion_mode (TRF §3.3)",
    )
    parser.add_argument(
        "--panel",
        type=Path,
        default=repo / "03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet",
        help="Aligned 1 m panel parquet",
    )
    parser.add_argument(
        "--terrain-map",
        type=Path,
        default=repo / "config/spatial_terrain_map_sut43.json",
        help="Terrain map JSON (operator gold friction tiers)",
    )
    parser.add_argument(
        "--kinematics-config",
        type=Path,
        default=DEFAULT_KINEMATICS_PATH,
        help="Subject locomotion thresholds JSON (default: config/subject_kinematics.local.json)",
    )
    parser.add_argument(
        "--session-type",
        default="race",
        help="Panel session_type filter (default: race)",
    )
    parser.add_argument(
        "--sidecar",
        type=Path,
        default=None,
        help="Output parquet sidecar (default: <panel_dir>/locomotion_mode_1m.parquet)",
    )
    parser.add_argument(
        "--write-panel",
        action="store_true",
        help="Merge locomotion_mode into panel parquet (in addition to sidecar)",
    )
    parser.add_argument("--km-start", type=float, default=None)
    parser.add_argument("--km-end", type=float, default=None)
    args = parser.parse_args()

    panel_path = args.panel if args.panel.is_absolute() else repo / args.panel
    map_path = args.terrain_map if args.terrain_map.is_absolute() else repo / args.terrain_map
    kin_path = args.kinematics_config if args.kinematics_config.is_absolute() else repo / args.kinematics_config

    terrain_map = json.loads(map_path.read_text(encoding="utf-8"))
    kinematics_config = load_subject_kinematics_config(str(kin_path))
    panel = pd.read_parquet(panel_path)
    tagged = tag_panel_locomotion(
        panel,
        terrain_map,
        kinematics_config=kinematics_config,
        session_type=args.session_type or None,
    )
    if args.km_start is not None:
        tagged = tagged[tagged["course_km"] >= args.km_start]
    if args.km_end is not None:
        tagged = tagged[tagged["course_km"] < args.km_end]

    sidecar_path = args.sidecar or (panel_path.parent / "locomotion_mode_1m.parquet")
    export_cols = ["course_m", "course_km", "locomotion_mode", "friction_tier"]
    if "donor_id" in tagged.columns:
        export_cols.insert(2, "donor_id")
    tagged[[c for c in export_cols if c in tagged.columns]].to_parquet(sidecar_path, index=False)

    run_n = int((tagged["locomotion_mode"] == "run").sum())
    hike_n = int((tagged["locomotion_mode"] == "hike").sum())
    print(f"Wrote {sidecar_path} ({len(tagged)} rows; run={run_n}, hike={hike_n})")

    if args.write_panel:
        full = panel.copy()
        side = tagged[["course_m", "locomotion_mode"] + (["donor_id"] if "donor_id" in tagged.columns else [])]
        merge_on = ["course_m", "donor_id"] if "donor_id" in side.columns and "donor_id" in full.columns else ["course_m"]
        full = full.drop(columns=["locomotion_mode"], errors="ignore").merge(side, on=merge_on, how="left")
        full.to_parquet(panel_path, index=False)
        print(f"Updated panel {panel_path}")


if __name__ == "__main__":
    _cli_main()
