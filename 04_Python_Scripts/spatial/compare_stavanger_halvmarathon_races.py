#!/usr/bin/env python3
"""
Year-over-year compare — Stavanger Halvmarathon race streams (Subject_A).

Aligns two washed micro parquets on shared stream course_km (0 → min race length)
and reports pace, TI, HR, and substrate-band deltas using operator gold tiers.

Usage (repo root, after wash both FITs):
    python3 04_Python_Scripts/spatial/compare_stavanger_halvmarathon_races.py

    python3 04_Python_Scripts/spatial/compare_stavanger_halvmarathon_races.py \\
        --activity-a Stavanger_Halvmarathon_20250830 \\
        --activity-b Stavanger_Halvmarathon_20260829 \\
        --label-a 2025 --label-b 2026
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from fit_micro.activity_frame import read_parquet  # noqa: E402
from spatial.compute_training_residual import resolve_friction_tiers  # noqa: E402
from spatial.spatial_hitl_overlay import load_terrain_map  # noqa: E402
from spatial.validation_dashboard import operator_gold_class_at_km  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_TERRAIN_MAP = BASE_DIR / "config" / "spatial_terrain_map_stavanger_halvmarathon.json"
DEFAULT_OUTPUT = BASE_DIR / "06_Visualizations" / "stavanger_halvmarathon_race_compare.png"
DEFAULT_JSON = BASE_DIR / "03_Processed_Data" / "spatial" / "stavanger_halvmarathon_race_compare.json"

COMPARE_COLS = ("speed_mps", "ti", "heart_rate", "cadence_spm", "grade_pct", "altitude_m")


def _resample_1m(frame: pd.DataFrame) -> pd.DataFrame:
    """Median telemetry on 1 m course_km bins."""
    work = frame.copy()
    if "course_km" not in work.columns:
        raise ValueError("course_km missing — re-wash with --project-course --race stavanger_halvmarathon")
    work["course_km"] = pd.to_numeric(work["course_km"], errors="coerce")
    work = work.dropna(subset=["course_km"])
    work["course_m"] = (work["course_km"] * 1000.0).round().astype(int)
    if "grade_pct" not in work.columns and "grade" in work.columns:
        work["grade_pct"] = pd.to_numeric(work["grade"], errors="coerce")
    agg: dict[str, Any] = {}
    for col in COMPARE_COLS:
        if col in work.columns:
            agg[col] = "median"
    if not agg:
        raise ValueError("No comparable telemetry columns in activity frame")
    out = work.groupby("course_m", as_index=False).agg(agg)
    out["course_km"] = out["course_m"] / 1000.0
    return out.sort_values("course_km")


def _series_or_empty(frame: pd.DataFrame, col: str) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[col], errors="coerce")


def _align_on_course_grid(a: pd.DataFrame, b: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    """Reindex both 1 m frames onto shared stream course_m (0 … km_hi)."""
    km_hi = min(float(a["course_km"].max()), float(b["course_km"].max()))
    grid = pd.DataFrame(
        {
            "course_m": np.arange(0, int(km_hi * 1000.0) + 1, dtype=int),
        }
    )
    grid["course_km"] = grid["course_m"] / 1000.0
    a_cols = [c for c in a.columns if c not in {"course_km"}]
    b_cols = [c for c in b.columns if c not in {"course_km"}]
    a_grid = grid.merge(a[a_cols], on="course_m", how="left")
    b_grid = grid.merge(b[b_cols], on="course_m", how="left")
    return a_grid, b_grid, km_hi


def _race_summary(frame: pd.DataFrame, label: str) -> dict[str, Any]:
    km = frame["course_km"]
    speed = _series_or_empty(frame, "speed_mps")
    ti = _series_or_empty(frame, "ti")
    hr = _series_or_empty(frame, "heart_rate")
    valid_speed = speed[speed > 0.3]
    pace_min_km = float((1000.0 / valid_speed.median() / 60.0)) if not valid_speed.empty else None
    return {
        "label": label,
        "km_start": round(float(km.min()), 3),
        "km_end": round(float(km.max()), 3),
        "distance_km": round(float(km.max() - km.min()), 3),
        "median_speed_mps": round(float(valid_speed.median()), 3) if not valid_speed.empty else None,
        "median_pace_min_per_km": round(pace_min_km, 2) if pace_min_km else None,
        "median_ti": round(float(ti.median()), 3) if ti.notna().any() else None,
        "median_hr_bpm": round(float(hr.median()), 1) if hr.notna().any() else None,
    }


def _substrate_breakdown(
    paired: pd.DataFrame,
    terrain_map: dict[str, Any],
    *,
    label_a: str,
    label_b: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tier in ("F0", "F1", "F2", "F3", "F4"):
        mask = paired["friction_tier"] == tier
        if not mask.any():
            continue
        sub = paired.loc[mask]
        spd_a = pd.to_numeric(sub[f"speed_mps_{label_a}"], errors="coerce")
        spd_b = pd.to_numeric(sub[f"speed_mps_{label_b}"], errors="coerce")
        ti_a = pd.to_numeric(sub[f"ti_{label_a}"], errors="coerce")
        ti_b = pd.to_numeric(sub[f"ti_{label_b}"], errors="coerce")
        rows.append(
            {
                "friction_tier": tier,
                "surface_class_mode": paired.loc[mask, "surface_class"].mode().iloc[0]
                if "surface_class" in paired.columns and mask.any()
                else None,
                "metres": int(mask.sum()),
                f"median_speed_mps_{label_a}": round(float(spd_a.median()), 3) if spd_a.notna().any() else None,
                f"median_speed_mps_{label_b}": round(float(spd_b.median()), 3) if spd_b.notna().any() else None,
                f"delta_speed_mps": round(float(spd_b.median() - spd_a.median()), 3)
                if spd_a.notna().any() and spd_b.notna().any()
                else None,
                f"median_ti_{label_a}": round(float(ti_a.median()), 3) if ti_a.notna().any() else None,
                f"median_ti_{label_b}": round(float(ti_b.median()), 3) if ti_b.notna().any() else None,
                f"delta_ti": round(float(ti_b.median() - ti_a.median()), 3)
                if ti_a.notna().any() and ti_b.notna().any()
                else None,
            }
        )
    return rows


def compare_races(
    frame_a: pd.DataFrame,
    frame_b: pd.DataFrame,
    terrain_map: dict[str, Any],
    *,
    label_a: str = "2025",
    label_b: str = "2026",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    a = _resample_1m(frame_a)
    b = _resample_1m(frame_b)
    a, b, km_hi = _align_on_course_grid(a, b)

    rename_a = {c: f"{c}_{label_a}" for c in COMPARE_COLS if c in a.columns}
    rename_b = {c: f"{c}_{label_b}" for c in COMPARE_COLS if c in b.columns}
    paired = a.rename(columns=rename_a).merge(
        b.rename(columns=rename_b),
        on=["course_m", "course_km"],
        how="left",
    )
    spd_a = f"speed_mps_{label_a}"
    spd_b = f"speed_mps_{label_b}"
    if spd_a in paired.columns and spd_b in paired.columns:
        valid = (
            pd.to_numeric(paired[spd_a], errors="coerce").gt(0.3)
            & pd.to_numeric(paired[spd_b], errors="coerce").gt(0.3)
        )
        paired = paired.loc[valid].copy()
    if paired.empty:
        raise ValueError("No overlapping course metres with speed in both races after 1 m grid align")

    paired["surface_class"] = paired["course_km"].apply(
        lambda km: operator_gold_class_at_km(terrain_map, float(km))
    )
    tier_df = resolve_friction_tiers(
        paired.rename(columns={"course_km": "course_km"}),
        terrain_map,
    )
    paired["friction_tier"] = tier_df["friction_tier"].values

    if f"speed_mps_{label_a}" in paired.columns and f"speed_mps_{label_b}" in paired.columns:
        paired["delta_speed_mps"] = (
            pd.to_numeric(paired[f"speed_mps_{label_b}"], errors="coerce")
            - pd.to_numeric(paired[f"speed_mps_{label_a}"], errors="coerce")
        )
    if f"ti_{label_a}" in paired.columns and f"ti_{label_b}" in paired.columns:
        paired["delta_ti"] = (
            pd.to_numeric(paired[f"ti_{label_b}"], errors="coerce")
            - pd.to_numeric(paired[f"ti_{label_a}"], errors="coerce")
        )

    tiered = paired["friction_tier"].notna()
    substrate_bands = _substrate_breakdown(paired, terrain_map, label_a=label_a, label_b=label_b)
    report: dict[str, Any] = {
        "race_id": "stavanger_halvmarathon",
        "donor_id": "Subject_A",
        "compare_window_km": [0.0, round(km_hi, 3)],
        "grid_metres": int(km_hi * 1000.0) + 1,
        "overlap_metres": int(len(paired)),
        "tier_assigned_metres": int(tiered.sum()),
        "substrate_band_metres": int(sum(row["metres"] for row in substrate_bands)),
        "summary_a": _race_summary(a, label_a),
        "summary_b": _race_summary(b, label_b),
        "substrate_bands": substrate_bands,
    }
    if "delta_speed_mps" in paired.columns:
        d_spd = paired["delta_speed_mps"].dropna()
        report["delta_speed_mps_mean"] = round(float(d_spd.mean()), 4) if not d_spd.empty else None
    if "delta_ti" in paired.columns:
        d_ti = paired["delta_ti"].dropna()
        report["delta_ti_mean"] = round(float(d_ti.mean()), 4) if not d_ti.empty else None
    return paired, report


def render_compare_figure(
    paired: pd.DataFrame,
    report: dict[str, Any],
    *,
    label_a: str,
    label_b: str,
    output_path: Path,
) -> Path:
    plt.style.use("dark_background")
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True, facecolor="#0A0A0A")
    km = paired["course_km"]

    ax0, ax1, ax2 = axes
    col_elev_a = f"altitude_m_{label_a}"
    col_elev_b = f"altitude_m_{label_b}"
    if col_elev_a in paired.columns:
        ax0.plot(km, paired[col_elev_a], color="#90CAF9", linewidth=1.2, label=label_a)
    if col_elev_b in paired.columns:
        ax0.plot(km, paired[col_elev_b], color="#FFE082", linewidth=1.0, alpha=0.85, label=label_b)
    ax0.set_ylabel("Elevation (m)")
    ax0.legend(loc="upper right", fontsize=8)
    ax0.grid(color="#333", linestyle="--", alpha=0.4)

    for col, color in ((f"speed_mps_{label_a}", "#4FC3F7"), (f"speed_mps_{label_b}", "#FFB74D")):
        if col in paired.columns:
            speed = pd.to_numeric(paired[col], errors="coerce")
            pace = speed.apply(lambda s: (1000.0 / s / 60.0) if s and s > 0.3 else np.nan)
            ax1.plot(km, pace, linewidth=1.4 if label_a in col else 1.1, label=col.split("_")[-1], color=color)
    ax1.set_ylabel("Pace (min/km)")
    ax1.invert_yaxis()
    ax1.legend(loc="upper right", fontsize=8)
    ax1.grid(color="#333", linestyle="--", alpha=0.4)

    for col, color in ((f"ti_{label_a}", "#81C784"), (f"ti_{label_b}", "#FF8A65")):
        if col in paired.columns:
            ax2.plot(km, paired[col], linewidth=1.4 if label_a in col else 1.1, label=col.split("_")[-1], color=color)
    if "delta_ti" in paired.columns:
        ax2_t = ax2.twinx()
        ax2_t.plot(km, paired["delta_ti"], color="#F48FB1", linewidth=0.9, alpha=0.7, label=f"ΔTI ({label_b}−{label_a})")
        ax2_t.axhline(0, color="#666", linewidth=0.8)
        ax2_t.set_ylabel(f"ΔTI ({label_b} − {label_a})", color="#F48FB1")
    ax2.set_ylabel("Terrain index")
    ax2.set_xlabel("Stream course km (operator gold axis — 2025 calibration)")
    ax2.legend(loc="upper left", fontsize=8)
    ax2.grid(color="#333", linestyle="--", alpha=0.4)

    sa = report["summary_a"]
    sb = report["summary_b"]
    title = (
        f"Stavanger Halvmarathon — {label_a} vs {label_b} · "
        f"pace {sa.get('median_pace_min_per_km')} vs {sb.get('median_pace_min_per_km')} min/km · "
        f"TI {sa.get('median_ti')} vs {sb.get('median_ti')}"
    )
    fig.suptitle(title, fontsize=11, color="white", y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two Stavanger Halvmarathon race streams.")
    parser.add_argument("--donor", default="Subject_A")
    parser.add_argument("--activity-a", default="Stavanger_Halvmarathon_20250830")
    parser.add_argument("--activity-b", default="Stavanger_Halvmarathon_20260829")
    parser.add_argument("--label-a", default="2025")
    parser.add_argument("--label-b", default="2026")
    parser.add_argument("--terrain-map", type=Path, default=DEFAULT_TERRAIN_MAP)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    terrain_path = args.terrain_map if args.terrain_map.is_absolute() else BASE_DIR / args.terrain_map
    terrain_map = load_terrain_map(terrain_path)

    frame_a = read_parquet(args.donor, args.activity_a)
    frame_b = read_parquet(args.donor, args.activity_b)
    paired, report = compare_races(
        frame_a,
        frame_b,
        terrain_map,
        label_a=args.label_a,
        label_b=args.label_b,
    )
    report["activity_a"] = args.activity_a
    report["activity_b"] = args.activity_b

    out_png = args.output if args.output.is_absolute() else BASE_DIR / args.output
    render_compare_figure(paired, report, label_a=args.label_a, label_b=args.label_b, output_path=out_png)

    out_json = args.json if args.json.is_absolute() else BASE_DIR / args.json
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"OK compare → {out_png.relative_to(BASE_DIR)}")
    print(f"    report → {out_json.relative_to(BASE_DIR)}")
    print(
        f"    {args.label_a}: {report['summary_a']['distance_km']} km, "
        f"pace {report['summary_a']['median_pace_min_per_km']} min/km, "
        f"TI {report['summary_a']['median_ti']}"
    )
    print(
        f"    {args.label_b}: {report['summary_b']['distance_km']} km, "
        f"pace {report['summary_b']['median_pace_min_per_km']} min/km, "
        f"TI {report['summary_b']['median_ti']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
