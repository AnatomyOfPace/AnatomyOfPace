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
from spatial.spatial_align import (  # noqa: E402
    aligned_parquet_path,
    panel_parquet_path,
    resample_to_grid_1m,
)
from spatial.spatial_hitl_overlay import load_terrain_map  # noqa: E402
from spatial.validation_dashboard import operator_gold_class_at_km  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CORRIDOR_ID = "stavanger_halvmarathon_course"
DEFAULT_PANEL = panel_parquet_path(corridor_id=DEFAULT_CORRIDOR_ID)
DEFAULT_TERRAIN_MAP = BASE_DIR / "config" / "spatial_terrain_map_stavanger_halvmarathon.json"
DEFAULT_OUTPUT = BASE_DIR / "06_Visualizations" / "stavanger_halvmarathon_race_compare.png"
DEFAULT_JSON = BASE_DIR / "03_Processed_Data" / "spatial" / "stavanger_halvmarathon_race_compare.json"
DEFAULT_KM_WINDOW = (0.0, 21.38)

COMPARE_COLS = ("speed_mps", "ti", "heart_rate", "cadence_spm", "grade_pct", "altitude_m")


def _resolve_km_window(terrain_map: dict[str, Any], km_window: tuple[float, float] | None) -> tuple[float, float]:
    if km_window is not None:
        return km_window
    corridor = terrain_map.get("corridor") or {}
    km_lo = float(corridor.get("km_start", DEFAULT_KM_WINDOW[0]))
    km_hi = float(corridor.get("km_end", DEFAULT_KM_WINDOW[1]))
    return km_lo, km_hi


def _load_panel_activity(panel_path: Path, activity_id: str, km_lo: float, km_hi: float) -> pd.DataFrame | None:
    if not panel_path.is_file():
        return None
    panel = pd.read_parquet(panel_path)
    if "activity_id" not in panel.columns:
        return None
    sub = panel.loc[panel["activity_id"] == activity_id].copy()
    if sub.empty:
        return None
    sub["course_km"] = pd.to_numeric(sub["course_km"], errors="coerce")
    return sub.loc[(sub["course_km"] >= km_lo) & (sub["course_km"] <= km_hi + 1e-9)].copy()


def _load_aligned_activity(
    donor_id: str,
    activity_id: str,
    *,
    corridor_id: str,
    km_lo: float,
    km_hi: float,
) -> pd.DataFrame | None:
    path = aligned_parquet_path(donor_id, activity_id, corridor_id=corridor_id, session_type="race")
    if not path.is_file():
        return None
    frame = pd.read_parquet(path)
    frame["course_km"] = pd.to_numeric(frame["course_km"], errors="coerce")
    return frame.loc[(frame["course_km"] >= km_lo) & (frame["course_km"] <= km_hi + 1e-9)].copy()


def _load_compare_frame(
    donor_id: str,
    activity_id: str,
    *,
    corridor_id: str,
    panel_path: Path,
    km_lo: float,
    km_hi: float,
    prefer_panel: bool,
) -> tuple[pd.DataFrame, str]:
    if prefer_panel:
        panel_frame = _load_panel_activity(panel_path, activity_id, km_lo, km_hi)
        if panel_frame is not None and not panel_frame.empty:
            return panel_frame, "panel_1m"
        aligned = _load_aligned_activity(
            donor_id, activity_id, corridor_id=corridor_id, km_lo=km_lo, km_hi=km_hi
        )
        if aligned is not None and not aligned.empty:
            return aligned, "aligned_parquet"

    raw = read_parquet(donor_id, activity_id)
    return resample_to_grid_1m(raw, km_lo, km_hi), "resample_to_grid_1m"


def _prepare_compare_grid(frame: pd.DataFrame, km_lo: float, km_hi: float) -> pd.DataFrame:
    """Ensure activity telemetry sits on the corridor 1 m interpolation grid."""
    if "course_m" in frame.columns:
        course_m = pd.to_numeric(frame["course_m"], errors="coerce")
        expected = float(int((km_hi - km_lo) * 1000.0) + 1)
        if course_m.notna().sum() >= expected * 0.95:
            out = frame.copy()
            out["course_km"] = pd.to_numeric(out["course_km"], errors="coerce")
            return out.loc[(out["course_km"] >= km_lo) & (out["course_km"] <= km_hi + 1e-9)].copy()
    return resample_to_grid_1m(frame, km_lo, km_hi)


def _series_or_empty(frame: pd.DataFrame, col: str) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[col], errors="coerce")


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
    km_window: tuple[float, float] | None = None,
    source_a: str = "unknown",
    source_b: str = "unknown",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    km_lo, km_hi = _resolve_km_window(terrain_map, km_window)
    a = _prepare_compare_grid(frame_a, km_lo, km_hi)
    b = _prepare_compare_grid(frame_b, km_lo, km_hi)

    rename_a = {c: f"{c}_{label_a}" for c in COMPARE_COLS if c in a.columns}
    rename_b = {c: f"{c}_{label_b}" for c in COMPARE_COLS if c in b.columns}
    paired = a.rename(columns=rename_a).merge(
        b.rename(columns=rename_b),
        on=["course_m", "course_km"],
        how="inner",
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
        "compare_window_km": [round(km_lo, 3), round(km_hi, 3)],
        "grid_metres": int((km_hi - km_lo) * 1000.0) + 1,
        "overlap_metres": int(len(paired)),
        "tier_assigned_metres": int(tiered.sum()),
        "substrate_band_metres": int(sum(row["metres"] for row in substrate_bands)),
        "source_a": source_a,
        "source_b": source_b,
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
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL, help="Dual-activity panel parquet (preferred)")
    parser.add_argument("--corridor-id", default=DEFAULT_CORRIDOR_ID)
    parser.add_argument("--raw-parquet", action="store_true", help="Skip panel/aligned parquets; resample washed micro frames")
    parser.add_argument("--terrain-map", type=Path, default=DEFAULT_TERRAIN_MAP)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    terrain_path = args.terrain_map if args.terrain_map.is_absolute() else BASE_DIR / args.terrain_map
    terrain_map = load_terrain_map(terrain_path)
    panel_path = args.panel if args.panel.is_absolute() else BASE_DIR / args.panel
    km_lo, km_hi = _resolve_km_window(terrain_map, None)

    frame_a, source_a = _load_compare_frame(
        args.donor,
        args.activity_a,
        corridor_id=args.corridor_id,
        panel_path=panel_path,
        km_lo=km_lo,
        km_hi=km_hi,
        prefer_panel=not args.raw_parquet,
    )
    frame_b, source_b = _load_compare_frame(
        args.donor,
        args.activity_b,
        corridor_id=args.corridor_id,
        panel_path=panel_path,
        km_lo=km_lo,
        km_hi=km_hi,
        prefer_panel=not args.raw_parquet,
    )
    paired, report = compare_races(
        frame_a,
        frame_b,
        terrain_map,
        label_a=args.label_a,
        label_b=args.label_b,
        source_a=source_a,
        source_b=source_b,
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
    print(f"    source {args.label_a}: {report.get('source_a')} · {args.label_b}: {report.get('source_b')}")
    print(
        f"    overlap {report['overlap_metres']} m / grid {report['grid_metres']} m · "
        f"substrate bands {report.get('substrate_band_metres')} m"
    )
    if report["overlap_metres"] < int(report["grid_metres"] * 0.9):
        print(
            "    WARN: overlap <90% of corridor grid — rebuild panel: "
            "./04_Python_Scripts/spatial/compare_stavanger_halvmarathon_races.sh",
            file=sys.stderr,
        )
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
