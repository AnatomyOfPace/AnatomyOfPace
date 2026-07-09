#!/usr/bin/env python3
"""
Print structured QC review for SUT_43 Baseline TI build output.

Usage (repo root):
    python3 04_Python_Scripts/spatial/review_baseline_ti_qc.py
    python3 04_Python_Scripts/spatial/review_baseline_ti_qc.py \\
        --report 07_ML_Models/spatial/baseline_ti_sut43_full_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.build_baseline_ti import BASE_DIR, DEFAULT_MATRIX_OUTPUT, DEFAULT_OUTPUT, DEFAULT_REPORT  # noqa: E402
from spatial.suggest_gold_spans import FRICTION_TI_BANDS  # noqa: E402

PASS_DELTA = 0.20  # flag if |median - band centre| exceeds this (spec §8 diagnostic)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _tier_table() -> str:
    lines = ["F-tier TI bands (friction_index_spec §3):"]
    for tier, lo, hi in FRICTION_TI_BANDS:
        centre = (lo + hi) / 2.0
        lines.append(f"  {tier}: [{lo:.2f}, {hi:.2f}]  centre={centre:.2f}")
    return "\n".join(lines)


def review(
    report: dict,
    grid: pd.DataFrame,
    matrix: pd.DataFrame,
) -> int:
    """Print review; return exit code 0 pass, 1 if tier-band flags."""
    print("=" * 60)
    print("SUT_43 Baseline TI QC review")
    print("=" * 60)
    print(f"cohort_label:    {report.get('cohort_label')}")
    print(f"cohort_donors:   {report.get('cohort_donors')}")
    print(f"cohort_warnings: {report.get('cohort_warnings') or 'none'}")
    print(f"course_metres:   {report.get('course_metres')}")
    print(f"matrix_cells:    {report.get('matrix_cells')}")
    print(f"cohort_rows:     {report.get('cohort_rows')}")
    print(f"cohort_ti_med:   {report.get('cohort_ti_median'):.3f}" if report.get("cohort_ti_median") else "")
    print()

    print(_tier_table())
    print()

    print("--- Tier-band QC (tier_only matrix cells) ---")
    flags = 0
    for row in report.get("tier_band_qc") or []:
        tier = row["friction_tier"]
        med = row["baseline_ti_median"]
        lo, hi = row["tier_band_lo"], row["tier_band_hi"]
        inside = row.get("inside_band")
        delta = row.get("delta_from_centre", 0)
        n = row.get("n_samples", 0)
        status = "PASS" if inside else "FAIL"
        if not inside or (delta and delta > PASS_DELTA):
            flags += 1
            status = "FLAG"
        print(
            f"  {tier}: median={med:.3f}  band=[{lo:.2f},{hi:.2f}]  "
            f"Δcentre={delta:.3f}  n={n}  [{status}]"
        )
    print()

    print("--- Fallback level counts (course grid) ---")
    for level, count in sorted((report.get("fallback_level_counts") or {}).items()):
        pct = 100.0 * count / max(len(grid), 1)
        print(f"  {level}: {count} m ({pct:.1f}%)")
    print()

    if "fallback_level" in grid.columns and "friction_tier" in grid.columns:
        print("--- Metres by F-tier × fallback (top cells) ---")
        cross = (
            grid.groupby(["friction_tier", "fallback_level"], observed=True)
            .size()
            .reset_index(name="metres")
            .sort_values("metres", ascending=False)
        )
        for row in cross.head(12).itertuples(index=False):
            print(f"  {row.friction_tier} / {row.fallback_level}: {row.metres} m")
        print()

    if {"baseline_ti", "ti_observed_median"}.issubset(grid.columns):
        diff = (grid["ti_observed_median"] - grid["baseline_ti"]).dropna()
        print("--- Cohort TI vs baseline (course grid) ---")
        print(f"  mean(ti_obs - baseline): {diff.mean():+.3f}")
        print(f"  median(ti_obs - baseline): {diff.median():+.3f}")
        print(f"  p95 |delta|: {diff.abs().quantile(0.95):.3f}")
        print()

    if not matrix.empty:
        print("--- Matrix coverage (by fallback_level) ---")
        for level in matrix["fallback_level"].value_counts().index:
            print(f"  {level}: {int((matrix['fallback_level'] == level).sum())} cells")
        print()

    print("--- PNG checklist (06_Visualizations/sut43_baseline_ti_qc.png) ---")
    print("  Panel 1: baseline_ti (blue) vs cohort TI median (orange) — should track; large")
    print("           sustained gaps → gold tier or cohort mismatch.")
    print("  Panel 2: F-tier strip — verify transitions match operator gold (e.g. F0 asphalt")
    print("           km 39–42, F3/F4 technical bands).")
    print("  Panel 3: tier bar chart — green bars inside grey band = PASS.")
    print()

    if report.get("cohort_label") == "interim_race_panel":
        print("NOTE: interim_race_panel — Subject_A/B race cohort, not Reference_Elite_*.")
        print("      Tier-band QC validates internal consistency; re-run when reference elite")
        print("      SUT_43 .fit enters panel_full_1m.parquet.")
        print()

    if flags:
        print(f"RESULT: {flags} tier-band FLAG(s) — review operator gold or cohort on those tiers.")
        return 1
    print("RESULT: tier-band QC PASS (all medians inside spec bands).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review Baseline TI QC artifacts.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--grid", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX_OUTPUT)
    args = parser.parse_args(argv)

    report_path = args.report if args.report.is_absolute() else BASE_DIR / args.report
    grid_path = args.grid if args.grid.is_absolute() else BASE_DIR / args.grid
    matrix_path = args.matrix if args.matrix.is_absolute() else BASE_DIR / args.matrix

    for label, path in [("report", report_path), ("grid", grid_path), ("matrix", matrix_path)]:
        if not path.exists():
            print(f"Missing {label}: {path}", file=sys.stderr)
            print("Run: ./04_Python_Scripts/spatial/build_baseline_ti_sut43.sh", file=sys.stderr)
            return 2

    report = _load_json(report_path)
    grid = pd.read_parquet(grid_path)
    matrix = pd.read_parquet(matrix_path)
    return review(report, grid, matrix)


if __name__ == "__main__":
    raise SystemExit(main())
