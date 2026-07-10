#!/usr/bin/env python3
"""
Ghost-safe blog figures — SUT_43 gramstad_band paired TRF (Subject_A vs Subject_B).

Outputs to 06_Visualizations/ (clinical IDs only; no personal names).

Usage (repo root):
    python3 04_Python_Scripts/spatial/render_sut43_gramstad_trf_blog.py

    python3 04_Python_Scripts/spatial/render_sut43_gramstad_trf_blog.py \\
        --gramstad-dir 03_Processed_Data/spatial/sut43_terrain_ontology/race_trf_gramstad \\
        --full-dir 03_Processed_Data/spatial/sut43_terrain_ontology/race_trf_full
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
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_GRAMSTAD_DIR = (
    BASE_DIR / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "race_trf_gramstad"
)
DEFAULT_FULL_DIR = (
    BASE_DIR / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "race_trf_full"
)
DEFAULT_SPINE_DIR = (
    BASE_DIR / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "race_trf_spine"
)
DEFAULT_TERRAIN_MAP = BASE_DIR / "config" / "spatial_terrain_map_sut43.json"
VIS_DIR = BASE_DIR / "06_Visualizations"

TIER_COLORS = {
    "F0": "#9E9E9E",
    "F1": "#66BB6A",
    "F2": "#42A5F5",
    "F3": "#FFA726",
    "F4": "#EF5350",
    None: "#444444",
}
BG = "#0A0A0A"
PANEL = "#111111"
TEXT = "#E0E0E0"
GRID = "#333333"


def _load_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing TRF report: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _find_cell(
    report: dict[str, Any],
    *,
    friction_tier: str,
    grade_band: str,
    locomotion_mode: str,
) -> dict[str, Any] | None:
    for cell in report.get("cells") or []:
        if (
            cell.get("friction_tier") == friction_tier
            and cell.get("grade_band") == grade_band
            and cell.get("locomotion_mode") == locomotion_mode
        ):
            return cell
    return None


def _cell_delta(cell: dict[str, Any] | None) -> float | None:
    if not cell:
        return None
    val = cell.get("delta_ti_mean")
    return float(val) if val is not None else None


def load_paired_gap_frame(spine_dir: Path) -> pd.DataFrame:
    """Load metre-level delta-TI gap (Subject_A - Subject_B) on ref_chainage_m."""
    spine_dir = spine_dir if spine_dir.is_absolute() else BASE_DIR / spine_dir
    paired_path = spine_dir / "cross_athlete_trf_paired.parquet"
    if paired_path.exists():
        return pd.read_parquet(paired_path)

    a_path = spine_dir / "training_residual_Subject_A.parquet"
    b_path = spine_dir / "training_residual_Subject_B.parquet"
    if not a_path.exists() or not b_path.exists():
        raise FileNotFoundError(
            f"Missing paired gap data in {spine_dir.relative_to(BASE_DIR)}. "
            "Run compute_trf_race_sut43.sh --cross-athlete first."
        )
    a = pd.read_parquet(a_path)
    b = pd.read_parquet(b_path)
    if "in_trf_exclusion" in a.columns:
        a = a.loc[~a["in_trf_exclusion"]]
        b = b.loc[~b["in_trf_exclusion"]]
    if "ref_chainage_m" in a.columns:
        a = a.drop_duplicates(subset=["ref_chainage_m"], keep="last")
        b = b.drop_duplicates(subset=["ref_chainage_m"], keep="last")
    join_cols = ["ref_chainage_m", "course_km"]
    paired = a[join_cols + ["delta_ti"]].merge(
        b[join_cols + ["delta_ti"]],
        on=join_cols,
        how="inner",
        suffixes=("_a", "_b"),
    )
    paired["delta_ti_gap"] = paired["delta_ti_a"] - paired["delta_ti_b"]
    return paired


def render_delta_ti_gap_spine(
    paired: pd.DataFrame,
    *,
    km_start: float = 29.0,
    km_end: float = 39.5,
    corridor_km: tuple[float, float] = (31.08, 33.80),
    rolling_m: int = 75,
    output_path: Path,
) -> Path:
    """Figure 4 — paired delta-TI gap (A - B) along gramstad spine with corridor markers."""
    work = paired.copy()
    work["course_km"] = pd.to_numeric(work["course_km"], errors="coerce")
    work["delta_ti_gap"] = pd.to_numeric(work["delta_ti_gap"], errors="coerce")
    work = work.dropna(subset=["course_km", "delta_ti_gap"])
    work = work[(work["course_km"] >= km_start) & (work["course_km"] <= km_end)].sort_values("course_km")
    if work.empty:
        raise ValueError(f"No paired gap metres in km {km_start}–{km_end}")

    work["gap_smooth"] = (
        work["delta_ti_gap"].rolling(window=rolling_m, center=True, min_periods=max(10, rolling_m // 5)).median()
    )
    plot_df = work.dropna(subset=["gap_smooth"])

    fig, ax = plt.subplots(figsize=(12, 3.8))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)

    c_lo, c_hi = corridor_km
    ax.axvspan(c_lo, c_hi, color="#FFA726", alpha=0.12, zorder=0)
    ax.axvline(c_lo, color="#FFA726", linestyle="--", linewidth=0.9, alpha=0.85)
    ax.axvline(c_hi, color="#FFA726", linestyle="--", linewidth=0.9, alpha=0.85)
    ax.axhline(0, color="#888888", linewidth=1, zorder=1)

    ax.plot(
        plot_df["course_km"],
        plot_df["gap_smooth"],
        color="#EF5350",
        linewidth=2.0,
        label="Rolling median gap (A − B)",
        zorder=3,
    )
    ax.fill_between(
        plot_df["course_km"],
        0,
        plot_df["gap_smooth"],
        where=plot_df["gap_smooth"] > 0,
        color="#EF5350",
        alpha=0.18,
        zorder=2,
    )

    ax.set_xlim(km_start, km_end)
    ymax = float(np.nanpercentile(plot_df["gap_smooth"].abs(), 99)) * 1.25
    ymax = max(ymax, 0.5)
    ax.set_ylim(-ymax, ymax)
    ax.set_xlabel("Course km (gramstad_band)", color=TEXT)
    ax.set_ylabel("delta-TI gap (A − B)", color=TEXT)
    ax.set_title(
        "Paired residual gap along spine — corridor slice highlighted",
        color=TEXT,
        fontsize=11,
        pad=8,
    )
    ax.text(
        (c_lo + c_hi) / 2,
        ymax * 0.92,
        "corridor slice",
        color="#FFB74D",
        fontsize=8,
        ha="center",
    )
    ax.tick_params(colors=TEXT)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.legend(loc="upper right", fontsize=8, framealpha=0.2, labelcolor=TEXT)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


def render_friction_strip(
    terrain_map_path: Path,
    *,
    km_start: float = 29.0,
    km_end: float = 39.5,
    output_path: Path,
) -> Path:
    """Figure 1 — locked friction tiers along course km."""
    reg = json.loads(terrain_map_path.read_text(encoding="utf-8"))
    spans = (reg.get("hitl") or {}).get("operator_gold_spans") or []
    rows = [
        s
        for s in spans
        if float(s["course_km_end"]) > km_start and float(s["course_km_start"]) < km_end
    ]
    rows.sort(key=lambda s: float(s["course_km_start"]))

    fig, ax = plt.subplots(figsize=(12, 2.2))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)

    y0, bar_h = 0.35, 0.3
    for span in rows:
        lo = max(km_start, float(span["course_km_start"]))
        hi = min(km_end, float(span["course_km_end"]))
        if hi <= lo:
            continue
        tier = span.get("friction_tier")
        color = TIER_COLORS.get(tier, TIER_COLORS[None])
        ax.barh(y0, hi - lo, left=lo, height=bar_h, color=color, edgecolor=GRID, linewidth=0.5)

    for km_mark, label in (
        (31.0, "bedrock onset"),
        (33.2, "late_braking"),
        (34.0, ""),
        (39.14, "asphalt"),
    ):
        if km_start <= km_mark <= km_end:
            ax.axvline(km_mark, color="#888888", linestyle="--", linewidth=0.8, alpha=0.7)
            if label:
                ax.text(km_mark, 0.78, label, color=TEXT, fontsize=8, ha="center", rotation=0)

    ax.set_xlim(km_start, km_end)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Course km (SUT_43 gramstad_band)", color=TEXT)
    ax.set_yticks([])
    ax.set_title(
        "Locked friction tiers — gramstad_band (operator gold)",
        color=TEXT,
        fontsize=11,
        pad=8,
    )
    patches = [
        mpatches.Patch(color=TIER_COLORS[t], label=t) for t in ("F0", "F1", "F2", "F3", "F4")
    ]
    ax.legend(handles=patches, loc="upper right", fontsize=7, framealpha=0.2, labelcolor=TEXT)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.tick_params(colors=TEXT)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


def render_dilution_figure(
    full_report_a: dict[str, Any],
    gramstad_report_a: dict[str, Any],
    output_path: Path,
) -> Path:
    """Figure 2 — F3 downhill hike ΔTI: full race vs gramstad window."""
    key = ("F3", "downhill", "hike")
    full_cell = _find_cell(full_report_a, friction_tier=key[0], grade_band=key[1], locomotion_mode=key[2])
    gram_cell = _find_cell(
        gramstad_report_a, friction_tier=key[0], grade_band=key[1], locomotion_mode=key[2]
    )
    vals = [_cell_delta(full_cell), _cell_delta(gram_cell)]
    labels = ["Full race\nkm 0.5–43", "Gramstad\nkm 29–41"]
    colors = ["#FFB74D" if (v or 0) > 0 else "#66BB6A" for v in vals]

    fig, ax = plt.subplots(figsize=(6, 4))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)
    bars = ax.bar(labels, [v or 0 for v in vals], color=colors, edgecolor=GRID)
    ax.axhline(0, color="#888888", linewidth=1)
    ax.set_ylabel("ΔTI vs cohort median", color=TEXT)
    ax.set_title(
        "Subject_A — F3 · downhill · hike\n(window dilution)",
        color=TEXT,
        fontsize=11,
    )
    for bar, val in zip(bars, vals):
        if val is None:
            continue
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + (0.02 if val >= 0 else -0.06),
            f"{val:+.3f}",
            ha="center",
            color=TEXT,
            fontsize=10,
        )
    ax.tick_params(colors=TEXT)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


def render_paired_figure(
    report_a: dict[str, Any],
    report_b: dict[str, Any],
    output_path: Path,
) -> Path:
    """Figure 3 — paired ΔTI by cell key (gramstad window)."""
    cell_specs = [
        ("F3", "downhill", "hike"),
        ("F3", "uphill", "hike"),
        ("F2", "downhill", "hike"),
        ("F4", "downhill", "hike"),
    ]
    labels = [f"{t} · {g} · {m}" for t, g, m in cell_specs]

    vals_a, vals_b = [], []
    for t, g, m in cell_specs:
        vals_a.append(_cell_delta(_find_cell(report_a, friction_tier=t, grade_band=g, locomotion_mode=m)))
        vals_b.append(_cell_delta(_find_cell(report_b, friction_tier=t, grade_band=g, locomotion_mode=m)))

    y_pos = range(len(cell_specs))
    height = 0.35
    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)

    for i, (va, vb) in enumerate(zip(vals_a, vals_b)):
        if va is not None:
            ax.barh(i + height / 2, va, height=height, color="#EF5350" if va > 0 else "#66BB6A", label="Subject_A" if i == 0 else "")
        if vb is not None:
            ax.barh(i - height / 2, vb, height=height, color="#42A5F5" if vb > 0 else "#26A69A", label="Subject_B" if i == 0 else "")

    ax.axvline(0, color="#888888", linewidth=1)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(labels, color=TEXT, fontsize=9)
    ax.set_xlabel("ΔTI vs cohort median (km 29–41)", color=TEXT)
    ax.set_title("Paired training residual — gramstad_band", color=TEXT, fontsize=11)
    ax.legend(loc="lower right", fontsize=8, framealpha=0.2, labelcolor=TEXT)
    ax.tick_params(colors=TEXT)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render ghost-safe SUT_43 gramstad TRF blog figures.")
    parser.add_argument("--gramstad-dir", type=Path, default=DEFAULT_GRAMSTAD_DIR)
    parser.add_argument("--spine-dir", type=Path, default=DEFAULT_SPINE_DIR)
    parser.add_argument("--full-dir", type=Path, default=DEFAULT_FULL_DIR)
    parser.add_argument("--terrain-map", type=Path, default=DEFAULT_TERRAIN_MAP)
    parser.add_argument("--output-dir", type=Path, default=VIS_DIR)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    gramstad_dir = args.gramstad_dir if args.gramstad_dir.is_absolute() else BASE_DIR / args.gramstad_dir
    spine_dir = args.spine_dir if args.spine_dir.is_absolute() else BASE_DIR / args.spine_dir
    full_dir = args.full_dir if args.full_dir.is_absolute() else BASE_DIR / args.full_dir
    terrain_map = args.terrain_map if args.terrain_map.is_absolute() else BASE_DIR / args.terrain_map
    out_dir = args.output_dir if args.output_dir.is_absolute() else BASE_DIR / args.output_dir

    report_a_g = _load_report(gramstad_dir / "training_residual_report_Subject_A.json")
    report_b_g = _load_report(gramstad_dir / "training_residual_report_Subject_B.json")

    paths = []
    paths.append(
        render_friction_strip(
            terrain_map,
            output_path=out_dir / "sut43_gramstad_friction_strip_blog.png",
        )
    )
    print(f"  Fig 1 → {paths[-1].relative_to(BASE_DIR)}")

    full_a_path = full_dir / "training_residual_report_Subject_A.json"
    if full_a_path.exists():
        report_a_f = _load_report(full_a_path)
        paths.append(
            render_dilution_figure(
                report_a_f,
                report_a_g,
                out_dir / "sut43_trf_dilution_blog.png",
            )
        )
        print(f"  Fig 2 → {paths[-1].relative_to(BASE_DIR)}")
    else:
        print(f"  SKIP Fig 2 — missing {full_a_path.relative_to(BASE_DIR)}", file=sys.stderr)

    paths.append(
        render_paired_figure(
            report_a_g,
            report_b_g,
            out_dir / "sut43_gramstad_paired_trf_blog.png",
        )
    )
    print(f"  Fig 3 → {paths[-1].relative_to(BASE_DIR)}")

    paired_path = spine_dir / "cross_athlete_trf_paired.parquet"
    fallback_a = spine_dir / "training_residual_Subject_A.parquet"
    if paired_path.exists() or fallback_a.exists():
        try:
            paired = load_paired_gap_frame(spine_dir)
            paths.append(
                render_delta_ti_gap_spine(
                    paired,
                    output_path=out_dir / "sut43_trf_delta_gap_spine_blog.png",
                )
            )
            print(f"  Fig 4 → {paths[-1].relative_to(BASE_DIR)}")
        except (FileNotFoundError, ValueError) as exc:
            print(f"  SKIP Fig 4 — {exc}", file=sys.stderr)
    else:
        print(
            f"  SKIP Fig 4 — missing {spine_dir.relative_to(BASE_DIR)}/cross_athlete_trf_paired.parquet",
            file=sys.stderr,
        )

    print("OK blog figures rendered (ghost-safe clinical IDs).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
