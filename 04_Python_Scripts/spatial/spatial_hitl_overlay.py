#!/usr/bin/env python3
"""
Phase D (legacy) — simple HITL visualization for spatial terrain map QC.

Prefer validation_dashboard.py for v2.0 (variance flags + ΔTI row + override protocol).
This module renders a three-row elevation / TI / surface-class draft overlay.

Manual overrides are applied by editing config/spatial_terrain_map.json
(hitl.manual_overrides[]) — this script does not mutate cluster output.

Usage:
    python3 04_Python_Scripts/spatial/spatial_hitl_overlay.py \\
        --terrain-map config/spatial_terrain_map.json \\
        --panel 03_Processed_Data/spatial/dale_to_paradisskaret_stress_test/panel_1m.parquet \\
        --output 06_Visualizations/spatial_terrain_hitl_draft.png
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.surface_ontology import SURFACE_CLASS_SPECS

BASE_DIR = Path(__file__).resolve().parent.parent.parent
VIS_DIR = BASE_DIR / "06_Visualizations"

SURFACE_COLORS = {
    "S1": "#FFFFFF",
    "S2": "#D3D3D3",
    "S3": "#7cb342",
    "S4": "#87CEEB",
    "S5": "#ff7043",
    "S6": "#FF00FF",
}


def load_terrain_map(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def segment_span_ax(ax, segments: list[dict], ylo: float, yhi: float) -> None:
    for seg in segments:
        cls = seg.get("surface_class", "S2")
        color = SURFACE_COLORS.get(cls, "#888888")
        km0 = seg.get("course_km_start", seg.get("course_m_start", 0) / 1000.0)
        km1 = seg.get("course_km_end", seg.get("course_m_end", 0) / 1000.0)
        ax.axvspan(km0, km1, alpha=0.18, color=color, label=cls if cls not in ax.get_legend_handles_labels()[1] else None)


def render_hitl_overlay(
    terrain_map: dict,
    panel: pd.DataFrame,
    *,
    output_path: Path,
) -> Path:
    """Three-row HITL draft: elevation, TI/NTI, surface class bands."""
    plt.style.use("dark_background")
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True, facecolor="#0A0A0A")
    fig.suptitle(
        "Spatial Terrain Map — HITL Draft (automated clusters; manual override pending)",
        color="white",
        fontsize=14,
        fontweight="bold",
    )

    work = panel.sort_values("course_m")
    km = work["course_km"] if "course_km" in work.columns else work["course_m"] / 1000.0
    segments = terrain_map.get("segments", [])

    # Panel 1 — elevation
    ax0 = axes[0]
    if "altitude_m" in work.columns:
        elev = work.groupby("course_km", as_index=False)["altitude_m"].median()
        ax0.plot(elev["course_km"], elev["altitude_m"], color="#00E5FF", linewidth=1.2)
    ax0.set_ylabel("Elevation (m)", color="#A0A0A0")
    segment_span_ax(ax0, segments, 0, 1)
    ax0.grid(color="#2A2A2A", linestyle="--", alpha=0.6)

    # Panel 2 — TI by donor
    ax1 = axes[1]
    if "ti" in work.columns and "donor_id" in work.columns:
        for donor, sub in work.groupby("donor_id"):
            med = sub.groupby("course_km", as_index=False)["ti"].median()
            ax1.plot(med["course_km"], med["ti"], linewidth=1.0, alpha=0.85, label=donor)
    ax1.axhline(1.0, color="#666", linestyle=":", linewidth=0.8)
    ax1.set_ylabel("TI", color="#A0A0A0")
    ax1.legend(loc="upper right", fontsize=8)
    segment_span_ax(ax1, segments, 0, 1)
    ax1.grid(color="#2A2A2A", linestyle="--", alpha=0.6)

    # Panel 3 — surface class step plot
    ax2 = axes[2]
    class_to_y = {cid: i for i, cid in enumerate(SURFACE_CLASS_SPECS)}
    for seg in segments:
        cls = seg.get("surface_class", "S2")
        km0 = seg.get("course_km_start", 0)
        km1 = seg.get("course_km_end", km0)
        y = class_to_y.get(cls, 1)
        ax2.fill_between([km0, km1], y - 0.35, y + 0.35, color=SURFACE_COLORS.get(cls, "#888"), alpha=0.7)
        ax2.text((km0 + km1) / 2, y, cls, ha="center", va="center", fontsize=8, color=("#1a1a1a" if cls == "S1" else "white"))
    ax2.set_yticks(list(class_to_y.values()))
    ax2.set_yticklabels(list(class_to_y.keys()))
    ax2.set_xlabel("Course km (SUT_160)", color="#A0A0A0")
    ax2.set_ylabel("Surface class", color="#A0A0A0")
    ax2.set_xlim(
        terrain_map.get("corridor", {}).get("km_start", km.min()),
        terrain_map.get("corridor", {}).get("km_end", km.max()),
    )
    ax2.grid(color="#2A2A2A", linestyle="--", alpha=0.6)

    cci = terrain_map.get("calibration_credibility_index", {}).get("index")
    if cci is not None:
        fig.text(
            0.02,
            0.02,
            f"Calibration credibility index: {cci:.3f} | HITL status: {terrain_map.get('hitl', {}).get('status', 'draft')}",
            color="#888",
            fontsize=9,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="#0A0A0A")
    plt.close(fig)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase D (legacy) — simple HITL terrain map overlay")
    parser.add_argument(
        "--terrain-map",
        type=Path,
        default=BASE_DIR / "config" / "spatial_terrain_map.json",
    )
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=VIS_DIR / "spatial_terrain_hitl_draft.png",
    )
    args = parser.parse_args()

    tmap_path = args.terrain_map if args.terrain_map.is_absolute() else BASE_DIR / args.terrain_map
    panel_path = args.panel if args.panel.is_absolute() else BASE_DIR / args.panel
    out_path = args.output if args.output.is_absolute() else BASE_DIR / args.output

    if not tmap_path.exists():
        raise FileNotFoundError(
            f"Terrain map not found: {tmap_path}. Run terrain_map_gen.py first."
        )

    terrain_map = load_terrain_map(tmap_path)
    panel = pd.read_parquet(panel_path)
    path = render_hitl_overlay(terrain_map, panel, output_path=out_path)
    print(f"OK HITL overlay → {path.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()
