#!/usr/bin/env python3
"""
HITL-style basemap — operator-defined bedrock corridor slice (SUT_43 gramstad_band).

Overlays operator gold S4/F3 locks on Kartverket topo (validation_dashboard decision-mode
styling) and highlights the TRF corridor telemetric window km 31.08–33.80.

Usage (repo root):
    python3 04_Python_Scripts/spatial/render_sut43_bedrock_corridor_basemap.py

    ./04_Python_Scripts/spatial/export_bedrock_corridor_basemap.sh
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.reproject_to_spine import normalize_panel_axes  # noqa: E402
from spatial.spatial_hitl_overlay import load_terrain_map  # noqa: E402
from spatial.validation_dashboard import (  # noqa: E402
    DEFAULT_BASEMAP_LAYER,
    DEFAULT_SUT43_GPX,
    DEFAULT_SUT43_MAP_TRACK_DONOR,
    DEFAULT_SUT43_RACE_ACTIVITY_ID,
    DECISION_FIG_WIDTH_IN,
    FIG_DPI,
    BasemapChoice,
    build_activity_track_geography,
    collect_decision_assigned_spans,
    corridor_geography_label,
    operator_gold_assigned_spans,
    render_dashboard_legend,
    render_reference_map,
    resolve_axis_label,
    verify_png_export,
    _interp_latlon_at_km,
    _map_subplot_target_aspect,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_PANEL = BASE_DIR / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "panel_race_1m_spine.parquet"
DEFAULT_TERRAIN_MAP = BASE_DIR / "config" / "spatial_terrain_map_sut43.json"
VIS_DIR = BASE_DIR / "06_Visualizations"
DEFAULT_OUTPUT = VIS_DIR / "sut43_bedrock_corridor_hitl_basemap.png"

# TRF telemetric corridor slice (F3 · downhill · hike top cell span).
BEDROCK_CORRIDOR_KM: tuple[float, float] = (31.08, 33.80)
# Map viewport — padded context around operator bedrock + late_braking band.
DEFAULT_VIEWPORT_KM: tuple[float, float] = (30.35, 34.35)

CORRIDOR_HIGHLIGHT_COLOR = "#FFB74D"
CORRIDOR_HIGHLIGHT_EDGE = "#FF9800"
CORRIDOR_TRACK_LW = 7.5
CORRIDOR_TRACK_ZORDER = 9


def plot_corridor_slice_highlight(
    ax: plt.Axes,
    track_geo: pd.DataFrame,
    corridor_km: tuple[float, float],
    *,
    pad_m: float = 75.0,
) -> bool:
    """Orange bbox + thick track emphasis for the TRF corridor slice on the basemap."""
    if track_geo.empty:
        return False
    c_lo, c_hi = corridor_km
    corridor_geo = track_geo[
        (track_geo["course_km"] >= c_lo) & (track_geo["course_km"] <= c_hi)
    ].dropna(subset=["latitude", "longitude"])
    if corridor_geo.empty:
        return False

    ax.plot(
        corridor_geo["longitude"],
        corridor_geo["latitude"],
        color=CORRIDOR_HIGHLIGHT_COLOR,
        linewidth=CORRIDOR_TRACK_LW,
        alpha=0.55,
        solid_capstyle="round",
        zorder=CORRIDOR_TRACK_ZORDER,
    )

    center_lat = float(corridor_geo["latitude"].mean())
    lon_m_per_deg = 111_320.0 * max(np.cos(np.radians(center_lat)), 1e-6)
    pad_lon = pad_m / lon_m_per_deg
    pad_lat = pad_m / 111_320.0
    west = float(corridor_geo["longitude"].min()) - pad_lon
    east = float(corridor_geo["longitude"].max()) + pad_lon
    south = float(corridor_geo["latitude"].min()) - pad_lat
    north = float(corridor_geo["latitude"].max()) + pad_lat
    rect = Rectangle(
        (west, south),
        east - west,
        north - south,
        fill=True,
        facecolor=CORRIDOR_HIGHLIGHT_COLOR,
        edgecolor=CORRIDOR_HIGHLIGHT_EDGE,
        linewidth=2.2,
        linestyle="--",
        alpha=0.14,
        zorder=CORRIDOR_TRACK_ZORDER - 1,
    )
    ax.add_patch(rect)

    for km_mark, ha in ((c_lo, "left"), (c_hi, "right")):
        pt = _interp_latlon_at_km(track_geo, km_mark)
        if pt is None:
            continue
        lat, lon = pt
        label = f"km {km_mark:.2f}"
        text = ax.text(
            lon,
            lat,
            label,
            ha=ha,
            va="bottom",
            fontsize=7.5,
            color="#FFF3E0",
            zorder=CORRIDOR_TRACK_ZORDER + 2,
        )
        text.set_path_effects([pe.withStroke(linewidth=1.4, foreground="#111111", alpha=0.9)])

    mid_km = (c_lo + c_hi) / 2.0
    mid_pt = _interp_latlon_at_km(track_geo, mid_km)
    if mid_pt is not None:
        lat, lon = mid_pt
        banner = ax.text(
            lon,
            lat,
            "corridor slice\nS4/F3 bedrock",
            ha="center",
            va="center",
            fontsize=8.0,
            color="#FFE0B2",
            zorder=CORRIDOR_TRACK_ZORDER + 3,
        )
        banner.set_path_effects([pe.withStroke(linewidth=1.6, foreground="#111111", alpha=0.92)])
    return True


def render_bedrock_corridor_basemap(
    terrain_map: dict[str, Any],
    panel: pd.DataFrame,
    *,
    output_path: Path,
    viewport_km: tuple[float, float] = DEFAULT_VIEWPORT_KM,
    corridor_km: tuple[float, float] = BEDROCK_CORRIDOR_KM,
    gpx_path: Path | None = DEFAULT_SUT43_GPX,
    map_track_activity: str | None = DEFAULT_SUT43_RACE_ACTIVITY_ID,
    map_track_donor: str | None = DEFAULT_SUT43_MAP_TRACK_DONOR,
    basemap: BasemapChoice = DEFAULT_BASEMAP_LAYER,
    require_basemap: bool = True,
    verify_export: bool = False,
) -> Path:
    """Map-only HITL export — operator gold on topo with corridor slice highlight."""
    panel = normalize_panel_axes(panel)
    plt.style.use("dark_background")
    v_lo, v_hi = viewport_km
    c_lo, c_hi = corridor_km

    assigned_spans = collect_decision_assigned_spans(
        terrain_map,
        km_lo=v_lo,
        km_hi=v_hi,
    )
    gold_spans = operator_gold_assigned_spans(terrain_map, v_lo, v_hi)
    n_gold = len(gold_spans)
    n_f3 = sum(1 for s in gold_spans if str(s.get("friction_tier", "")).upper() == "F3")

    fig_w = DECISION_FIG_WIDTH_IN
    fig_h = 9.5
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor="#0A0A0A")
    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[5.75, 0.38],
        wspace=0.08,
    )
    ax_map = fig.add_subplot(gs[0, 0])
    ax_legend = fig.add_subplot(gs[0, 1])

    title = f"Bedrock corridor — operator gold (km {c_lo:.2f}–{c_hi:.2f})"
    fig.suptitle(title, color="white", fontsize=14, fontweight="bold", y=0.98)
    place = corridor_geography_label(terrain_map)
    axis_label = resolve_axis_label(terrain_map, panel)
    subtitle_bits = [
        p
        for p in (
            place,
            axis_label,
            f"viewport km {v_lo:.1f}–{v_hi:.1f}",
            f"{n_gold} operator gold spans ({n_f3} F3)",
        )
        if p
    ]
    if subtitle_bits:
        fig.text(0.5, 0.955, " · ".join(subtitle_bits), ha="center", va="top", color="#B0BEC5", fontsize=9)

    map_aspect = _map_subplot_target_aspect(decision_mode=True, with_cluster_ti=False, with_locomotion_strip=False)
    _, ml_map_drawn, assigned_map_drawn = render_reference_map(
        ax_map,
        panel,
        terrain_map,
        viewport_km=viewport_km,
        chunk_km=viewport_km,
        gpx_path=gpx_path,
        basemap=basemap,
        ml_pred_df=None,
        decision_mode=True,
        assigned_spans=assigned_spans,
        map_track_activity=map_track_activity,
        map_track_donor=map_track_donor,
        map_display_aspect=map_aspect,
        require_basemap=require_basemap,
    )

    track_geo = build_activity_track_geography(
        panel,
        v_lo,
        v_hi,
        activity_id=map_track_activity,
        donor_id=map_track_donor,
        session_type="race",
    )
    corridor_drawn = plot_corridor_slice_highlight(ax_map, track_geo, corridor_km)

    render_dashboard_legend(
        ax_legend,
        decision_mode=True,
        show_assigned_map_track=assigned_map_drawn,
        show_ml_map_track=ml_map_drawn,
    )
    if corridor_drawn:
        ax_legend.text(
            0.02,
            0.02,
            f"TRF corridor slice km {c_lo:.2f}–{c_hi:.2f}\n"
            "S4/F3 bedrock descent (operator lock)",
            transform=ax_legend.transAxes,
            ha="left",
            va="bottom",
            fontsize=8.5,
            color="#FFE0B2",
            linespacing=1.35,
            bbox=dict(boxstyle="round,pad=0.35", facecolor=(0, 0, 0, 0.45), edgecolor=CORRIDOR_HIGHLIGHT_EDGE),
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=FIG_DPI, facecolor=fig.get_facecolor())
    plt.close(fig)
    if verify_export:
        verify_png_export(output_path)
    return output_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HITL basemap — operator bedrock corridor slice on Kartverket topo."
    )
    parser.add_argument("--terrain-map", type=Path, default=DEFAULT_TERRAIN_MAP)
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--gpx", type=Path, default=DEFAULT_SUT43_GPX)
    parser.add_argument("--activity", type=str, default=DEFAULT_SUT43_RACE_ACTIVITY_ID)
    parser.add_argument("--map-track-donor", type=str, default=DEFAULT_SUT43_MAP_TRACK_DONOR)
    parser.add_argument(
        "--viewport-km",
        type=float,
        nargs=2,
        metavar=("LO", "HI"),
        default=DEFAULT_VIEWPORT_KM,
    )
    parser.add_argument(
        "--corridor-km",
        type=float,
        nargs=2,
        metavar=("LO", "HI"),
        default=BEDROCK_CORRIDOR_KM,
    )
    parser.add_argument(
        "--basemap",
        choices=["topo_standard", "topo_grayscale", "satellite_flyfoto", "kartverket-topo", "kartverket-gray", "opentopomap"],
        default=DEFAULT_BASEMAP_LAYER,
    )
    parser.add_argument("--no-require-basemap", action="store_true", help="Allow export without tile fetch (tests).")
    parser.add_argument("--verify-export", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    terrain_path = args.terrain_map if args.terrain_map.is_absolute() else BASE_DIR / args.terrain_map
    panel_path = args.panel if args.panel.is_absolute() else BASE_DIR / args.panel
    out_path = args.output if args.output.is_absolute() else BASE_DIR / args.output
    gpx_path = args.gpx if args.gpx.is_absolute() else BASE_DIR / args.gpx

    if not terrain_path.exists():
        raise FileNotFoundError(f"Terrain map not found: {terrain_path}")
    if not panel_path.exists():
        raise FileNotFoundError(
            f"Panel not found: {panel_path}. Build panel_race_1m_spine.parquet before export."
        )

    terrain_map = load_terrain_map(terrain_path)
    panel = normalize_panel_axes(pd.read_parquet(panel_path))
    gpx = gpx_path if gpx_path.exists() else None

    path = render_bedrock_corridor_basemap(
        terrain_map,
        panel,
        output_path=out_path,
        viewport_km=(float(args.viewport_km[0]), float(args.viewport_km[1])),
        corridor_km=(float(args.corridor_km[0]), float(args.corridor_km[1])),
        gpx_path=gpx,
        map_track_activity=args.activity,
        map_track_donor=args.map_track_donor,
        basemap=args.basemap,
        require_basemap=not args.no_require_basemap,
        verify_export=args.verify_export,
    )
    print(f"OK bedrock corridor basemap → {path.relative_to(BASE_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
