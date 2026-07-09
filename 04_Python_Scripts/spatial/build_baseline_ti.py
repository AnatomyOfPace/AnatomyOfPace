#!/usr/bin/env python3
"""
Build reference-elite Baseline TI matrix and per-metre course grid (friction_index_spec §7 C2).

Aggregates observed TI from cohort donors on operator-locked friction tiers, stratified by
grade_bin and locomotion_mode. Exports:

  - Per-metre course grid with baseline_ti lookup (TPR denominator)
  - Cell matrix with sample counts and fallback levels
  - Summary JSON with tier-band QC
  - Optional QC visualization

Usage (from repo root):
    python3 04_Python_Scripts/spatial/build_baseline_ti.py \\
        --terrain-map config/spatial_terrain_map_sut43_full.json \\
        --panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_full_1m.parquet

    python3 04_Python_Scripts/spatial/build_baseline_ti_sut43.sh
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

from spatial.compute_training_residual import (  # noqa: E402
    load_terrain_map,
    resolve_friction_tiers,
)
from spatial.gold_training_common import resolve_gold_training_defaults  # noqa: E402
from spatial.locomotion_mode import (  # noqa: E402
    assign_grade_bin,
    classify_locomotion_mode,
    load_subject_kinematics_config,
)
from spatial.reproject_to_spine import normalize_panel_axes, subject_id_column  # noqa: E402
from spatial.suggest_gold_spans import FRICTION_TI_BANDS, FRICTION_TIER_CENTRES  # noqa: E402
from spatial.validation_dashboard import operator_gold_spans  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_TERRAIN_MAP = BASE_DIR / "config" / "spatial_terrain_map_sut43_full.json"
DEFAULT_PANEL = BASE_DIR / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "panel_full_1m.parquet"
DEFAULT_OUTPUT = BASE_DIR / "03_Processed_Data" / "spatial" / "baseline_ti_sut43_full.parquet"
DEFAULT_MATRIX_OUTPUT = BASE_DIR / "03_Processed_Data" / "spatial" / "baseline_ti_sut43_full_matrix.parquet"
DEFAULT_REPORT = BASE_DIR / "07_ML_Models" / "spatial" / "baseline_ti_sut43_full_report.json"
DEFAULT_QC_PNG = BASE_DIR / "06_Visualizations" / "sut43_baseline_ti_qc.png"

CohortMode = Literal["reference_elite", "race_panel", "explicit"]
MIN_CELL_SAMPLES = 3
REFERENCE_ELITE_PREFIX = "Reference_Elite_"

MATRIX_COLUMNS = (
    "friction_tier",
    "grade_bin",
    "locomotion_mode",
    "baseline_ti",
    "n_samples",
    "ti_p25",
    "ti_p75",
    "fallback_level",
)

COURSE_COLUMNS = (
    "course_m",
    "course_km",
    "friction_tier",
    "grade_bin",
    "locomotion_mode",
    "baseline_ti",
    "fallback_level",
    "ti_observed_median",
    "n_cohort_samples",
    "tier_band_lo",
    "tier_band_hi",
    "tier_band_centre",
    "tier_band_delta",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tier_band_bounds(tier: str) -> tuple[float, float, float]:
    for name, lo, hi in FRICTION_TI_BANDS:
        if name == tier:
            centre = FRICTION_TIER_CENTRES[name]
            return lo, hi, centre
    centre = FRICTION_TIER_CENTRES.get(tier, np.nan)
    return np.nan, np.nan, centre


def locked_gold_mask(km: pd.Series, terrain_map: dict[str, Any]) -> pd.Series:
    """True on metres covered by operator gold spans with tier or surface labels."""
    mask = pd.Series(False, index=km.index)
    for span in operator_gold_spans(terrain_map):
        if not (span.get("friction_tier") or span.get("surface_class")):
            continue
        km0 = float(span["course_km_start"])
        km1 = float(span["course_km_end"])
        mask |= (km >= km0) & (km < km1)
    return mask


def select_cohort_donors(
    panel: pd.DataFrame,
    *,
    cohort_mode: CohortMode,
    explicit_donors: list[str] | None,
    reference_prefix: str,
    strict_reference_elite: bool,
) -> tuple[list[str], str, list[str]]:
    """
    Return (donor_ids, cohort_label, warnings).

    cohort_label documents whether the build used reference elites or an interim fallback.
    """
    sid_col = subject_id_column(panel)
    all_donors = sorted(panel[sid_col].dropna().astype(str).unique().tolist())
    warnings: list[str] = []

    if cohort_mode == "explicit":
        donors = explicit_donors or []
        if not donors:
            raise ValueError("--cohort-donors required when --cohort-mode explicit")
        missing = [d for d in donors if d not in all_donors]
        if missing:
            raise ValueError(f"Cohort donors not in panel: {missing}")
        return donors, "explicit", warnings

    if cohort_mode == "race_panel":
        if "session_type" in panel.columns:
            race = panel[panel["session_type"] == "race"]
            donors = sorted(race[sid_col].dropna().astype(str).unique().tolist()) if not race.empty else all_donors
        else:
            donors = all_donors
        warnings.append(
            "cohort_mode=race_panel — interim Baseline TI from race-day panel donors; "
            "replace with Reference_Elite_* when SUT_43 reference .fit streams arrive."
        )
        return donors, "interim_race_panel", warnings

    ref_donors = [d for d in all_donors if d.startswith(reference_prefix)]
    if ref_donors:
        return ref_donors, "reference_elite", warnings

    if strict_reference_elite:
        raise ValueError(
            f"No donors matching prefix {reference_prefix!r} in panel. "
            "Use --cohort-mode race_panel or --allow-interim-cohort."
        )

    if "session_type" in panel.columns:
        race = panel[panel["session_type"] == "race"]
        donors = sorted(race[sid_col].dropna().astype(str).unique().tolist()) if not race.empty else all_donors
    else:
        donors = all_donors
    warnings.append(
        f"No {reference_prefix}* donors in panel — fell back to race_panel cohort "
        f"({', '.join(donors)}). Mark report cohort_label interim until reference elites ingest."
    )
    return donors, "interim_race_panel", warnings


def prepare_cohort_frame(
    panel: pd.DataFrame,
    terrain_map: dict[str, Any],
    *,
    donors: list[str],
    session_type: str | None,
    km_start: float,
    km_end: float,
    kinematics_config: dict[str, Any] | None,
    locked_gold_only: bool,
) -> pd.DataFrame:
    """Filter panel to cohort donors and attach TI, friction tier, grade_bin, locomotion_mode."""
    work = normalize_panel_axes(panel.copy())
    sid_col = subject_id_column(work)

    if session_type and "session_type" in work.columns:
        session_filtered = work[work["session_type"] == session_type]
        if not session_filtered.empty:
            work = session_filtered

    work = work[
        work[sid_col].isin(donors)
        & (work["course_km"] >= km_start)
        & (work["course_km"] < km_end)
    ].copy()
    if work.empty:
        raise ValueError(f"No cohort rows for donors {donors} in km {km_start}–{km_end}")

    work["ti"] = pd.to_numeric(work["ti"], errors="coerce")
    work = work.dropna(subset=["ti"])
    work["grade_bin"] = assign_grade_bin(work["grade_pct"])
    work = resolve_friction_tiers(work, terrain_map)

    if kinematics_config is None:
        kinematics_config = load_subject_kinematics_config()
    work["locomotion_mode"] = classify_locomotion_mode(
        work,
        subject_id_col=sid_col,
        kinematics_config=kinematics_config,
    )

    if locked_gold_only:
        km = pd.to_numeric(work["course_km"], errors="coerce")
        work = work.loc[locked_gold_mask(km, terrain_map)].copy()
        work = work[work["friction_tier"].notna()].copy()

    if work.empty:
        raise ValueError("Cohort empty after locked-gold friction-tier filter")

    return work


def _cell_stats(sub: pd.Series) -> dict[str, float | int]:
    vals = sub.dropna()
    return {
        "baseline_ti": float(vals.median()),
        "n_samples": int(len(vals)),
        "ti_p25": float(vals.quantile(0.25)) if len(vals) else np.nan,
        "ti_p75": float(vals.quantile(0.75)) if len(vals) else np.nan,
    }


def _group_cells(
    cohort: pd.DataFrame,
    keys: tuple[str, ...],
    *,
    fallback_level: str,
    min_samples: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    grouped = cohort.groupby(list(keys), observed=True)["ti"]
    for key_tuple, series in grouped:
        if len(series) < min_samples:
            continue
        if not isinstance(key_tuple, tuple):
            key_tuple = (key_tuple,)
        row: dict[str, Any] = dict(zip(keys, key_tuple))
        row.update(_cell_stats(series))
        row["fallback_level"] = fallback_level
        rows.append(row)
    return rows


def build_baseline_matrix(
    cohort: pd.DataFrame,
    *,
    min_samples: int = MIN_CELL_SAMPLES,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build cell matrix and lookup tables for fallback chain."""
    rows: list[dict[str, Any]] = []
    rows.extend(
        _group_cells(
            cohort,
            ("friction_tier", "grade_bin", "locomotion_mode"),
            fallback_level="tier_grade_mode",
            min_samples=min_samples,
        )
    )
    rows.extend(
        _group_cells(
            cohort,
            ("friction_tier", "grade_bin"),
            fallback_level="tier_grade",
            min_samples=min_samples,
        )
    )
    rows.extend(
        _group_cells(
            cohort,
            ("friction_tier", "locomotion_mode"),
            fallback_level="tier_mode",
            min_samples=min_samples,
        )
    )
    rows.extend(
        _group_cells(
            cohort,
            ("friction_tier",),
            fallback_level="tier_only",
            min_samples=min_samples,
        )
    )

    matrix = pd.DataFrame(rows)
    if matrix.empty:
        matrix = pd.DataFrame(columns=list(MATRIX_COLUMNS))

    lookups: dict[str, Any] = {
        "tier_grade_mode": {},
        "tier_grade": {},
        "tier_mode": {},
        "tier_only": {},
    }
    for row in rows:
        level = row["fallback_level"]
        if level == "tier_grade_mode":
            key = (row["friction_tier"], row["grade_bin"], row["locomotion_mode"])
        elif level == "tier_grade":
            key = (row["friction_tier"], row["grade_bin"])
        elif level == "tier_mode":
            key = (row["friction_tier"], row["locomotion_mode"])
        else:
            key = row["friction_tier"]
        lookups[level][key] = (row["baseline_ti"], row["n_samples"])

    return matrix, lookups


def lookup_baseline(
    *,
    friction_tier: str | None,
    grade_bin: str,
    locomotion_mode: str,
    lookups: dict[str, Any],
) -> tuple[float, str, int]:
    """Resolve baseline TI with fallback chain; returns (value, level, n_samples)."""
    if friction_tier:
        key3 = (friction_tier, grade_bin, locomotion_mode)
        hit = lookups["tier_grade_mode"].get(key3)
        if hit:
            return hit[0], "tier_grade_mode", hit[1]

        key_tg = (friction_tier, grade_bin)
        hit = lookups["tier_grade"].get(key_tg)
        if hit:
            return hit[0], "tier_grade", hit[1]

        key_tm = (friction_tier, locomotion_mode)
        hit = lookups["tier_mode"].get(key_tm)
        if hit:
            return hit[0], "tier_mode", hit[1]

        hit = lookups["tier_only"].get(friction_tier)
        if hit:
            return hit[0], "tier_only", hit[1]

        centre = FRICTION_TIER_CENTRES.get(friction_tier, np.nan)
        return float(centre), "tier_band_centre", 0

    return np.nan, "unresolved", 0


def build_course_grid(
    panel: pd.DataFrame,
    terrain_map: dict[str, Any],
    cohort: pd.DataFrame,
    lookups: dict[str, Any],
    *,
    donors: list[str],
    session_type: str | None,
    km_start: float,
    km_end: float,
    kinematics_config: dict[str, Any] | None,
) -> pd.DataFrame:
    """One row per course metre with baseline_ti from matrix lookup."""
    sid_col = subject_id_column(panel)
    scope = normalize_panel_axes(panel.copy())
    if session_type and "session_type" in scope.columns:
        race = scope[scope["session_type"] == "race"]
        if not race.empty:
            scope = race
    scope = scope[(scope["course_km"] >= km_start) & (scope["course_km"] < km_end)]

    agg_cols = {
        "course_km": "first",
        "grade_pct": "median",
        "cadence_spm": "median",
        "speed_mps": "median",
    }
    present_agg = {k: v for k, v in agg_cols.items() if k in scope.columns}
    grid = scope.groupby("course_m", as_index=False).agg(present_agg)
    grid["grade_bin"] = assign_grade_bin(grid["grade_pct"])
    grid = resolve_friction_tiers(grid, terrain_map)

    if kinematics_config is None:
        kinematics_config = load_subject_kinematics_config()
    grid["locomotion_mode"] = classify_locomotion_mode(
        grid,
        kinematics_config=kinematics_config,
    )

    cohort_counts = (
        cohort.groupby("course_m", observed=True)["ti"]
        .agg(ti_observed_median="median", n_cohort_samples="count")
        .reset_index()
    )
    grid = grid.merge(cohort_counts, on="course_m", how="left")

    baselines: list[float] = []
    levels: list[str] = []
    n_lookup: list[int] = []
    for row in grid.itertuples(index=False):
        val, level, n = lookup_baseline(
            friction_tier=getattr(row, "friction_tier", None),
            grade_bin=row.grade_bin,
            locomotion_mode=row.locomotion_mode,
            lookups=lookups,
        )
        baselines.append(val)
        levels.append(level)
        n_lookup.append(n)
    grid["baseline_ti"] = baselines
    grid["fallback_level"] = levels
    grid["matrix_n_samples"] = n_lookup

    band_lo: list[float] = []
    band_hi: list[float] = []
    band_centre: list[float] = []
    band_delta: list[float] = []
    for row in grid.itertuples(index=False):
        tier = getattr(row, "friction_tier", None)
        if tier:
            lo, hi, centre = _tier_band_bounds(str(tier))
        else:
            lo, hi, centre = np.nan, np.nan, np.nan
        band_lo.append(lo)
        band_hi.append(hi)
        band_centre.append(centre)
        if pd.notna(centre) and pd.notna(row.baseline_ti):
            band_delta.append(abs(float(row.baseline_ti) - float(centre)))
        else:
            band_delta.append(np.nan)
    grid["tier_band_lo"] = band_lo
    grid["tier_band_hi"] = band_hi
    grid["tier_band_centre"] = band_centre
    grid["tier_band_delta"] = band_delta

    corridor = terrain_map.get("corridor") or {}
    grid["race_id"] = corridor.get("race_id")
    grid["sector_id"] = corridor.get("sector_id")
    grid["cohort_donors"] = ",".join(donors)

    export_cols = [c for c in COURSE_COLUMNS if c in grid.columns]
    extra = ["race_id", "sector_id", "cohort_donors", "matrix_n_samples", "grade_pct"]
    for col in extra:
        if col in grid.columns and col not in export_cols:
            export_cols.append(col)
    return grid[export_cols].sort_values("course_m")


def tier_band_qc(matrix: pd.DataFrame) -> list[dict[str, Any]]:
    """Per-tier median TI vs friction_index_spec §3 band centre (tier_only cells)."""
    tier_rows = matrix[matrix["fallback_level"] == "tier_only"] if not matrix.empty else matrix
    out: list[dict[str, Any]] = []
    for tier in sorted(tier_rows["friction_tier"].dropna().unique()):
        sub = tier_rows[tier_rows["friction_tier"] == tier]
        if sub.empty:
            continue
        med = float(sub["baseline_ti"].iloc[0])
        lo, hi, centre = _tier_band_bounds(str(tier))
        out.append(
            {
                "friction_tier": tier,
                "baseline_ti_median": med,
                "tier_band_lo": lo,
                "tier_band_hi": hi,
                "tier_band_centre": centre,
                "delta_from_centre": abs(med - centre) if pd.notna(centre) else np.nan,
                "inside_band": bool(lo <= med <= hi) if pd.notna(lo) and pd.notna(hi) else None,
                "n_samples": int(sub["n_samples"].iloc[0]),
            }
        )
    return out


def render_qc_plot(
    course_grid: pd.DataFrame,
    matrix: pd.DataFrame,
    output_path: Path,
    *,
    km_start: float,
    km_end: float,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    fig.patch.set_facecolor("#0A0A0A")

    km = course_grid["course_km"]
    ax0 = axes[0]
    ax0.set_facecolor("#111111")
    ax0.plot(km, course_grid["baseline_ti"], color="#4FC3F7", linewidth=0.8, label="baseline_ti")
    if "ti_observed_median" in course_grid.columns:
        ax0.plot(
            km,
            course_grid["ti_observed_median"],
            color="#FFB74D",
            linewidth=0.6,
            alpha=0.7,
            label="cohort TI median",
        )
    ax0.set_ylabel("TI")
    ax0.set_title("SUT_43 full course — Baseline TI (C2)", color="white")
    ax0.legend(loc="upper right", fontsize=8)
    ax0.tick_params(colors="white")
    for spine in ax0.spines.values():
        spine.set_color("#444444")

    ax1 = axes[1]
    ax1.set_facecolor("#111111")
    tier_codes = {t: i for i, t in enumerate(["F0", "F1", "F2", "F3", "F4"])}
    tier_y = course_grid["friction_tier"].map(tier_codes)
    ax1.scatter(km, tier_y, c=tier_y, cmap="viridis", s=1, alpha=0.8)
    ax1.set_yticks(list(tier_codes.values()))
    ax1.set_yticklabels(list(tier_codes.keys()))
    ax1.set_ylabel("F-tier")
    ax1.tick_params(colors="white")
    for spine in ax1.spines.values():
        spine.set_color("#444444")

    ax2 = axes[2]
    ax2.set_facecolor("#111111")
    tier_only = matrix[matrix["fallback_level"] == "tier_only"] if not matrix.empty else matrix
    if not tier_only.empty:
        tiers = tier_only["friction_tier"].tolist()
        vals = tier_only["baseline_ti"].tolist()
        colors = ["#66BB6A" if _tier_band_bounds(t)[0] <= v <= _tier_band_bounds(t)[1] else "#EF5350" for t, v in zip(tiers, vals)]
        ax2.bar(tiers, vals, color=colors, edgecolor="#333333")
        for tier in tiers:
            lo, hi, _ = _tier_band_bounds(tier)
            if pd.notna(lo):
                ax2.axhspan(lo, hi, alpha=0.15, color="white")
    ax2.set_ylabel("tier median TI")
    ax2.set_xlabel("course km")
    ax2.tick_params(colors="white")
    for spine in ax2.spines.values():
        spine.set_color("#444444")

    axes[0].set_xlim(km_start, km_end)
    fig.tight_layout()
    fig.savefig(output_path, dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)


def resolve_defaults(terrain_map_path: Path) -> dict[str, Any]:
    """Derive panel/km window from terrain map; Baseline TI paths are never gold-training paths."""
    resolved = resolve_gold_training_defaults(terrain_map_path)
    if not resolved:
        return {}
    corridor = json.loads(terrain_map_path.read_text(encoding="utf-8")).get("corridor") or {}
    race_id = corridor.get("race_id")
    out: dict[str, Any] = {
        "panel": resolved.get("panel"),
        "km_start": resolved.get("km_start"),
        "km_end": resolved.get("km_end"),
    }
    if race_id == "SUT_43":
        slug = "sut43_full"
        out["output"] = BASE_DIR / f"03_Processed_Data/spatial/baseline_ti_{slug}.parquet"
        out["matrix_output"] = BASE_DIR / f"03_Processed_Data/spatial/baseline_ti_{slug}_matrix.parquet"
        out["report"] = BASE_DIR / f"07_ML_Models/spatial/baseline_ti_{slug}_report.json"
        out["qc_png"] = BASE_DIR / "06_Visualizations/sut43_baseline_ti_qc.png"
    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Baseline TI matrix and per-metre course grid.")
    parser.add_argument("--terrain-map", type=Path, default=DEFAULT_TERRAIN_MAP)
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--km-start", type=float, default=None)
    parser.add_argument("--km-end", type=float, default=None)
    parser.add_argument("--session-type", default="race", help="Panel session filter (default: race)")
    parser.add_argument(
        "--cohort-mode",
        choices=("reference_elite", "race_panel", "explicit"),
        default="reference_elite",
        help="Donor selection strategy (default: Reference_Elite_* with interim fallback)",
    )
    parser.add_argument(
        "--cohort-donors",
        default="",
        help="Comma-separated donor IDs when --cohort-mode explicit",
    )
    parser.add_argument(
        "--reference-prefix",
        default=REFERENCE_ELITE_PREFIX,
        help="Donor ID prefix for reference_elite mode",
    )
    parser.add_argument(
        "--allow-interim-cohort",
        action="store_true",
        help="When no reference elites in panel, fall back to race_panel donors (default behaviour)",
    )
    parser.add_argument(
        "--strict-reference-elite",
        action="store_true",
        help="Fail if no Reference_Elite_* donors (no interim fallback)",
    )
    parser.add_argument(
        "--include-variance-gaps",
        action="store_true",
        help="Include metres outside operator gold spans in cohort (default: locked gold only)",
    )
    parser.add_argument("--min-cell-samples", type=int, default=MIN_CELL_SAMPLES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--matrix-output", type=Path, default=DEFAULT_MATRIX_OUTPUT)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--qc-png", type=Path, default=DEFAULT_QC_PNG)
    parser.add_argument("--no-qc", action="store_true", help="Skip QC PNG")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    terrain_map_path = args.terrain_map if args.terrain_map.is_absolute() else BASE_DIR / args.terrain_map
    panel_path = args.panel if args.panel.is_absolute() else BASE_DIR / args.panel

    if not terrain_map_path.exists():
        print(f"Terrain map not found: {terrain_map_path}", file=sys.stderr)
        return 1
    if not panel_path.exists():
        print(f"Panel not found: {panel_path}", file=sys.stderr)
        return 1

    defaults = resolve_defaults(terrain_map_path)
    km_start = args.km_start if args.km_start is not None else defaults.get("km_start", 0.5)
    km_end = args.km_end if args.km_end is not None else defaults.get("km_end", 43.0)
    output_path = args.output if args.output.is_absolute() else BASE_DIR / args.output
    matrix_path = args.matrix_output if args.matrix_output.is_absolute() else BASE_DIR / args.matrix_output
    report_path = args.report_json if args.report_json.is_absolute() else BASE_DIR / args.report_json
    qc_path = args.qc_png if args.qc_png.is_absolute() else BASE_DIR / args.qc_png

    if defaults:
        if args.output == DEFAULT_OUTPUT and "output" in defaults:
            output_path = defaults["output"]
        if args.matrix_output == DEFAULT_MATRIX_OUTPUT and "matrix_output" in defaults:
            matrix_path = defaults["matrix_output"]
        if args.report_json == DEFAULT_REPORT and "report" in defaults:
            report_path = defaults["report"]
        if args.qc_png == DEFAULT_QC_PNG and "qc_png" in defaults:
            qc_path = defaults["qc_png"]

    terrain_map = load_terrain_map(terrain_map_path)
    panel = pd.read_parquet(panel_path)
    kinematics_config = load_subject_kinematics_config()

    explicit = [d.strip() for d in args.cohort_donors.split(",") if d.strip()]
    strict = args.strict_reference_elite and not args.allow_interim_cohort
    donors, cohort_label, cohort_warnings = select_cohort_donors(
        panel,
        cohort_mode=args.cohort_mode,
        explicit_donors=explicit or None,
        reference_prefix=args.reference_prefix,
        strict_reference_elite=strict,
    )

    cohort = prepare_cohort_frame(
        panel,
        terrain_map,
        donors=donors,
        session_type=args.session_type or None,
        km_start=km_start,
        km_end=km_end,
        kinematics_config=kinematics_config,
        locked_gold_only=not args.include_variance_gaps,
    )

    matrix, lookups = build_baseline_matrix(cohort, min_samples=args.min_cell_samples)
    course_grid = build_course_grid(
        panel,
        terrain_map,
        cohort,
        lookups,
        donors=donors,
        session_type=args.session_type or None,
        km_start=km_start,
        km_end=km_end,
        kinematics_config=kinematics_config,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    matrix_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    course_grid.to_parquet(output_path, index=False)
    matrix.to_parquet(matrix_path, index=False)

    def _rel(path: Path) -> str:
        try:
            return str(path.relative_to(BASE_DIR))
        except ValueError:
            return str(path)

    corridor = terrain_map.get("corridor") or {}
    fallback_counts = course_grid["fallback_level"].value_counts().to_dict() if not course_grid.empty else {}
    report = {
        "schema_version": "baseline_ti_v0",
        "generated_at": _utc_now(),
        "spec_ref": "friction_index_spec.md §7 C2",
        "terrain_map": _rel(terrain_map_path),
        "panel": _rel(panel_path),
        "km_start": km_start,
        "km_end": km_end,
        "session_type": args.session_type,
        "cohort_mode": args.cohort_mode,
        "cohort_label": cohort_label,
        "cohort_donors": donors,
        "cohort_warnings": cohort_warnings,
        "cohort_rows": int(len(cohort)),
        "cohort_ti_median": float(cohort["ti"].median()),
        "course_metres": int(len(course_grid)),
        "matrix_cells": int(len(matrix)),
        "fallback_level_counts": fallback_counts,
        "tier_band_qc": tier_band_qc(matrix),
        "output_parquet": _rel(output_path),
        "matrix_parquet": _rel(matrix_path),
        "race_id": corridor.get("race_id"),
        "sector_id": corridor.get("sector_id"),
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if not args.no_qc:
        render_qc_plot(course_grid, matrix, qc_path, km_start=km_start, km_end=km_end)
        report["qc_png"] = _rel(qc_path)

    print(f"OK cohort donors: {', '.join(donors)} ({cohort_label})")
    if cohort_warnings:
        for w in cohort_warnings:
            print(f"WARN {w}", file=sys.stderr)
    print(f"OK course grid: {len(course_grid)} m → {output_path}")
    print(f"OK matrix: {len(matrix)} cells → {matrix_path}")
    print(f"OK report → {report_path}")
    if not args.no_qc:
        print(f"OK QC → {qc_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
