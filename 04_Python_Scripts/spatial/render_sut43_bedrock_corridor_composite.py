#!/usr/bin/env python3
"""
Composite bedrock corridor figure — HITL basemap + shared-km elevation and delta-TI profiles.

Stack:
  1. Kartverket topo + operator gold track + bedrock corridor highlight
  2. Elevation (m) vs course km (Subject_A race spine)
  3. Paired delta-TI gap (Subject_A − Subject_B) vs course km

Usage (repo root):
    python3 04_Python_Scripts/spatial/render_sut43_bedrock_corridor_composite.py

    ./04_Python_Scripts/spatial/export_bedrock_corridor_composite.sh
"""

from __future__ import annotations

import argparse
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

from spatial.corridor_scope import (  # noqa: E402
    SUT43_DALSNUTEN_GRAMSTAD_VIEWPORT_KM,
    SUT43_DALSNUTEN_SUMMIT_KM,
    SUT43_PRIMARY_KM_END,
)
from spatial.render_sut43_bedrock_corridor_basemap import (  # noqa: E402
    BEDROCK_CORRIDOR_KM,
    CORRIDOR_HIGHLIGHT_COLOR,
    CORRIDOR_HIGHLIGHT_EDGE,
    DEFAULT_VIEWPORT_KM,
    plot_corridor_slice_highlight,
)
from spatial.render_sut43_gramstad_trf_blog import load_paired_gap_frame  # noqa: E402
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
    filter_map_track_panel,
    operator_gold_assigned_spans,
    render_dashboard_legend,
    render_reference_map,
    resolve_axis_label,
    verify_png_export,
    _map_subplot_target_aspect,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_PANEL = BASE_DIR / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "panel_race_1m_spine.parquet"
DEFAULT_SPINE_DIR = BASE_DIR / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "race_trf_spine"
DEFAULT_TERRAIN_MAP = BASE_DIR / "config" / "spatial_terrain_map_sut43.json"
VIS_DIR = BASE_DIR / "06_Visualizations"
DEFAULT_OUTPUT = VIS_DIR / "sut43_bedrock_corridor_composite.png"

# Geographic Dalsnuten summit (Garmin marker 25) — race_corridors.json dalsnuten_summit.
DALSENUTEN_SUMMIT_KM = SUT43_DALSNUTEN_SUMMIT_KM
GRAMSTAD_BAND_END_KM = SUT43_PRIMARY_KM_END  # 41.0
DEFAULT_GRAMSTAD_BLOG_VIEWPORT_KM = SUT43_DALSNUTEN_GRAMSTAD_VIEWPORT_KM
DEFAULT_BLOG_BASEMAP: BasemapChoice = "carto_nolabels"
DEFAULT_BLOG_MAP_KM_STEP = 5.0

BG = "#0A0A0A"
PANEL = "#111111"
TEXT = "#E0E0E0"
GRID = "#333333"
GAP_COLOR = "#EF5350"


def _style_axis(ax: plt.Axes) -> None:
    ax.set_facecolor(PANEL)
    ax.tick_params(colors=TEXT)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.grid(color=GRID, linestyle="--", alpha=0.35)


def plot_corridor_km_band(
    ax: plt.Axes,
    corridor_km: tuple[float, float],
    *,
    km_lo: float,
    km_hi: float,
    label: bool = False,
) -> None:
    """Orange km window band on profile axes (shared with Fig 4 styling)."""
    c_lo, c_hi = corridor_km
    ax.axvspan(c_lo, c_hi, color=CORRIDOR_HIGHLIGHT_COLOR, alpha=0.12, zorder=0)
    ax.axvline(c_lo, color=CORRIDOR_HIGHLIGHT_EDGE, linestyle="--", linewidth=0.9, alpha=0.85)
    ax.axvline(c_hi, color=CORRIDOR_HIGHLIGHT_EDGE, linestyle="--", linewidth=0.9, alpha=0.85)
    ax.set_xlim(km_lo, km_hi)
    if label:
        ax.text(
            (c_lo + c_hi) / 2,
            0.97,
            "corridor slice",
            transform=ax.get_xaxis_transform(),
            color=CORRIDOR_HIGHLIGHT_COLOR,
            fontsize=8,
            ha="center",
            va="top",
        )


def build_elevation_profile(
    panel: pd.DataFrame,
    km_lo: float,
    km_hi: float,
    *,
    map_track_activity: str | None = DEFAULT_SUT43_RACE_ACTIVITY_ID,
    map_track_donor: str | None = DEFAULT_SUT43_MAP_TRACK_DONOR,
) -> pd.DataFrame:
    """Median elevation by course km on the canonical race map track."""
    work = filter_map_track_panel(
        panel,
        activity_id=map_track_activity,
        donor_id=map_track_donor,
        session_type="race",
    )
    if work.empty or "altitude_m" not in work.columns:
        return pd.DataFrame(columns=["course_km", "altitude_m"])
    sub = work[(work["course_km"] >= km_lo) & (work["course_km"] <= km_hi)].copy()
    sub["course_km"] = pd.to_numeric(sub["course_km"], errors="coerce")
    sub["altitude_m"] = pd.to_numeric(sub["altitude_m"], errors="coerce")
    sub = sub.dropna(subset=["course_km", "altitude_m"])
    if sub.empty:
        return pd.DataFrame(columns=["course_km", "altitude_m"])
    return (
        sub.groupby("course_km", as_index=False)["altitude_m"]
        .median()
        .sort_values("course_km")
    )


def build_delta_ti_gap_profile(
    paired: pd.DataFrame,
    km_lo: float,
    km_hi: float,
    *,
    rolling_m: int = 75,
) -> pd.DataFrame:
    """Rolling median paired delta-TI gap (Subject_A − Subject_B) by course km."""
    work = paired.copy()
    work["course_km"] = pd.to_numeric(work["course_km"], errors="coerce")
    work["delta_ti_gap"] = pd.to_numeric(work["delta_ti_gap"], errors="coerce")
    work = work.dropna(subset=["course_km", "delta_ti_gap"])
    work = work[(work["course_km"] >= km_lo) & (work["course_km"] <= km_hi)].sort_values("course_km")
    if work.empty:
        return pd.DataFrame(columns=["course_km", "gap_smooth"])
    work["gap_smooth"] = (
        work["delta_ti_gap"]
        .rolling(window=rolling_m, center=True, min_periods=max(10, rolling_m // 5))
        .median()
    )
    return work.dropna(subset=["gap_smooth"])


def render_bedrock_corridor_composite(
    terrain_map: dict[str, Any],
    panel: pd.DataFrame,
    paired: pd.DataFrame,
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
    rolling_m: int = 75,
    show_map_km_markers: bool = True,
    show_fit_track_caption: bool = True,
    map_km_marker_step_km: float | None = None,
    viewport_label: str | None = None,
) -> Path:
    """Basemap + elevation + paired delta-TI gap on a shared course-km axis."""
    panel = normalize_panel_axes(panel)
    plt.style.use("dark_background")
    v_lo, v_hi = viewport_km
    c_lo, c_hi = corridor_km

    elev = build_elevation_profile(
        panel,
        v_lo,
        v_hi,
        map_track_activity=map_track_activity,
        map_track_donor=map_track_donor,
    )
    gap = build_delta_ti_gap_profile(paired, v_lo, v_hi, rolling_m=rolling_m)
    if elev.empty:
        raise ValueError(f"No elevation metres in viewport km {v_lo}–{v_hi}")
    if gap.empty:
        raise ValueError(f"No paired delta-TI gap metres in viewport km {v_lo}–{v_hi}")
    gap_lo = float(gap["course_km"].min())
    if gap_lo > v_lo + 0.15:
        raise ValueError(
            f"Paired delta-TI gap starts at km {gap_lo:.2f} but viewport begins at km {v_lo:.2f}. "
            "Re-run cross-athlete TRF from Dalsnuten: "
            "./04_Python_Scripts/spatial/compute_trf_race_sut43.sh --spine-only "
            "(requires config/spatial_terrain_map_sut43_full.json for km 25–29)."
        )

    assigned_spans = collect_decision_assigned_spans(terrain_map, km_lo=v_lo, km_hi=v_hi)
    gold_spans = operator_gold_assigned_spans(terrain_map, v_lo, v_hi)
    n_gold = len(gold_spans)
    n_f3 = sum(1 for s in gold_spans if str(s.get("friction_tier", "")).upper() == "F3")

    fig = plt.figure(figsize=(DECISION_FIG_WIDTH_IN, 13.5), facecolor=BG)
    gs = fig.add_gridspec(
        3,
        2,
        height_ratios=[2.35, 0.95, 0.95],
        width_ratios=[5.75, 0.38],
        hspace=0.28,
        wspace=0.08,
    )
    ax_map = fig.add_subplot(gs[0, 0])
    ax_legend = fig.add_subplot(gs[0, 1])
    ax_elev = fig.add_subplot(gs[1, 0])
    ax_gap = fig.add_subplot(gs[2, 0], sharex=ax_elev)

    title = viewport_label or (
        f"Bedrock corridor composite — operator gold (km {c_lo:.2f}–{c_hi:.2f}; mixed grade)"
    )
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
        show_map_km_markers=show_map_km_markers,
        show_fit_track_caption=show_fit_track_caption,
        map_km_marker_step_km=map_km_marker_step_km,
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
            "S4/F3 bedrock band (operator lock)\n"
            "mixed grade — climb, roll, and descent",
            transform=ax_legend.transAxes,
            ha="left",
            va="bottom",
            fontsize=8.0,
            color="#FFE0B2",
            linespacing=1.35,
            bbox=dict(boxstyle="round,pad=0.35", facecolor=(0, 0, 0, 0.45), edgecolor=CORRIDOR_HIGHLIGHT_EDGE),
        )

    plot_corridor_km_band(ax_elev, corridor_km, km_lo=v_lo, km_hi=v_hi)
    if abs(v_lo - DALSENUTEN_SUMMIT_KM) < 0.05:
        ax_elev.axvline(
            DALSENUTEN_SUMMIT_KM,
            color="#9E9E9E",
            linestyle=":",
            linewidth=0.9,
            alpha=0.75,
            zorder=1,
        )
        ax_elev.text(
            DALSENUTEN_SUMMIT_KM,
            0.04,
            "Dalsnuten summit",
            transform=ax_elev.get_xaxis_transform(),
            ha="left",
            va="bottom",
            fontsize=7.5,
            color="#B0BEC5",
        )
    ax_elev.plot(elev["course_km"], elev["altitude_m"], color="#00E5FF", linewidth=1.6, zorder=3)
    ax_elev.set_ylabel("Elevation (m)", color=TEXT)
    ax_elev.set_title("Course profile — Subject_A race spine", color=TEXT, fontsize=10, pad=6)
    _style_axis(ax_elev)
    plt.setp(ax_elev.get_xticklabels(), visible=False)

    plot_corridor_km_band(ax_gap, corridor_km, km_lo=v_lo, km_hi=v_hi, label=True)
    ax_gap.axhline(0, color="#888888", linewidth=1, zorder=1)
    ax_gap.plot(gap["course_km"], gap["gap_smooth"], color=GAP_COLOR, linewidth=2.0, zorder=3)
    ax_gap.fill_between(
        gap["course_km"],
        0,
        gap["gap_smooth"],
        where=gap["gap_smooth"] > 0,
        color=GAP_COLOR,
        alpha=0.18,
        zorder=2,
    )
    ymax = float(np.nanpercentile(gap["gap_smooth"].abs(), 99)) * 1.25
    ymax = max(ymax, 0.5)
    ax_gap.set_ylim(-ymax, ymax)
    ax_gap.set_ylabel("ΔTI gap (A − B)", color=TEXT)
    ax_gap.set_xlabel("Course km (gramstad_band)", color=TEXT)
    ax_gap.set_title(
        f"Paired training residual gap — rolling median ({rolling_m} m)",
        color=TEXT,
        fontsize=10,
        pad=6,
    )
    _style_axis(ax_gap)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=FIG_DPI, facecolor=fig.get_facecolor())
    plt.close(fig)
    if verify_export:
        verify_png_export(output_path)
    return output_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bedrock corridor composite — basemap + elevation + delta-TI.")
    parser.add_argument("--terrain-map", type=Path, default=DEFAULT_TERRAIN_MAP)
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--spine-dir", type=Path, default=DEFAULT_SPINE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--gpx", type=Path, default=DEFAULT_SUT43_GPX)
    parser.add_argument("--activity", type=str, default=DEFAULT_SUT43_RACE_ACTIVITY_ID)
    parser.add_argument("--map-track-donor", type=str, default=DEFAULT_SUT43_MAP_TRACK_DONOR)
    parser.add_argument("--viewport-km", type=float, nargs=2, metavar=("LO", "HI"), default=DEFAULT_VIEWPORT_KM)
    parser.add_argument("--corridor-km", type=float, nargs=2, metavar=("LO", "HI"), default=BEDROCK_CORRIDOR_KM)
    parser.add_argument("--rolling-m", type=int, default=75)
    parser.add_argument(
        "--basemap",
        choices=[
            "topo_standard",
            "topo_grayscale",
            "satellite_flyfoto",
            "kartverket-topo",
            "kartverket-gray",
            "opentopomap",
            "carto_nolabels",
            "blog_grey",
        ],
        default=DEFAULT_BASEMAP_LAYER,
    )
    parser.add_argument(
        "--blog-style",
        action="store_true",
        help="Dalsnuten summit (km 25) → Gramstad end (km 41); grey no-label basemap; map km labels every 5 km.",
    )
    parser.add_argument("--show-map-km-markers", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument(
        "--map-km-marker-step",
        type=float,
        default=None,
        metavar="KM",
        help="Map course-km labels every N km (skips 100 m ticks); blog-style default 5.",
    )
    parser.add_argument("--no-require-basemap", action="store_true")
    parser.add_argument("--verify-export", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    terrain_path = args.terrain_map if args.terrain_map.is_absolute() else BASE_DIR / args.terrain_map
    panel_path = args.panel if args.panel.is_absolute() else BASE_DIR / args.panel
    spine_dir = args.spine_dir if args.spine_dir.is_absolute() else BASE_DIR / args.spine_dir
    out_path = args.output if args.output.is_absolute() else BASE_DIR / args.output
    gpx_path = args.gpx if args.gpx.is_absolute() else BASE_DIR / args.gpx

    if not terrain_path.exists():
        raise FileNotFoundError(f"Terrain map not found: {terrain_path}")
    if not panel_path.exists():
        raise FileNotFoundError(f"Panel not found: {panel_path}")

    terrain_map = load_terrain_map(terrain_path)
    panel = normalize_panel_axes(pd.read_parquet(panel_path))
    paired = load_paired_gap_frame(spine_dir)
    gpx = gpx_path if gpx_path.exists() else None

    viewport = (float(args.viewport_km[0]), float(args.viewport_km[1]))
    basemap = args.basemap
    show_map_km_markers = args.show_map_km_markers
    map_km_marker_step_km = args.map_km_marker_step
    viewport_label: str | None = None
    if args.blog_style:
        viewport = DEFAULT_GRAMSTAD_BLOG_VIEWPORT_KM
        basemap = DEFAULT_BLOG_BASEMAP
        if show_map_km_markers is None:
            show_map_km_markers = True
        if map_km_marker_step_km is None:
            map_km_marker_step_km = DEFAULT_BLOG_MAP_KM_STEP
        viewport_label = (
            f"Dalsnuten summit → Gramstad band — bedrock corridor km {BEDROCK_CORRIDOR_KM[0]:.2f}–"
            f"{BEDROCK_CORRIDOR_KM[1]:.2f}"
        )
    if show_map_km_markers is None:
        show_map_km_markers = True

    path = render_bedrock_corridor_composite(
        terrain_map,
        panel,
        paired,
        output_path=out_path,
        viewport_km=viewport,
        corridor_km=(float(args.corridor_km[0]), float(args.corridor_km[1])),
        gpx_path=gpx,
        map_track_activity=args.activity,
        map_track_donor=args.map_track_donor,
        basemap=basemap,
        require_basemap=not args.no_require_basemap,
        verify_export=args.verify_export,
        rolling_m=int(args.rolling_m),
        show_map_km_markers=show_map_km_markers,
        show_fit_track_caption=False if args.blog_style else show_map_km_markers,
        map_km_marker_step_km=map_km_marker_step_km,
        viewport_label=viewport_label,
    )
    print(f"OK bedrock corridor composite → {path.relative_to(BASE_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
