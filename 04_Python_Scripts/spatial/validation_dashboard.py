#!/usr/bin/env python3
"""
Phase D — validation dashboard for spatial terrain map QC.

Overlays draft S1–S6 segments on elevation, NTI consensus, and ΔTI profiles;
flags high-variance course metres for operator review. Manual class overrides are written to the terrain map JSON via hitl.manual_overrides[].

**TI-band draft:** ``ti_draft_segments[]`` (from ``ti_draft_layer.py``) assigns S-class
from per-metre ``nti_median`` + ``ti_band`` with σ-gating; rendered as a low-alpha
secondary track below GMM ``segments[]`` when ``--ti-draft`` is set or the sidecar is
present. Uses ``nti_median`` (same as hitl_nti_consistency), not IQR-trimmed ``consensus_nti``.

**HITL v1 intent:** per-metre effective class (or ``hitl_v1_effective.parquet``) plus
deferred operator guidance — subtle tint/outline on the draft-class row where v1 ≠ GMM.

This module surfaces draft clusters, variance flags, and the documented override path
for HITL review. Overrides default to **guidance** (annotation layer; cluster draft
remains primary). Set mode **lock** only after explicit QC sign-off — lock overrides
are merged at render time into effective_segments (segments[] in the JSON is not mutated).

Usage:
    python3 04_Python_Scripts/spatial/validation_dashboard.py \\
        --terrain-map config/spatial_terrain_map.json \\
        --panel 03_Processed_Data/spatial/dale_to_paradisskaret_stress_test/panel_1m.parquet \\
        --structural-invoice 03_Processed_Data/spatial/dale_to_paradisskaret_stress_test/structural_invoice.json

    python3 04_Python_Scripts/spatial/validation_dashboard.py \\
        --terrain-map config/spatial_terrain_map.json \\
        --panel .../panel_1m.parquet \\
        --variance-threshold 0.35 \\
        --write-flags config/spatial_validation_flags.json

    python3 04_Python_Scripts/spatial/validation_dashboard.py \\
        --terrain-map config/spatial_terrain_map_sut43.json \\
        --panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_race_1m_spine.parquet \\
        --chunk-km 2 --chunk-index 1 --with-map --decision-mode
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

OverrideMode = Literal["guidance", "lock"]
BasemapLayerId = Literal["topo_standard", "topo_grayscale", "satellite_flyfoto", "carto_nolabels"]
BasemapChoice = BasemapLayerId | Literal["kartverket-topo", "kartverket-gray", "opentopomap", "blog_grey"]
MLPredictionsMode = Literal["full", "loocv", "path"]

import matplotlib

matplotlib.use("Agg")

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from fit_micro.course_project import load_gpx_course_km, load_gpx_latlon, project_course_km
from spatial.corridor_scope import SUT43_PRIMARY_KM_END, SUT43_PRIMARY_KM_START
from spatial.reproject_to_spine import is_spine_panel, normalize_panel_axes, subject_id_column
from spatial.spatial_hitl_overlay import SURFACE_COLORS, load_terrain_map
from spatial.surface_ontology import SURFACE_CLASS_SPECS
from spatial.terrain_map_gen import aggregate_nti_by_course_m, compute_nti
from spatial.ti_draft_layer import DEFERRED_CLASS, build_ti_draft_segments

BASE_DIR = Path(__file__).resolve().parent.parent.parent
VIS_DIR = BASE_DIR / "06_Visualizations"
DEFAULT_SUT43_HITL_DIR = VIS_DIR / "sut43_hitl"
DEFAULT_FLAGS_PATH = BASE_DIR / "config" / "spatial_validation_flags.json"
DEFAULT_SUT43_GPX = BASE_DIR / "02_Raw_Data" / "organiser_gpx" / "COURSE_SUT43_official_2027.gpx"
DEFAULT_SUT43_RACE_ACTIVITY_ID = "SUT43_20260418"
DEFAULT_SUT43_MAP_TRACK_DONOR = "Subject_A"
DEFAULT_ML_FULL_CORRIDOR_PREDICTIONS = (
    BASE_DIR / "07_ML_Models" / "terrain_gb_sut43_full_corridor_predictions.parquet"
)
DEFAULT_ML_LOOCV_PREDICTIONS = (
    BASE_DIR / "07_ML_Models" / "terrain_gb_sut43_loocv_predictions_baseline.parquet"
)
TILE_CACHE_ROOT = BASE_DIR / ".tile_cache"
KARTVERKET_TILE_CACHE = TILE_CACHE_ROOT / "kartverket"
BASEMAP_FETCH_ATTEMPTS = 4
BASEMAP_FETCH_BACKOFF_S = 0.75
BASEMAP_MIN_TILE_STD = 12.0
CHUNK_EXPORT_PAUSE_S = 0.75
KARTVERKET_TOPO_URL = (
    "https://cache.kartverket.no/v1/wmts/1.0.0/topo/default/webmercator/{z}/{y}/{x}.png"
)
KARTVERKET_GRAY_URL = (
    "https://cache.kartverket.no/v1/wmts/1.0.0/topograatone/default/webmercator/{z}/{y}/{x}.png"
)
NIB_ORTHO_WMTS_URL = (
    "https://tilecache.norgeibilder.no/wmts/webmercator?"
    "service=WMTS&request=GetTile&version=1.0.0&layer=nib&style=default&format=image/jpeg"
    "&tileMatrixSet=webmercator&tileMatrix={z}&tileRow={y}&tileCol={x}"
)
KARTVERKET_ATTRIBUTION = "© Kartverket / Geovekst"
NIB_ATTRIBUTION = "© Kartverket / Norge i bilder"
BLOCKED_MARITIME_LAYER_IDS = frozenset(
    {"sjokartraster", "sjokart", "sjøkart", "maritime", "sea_chart"}
)
BASEMAP_LAYER_REGISTRY: dict[BasemapLayerId, dict[str, str]] = {
    "topo_standard": {
        "label": "Kartverket standard topo",
        "url": KARTVERKET_TOPO_URL,
        "attribution": KARTVERKET_ATTRIBUTION,
    },
    "topo_grayscale": {
        "label": "Kartverket greyscale topo",
        "url": KARTVERKET_GRAY_URL,
        "attribution": KARTVERKET_ATTRIBUTION,
    },
    "satellite_flyfoto": {
        "label": "Kartverket orthophoto (flyfoto)",
        "url": NIB_ORTHO_WMTS_URL,
        "attribution": NIB_ATTRIBUTION,
    },
}
HITL_BASEMAP_LAYER_LABELS: dict[BasemapLayerId, str] = {
    "topo_standard": "Standard (topographic)",
    "topo_grayscale": "Greyscale (Gråtone)",
    "satellite_flyfoto": "Satellite (orthophoto)",
}
DEFAULT_BASEMAP_LAYER: BasemapLayerId = "topo_standard"
SCALEBAR_NICE_LENGTHS_M = (
    5.0,
    10.0,
    20.0,
    25.0,
    50.0,
    100.0,
    200.0,
    250.0,
    500.0,
    1000.0,
    2000.0,
    5000.0,
)
SCALEBAR_TARGET_VIEWPORT_FRACTION = 0.22
SCALEBAR_PAD_X_FRAC = 0.04
SCALEBAR_PAD_Y_FRAC = 0.05
SCALEBAR_TICK_FRAC = 0.018
SCALEBAR_LABEL_FRAC = 0.028
SCALEBAR_LINEWIDTH = 2.6
SCALEBAR_FONTSIZE = 7.5
CHUNK_MAP_PAD_FRAC = 0.12
VIEWPORT_MAP_PAD_FRAC = 0.06
COURSE_KM_MARKER_STEP_SHORT = 0.5
COURSE_KM_MARKER_STEP_LONG = 1.0
COURSE_KM_MARKER_SHORT_SPAN_KM = 2.0
COURSE_100M_MARKER_STEP = 0.1
COURSE_100M_TICK_FRAC = 0.004
COURSE_100M_LABEL_FRAC = 0.009
COURSE_100M_LABEL_FONTSIZE = 5.5
DECISION_TOP_HEIGHT_RATIO = 1.9
TOP_MAP_WIDTH_RATIO = 5.75
TOP_LEGEND_WIDTH_RATIO = 0.38
LEGEND_NCOL = 2
LEGEND_FONT_SIZE = 10.5
LEGEND_HANDLELENGTH = 1.25
LEGEND_LABELSPACING = 0.28
LEGEND_HANDLETEXTPAD = 0.38
LEGEND_BORDERAXESPAD = 0.10

# Per-athlete NTI overlay colours on ref_chainage_m spine panels.
SPINE_ATHLETE_NTI_COLORS: dict[str, str] = {
    "Subject_A": "#4FC3F7",
    "Subject_B": "#FF8A65",
}

# Default NTI cross-athlete std above which a metre is flagged for review.
DEFAULT_VARIANCE_THRESHOLD = 0.30

# Operator-readable export — fixed canvas; avoid bbox_inches="tight" (expands with off-axis artists).
FIG_SIZE_IN = (16.0, 10.0)
DECISION_FIG_WIDTH_IN = 20.0
FIG_DPI = 150
# Map layout margins (fraction of figure). Decision mode needs wider left/right for grade + NTI twins.
WITH_MAP_MARGINS = dict(left=0.05, right=0.99, top=0.91, bottom=0.05, hspace=0.38)
DECISION_MAP_MARGINS = dict(left=0.13, right=0.88, top=0.91, bottom=0.10, hspace=0.38)
MIN_SEGMENT_LABEL_SPAN_KM = 0.08
MIN_ML_PRED_SEGMENT_LABEL_SPAN_KM = 0.06

OVERRIDE_PROTOCOL = """
Manual override path (HITL guidance → lock):
  1. Edit the terrain map JSON (e.g. config/spatial_terrain_map_sut43.json)
  2. Append to hitl.manual_overrides[] per review chunk (default mode = guidance):
       { "course_km_start": <float>, "course_km_end": <float>,
         "surface_class": "S1"|..|"S6", "reason": "<operator note>", "mode": "guidance" }
     Memory-based or unvalidated field notes stay guidance — dashed overlay only.
  3. After GPS revisit, second-athlete agreement, or corridor QC sign-off, promote span:
         "mode": "lock"
     Set hitl.status to "review" during review; "locked" only when all spans are lock-promoted.
  4. Re-run chunk dashboards (--export-chunks or --chunk-index N) to verify.
Schema: config/spatial_terrain_map.schema.json
"""

GUIDANCE_SPAN_ALPHA = 0.09
GUIDANCE_EDGE_ALPHA = 0.55
ACCEPT_DRAFT_SPAN_ALPHA = 0.38
ACCEPT_DRAFT_EDGE_ALPHA = 0.92
VARIANCE_GAP_COLOR = "#9E9E9E"
VARIANCE_GAP_ALPHA = 0.22
VARIANCE_GAP_EDGE_ALPHA = 0.45
FLAG_SEGMENT_ALPHA = 0.22
FLAG_SEGMENT_EDGE = "#FF1744"
TI_DRAFT_EDGE_ALPHA = 0.55
TI_DRAFT_FILL_ALPHA = 0.14
TI_DRAFT_TRACK_OFFSET = 0.42
MAJORITY_DRAFT_ALPHA = 0.16
MAJORITY_DRAFT_EDGE_ALPHA = 0.55
V1_HITL_FILL_ALPHA = 0.09
V1_HITL_EDGE_ALPHA = 0.55
V1_HITL_DEFERRED_FILL_ALPHA = 0.06
V1_HITL_DEFERRED_EDGE_ALPHA = 0.38
V1_HITL_EDGE_COLOR = "#80DEEA"
V1_HITL_LINEWIDTH = 1.1

OPERATOR_GOLD_EDGE_COLOR = "#FFC107"
OPERATOR_GOLD_EDGE_ALPHA = 0.85
OPERATOR_GOLD_LINEWIDTH = 1.4
FRICTION_TIER_EDGE_COLORS: dict[str, str] = {
    "F0": "#81D4FA",
    "F1": "#AED581",
    "F2": "#FFEE58",
    # Distinct from S5 fill (#ff7043) — orange F3 edge on S4 fill was misread as S5.
    "F3": "#D84315",
    "F4": "#CE93D8",
}
FRICTION_TIER_EDGE_LW = 1.55
FRICTION_TIER_EDGE_ALPHA = 0.95
GEO_MISMATCH_WARN_MEDIAN_M = 15.0
GEO_MISMATCH_WARN_P95_M = 40.0
PNG_VERIFY_MIN_BYTES = 1024
ASSIGNED_CLASS_EDGE_COLOR = "#555555"
ASSIGNED_CLASS_EDGE_LW = 0.45
ASSIGNED_CLASS_EDGE_ALPHA = 0.55

# Decision-mode assigned-class source styling (S-class fill + border/hatch by derivation).
ASSIGNED_SOURCE_STYLE: dict[str, dict[str, Any]] = {
    "operator_gold": {
        "fill_alpha": 0.72,
        "edge_color": OPERATOR_GOLD_EDGE_COLOR,
        "edge_lw": 1.5,
        "linestyle": "-",
        "edge_alpha": 0.95,
        "hatch": None,
    },
    "accept_draft": {
        "fill_alpha": 0.52,
        "edge_color": None,
        "edge_lw": 1.0,
        "linestyle": "-",
        "edge_alpha": 0.88,
        "hatch": None,
    },
    "gmm_draft": {
        "fill_alpha": 0.42,
        "edge_color": None,
        "edge_lw": 0.55,
        "linestyle": "-",
        "edge_alpha": 0.45,
        "hatch": None,
    },
    "review": {
        "fill_alpha": 0.38,
        "edge_color": "#FF5252",
        "edge_lw": 1.0,
        "linestyle": "--",
        "edge_alpha": 0.72,
        "hatch": "//",
    },
    "abstain": {
        "fill_alpha": 0.22,
        "edge_color": "#616161",
        "edge_lw": 0.75,
        "linestyle": ":",
        "edge_alpha": 0.55,
        "hatch": "..",
    },
    "unassigned": {
        "fill_alpha": 0.16,
        "edge_color": "#616161",
        "edge_lw": 0.55,
        "linestyle": ":",
        "edge_alpha": 0.42,
        "hatch": "..",
    },
}
UNASSIGNED_CLASS_COLOR = "#424242"
DECISION_GOLD_TRACK_Y = 1.0
DECISION_ML_TRACK_Y = 0.0
DECISION_CLUSTER_A_TRACK_Y = -1.0
DECISION_CLUSTER_B_TRACK_Y = -2.0
DECISION_TRACK_HALF_HEIGHT = 0.35
CLUSTER_TI_RANK_COUNT = 6
HIGH_CLUSTER_TI_RANK_THRESHOLD = 4
CLUSTER_TI_RANK_COLORS: dict[int, str] = {
    0: "#1B7837",
    1: "#5AAE61",
    2: "#A6D96A",
    3: "#FDAE61",
    4: "#F46D43",
    5: "#D73027",
}
CLUSTER_HIGH_RANK_EDGE_COLOR = "#FFEB3B"
CLUSTER_HIGH_RANK_EDGE_LW = 1.15
CLUSTER_HIGH_RANK_EDGE_ALPHA = 0.92
CLUSTER_TI_RANK_FILL_ALPHA = 0.82
DEFAULT_CLUSTER_TI_PARQUET_A = (
    BASE_DIR
    / "03_Processed_Data"
    / "spatial"
    / "sut43_terrain_ontology"
    / "fit_ti_clusters_Subject_A.parquet"
)
DEFAULT_CLUSTER_TI_PARQUET_B = (
    BASE_DIR
    / "03_Processed_Data"
    / "spatial"
    / "sut43_terrain_ontology"
    / "fit_ti_clusters_Subject_B.parquet"
)
DECISION_TRACK_FILL_ALPHA = 0.78
DECISION_ML_TRACK_FILL_ALPHA = 0.72
DECISION_ML_TRACK_FILL_ALPHA_LOOCV = 0.94
DECISION_ML_TRACK_FILL_ALPHA_FULL = 0.75
ASSIGNED_MAP_TRACK_LINEWIDTH = 9.0
ASSIGNED_MAP_TRACK_ALPHA = 0.88
ASSIGNED_MAP_TRACK_ZORDER = 6
MAP_TRACK_PERP_OFFSET_M = 12.0
ASSIGNED_MAP_TRACK_OFFSET_M = -MAP_TRACK_PERP_OFFSET_M
ASSIGNED_MAP_LABEL_MIN_SPAN_KM = 0.25
ASSIGNED_MAP_LABEL_FONTSIZE = 7.5
# Dark underlay so S3/S4 pale fills stay visible on OpenTopoMap orthophoto.
ASSIGNED_MAP_TRACK_STROKE: dict[str, str] = {
    "S2": "#3E2723",
    "S3": "#1B5E20",
    "S4": "#0D47A1",
    "S6": "#4A148C",
}
ML_MAP_TRACK_LINEWIDTH = 3.5
ML_MAP_TRACK_ALPHA = 0.94
ML_MAP_TRACK_ALPHA_FULL = 0.75
ML_MAP_TRACK_ZORDER = 8
ML_MAP_TRACK_OFFSET_M = MAP_TRACK_PERP_OFFSET_M
DECISION_UNLABELED_ALPHA = 0.35
DECISION_SIGMA_FLAG_ALPHA = 0.07
DECISION_SIGMA_EDGE_THRESHOLD = 0.45
LOCOMOTION_HIKE_COLOR = "#42A5F5"
LOCOMOTION_RUN_COLOR = "#FFEB3B"
LOCOMOTION_HIKE_BAR_HEIGHT = 0.32
LOCOMOTION_RUN_BAR_HEIGHT = 0.88
LOCOMOTION_STRIP_FILL_ALPHA = 0.88
LOCOMOTION_PROFILE_HEIGHT_RATIO = 0.55

AGREEMENT_TIER_ALPHA = {
    "gold": 0.28,
    "silver": 0.22,
    "bronze": 0.18,
    "review": 0.14,
    "abstain": 0.10,
}


def _solid_axvspan(
    ax: plt.Axes,
    km0: float,
    km1: float,
    *,
    facecolor: str,
    alpha: float,
    zorder: int = 3,
    edgecolor: str | None = None,
    linewidth: float = 0.0,
    linestyle: str = "-",
    edge_alpha: float = 0.5,
) -> None:
    """Solid full-height km span — borders via axvline (axvspan edge linewidth causes hatch)."""
    ax.axvspan(km0, km1, facecolor=facecolor, alpha=alpha, zorder=zorder)
    if edgecolor and linewidth > 0:
        for x in (km0, km1):
            ax.axvline(
                x,
                color=edgecolor,
                linewidth=linewidth,
                linestyle=linestyle,
                alpha=edge_alpha,
                zorder=zorder + 1,
            )


def _solid_yband(
    ax: plt.Axes,
    km0: float,
    km1: float,
    ylo: float,
    yhi: float,
    *,
    facecolor: str,
    alpha: float,
    zorder: int = 3,
    edgecolor: str | None = None,
    linewidth: float = 0.0,
    linestyle: str = "-",
    edge_alpha: float = 0.5,
) -> None:
    """Solid class-row band — border via unfilled Rectangle (fill_between edge linewidth causes hatch)."""
    ax.fill_between([km0, km1], ylo, yhi, color=facecolor, alpha=alpha, zorder=zorder)
    if edgecolor and linewidth > 0:
        rect = Rectangle(
            (km0, ylo),
            km1 - km0,
            yhi - ylo,
            fill=False,
            edgecolor=edgecolor,
            linewidth=linewidth,
            linestyle=linestyle,
            alpha=edge_alpha,
            zorder=zorder + 1,
        )
        ax.add_patch(rect)


def _rle_metre_rows(
    rows: list[tuple[float, tuple[Any, ...]]],
    *,
    km_step: float = 0.001,
) -> list[tuple[float, float, tuple[Any, ...]]]:
    """Merge consecutive per-metre rows sharing the same key tuple into km spans."""
    if not rows:
        return []
    spans: list[tuple[float, float, tuple[Any, ...]]] = []
    start_km, key = rows[0]
    end_km = start_km + km_step
    for km, next_key in rows[1:]:
        if next_key == key and abs(km - end_km) < 1e-6:
            end_km = km + km_step
            continue
        spans.append((start_km, end_km, key))
        start_km, end_km, key = km, km + km_step, next_key
    spans.append((start_km, end_km, key))
    return spans


def _normalize_basemap_token(raw: str) -> str:
    return raw.strip().lower().replace("-", "_")


def assert_basemap_not_maritime(basemap: str) -> None:
    """Reject Sjøkart / maritime tile layer identifiers."""
    token = _normalize_basemap_token(basemap)
    if token in BLOCKED_MARITIME_LAYER_IDS or "sjokart" in token or "sjøkart" in token:
        raise ValueError(f"Maritime basemap layer blocked: {basemap}")


def normalize_basemap_layer(basemap: BasemapChoice | str) -> BasemapLayerId | Literal["opentopomap"]:
    """Map CLI / legacy aliases to registry layer ids."""
    assert_basemap_not_maritime(str(basemap))
    token = _normalize_basemap_token(str(basemap))
    aliases: dict[str, BasemapLayerId | Literal["opentopomap"]] = {
        "topo_standard": "topo_standard",
        "kartverket_topo": "topo_standard",
        "topo": "topo_standard",
        "topo_grayscale": "topo_grayscale",
        "kartverket_gray": "topo_grayscale",
        "kartverket_greyscale": "topo_grayscale",
        "topograatone": "topo_grayscale",
        "satellite_flyfoto": "satellite_flyfoto",
        "flyfoto": "satellite_flyfoto",
        "orthophoto": "satellite_flyfoto",
        "opentopomap": "opentopomap",
        "carto_nolabels": "carto_nolabels",
        "blog_grey": "carto_nolabels",
    }
    if token in aliases:
        return aliases[token]
    if token in BASEMAP_LAYER_REGISTRY:
        return token  # type: ignore[return-value]
    raise ValueError(f"Unknown basemap layer: {basemap}")


def nib_wmts_token_configured() -> bool:
    """True when Kartverket Norge i bilder orthophoto WMTS token is set and non-empty."""
    return bool(os.environ.get("NIB_WMTS_TOKEN", "").strip())


def resolve_basemap_tile_source(
    basemap: BasemapChoice | str,
) -> tuple[str, str, str | None]:
    """Return tile URL template, human label, and optional attribution."""
    layer = normalize_basemap_layer(basemap)
    if layer == "opentopomap":
        return "opentopomap", "OpenTopoMap", None
    spec = BASEMAP_LAYER_REGISTRY[layer]
    url = spec["url"]
    if layer == "satellite_flyfoto":
        token = os.environ.get("NIB_WMTS_TOKEN", "").strip()
        if token:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}token={token}"
    return url, spec["label"], spec.get("attribution")


def _kartverket_tile_url(basemap: BasemapChoice | str) -> str:
    url, _, _ = resolve_basemap_tile_source(basemap)
    if url == "opentopomap":
        return KARTVERKET_TOPO_URL
    return url


def _map_span_meters(bounds: tuple[float, float, float, float]) -> tuple[float, float]:
    """Approximate map width and height in metres for EPSG:4326 bounds."""
    west, south, east, north = bounds
    center_lat = (south + north) / 2.0
    lat_m_per_deg = 111_320.0
    lon_m_per_deg = lat_m_per_deg * max(np.cos(np.radians(center_lat)), 1e-6)
    width_m = max((east - west) * lon_m_per_deg, 1.0)
    height_m = max((north - south) * lat_m_per_deg, 1.0)
    return width_m, height_m


def pick_metric_scalebar_length_m(viewport_width_m: float) -> tuple[float, str]:
    """Choose a round metric scalebar length for the current geographic zoom."""
    target_m = viewport_width_m * SCALEBAR_TARGET_VIEWPORT_FRACTION
    chosen = SCALEBAR_NICE_LENGTHS_M[0]
    for length_m in SCALEBAR_NICE_LENGTHS_M:
        if length_m <= target_m * 1.35:
            chosen = length_m
    if chosen >= 1000.0 and chosen % 1000.0 == 0.0:
        label = f"{int(chosen / 1000.0)} km"
    elif chosen >= 1000.0:
        label = f"{chosen / 1000.0:.1f} km"
    else:
        label = f"{int(chosen)} m" if chosen == int(chosen) else f"{chosen:.0f} m"
    return chosen, label


def plot_metric_scalebar(
    ax: plt.Axes,
    bounds: tuple[float, float, float, float],
) -> tuple[float, str]:
    """Draw a bottom-left metric scalebar that tracks geographic zoom."""
    west, south, east, north = bounds
    width_m, height_m = _map_span_meters(bounds)
    bar_m, label = pick_metric_scalebar_length_m(width_m)
    center_lat = (south + north) / 2.0
    lon_m_per_deg = 111_320.0 * max(np.cos(np.radians(center_lat)), 1e-6)
    bar_lon = bar_m / lon_m_per_deg
    lon_span = max(east - west, 1e-9)
    lat_span = max(north - south, 1e-9)
    pad_x = lon_span * SCALEBAR_PAD_X_FRAC
    pad_y = lat_span * SCALEBAR_PAD_Y_FRAC
    tick_h = lat_span * SCALEBAR_TICK_FRAC
    label_y = south + pad_y + lat_span * SCALEBAR_LABEL_FRAC
    x0 = west + pad_x
    x1 = x0 + bar_lon
    y0 = south + pad_y
    ax.plot(
        [x0, x1],
        [y0, y0],
        color="#F5F5F5",
        linewidth=SCALEBAR_LINEWIDTH,
        solid_capstyle="butt",
        zorder=25,
    )
    ax.plot(
        [x0, x0],
        [y0 - tick_h, y0 + tick_h],
        color="#F5F5F5",
        linewidth=SCALEBAR_LINEWIDTH * 0.85,
        solid_capstyle="butt",
        zorder=25,
    )
    ax.plot(
        [x1, x1],
        [y0 - tick_h, y0 + tick_h],
        color="#F5F5F5",
        linewidth=SCALEBAR_LINEWIDTH * 0.85,
        solid_capstyle="butt",
        zorder=25,
    )
    text = ax.text(
        (x0 + x1) / 2.0,
        label_y,
        label,
        ha="center",
        va="bottom",
        fontsize=SCALEBAR_FONTSIZE,
        color="#F0F0F0",
        zorder=26,
    )
    text.set_path_effects([pe.withStroke(linewidth=1.4, foreground="#111111", alpha=0.9)])
    return bar_m, label


def lock_plotly_geo_aspect_1_1(
    fig: Any,
    bounds: tuple[float, float, float, float],
    *,
    geo_ref: str = "geo",
) -> None:
    """Force 1:1 lon/lat scaling on a Plotly geo subplot (mercator data axes)."""
    west, south, east, north = bounds
    fig.update_layout(
        **{
            geo_ref: dict(
                projection_type="mercator",
                lonaxis=dict(range=[west, east]),
                lataxis=dict(range=[south, north], scaleanchor=f"{geo_ref}.lonaxis"),
                fitbounds=False,
            )
        }
    )


def plotly_geo_scalebar_annotations(
    bounds: tuple[float, float, float, float],
    *,
    xref: str = "paper",
    yref: str = "paper",
) -> list[dict[str, Any]]:
    """Bottom-left scalebar annotations for a Plotly geo/map viewport."""
    width_m, _ = _map_span_meters(bounds)
    _, label = pick_metric_scalebar_length_m(width_m)
    return [
        dict(
            x=0.04,
            y=0.06,
            xref=xref,
            yref=yref,
            text=label,
            showarrow=False,
            font=dict(size=11, color="#F0F0F0"),
            bgcolor="rgba(17,17,17,0.72)",
            borderpad=3,
        ),
        dict(
            x=0.04,
            y=0.03,
            xref=xref,
            yref=yref,
            ax=0.18,
            ay=0,
            axref=xref,
            ayref=yref,
            arrowhead=0,
            arrowwidth=2,
            arrowcolor="#F5F5F5",
            showarrow=True,
        ),
    ]


def _geo_bounds_with_padding(
    geo: pd.DataFrame,
    *,
    pad_frac: float,
    min_pad_deg: float = 0.0008,
) -> tuple[float, float, float, float]:
    """Return west, south, east, north with fractional lat/lon padding."""
    lon_span = float(geo["longitude"].max() - geo["longitude"].min())
    lat_span = float(geo["latitude"].max() - geo["latitude"].min())
    lon_pad = max(lon_span * pad_frac, min_pad_deg)
    lat_pad = max(lat_span * pad_frac, min_pad_deg)
    west = float(geo["longitude"].min()) - lon_pad
    east = float(geo["longitude"].max()) + lon_pad
    south = float(geo["latitude"].min()) - lat_pad
    north = float(geo["latitude"].max()) + lat_pad
    return west, south, east, north


def apply_geo_coordinate_offset(
    geo: pd.DataFrame,
    *,
    lat_offset: float = 0.0,
    lon_offset: float = 0.0,
) -> pd.DataFrame:
    """Shift lat/lon columns for GPS–basemap drift correction (degrees)."""
    if geo.empty or (lat_offset == 0.0 and lon_offset == 0.0):
        return geo
    out = geo.copy()
    out["latitude"] = out["latitude"] + lat_offset
    out["longitude"] = out["longitude"] + lon_offset
    return out


def offset_panel_gps(
    panel: pd.DataFrame,
    *,
    lat_offset: float = 0.0,
    lon_offset: float = 0.0,
) -> pd.DataFrame:
    """Return panel copy with latitude/longitude shifted for map overlay alignment."""
    if lat_offset == 0.0 and lon_offset == 0.0:
        return panel
    out = panel.copy()
    if "latitude" in out.columns:
        out["latitude"] = out["latitude"] + lat_offset
    if "longitude" in out.columns:
        out["longitude"] = out["longitude"] + lon_offset
    return out


def _expand_bounds_to_display_aspect(
    bounds: tuple[float, float, float, float],
    target_aspect: float,
    *,
    min_span_deg: float = 0.0008,
) -> tuple[float, float, float, float]:
    """Pad lon/lat span so an equal-aspect map fills a wide subplot cell."""
    if target_aspect <= 0:
        return bounds
    west, south, east, north = bounds
    lon_span = max(float(east - west), min_span_deg)
    lat_span = max(float(north - south), min_span_deg)
    data_aspect = lon_span / lat_span
    center_lon = (west + east) / 2.0
    center_lat = (south + north) / 2.0
    if data_aspect < target_aspect:
        lon_span = lat_span * target_aspect
    else:
        lat_span = lon_span / target_aspect
    return (
        center_lon - lon_span / 2.0,
        center_lat - lat_span / 2.0,
        center_lon + lon_span / 2.0,
        center_lat + lat_span / 2.0,
    )


def _expand_bounds_to_metric_aspect(
    bounds: tuple[float, float, float, float],
    target_aspect: float,
    *,
    min_span_deg: float = 0.0008,
) -> tuple[float, float, float, float]:
    """Pad bounds so ground width/height matches target_aspect (metres, latitude-aware)."""
    if target_aspect <= 0:
        return bounds
    west, south, east, north = bounds
    center_lon = (west + east) / 2.0
    center_lat = (south + north) / 2.0
    width_m, height_m = _map_span_meters(bounds)
    if width_m / max(height_m, 1.0) < target_aspect:
        width_m = height_m * target_aspect
    else:
        height_m = width_m / target_aspect
    lat_m_per_deg = 111_320.0
    lon_m_per_deg = lat_m_per_deg * max(np.cos(np.radians(center_lat)), 1e-6)
    lon_span = max(width_m / lon_m_per_deg, min_span_deg)
    lat_span = max(height_m / lat_m_per_deg, min_span_deg)
    return (
        center_lon - lon_span / 2.0,
        center_lat - lat_span / 2.0,
        center_lon + lon_span / 2.0,
        center_lat + lat_span / 2.0,
    )


def _map_subplot_target_aspect(
    *,
    decision_mode: bool,
    with_cluster_ti: bool = True,
    with_locomotion_strip: bool = False,
) -> float:
    """Width/height of map data limits needed to fill the top-left GridSpec cell."""
    map_h = DECISION_TOP_HEIGHT_RATIO if decision_mode else 1.85
    if decision_mode:
        profile_heights = [2.25, 1.45 if with_cluster_ti else 1.15]
        if with_locomotion_strip:
            profile_heights.append(LOCOMOTION_PROFILE_HEIGHT_RATIO)
    else:
        profile_heights = [2.0, 1.0]
    row_frac = map_h / (map_h + sum(profile_heights))
    col_frac = TOP_MAP_WIDTH_RATIO / (TOP_MAP_WIDTH_RATIO + TOP_LEGEND_WIDTH_RATIO)
    margins = DECISION_MAP_MARGINS if decision_mode else WITH_MAP_MARGINS
    usable_w = float(margins["right"] - margins["left"])
    usable_h = float(margins["top"] - margins["bottom"])
    fig_w = DECISION_FIG_WIDTH_IN if decision_mode else FIG_SIZE_IN[0]
    fig_h = 12.5 if decision_mode else 12.0
    cell_w_frac = col_frac * usable_w
    cell_h_frac = row_frac * usable_h
    if cell_h_frac <= 0:
        return 1.0
    return (cell_w_frac / cell_h_frac) * (fig_w / fig_h)


def _basemap_zoom_for_bounds(bounds: tuple[float, float, float, float]) -> int | Literal["auto"]:
    west, south, east, north = bounds
    try:
        from contextily.tile import _calculate_zoom

        return int(_calculate_zoom(west, south, east, north))
    except Exception:
        return "auto"


def _format_basemap_status(
    label: str,
    *,
    url: str,
    bounds: tuple[float, float, float, float],
    zoom: int | Literal["auto"],
    attribution: str | None = None,
) -> str:
    west, south, east, north = bounds
    parts = [
        label,
        f"z={zoom}",
        f"bbox W{west:.5f} S{south:.5f} E{east:.5f} N{north:.5f}",
        url,
    ]
    if attribution:
        parts.append(attribution)
    return " | ".join(parts)


def _clamp_tile_zoom(zoom: int | Literal["auto"]) -> int | Literal["auto"]:
    if zoom == "auto":
        return zoom
    return max(9, min(18, int(zoom)))


def _ensure_contextily_cache() -> None:
    TILE_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    import contextily as cx

    cx.set_cache_dir(str(TILE_CACHE_ROOT))


def _safe_log_error(msg: str) -> None:
    """Log to stderr without crashing when the pipe is closed (e.g. Streamlit cache)."""
    try:
        print(f"ERROR {msg}", file=sys.stderr)
    except BrokenPipeError:
        pass


def _safe_canvas_draw(fig: plt.Figure) -> None:
    """Draw matplotlib canvas; surface BrokenPipeError as RuntimeError for basemap fallback."""
    try:
        fig.canvas.draw()
    except BrokenPipeError as exc:
        raise RuntimeError("matplotlib canvas draw pipe closed") from exc


def _invoke_add_basemap(
    cx: Any,
    ax: plt.Axes,
    *,
    source: Any,
    zoom: int | Literal["auto"],
    alpha: float,
) -> None:
    cx.add_basemap(
        ax,
        source=source,
        crs="EPSG:4326",
        zoom=zoom,
        attribution="",
        attribution_size=0,
        alpha=alpha,
        reset_extent=False,
    )
    _safe_canvas_draw(ax.figure)
    if not ax.images:
        raise RuntimeError("basemap tile layer missing after add_basemap")
    tile_arr = ax.images[-1].get_array()
    if tile_arr is not None and float(np.std(tile_arr)) < BASEMAP_MIN_TILE_STD:
        raise RuntimeError(
            f"basemap tiles appear blank (std={float(np.std(tile_arr)):.1f})"
        )


def _atomic_savefig(fig: plt.Figure, output_path: Path, **kwargs: Any) -> None:
    """Write PNG atomically so HITL previews never read a partial file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")
    try:
        _safe_canvas_draw(fig)
        fig.savefig(tmp_path, **kwargs)
        os.replace(tmp_path, output_path)
    except (BrokenPipeError, OSError) as exc:
        raise RuntimeError(f"PNG export failed: {type(exc).__name__}: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)


def verify_png_export(output_path: Path) -> tuple[int, int, int]:
    """PIL verify PNG integrity; return (width, height, size_bytes). Raises on corrupt file."""
    if not output_path.exists():
        raise ValueError(f"PNG missing: {output_path}")
    size_bytes = output_path.stat().st_size
    if size_bytes < PNG_VERIFY_MIN_BYTES:
        raise ValueError(
            f"PNG too small ({size_bytes} B, min {PNG_VERIFY_MIN_BYTES}): {output_path}"
        )
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("PIL/Pillow required for --verify-export") from exc
    with Image.open(output_path) as im:
        im.verify()
    with Image.open(output_path) as im:
        width, height = im.size
    if width < 100 or height < 100:
        raise ValueError(f"PNG dimensions suspicious ({width}x{height}): {output_path}")
    return width, height, size_bytes


def _try_add_basemap(
    ax: plt.Axes,
    basemap: BasemapChoice,
    bounds: tuple[float, float, float, float],
    *,
    alpha: float = 0.92,
) -> str:
    """Add topo basemap tiles via contextily; return legend footer status."""
    try:
        import contextily as cx  # noqa: F401
    except ImportError:
        return "no (contextily not installed)"
    import contextily as cx

    west, south, east, north = bounds
    zoom = _clamp_tile_zoom(_basemap_zoom_for_bounds(bounds))
    layer = normalize_basemap_layer(basemap)
    _ensure_contextily_cache()

    def _add(source: Any, *, label: str, url: str, attribution: str | None) -> str:
        last_exc: Exception | None = None
        for attempt in range(BASEMAP_FETCH_ATTEMPTS):
            try:
                _invoke_add_basemap(cx, ax, source=source, zoom=zoom, alpha=alpha)
                return _format_basemap_status(
                    label,
                    url=url,
                    bounds=bounds,
                    zoom=zoom,
                    attribution=attribution,
                )
            except Exception as exc:
                last_exc = exc
                if attempt < BASEMAP_FETCH_ATTEMPTS - 1:
                    time.sleep(BASEMAP_FETCH_BACKOFF_S * (attempt + 1))
        assert last_exc is not None
        raise last_exc

    fallback_sources: list[tuple[Any, str, str]] = [
        (
            cx.providers.OpenTopoMap,
            "OpenTopoMap (fallback)",
            str(getattr(cx.providers.OpenTopoMap, "url", "OpenTopoMap")),
        ),
        (
            cx.providers.OpenStreetMap.Mapnik,
            "OpenStreetMap (fallback)",
            str(getattr(cx.providers.OpenStreetMap.Mapnik, "url", "OpenStreetMap")),
        ),
    ]

    if layer == "carto_nolabels":
        carto_url = str(getattr(cx.providers.CartoDB.PositronNoLabels, "url", "CartoDB PositronNoLabels"))
        try:
            return _add(
                cx.providers.CartoDB.PositronNoLabels,
                label="CartoDB Positron (no labels)",
                url=carto_url,
                attribution="© OpenStreetMap © CARTO",
            )
        except Exception as exc:
            logging.warning("CartoDB PositronNoLabels fetch failed (%s); trying Kartverket greyscale", exc)
            layer = "topo_grayscale"

    if layer != "opentopomap":
        url, label, attribution = resolve_basemap_tile_source(layer)
        if layer == "satellite_flyfoto" and not nib_wmts_token_configured():
            return "no (NIB_WMTS_TOKEN required for Kartverket orthophoto)"
        try:
            return _add(url, label=label, url=url, attribution=attribution)
        except Exception as exc:
            if layer == "satellite_flyfoto":
                logging.error("Kartverket orthophoto fetch failed (%s)", exc)
                return f"no ({type(exc).__name__}: {exc})"
            logging.warning(
                "%s basemap fetch failed (%s); trying OpenTopoMap / OSM fallbacks",
                label,
                exc,
            )
            for source, fb_label, fb_url in fallback_sources:
                try:
                    return _add(source, label=fb_label, url=fb_url, attribution=None)
                except Exception as fallback_exc:
                    logging.warning("%s basemap fetch failed (%s)", fb_label, fallback_exc)
            logging.error("All basemap sources failed for %s request (last: %s)", label, exc)
            return f"no ({type(exc).__name__}: {exc})"

    try:
        fb_url = str(getattr(cx.providers.OpenTopoMap, "url", "OpenTopoMap"))
        return _add(
            cx.providers.OpenTopoMap,
            label="OpenTopoMap",
            url=fb_url,
            attribution=None,
        )
    except Exception as exc:
        logging.warning("OpenTopoMap basemap fetch failed (%s); trying OSM fallback", exc)
        try:
            fb_url = str(getattr(cx.providers.OpenStreetMap.Mapnik, "url", "OpenStreetMap"))
            return _add(
                cx.providers.OpenStreetMap.Mapnik,
                label="OpenStreetMap (fallback)",
                url=fb_url,
                attribution=None,
            )
        except Exception as fallback_exc:
            logging.error("All basemap sources failed (last: %s)", fallback_exc)
            return f"no ({type(fallback_exc).__name__}: {fallback_exc})"


def resolve_axis_label(terrain_map: dict[str, Any], panel: pd.DataFrame) -> str:
    """
    Course-axis label for x-axis — panel telemetry wins when corridor metadata is stale.
    Spine panels use ref_chainage_m (Subject_A race spine); operator gold joins 1:1 on course_km.
    """
    sort_col = "course_m" if "course_m" in panel.columns else "ref_chainage_m"
    work = panel.sort_values(sort_col)
    if is_spine_panel(panel):
        return "SUT_43 ref_chainage km (Subject_A spine)"
    p_lo = float(work["course_km"].min())
    p_hi = float(work["course_km"].max())
    corridor = terrain_map.get("corridor") or {}
    c_lo = corridor.get("km_start")
    c_hi = corridor.get("km_end")
    stale = False
    if c_lo is not None and c_hi is not None:
        c_lo, c_hi = float(c_lo), float(c_hi)
        stale = not (c_lo <= p_hi + 0.5 and c_hi >= p_lo - 0.5)
    if stale or corridor.get("course_axis") == "stream_distance":
        race_id = str(corridor.get("race_id") or "stream")
        if race_id == "SUT_43":
            return "SUT_43 stream km"
        return f"{race_id} stream km"
    race_id = corridor.get("race_id", "SUT_160")
    if race_id == "SUT_43":
        return "SUT_43 stream km"
    return f"{race_id} course km"


def corridor_geography_label(terrain_map: dict[str, Any]) -> str | None:
    """Human place label for map titles (e.g. Uskedalen · Kvinnherad · Vestland)."""
    corridor = terrain_map.get("corridor") or {}
    geo = corridor.get("geography") or {}
    parts = [geo.get("settlement"), geo.get("municipality"), geo.get("county")]
    label = " · ".join(str(p) for p in parts if p)
    if label:
        return label
    race_id = corridor.get("race_id")
    return str(race_id) if race_id else None


def resolve_dashboard_gpx_path(
    terrain_map: dict[str, Any],
    explicit: Path | None,
    *,
    no_gpx: bool = False,
) -> Path | None:
    """Organiser GPX overlay — SUT_43 only unless explicitly passed (and not --no-gpx)."""
    if no_gpx:
        return None
    if explicit is not None:
        return explicit if explicit.is_absolute() else BASE_DIR / explicit
    race_id = str((terrain_map.get("corridor") or {}).get("race_id") or "")
    if race_id != "SUT_43":
        return None
    return DEFAULT_SUT43_GPX if DEFAULT_SUT43_GPX.exists() else None


def corridor_allows_gpx_overlay(terrain_map: dict[str, Any]) -> bool:
    return str((terrain_map.get("corridor") or {}).get("race_id") or "") == "SUT_43"


def iter_review_chunks(
    km_start: float,
    km_end: float,
    *,
    chunk_km: float,
) -> list[tuple[int, float, float]]:
    """Return (index, km_lo, km_hi) tuples covering [km_start, km_end] in chunk_km steps."""
    if chunk_km <= 0:
        raise ValueError("chunk_km must be positive")
    chunks: list[tuple[int, float, float]] = []
    lo = float(km_start)
    idx = 0
    while lo < km_end - 1e-9:
        hi = min(lo + chunk_km, float(km_end))
        chunks.append((idx, lo, hi))
        lo = hi
        idx += 1
    return chunks


def _segment_km_bounds(seg: dict[str, Any]) -> tuple[float, float]:
    km0 = seg.get("course_km_start", seg.get("course_m_start", 0) / 1000.0)
    km1 = seg.get("course_km_end", seg.get("course_m_end", km0) / 1000.0)
    return float(km0), float(km1)


def _segment_for_span(
    template: dict[str, Any] | None,
    km0: float,
    km1: float,
    surface_class: str,
    *,
    source: str,
    reason: str = "",
) -> dict[str, Any]:
    seg: dict[str, Any] = {
        "course_km_start": km0,
        "course_km_end": km1,
        "course_m_start": round(km0 * 1000.0, 3),
        "course_m_end": round(km1 * 1000.0, 3),
        "surface_class": surface_class,
        "source": source,
    }
    if reason:
        seg["reason"] = reason
    if template:
        for key in ("cluster_id", "nti_median"):
            if key in template:
                seg[key] = template[key]
    return seg


def override_mode(ov: dict[str, Any]) -> OverrideMode:
    """Resolve override mode; legacy locked:true → lock; default guidance."""
    raw = ov.get("mode")
    if raw in ("guidance", "lock"):
        return raw
    if ov.get("locked") is True:
        return "lock"
    return "guidance"


def manual_overrides_by_mode(
    terrain_map: dict[str, Any],
    mode: OverrideMode,
) -> list[dict[str, Any]]:
    overrides = terrain_map.get("hitl", {}).get("manual_overrides") or []
    return [ov for ov in overrides if override_mode(ov) == mode]


def apply_manual_overrides(
    segments: list[dict[str, Any]],
    overrides: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return draft segments with lock-mode HITL overrides spliced in (render-time only)."""
    lock_overrides = [ov for ov in overrides if override_mode(ov) == "lock"]
    if not lock_overrides:
        return segments

    result = list(segments)
    for ov in lock_overrides:
        ov_start = float(ov["course_km_start"])
        ov_end = float(ov["course_km_end"])
        cls = str(ov["surface_class"])
        reason = str(ov.get("reason", ""))
        next_segments: list[dict[str, Any]] = []
        for seg in result:
            km0, km1 = _segment_km_bounds(seg)
            if km1 <= ov_start or km0 >= ov_end:
                next_segments.append(seg)
                continue
            if km0 < ov_start:
                next_segments.append(
                    _segment_for_span(
                        seg,
                        km0,
                        ov_start,
                        str(seg.get("surface_class", "S2")),
                        source=str(seg.get("source", "cluster")),
                    )
                )
            overlap_start = max(km0, ov_start)
            overlap_end = min(km1, ov_end)
            next_segments.append(
                _segment_for_span(
                    seg,
                    overlap_start,
                    overlap_end,
                    cls,
                    source="hitl_override",
                    reason=reason,
                )
            )
            if km1 > ov_end:
                next_segments.append(
                    _segment_for_span(
                        seg,
                        ov_end,
                        km1,
                        str(seg.get("surface_class", "S2")),
                        source=str(seg.get("source", "cluster")),
                    )
                )
        result = next_segments
    return result


def cluster_segments(terrain_map: dict[str, Any]) -> list[dict[str, Any]]:
    """GMM/cluster draft only — unchanged by HITL."""
    return terrain_map.get("segments", [])


def ti_draft_segments_from_map(terrain_map: dict[str, Any]) -> list[dict[str, Any]]:
    """TI-band sidecar segments (nti_median + ti_band classifier)."""
    return terrain_map.get("ti_draft_segments") or []


def resolve_ti_draft_segments(
    terrain_map: dict[str, Any],
    panel: pd.DataFrame,
    *,
    km_lo: float,
    km_hi: float,
    variance_threshold: float,
    enable: bool,
) -> list[dict[str, Any]]:
    """Sidecar from terrain map, or compute live when enabled and sidecar empty."""
    stored = ti_draft_segments_from_map(terrain_map)
    if stored:
        return stored
    if not enable:
        return []
    return build_ti_draft_segments(
        panel,
        km_lo,
        km_hi,
        variance_threshold=variance_threshold,
    )


def effective_segments(terrain_map: dict[str, Any]) -> list[dict[str, Any]]:
    """Cluster draft with lock-mode overrides applied (authoritative when promoted)."""
    overrides = terrain_map.get("hitl", {}).get("manual_overrides") or []
    return apply_manual_overrides(terrain_map.get("segments", []), overrides)


def guidance_overrides(terrain_map: dict[str, Any]) -> list[dict[str, Any]]:
    return manual_overrides_by_mode(terrain_map, "guidance")


def annotate_lock_spans(
    ax: plt.Axes,
    overrides: list[dict[str, Any]],
    *,
    km_lo: float | None = None,
    km_hi: float | None = None,
) -> None:
    """Solid lock tint — replaces cluster draft visually on profile axes."""
    for ov in overrides:
        km0 = float(ov["course_km_start"])
        km1 = float(ov["course_km_end"])
        if km_lo is not None and km1 < km_lo:
            continue
        if km_hi is not None and km0 > km_hi:
            continue
        cls = str(ov.get("surface_class", "S2"))
        color = SURFACE_COLORS.get(cls, "#888888")
        ax.axvspan(km0, km1, facecolor=color, alpha=0.22, zorder=4)


def segment_span_ax(
    ax: plt.Axes,
    segments: list[dict[str, Any]],
    ylo: float,
    yhi: float,
    *,
    alpha: float = 0.18,
    policies: list[dict[str, Any]] | None = None,
) -> None:
    """Coloured km spans for profile rows (cluster draft or effective lock spans)."""
    for seg in segments:
        cls = seg.get("surface_class", "S2")
        km0 = seg.get("course_km_start", seg.get("course_m_start", 0) / 1000.0)
        km1 = seg.get("course_km_end", seg.get("course_m_end", 0) / 1000.0)
        color = SURFACE_COLORS.get(cls, "#888888")
        ax.axvspan(
            km0,
            km1,
            alpha=alpha,
            color=color,
            label=cls if cls not in ax.get_legend_handles_labels()[1] else None,
        )


def annotate_guidance_spans(
    ax: plt.Axes,
    overrides: list[dict[str, Any]],
    *,
    km_lo: float | None = None,
    km_hi: float | None = None,
) -> None:
    """Guidance tint on profile axes — dashed active guidance or solid accept-draft."""
    for ov in overrides:
        km0 = float(ov["course_km_start"])
        km1 = float(ov["course_km_end"])
        if km_lo is not None and km1 < km_lo:
            continue
        if km_hi is not None and km0 > km_hi:
            continue
        cls = str(ov.get("surface_class", "S2"))
        color = SURFACE_COLORS.get(cls, "#888888")
        accept_draft = ov.get("source") == "accept_draft"
        alpha = ACCEPT_DRAFT_SPAN_ALPHA if accept_draft else GUIDANCE_SPAN_ALPHA
        edge_lw = 1.4 if accept_draft else 1.2
        edge_ls = "-" if accept_draft else "--"
        edge_a = ACCEPT_DRAFT_EDGE_ALPHA if accept_draft else GUIDANCE_EDGE_ALPHA
        _solid_axvspan(
            ax,
            km0,
            km1,
            facecolor=color,
            alpha=alpha,
            zorder=5,
            edgecolor=color,
            linewidth=edge_lw,
            linestyle=edge_ls,
            edge_alpha=edge_a,
        )


def annotate_ti_draft_on_class_axis(
    ax: plt.Axes,
    segments: list[dict[str, Any]],
    class_to_y: dict[str, int],
    *,
    km_lo: float,
    km_hi: float,
) -> None:
    """Low-alpha secondary track for TI-band draft — distinct from solid GMM draft fills."""
    for seg in segments:
        cls = str(seg.get("surface_class", "S2"))
        km0 = float(seg.get("course_km_start", 0))
        km1 = float(seg.get("course_km_end", km0))
        if km1 < km_lo or km0 > km_hi:
            continue
        if cls == DEFERRED_CLASS:
            _solid_axvspan(
                ax,
                km0,
                km1,
                facecolor=VARIANCE_GAP_COLOR,
                alpha=VARIANCE_GAP_ALPHA,
                zorder=3,
                edgecolor="#BDBDBD",
                linewidth=0.6,
                edge_alpha=VARIANCE_GAP_EDGE_ALPHA,
            )
            continue
        y = class_to_y.get(cls, 1) - TI_DRAFT_TRACK_OFFSET
        color = SURFACE_COLORS.get(cls, "#888888")
        _solid_yband(
            ax,
            km0,
            km1,
            y - 0.22,
            y + 0.22,
            facecolor=color,
            alpha=TI_DRAFT_FILL_ALPHA,
            zorder=3,
            edgecolor=color,
            linewidth=0.7,
            edge_alpha=TI_DRAFT_EDGE_ALPHA,
        )


def annotate_guidance_on_class_axis(
    ax: plt.Axes,
    overrides: list[dict[str, Any]],
    class_to_y: dict[str, int],
    *,
    km_lo: float,
    km_hi: float,
) -> None:
    """Operator guidance on the surface-class row — dashed active guidance or solid accept-draft."""
    ymin, ymax = ax.get_ylim()
    for ov in overrides:
        km0 = float(ov["course_km_start"])
        km1 = float(ov["course_km_end"])
        if km1 < km_lo or km0 > km_hi:
            continue
        cls = str(ov.get("surface_class", "S2"))
        y = class_to_y.get(cls, 1)
        color = SURFACE_COLORS.get(cls, "#888888")
        accept_draft = ov.get("source") == "accept_draft"
        fill_alpha = ACCEPT_DRAFT_SPAN_ALPHA if accept_draft else GUIDANCE_SPAN_ALPHA
        edge_alpha = ACCEPT_DRAFT_EDGE_ALPHA if accept_draft else GUIDANCE_EDGE_ALPHA
        ax.fill_between(
            [km0, km1],
            y - 0.35,
            y + 0.35,
            color=color,
            alpha=fill_alpha,
            zorder=6,
        )
        rect = Rectangle(
            (km0, y - 0.35),
            km1 - km0,
            0.7,
            fill=False,
            edgecolor=color,
            linestyle="-" if accept_draft else "--",
            linewidth=1.6 if accept_draft else 1.4,
            alpha=edge_alpha,
            zorder=7,
        )
        ax.add_patch(rect)
        if km1 - km0 >= MIN_SEGMENT_LABEL_SPAN_KM:
            label = f"{cls} accept draft" if accept_draft else f"{cls} guidance"
            ax.text(
                (km0 + km1) / 2,
                y + 0.42,
                label,
                ha="center",
                va="bottom",
                fontsize=6,
                color=color,
                alpha=0.9,
                style="normal" if accept_draft else "italic",
                zorder=8,
            )
    ax.set_ylim(ymin, ymax)


def plot_guidance_track_overlay(
    ax: plt.Axes,
    geo: pd.DataFrame,
    overrides: list[dict[str, Any]],
    *,
    km_axis: str = "course_km",
    km_lo: float | None = None,
    km_hi: float | None = None,
) -> None:
    """Dashed S-class polyline segments for guidance-only spans on the reference map."""
    if km_axis not in geo.columns or not overrides:
        return
    pts = geo.sort_values(km_axis)
    if len(pts) < 2:
        return
    for ov in overrides:
        ov_lo = float(ov["course_km_start"])
        ov_hi = float(ov["course_km_end"])
        cls = str(ov.get("surface_class", "S2"))
        color = SURFACE_COLORS.get(cls, "#888888")
        accept_draft = ov.get("source") == "accept_draft"
        for i in range(len(pts) - 1):
            row0, row1 = pts.iloc[i], pts.iloc[i + 1]
            km_mid = 0.5 * (float(row0[km_axis]) + float(row1[km_axis]))
            if km_mid < ov_lo or km_mid > ov_hi:
                continue
            if km_lo is not None and km_mid < km_lo:
                continue
            if km_hi is not None and km_mid > km_hi:
                continue
            ax.plot(
                [row0["longitude"], row1["longitude"]],
                [row0["latitude"], row1["latitude"]],
                color=color,
                linewidth=2.6 if accept_draft else 2.4,
                alpha=ACCEPT_DRAFT_EDGE_ALPHA if accept_draft else GUIDANCE_EDGE_ALPHA,
                linestyle="-" if accept_draft else "--",
                solid_capstyle="round",
                zorder=5,
            )


def _ml_pred_lookup(
    ml_df: pd.DataFrame | None,
    *,
    pred_col: str = "pred_class",
    km_col: str = "course_km",
) -> dict[float, str | None]:
    """Per-metre ML class lookup keyed by rounded stream course_km."""
    if ml_df is None or ml_df.empty or pred_col not in ml_df.columns or km_col not in ml_df.columns:
        return {}
    lookup: dict[float, str | None] = {}
    for km, pred in zip(ml_df[km_col].astype(float), ml_df[pred_col]):
        lookup[round(float(km), 3)] = _normalize_assigned_class(pred)
    return lookup


def resolve_map_first_ml_predictions_path(
    panel_path: Path,
    terrain_map: dict[str, Any],
) -> Path | None:
    """Per-course ML predictions parquet beside panel (map-first HITL export)."""
    if not is_map_first_operator_gold(terrain_map):
        return None
    race_id = str((terrain_map.get("corridor") or {}).get("race_id") or "")
    for name in (f"{race_id}_ml_predictions.parquet", "ml_predictions.parquet"):
        candidate = panel_path.parent / name
        if candidate.exists():
            return candidate
    return None


def resolve_ml_predictions_path(
    *,
    mode: MLPredictionsMode,
    explicit_path: Path | None = None,
) -> Path:
    """Resolve parquet path for full-corridor, LOOCV, or explicit override."""
    if mode == "path":
        if explicit_path is None:
            raise ValueError("--ml-predictions-mode path requires --ml-predictions")
        return explicit_path if explicit_path.is_absolute() else BASE_DIR / explicit_path
    if mode == "loocv":
        return DEFAULT_ML_LOOCV_PREDICTIONS
    return DEFAULT_ML_FULL_CORRIDOR_PREDICTIONS


def ml_track_alphas(mode: MLPredictionsMode) -> tuple[float, float]:
    """Return (strip_fill_alpha, map_track_alpha) for the active ML prediction source."""
    if mode == "loocv":
        return DECISION_ML_TRACK_FILL_ALPHA_LOOCV, ML_MAP_TRACK_ALPHA
    if mode == "full":
        return DECISION_ML_TRACK_FILL_ALPHA_FULL, ML_MAP_TRACK_ALPHA_FULL
    return DECISION_ML_TRACK_FILL_ALPHA, ML_MAP_TRACK_ALPHA


def ml_legend_label(mode: MLPredictionsMode) -> str:
    if mode == "loocv":
        return "ML predicted (LOOCV)"
    if mode == "full":
        return "ML predicted (full corridor)"
    return "ML predicted (custom)"


def _span_km_bounds_dict(span: dict[str, Any]) -> tuple[float, float]:
    """Resolve [km0, km1) from assigned-span or operator-gold dict keys."""
    if "km0" in span and "km1" in span:
        return float(span["km0"]), float(span["km1"])
    return (
        float(span.get("course_km_start", span.get("course_m_start", 0) / 1000.0)),
        float(span.get("course_km_end", span.get("course_m_end", 0) / 1000.0)),
    )


def _span_width_km(span: dict[str, Any]) -> float:
    km0, km1 = _span_km_bounds_dict(span)
    return max(km1 - km0, 0.0)


def _spans_matching_km(spans: list[dict[str, Any]], km: float) -> list[dict[str, Any]]:
    """Half-open [start, end) interior match; exact end km resolves to that span."""
    matches: list[dict[str, Any]] = []
    for span in spans:
        km0, km1 = _span_km_bounds_dict(span)
        if km0 <= km < km1:
            matches.append(span)
    if matches:
        return matches
    for span in reversed(spans):
        _, km1 = _span_km_bounds_dict(span)
        if abs(km - km1) < 1e-6:
            return [span]
    return []


def _pick_span_at_km(spans: list[dict[str, Any]], km: float) -> dict[str, Any] | None:
    """Prefer the narrowest overlapping span (later entries win ties)."""
    matches = _spans_matching_km(spans, km)
    if not matches:
        return None
    return min(
        matches,
        key=lambda span: (_span_width_km(span), -matches.index(span)),
    )


def _class_at_km_from_spans(spans: list[dict[str, Any]], km: float) -> str | None:
    span = _pick_span_at_km(spans, km)
    if span is None:
        return None
    cls = span.get("class") or span.get("surface_class")
    return _normalize_assigned_class(cls) if cls else None


def _offset_map_segment_coords(
    geo: pd.DataFrame,
    lat0: float,
    lon0: float,
    lat1: float,
    lon1: float,
    km_mid: float,
    offset_m: float,
) -> tuple[list[float], list[float]]:
    """Shift a map segment perpendicular to local course bearing (metres)."""
    if abs(offset_m) < 1e-6:
        return [lon0, lon1], [lat0, lat1]
    bearing = _track_bearing_deg(geo, km_mid)
    if bearing is None:
        return [lon0, lon1], [lat0, lat1]
    dist_deg = abs(offset_m) / 111_320.0
    side = 90.0 if offset_m >= 0 else -90.0
    o_lat0, o_lon0 = _offset_latlon_by_bearing(lat0, lon0, bearing + side, dist_deg)
    o_lat1, o_lon1 = _offset_latlon_by_bearing(lat1, lon1, bearing + side, dist_deg)
    return [o_lon0, o_lon1], [o_lat0, o_lat1]


def _plot_class_coloured_map_track(
    ax: plt.Axes,
    geo: pd.DataFrame,
    class_at_km: Any,
    *,
    km_axis: str = "course_km",
    km_lo: float | None = None,
    km_hi: float | None = None,
    linewidth: float = ML_MAP_TRACK_LINEWIDTH,
    alpha: float = ML_MAP_TRACK_ALPHA,
    zorder: int = ML_MAP_TRACK_ZORDER,
    offset_m: float = 0.0,
    stroke_classes: frozenset[str] | None = None,
) -> bool:
    """Segment-coloured lat/lon track; optional perpendicular offset from centerline."""
    if km_axis not in geo.columns:
        return False
    pts = geo.sort_values(km_axis)
    if len(pts) < 2:
        return False
    drew = False
    for i in range(len(pts) - 1):
        row0, row1 = pts.iloc[i], pts.iloc[i + 1]
        km_mid = 0.5 * (float(row0[km_axis]) + float(row1[km_axis]))
        if km_lo is not None and km_mid < km_lo:
            continue
        if km_hi is not None and km_mid > km_hi:
            continue
        cls = class_at_km(km_mid)
        if not cls:
            continue
        color = SURFACE_COLORS.get(cls, "#888888")
        xs, ys = _offset_map_segment_coords(
            geo,
            float(row0["latitude"]),
            float(row0["longitude"]),
            float(row1["latitude"]),
            float(row1["longitude"]),
            km_mid,
            offset_m,
        )
        if cls == "S1" or (stroke_classes and cls in stroke_classes):
            stroke = ASSIGNED_MAP_TRACK_STROKE.get(cls, "#1A1A1A")
            ax.plot(
                xs,
                ys,
                color=stroke,
                linewidth=linewidth + 1.4,
                alpha=min(alpha + 0.08, 1.0),
                solid_capstyle="round",
                zorder=zorder - 1,
            )
        ax.plot(
            xs,
            ys,
            color=color,
            linewidth=linewidth,
            alpha=alpha,
            solid_capstyle="round",
            zorder=zorder,
        )
        drew = True
    return drew


def plot_faint_centerline_track(
    ax: plt.Axes,
    geo: pd.DataFrame,
    *,
    km_axis: str = "course_km",
    km_lo: float | None = None,
    km_hi: float | None = None,
    linewidth: float = 2.0,
    alpha: float = 0.72,
    zorder: int = 3,
) -> bool:
    """Neutral FIT/GPS centerline so decision-mode maps stay readable between gold locks."""
    if km_axis not in geo.columns or geo.empty:
        return False
    pts = geo.sort_values(km_axis)
    if len(pts) < 2:
        return False
    drew = False
    for i in range(len(pts) - 1):
        row0, row1 = pts.iloc[i], pts.iloc[i + 1]
        km_mid = 0.5 * (float(row0[km_axis]) + float(row1[km_axis]))
        if km_lo is not None and km_mid < km_lo:
            continue
        if km_hi is not None and km_mid > km_hi:
            continue
        ax.plot(
            [row0["longitude"], row1["longitude"]],
            [row0["latitude"], row1["latitude"]],
            color="#E0E0E0",
            linewidth=linewidth,
            alpha=alpha,
            solid_capstyle="round",
            zorder=zorder,
        )
        drew = True
    return drew


def plot_assigned_span_labels_on_map(
    ax: plt.Axes,
    geo: pd.DataFrame,
    assigned_spans: list[dict[str, Any]] | None,
    *,
    km_lo: float | None = None,
    km_hi: float | None = None,
    offset_m: float = ASSIGNED_MAP_TRACK_OFFSET_M,
    min_label_span_km: float = ASSIGNED_MAP_LABEL_MIN_SPAN_KM,
) -> None:
    """Surface-class (+ F-tier) labels on the assigned map track for chunk QC."""
    if not assigned_spans or geo.empty:
        return
    for span in assigned_spans:
        if str(span.get("kind", "")) != "operator_gold":
            continue
        km0 = float(span["km0"])
        km1 = float(span["km1"])
        if km1 - km0 < min_label_span_km:
            continue
        cls = span.get("class")
        if not cls:
            continue
        km_mid = 0.5 * (km0 + km1)
        if km_lo is not None and km_mid < km_lo - 1e-9:
            continue
        if km_hi is not None and km_mid > km_hi + 1e-9:
            continue
        pt = _interp_latlon_at_km(geo, km_mid)
        if pt is None:
            continue
        lat, lon = pt
        label = str(cls)
        friction_tier = span.get("friction_tier")
        if friction_tier:
            label = f"{label}/{friction_tier}"
        bearing = _track_bearing_deg(geo, km_mid)
        label_dist = 0.00014
        if bearing is not None:
            label_lat, label_lon = _offset_latlon_by_bearing(
                lat, lon, bearing + 90.0, label_dist
            )
        else:
            label_lat, label_lon = lat + label_dist, lon
        text = ax.text(
            label_lon,
            label_lat,
            label,
            ha="center",
            va="center",
            fontsize=ASSIGNED_MAP_LABEL_FONTSIZE,
            color="#F8F8F8" if str(cls) != "S1" else "#1A1A1A",
            zorder=ASSIGNED_MAP_TRACK_ZORDER + 2,
        )
        text.set_path_effects(
            [pe.withStroke(linewidth=1.4, foreground="#111111", alpha=0.85)]
        )


def plot_gold_class_seam_markers(
    ax: plt.Axes,
    geo: pd.DataFrame,
    assigned_spans: list[dict[str, Any]] | None,
    *,
    km_lo: float | None = None,
    km_hi: float | None = None,
    offset_m: float = ASSIGNED_MAP_TRACK_OFFSET_M,
) -> None:
    """Tick + label at internal operator-gold class seams (e.g. km 4.5 S3→S4 on chunk 4–5)."""
    if not assigned_spans or geo.empty or km_lo is None or km_hi is None:
        return
    gold = sorted(
        (
            s
            for s in assigned_spans
            if str(s.get("kind", "")) == "operator_gold" and s.get("class")
        ),
        key=lambda s: float(s["km0"]),
    )
    for left, right in zip(gold, gold[1:]):
        seam_km = float(left["km1"])
        if abs(seam_km - float(right["km0"])) > 1e-6:
            continue
        if not (km_lo + 1e-9 < seam_km < km_hi - 1e-9):
            continue
        pt = _interp_latlon_at_km(geo, seam_km)
        if pt is None:
            continue
        lat, lon = pt
        bearing = _track_bearing_deg(geo, seam_km)
        tick_len = 0.00010
        label_dist = 0.00018
        if bearing is not None:
            lat_a, lon_a = _offset_latlon_by_bearing(lat, lon, bearing + 90.0, tick_len)
            lat_b, lon_b = _offset_latlon_by_bearing(lat, lon, bearing - 90.0, tick_len)
            label_lat, label_lon = _offset_latlon_by_bearing(
                lat, lon, bearing + 90.0, label_dist
            )
        else:
            lat_a, lon_a = lat, lon - tick_len
            lat_b, lon_b = lat, lon + tick_len
            label_lat, label_lon = lat + label_dist, lon
        ax.plot(
            [lon_a, lon_b],
            [lat_a, lat_b],
            color="#FFD54F",
            linewidth=1.6,
            alpha=0.95,
            solid_capstyle="round",
            zorder=ASSIGNED_MAP_TRACK_ZORDER + 3,
        )
        label = f"{seam_km:g} {left['class']}|{right['class']}"
        text = ax.text(
            label_lon,
            label_lat,
            label,
            ha="center",
            va="center",
            fontsize=6.0,
            color="#FFFDE7",
            zorder=ASSIGNED_MAP_TRACK_ZORDER + 4,
        )
        text.set_path_effects(
            [pe.withStroke(linewidth=1.2, foreground="#111111", alpha=0.9)]
        )


def plot_assigned_gold_track_overlay(
    ax: plt.Axes,
    geo: pd.DataFrame,
    assigned_spans: list[dict[str, Any]] | None,
    *,
    km_axis: str = "course_km",
    km_lo: float | None = None,
    km_hi: float | None = None,
    linewidth: float = ASSIGNED_MAP_TRACK_LINEWIDTH,
    alpha: float = ASSIGNED_MAP_TRACK_ALPHA,
    zorder: int = ASSIGNED_MAP_TRACK_ZORDER,
    offset_m: float = ASSIGNED_MAP_TRACK_OFFSET_M,
) -> bool:
    """Wide bottom-offset map track coloured by decision-mode assigned class spans."""
    if not assigned_spans:
        return False
    return _plot_class_coloured_map_track(
        ax,
        geo,
        lambda km: _class_at_km_from_spans(assigned_spans, km),
        km_axis=km_axis,
        km_lo=km_lo,
        km_hi=km_hi,
        linewidth=linewidth,
        alpha=alpha,
        zorder=zorder,
        offset_m=offset_m,
        stroke_classes=frozenset(ASSIGNED_MAP_TRACK_STROKE),
    )


def plot_ml_pred_track_overlay(
    ax: plt.Axes,
    geo: pd.DataFrame,
    ml_df: pd.DataFrame | None,
    *,
    km_axis: str = "course_km",
    km_lo: float | None = None,
    km_hi: float | None = None,
    linewidth: float = ML_MAP_TRACK_LINEWIDTH,
    alpha: float = ML_MAP_TRACK_ALPHA,
    zorder: int = ML_MAP_TRACK_ZORDER,
    offset_m: float = 0.0,
) -> bool:
    """Segment-coloured course track from pred_class (skip unlabeled metres)."""
    if ml_df is None or ml_df.empty:
        return False
    lookup = _ml_pred_lookup(ml_df)
    if not lookup:
        return False
    return _plot_class_coloured_map_track(
        ax,
        geo,
        lambda km: lookup.get(round(km, 3)),
        km_axis=km_axis,
        km_lo=km_lo,
        km_hi=km_hi,
        linewidth=linewidth,
        alpha=alpha,
        zorder=zorder,
        offset_m=offset_m,
    )


def variance_gaps(terrain_map: dict[str, Any]) -> list[dict[str, Any]]:
    return terrain_map.get("hitl", {}).get("variance_gaps") or []


def draft_preservation_policies(terrain_map: dict[str, Any]) -> list[dict[str, Any]]:
    """HITL span policies (accept-draft / no-input). Legacy key: draft_preservation_spans."""
    return terrain_map.get("hitl", {}).get("draft_preservation_spans") or []


def _accept_draft_classes_for_policy(policy: dict[str, Any]) -> set[str]:
    if policy.get("accept_draft_classes"):
        return {str(c) for c in policy["accept_draft_classes"]}
    if policy.get("preserve_when_draft_in"):
        return {str(c) for c in policy["preserve_when_draft_in"]}
    if policy.get("surface_classes_expected"):
        return {str(c) for c in policy["surface_classes_expected"]}
    return set()


def _no_input_classes_for_policy(policy: dict[str, Any]) -> set[str]:
    if policy.get("no_input_classes"):
        return {str(c) for c in policy["no_input_classes"]}
    if policy.get("draft_s2_policy") == "unassigned":
        return {"S2"}
    return set()


def _policies_overlapping_span(
    km0: float,
    km1: float,
    policies: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        policy
        for policy in policies
        if km1 > float(policy["course_km_start"]) and km0 < float(policy["course_km_end"])
    ]


def _accept_draft_classes_on_span(
    km0: float,
    km1: float,
    policies: list[dict[str, Any]],
) -> set[str]:
    """Union of accept_draft_classes across overlapping span policies."""
    accepted: set[str] = set()
    for policy in _policies_overlapping_span(km0, km1, policies):
        accepted |= _accept_draft_classes_for_policy(policy)
    return accepted


def _no_input_classes_on_span(
    km0: float,
    km1: float,
    policies: list[dict[str, Any]],
) -> set[str]:
    """Union of no_input_classes across overlapping span policies."""
    abstained: set[str] = set()
    for policy in _policies_overlapping_span(km0, km1, policies):
        abstained |= _no_input_classes_for_policy(policy)
    return abstained


def _class_is_no_input_on_span(
    km0: float,
    km1: float,
    surface_class: str,
    policies: list[dict[str, Any]],
) -> bool:
    return surface_class in _no_input_classes_on_span(km0, km1, policies)


def _class_is_accept_draft_on_span(
    km0: float,
    km1: float,
    surface_class: str,
    policies: list[dict[str, Any]],
) -> bool:
    return surface_class in _accept_draft_classes_on_span(km0, km1, policies)


def _merge_km_spans(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not spans:
        return []
    ordered = sorted(spans, key=lambda pair: pair[0])
    merged: list[tuple[float, float]] = [ordered[0]]
    for km0, km1 in ordered[1:]:
        prev0, prev1 = merged[-1]
        if km0 <= prev1 + 1e-6:
            merged[-1] = (prev0, max(prev1, km1))
        else:
            merged.append((km0, km1))
    return merged


def manual_guidance_subspans(
    km0: float,
    km1: float,
    surface_class: str,
    segments: list[dict[str, Any]],
    policies: list[dict[str, Any]],
) -> list[tuple[float, float]]:
    """Sub-spans within [km0, km1] where active (dashed) operator guidance may render."""
    if not policies:
        return [(km0, km1)]
    allowed: list[tuple[float, float]] = []
    for seg in segments:
        s0, s1 = _segment_km_bounds(seg)
        o0, o1 = max(s0, km0), min(s1, km1)
        if o1 <= o0:
            continue
        draft_cls = str(seg.get("surface_class", "S2"))
        if _class_is_no_input_on_span(o0, o1, surface_class, policies):
            continue
        if _class_is_no_input_on_span(o0, o1, draft_cls, policies):
            continue
        if (
            draft_cls == surface_class
            and _class_is_accept_draft_on_span(o0, o1, surface_class, policies)
        ):
            continue
        allowed.append((o0, o1))
    return _merge_km_spans(allowed)


def accept_draft_guidance(terrain_map: dict[str, Any]) -> list[dict[str, Any]]:
    """Synthetic guidance matching GMM draft where operator assignment equals draft."""
    policies = draft_preservation_policies(terrain_map)
    if not policies:
        return []
    result: list[dict[str, Any]] = []
    for seg in cluster_segments(terrain_map):
        s0, s1 = _segment_km_bounds(seg)
        cls = str(seg.get("surface_class", "S2"))
        if not _class_is_accept_draft_on_span(s0, s1, cls, policies):
            continue
        result.append(
            {
                "course_km_start": s0,
                "course_km_end": s1,
                "course_m_start": round(s0 * 1000.0, 3),
                "course_m_end": round(s1 * 1000.0, 3),
                "surface_class": cls,
                "source": "accept_draft",
                "mode": "guidance",
                "reason": "operator: accept GMM draft (assignment equals draft)",
            }
        )
    return result


def active_manual_guidance(terrain_map: dict[str, Any]) -> list[dict[str, Any]]:
    """Dashed operator guidance — excludes deferred, accept-draft, and no-input spans."""
    policies = draft_preservation_policies(terrain_map)
    segments = cluster_segments(terrain_map)
    result: list[dict[str, Any]] = []
    for ov in guidance_overrides(terrain_map):
        if ov.get("deferred"):
            continue
        km0 = float(ov["course_km_start"])
        km1 = float(ov["course_km_end"])
        cls = str(ov.get("surface_class", "S2"))
        subspans = manual_guidance_subspans(km0, km1, cls, segments, policies)
        for s0, s1 in subspans:
            if s1 - s0 < 1e-6:
                continue
            fragment = dict(ov)
            fragment["course_km_start"] = s0
            fragment["course_km_end"] = s1
            fragment["course_m_start"] = round(s0 * 1000.0, 3)
            fragment["course_m_end"] = round(s1 * 1000.0, 3)
            fragment["source"] = "guidance"
            result.append(fragment)
    return result


def active_guidance_overrides(terrain_map: dict[str, Any]) -> list[dict[str, Any]]:
    """All visible operator layers: dashed active guidance + solid accept-draft."""
    return active_manual_guidance(terrain_map) + accept_draft_guidance(terrain_map)


def count_no_input_metres(
    terrain_map: dict[str, Any],
    *,
    km_lo: float | None = None,
    km_hi: float | None = None,
) -> float:
    """Course metres where operator abstains (no-input); draft still visible."""
    policies = draft_preservation_policies(terrain_map)
    if not policies:
        return 0.0
    total = 0.0
    for seg in cluster_segments(terrain_map):
        s0, s1 = _segment_km_bounds(seg)
        cls = str(seg.get("surface_class", "S2"))
        if not _class_is_no_input_on_span(s0, s1, cls, policies):
            continue
        o0, o1 = s0, s1
        if km_lo is not None:
            o0 = max(o0, km_lo)
        if km_hi is not None:
            o1 = min(o1, km_hi)
        if o1 > o0:
            total += o1 - o0
    return total


def count_accept_draft_metres(
    terrain_map: dict[str, Any],
    *,
    km_lo: float | None = None,
    km_hi: float | None = None,
) -> float:
    """Course metres where operator accepts GMM draft (assignment equals draft)."""
    policies = draft_preservation_policies(terrain_map)
    if not policies:
        return 0.0
    total = 0.0
    for seg in cluster_segments(terrain_map):
        s0, s1 = _segment_km_bounds(seg)
        cls = str(seg.get("surface_class", "S2"))
        if not _class_is_accept_draft_on_span(s0, s1, cls, policies):
            continue
        o0, o1 = s0, s1
        if km_lo is not None:
            o0 = max(o0, km_lo)
        if km_hi is not None:
            o1 = min(o1, km_hi)
        if o1 > o0:
            total += o1 - o0
    return total


def count_draft_metres_by_class(
    terrain_map: dict[str, Any],
    *,
    km_lo: float | None = None,
    km_hi: float | None = None,
) -> dict[str, dict[str, float]]:
    """Per-class draft metres split by accept-draft vs no-input policy on overlapping span."""
    policies = draft_preservation_policies(terrain_map)
    by_class: dict[str, dict[str, float]] = {}
    for seg in cluster_segments(terrain_map):
        s0, s1 = _segment_km_bounds(seg)
        cls = str(seg.get("surface_class", "S2"))
        o0, o1 = s0, s1
        if km_lo is not None:
            o0 = max(o0, km_lo)
        if km_hi is not None:
            o1 = min(o1, km_hi)
        if o1 <= o0:
            continue
        length = o1 - o0
        bucket = by_class.setdefault(cls, {"accept_draft": 0.0, "no_input": 0.0, "other": 0.0})
        if policies and _class_is_no_input_on_span(o0, o1, cls, policies):
            bucket["no_input"] += length
        elif policies and _class_is_accept_draft_on_span(o0, o1, cls, policies):
            bucket["accept_draft"] += length
        else:
            bucket["other"] += length
    return by_class


def deferred_guidance_overrides(terrain_map: dict[str, Any]) -> list[dict[str, Any]]:
    """Operator guidance stored in JSON but deferred pending σ revisit."""
    return [ov for ov in guidance_overrides(terrain_map) if ov.get("deferred")]


def _merge_km_class_runs(
    rows: list[tuple[float, float, str, str]],
) -> list[dict[str, Any]]:
    """Merge consecutive (km0, km1, class, kind) tuples into display spans."""
    if not rows:
        return []
    ordered = sorted(rows, key=lambda item: (item[3], item[2], item[0]))
    merged: list[dict[str, Any]] = []
    cur_km0, cur_km1, cur_cls, cur_kind = ordered[0]
    for km0, km1, cls, kind in ordered[1:]:
        if cls == cur_cls and kind == cur_kind and km0 <= cur_km1 + 0.002:
            cur_km1 = max(cur_km1, km1)
        else:
            merged.append({"km0": cur_km0, "km1": cur_km1, "class": cur_cls, "kind": cur_kind})
            cur_km0, cur_km1, cur_cls, cur_kind = km0, km1, cls, kind
    merged.append({"km0": cur_km0, "km1": cur_km1, "class": cur_cls, "kind": cur_kind})
    return merged


def _v1_overlay_visible(
    effective_class: str,
    source_layer: str,
    gmm_class: str,
) -> bool:
    if source_layer in ("lock", "guidance"):
        return True
    return effective_class != gmm_class


def collect_v1_display_spans(
    terrain_map: dict[str, Any],
    v1_df: pd.DataFrame | None,
    *,
    km_lo: float,
    km_hi: float,
) -> list[dict[str, Any]]:
    """Spans for subtle v1 HITL overlay: deferred intent + effective class ≠ GMM."""
    segments = cluster_segments(terrain_map)
    spans: list[dict[str, Any]] = []

    for ov in deferred_guidance_overrides(terrain_map):
        km0 = max(float(ov["course_km_start"]), km_lo)
        km1 = min(float(ov["course_km_end"]), km_hi)
        if km1 <= km0:
            continue
        cls = str(ov.get("surface_class", "S2"))
        gmm_mid = surface_class_for_km(segments, 0.5 * (km0 + km1))
        spans.append(
            {
                "km0": km0,
                "km1": km1,
                "class": cls,
                "kind": "deferred",
                "label_v1": cls != gmm_mid,
            }
        )

    if v1_df is not None and not v1_df.empty:
        work = v1_df[(v1_df["course_km"] >= km_lo) & (v1_df["course_km"] < km_hi)].sort_values(
            "course_km"
        )
        run_rows: list[tuple[float, float, str, str]] = []
        for row in work.itertuples(index=False):
            km = float(row.course_km)
            eff = getattr(row, "effective_class", None)
            src = str(getattr(row, "source_layer", ""))
            if eff is None or (isinstance(eff, float) and pd.isna(eff)):
                continue
            eff_s = str(eff)
            gmm = surface_class_for_km(segments, km)
            if not _v1_overlay_visible(eff_s, src, gmm):
                continue
            run_rows.append((km, km + 0.001, eff_s, src))
        for span in _merge_km_class_runs(run_rows):
            gmm_mid = surface_class_for_km(segments, 0.5 * (span["km0"] + span["km1"]))
            span["label_v1"] = span["class"] != gmm_mid
            spans.append(span)
    return spans


def resolve_v1_effective_df(
    terrain_map: dict[str, Any],
    panel: pd.DataFrame,
    *,
    km_lo: float,
    km_hi: float,
    v1_df: pd.DataFrame | None = None,
) -> pd.DataFrame | None:
    """Load sidecar parquet for [km_lo, km_hi) or compute v1 effective inline."""
    from spatial.hitl_v1_layer import build_hitl_v1_effective

    if v1_df is not None and not v1_df.empty and "course_km" in v1_df.columns:
        window = v1_df[
            (v1_df["course_km"] >= km_lo) & (v1_df["course_km"] < km_hi)
        ].copy()
        if not window.empty:
            return window.reset_index(drop=True)
    return build_hitl_v1_effective(terrain_map, panel, km_lo, km_hi)


def annotate_v1_hitl_on_class_axis(
    ax: plt.Axes,
    terrain_map: dict[str, Any],
    class_to_y: dict[str, int],
    *,
    km_lo: float,
    km_hi: float,
    v1_df: pd.DataFrame | None = None,
) -> None:
    """Subtle v1 HITL tint/outline on draft-class row (locks, deferred intent, v1 ≠ GMM)."""
    spans = collect_v1_display_spans(terrain_map, v1_df, km_lo=km_lo, km_hi=km_hi)
    if not spans:
        return
    ymin, ymax = ax.get_ylim()
    for span in spans:
        km0 = float(span["km0"])
        km1 = float(span["km1"])
        cls = str(span["class"])
        kind = str(span.get("kind", "v1"))
        deferred = kind == "deferred"
        y = class_to_y.get(cls, 1)
        color = SURFACE_COLORS.get(cls, "#888888")
        fill_alpha = V1_HITL_DEFERRED_FILL_ALPHA if deferred else V1_HITL_FILL_ALPHA
        edge_alpha = V1_HITL_DEFERRED_EDGE_ALPHA if deferred else V1_HITL_EDGE_ALPHA
        ax.fill_between(
            [km0, km1],
            y - 0.22,
            y + 0.22,
            color=color,
            alpha=fill_alpha,
            zorder=4,
        )
        rect = Rectangle(
            (km0, y - 0.22),
            km1 - km0,
            0.44,
            fill=False,
            edgecolor=V1_HITL_EDGE_COLOR,
            linestyle=":" if deferred else "-",
            linewidth=V1_HITL_LINEWIDTH,
            alpha=edge_alpha,
            zorder=5,
        )
        ax.add_patch(rect)
        if span.get("label_v1") and km1 - km0 >= MIN_SEGMENT_LABEL_SPAN_KM:
            ax.text(
                (km0 + km1) / 2,
                y + 0.48,
                "v1",
                ha="center",
                va="bottom",
                fontsize=5.5,
                color=V1_HITL_EDGE_COLOR,
                alpha=0.85,
                zorder=8,
            )
    ax.set_ylim(ymin, ymax)


def annotate_variance_gaps(
    ax: plt.Axes,
    gaps: list[dict[str, Any]],
    *,
    km_lo: float | None = None,
    km_hi: float | None = None,
) -> None:
    """Light grey fill for HITL-deferred high-σ spans."""
    for gap in gaps:
        km0 = float(gap["course_km_start"])
        km1 = float(gap["course_km_end"])
        if km_lo is not None and km1 < km_lo:
            continue
        if km_hi is not None and km0 > km_hi:
            continue
        _solid_axvspan(
            ax,
            km0,
            km1,
            facecolor=VARIANCE_GAP_COLOR,
            alpha=VARIANCE_GAP_ALPHA,
            zorder=3,
            edgecolor="#BDBDBD",
            linewidth=0.7,
            edge_alpha=VARIANCE_GAP_EDGE_ALPHA,
        )


AGREEMENT_TIER_COLORS = {
    "gold": "#FFD700",
    "silver": "#B0BEC5",
    "bronze": "#CD7F32",
    "review": "#FF5252",
    "abstain": "#616161",
}


def operator_gold_spans(terrain_map: dict[str, Any]) -> list[dict[str, Any]]:
    return list(terrain_map.get("hitl", {}).get("operator_gold_spans") or [])


def is_map_first_operator_gold(terrain_map: dict[str, Any]) -> bool:
    """Map-first HITL courses use operator_gold_spans[] only — not GMM/seed draft on export."""
    clustering = terrain_map.get("clustering") or {}
    if clustering.get("fallback") == "map_first_operator_gold":
        return True
    return str((terrain_map.get("corridor") or {}).get("race_id") or "") == "tverrfjell"


def collect_decision_assigned_spans(
    terrain_map: dict[str, Any],
    *,
    km_lo: float,
    km_hi: float,
    v1_df: pd.DataFrame | None = None,
    agreement_df: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    """Decision view: operator gold where locked; seed draft fills unlabeled gaps on map-first courses."""
    return collect_assigned_class_spans(
        terrain_map,
        km_lo=km_lo,
        km_hi=km_hi,
        v1_df=v1_df,
        agreement_df=agreement_df,
    )


def operator_gold_assigned_spans(
    terrain_map: dict[str, Any],
    km_lo: float,
    km_hi: float,
) -> list[dict[str, Any]]:
    """operator_gold_spans[] clipped to window — decision-mode map/strip overlay."""
    assigned: list[dict[str, Any]] = []
    for span in operator_gold_spans(terrain_map):
        s0 = float(span.get("course_km_start", span.get("course_m_start", 0) / 1000.0))
        s1 = float(span.get("course_km_end", span.get("course_m_end", s0) / 1000.0))
        if s1 <= km_lo or s0 >= km_hi:
            continue
        km0 = max(s0, km_lo)
        km1 = min(s1, km_hi)
        if km1 <= km0 + 1e-9:
            continue
        entry: dict[str, Any] = {
            "km0": km0,
            "km1": km1,
            "class": str(span.get("surface_class", "S2")),
            "kind": "operator_gold",
        }
        tier = str(span.get("friction_tier", "")).strip().upper()
        if tier:
            entry["friction_tier"] = tier
        assigned.append(entry)
    return assigned


def annotate_operator_gold_on_class_axis(
    ax: plt.Axes,
    terrain_map: dict[str, Any],
    class_to_y: dict[str, int],
    *,
    km_lo: float,
    km_hi: float,
) -> None:
    """Gold border on draft-class row for operator-promoted ML-ready spans."""
    spans = operator_gold_spans(terrain_map)
    if not spans:
        return
    y_max = max(class_to_y.values())
    for span in spans:
        km0 = float(span["course_km_start"])
        km1 = float(span["course_km_end"])
        if km1 < km_lo or km0 > km_hi:
            continue
        cls = str(span.get("surface_class", "S2"))
        y = class_to_y.get(cls, y_max)
        _solid_yband(
            ax,
            km0,
            km1,
            y - 0.35,
            y + 0.35,
            facecolor="none",
            alpha=0.0,
            zorder=10,
            edgecolor=OPERATOR_GOLD_EDGE_COLOR,
            linewidth=OPERATOR_GOLD_LINEWIDTH,
            edge_alpha=OPERATOR_GOLD_EDGE_ALPHA,
        )


def annotate_agreement_tiers_on_class_axis(
    ax: plt.Axes,
    agreement_df: pd.DataFrame,
    class_to_y: dict[str, int],
    *,
    km_lo: float,
    km_hi: float,
) -> None:
    """Agreement tier tint on surface-class row (gold/silver/bronze/review/abstain)."""
    if agreement_df is None or agreement_df.empty:
        return
    work = agreement_df.sort_values("course_km")
    rows: list[tuple[float, tuple[Any, ...]]] = []
    for row in work.itertuples(index=False):
        km = float(row.course_km)
        if km < km_lo or km >= km_hi:
            continue
        if str(getattr(row, "gold_source", "") or "") == "operator":
            continue
        tier = str(getattr(row, "agreement_tier", "review"))
        cls = getattr(row, "effective_class", None) or getattr(row, "majority_class", None)
        cls_key = str(cls) if cls is not None else ""
        rows.append((km, (tier, cls_key)))
    y_max = max(class_to_y.values())
    for km0, km1, (tier, cls_key) in _rle_metre_rows(rows):
        color = AGREEMENT_TIER_COLORS.get(tier, "#888888")
        alpha = AGREEMENT_TIER_ALPHA.get(tier, 0.18)
        y = class_to_y.get(cls_key, y_max) if cls_key else y_max + 0.2
        border = tier in ("review", "abstain")
        _solid_yband(
            ax,
            km0,
            km1,
            y - 0.42,
            y + 0.42,
            facecolor=color,
            alpha=alpha,
            zorder=8,
            edgecolor=color if border else None,
            linewidth=0.55 if border else 0.0,
            edge_alpha=0.38 if tier == "abstain" else 0.45,
        )


def annotate_majority_draft_on_class_axis(
    ax: plt.Axes,
    majority_df: pd.DataFrame,
    class_to_y: dict[str, int],
    *,
    km_lo: float,
    km_hi: float,
) -> None:
    """Low-alpha v2 majority class track offset below GMM draft row."""
    if majority_df is None or majority_df.empty:
        return
    offset = TI_DRAFT_TRACK_OFFSET + 0.35
    rows: list[tuple[float, tuple[Any, ...]]] = []
    for row in majority_df.itertuples(index=False):
        km = float(row.course_km)
        if km < km_lo or km >= km_hi:
            continue
        if bool(getattr(row, "is_tie", False)) or getattr(row, "majority_class", None) is None:
            continue
        cls = str(row.majority_class)
        rows.append((km, (cls,)))
    for km0, km1, (cls,) in _rle_metre_rows(rows):
        y = class_to_y.get(cls, 1) - offset
        color = SURFACE_COLORS.get(cls, "#888888")
        _solid_yband(
            ax,
            km0,
            km1,
            y - 0.18,
            y + 0.18,
            facecolor=color,
            alpha=MAJORITY_DRAFT_ALPHA,
            zorder=2,
            edgecolor=color,
            linewidth=0.6,
            edge_alpha=MAJORITY_DRAFT_EDGE_ALPHA,
        )


def _apply_hitl_layers_on_profile_axes(
    ax: plt.Axes,
    terrain_map: dict[str, Any],
    *,
    km_lo: float | None = None,
    km_hi: float | None = None,
    gap_class_row_only: bool = False,
) -> None:
    """Cluster draft spans + variance gaps + lock tint + guidance annotation."""
    if not gap_class_row_only:
        gaps = variance_gaps(terrain_map)
        if gaps:
            annotate_variance_gaps(ax, gaps, km_lo=km_lo, km_hi=km_hi)
    policies = draft_preservation_policies(terrain_map)
    segment_span_ax(ax, cluster_segments(terrain_map), 0, 1, policies=policies)
    lock_ovs = manual_overrides_by_mode(terrain_map, "lock")
    if lock_ovs:
        annotate_lock_spans(ax, lock_ovs, km_lo=km_lo, km_hi=km_hi)
    guidance = active_guidance_overrides(terrain_map)
    if guidance:
        annotate_guidance_spans(ax, guidance, km_lo=km_lo, km_hi=km_hi)


def surface_class_for_km(segments: list[dict[str, Any]], km: float) -> str:
    for seg in segments:
        km0 = seg.get("course_km_start", seg.get("course_m_start", 0) / 1000.0)
        km1 = seg.get("course_km_end", seg.get("course_m_end", km0) / 1000.0)
        if km0 <= km < km1 or (km >= km1 and abs(km - km1) < 1e-6):
            return str(seg.get("surface_class", "S2"))
    return "S2"


def course_geography(
    panel: pd.DataFrame,
    km_lo: float,
    km_hi: float,
) -> pd.DataFrame:
    """Median lat/lon per course km in window (cross-athlete consensus track)."""
    if "latitude" not in panel.columns or "longitude" not in panel.columns:
        return pd.DataFrame()
    work = panel[(panel["course_km"] >= km_lo) & (panel["course_km"] <= km_hi)].copy()
    if work.empty or work["latitude"].isna().all():
        return pd.DataFrame()
    geo = (
        work.groupby("course_km", as_index=False)
        .agg(latitude=("latitude", "median"), longitude=("longitude", "median"))
        .sort_values("course_km")
    )
    return geo.dropna(subset=["latitude", "longitude"])


def filter_map_track_panel(
    panel: pd.DataFrame,
    *,
    activity_id: str | None = None,
    donor_id: str | None = None,
    session_type: str | None = "race",
) -> pd.DataFrame:
    """Restrict panel rows used for map-track GPS (avoid multi-activity median drift)."""
    work = panel
    if activity_id and "activity_id" in work.columns:
        work = work[work["activity_id"] == activity_id]
    elif session_type and "session_type" in work.columns:
        sub = work[work["session_type"] == session_type]
        work = sub if not sub.empty else work
    if donor_id and "donor_id" in work.columns:
        work = work[work["donor_id"] == donor_id]
    return work


def select_primary_telemetry_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Race sessions for multi-athlete corridors; full panel for training-only courses."""
    if "session_type" not in panel.columns:
        return panel
    race = panel[panel["session_type"] == "race"]
    return race if not race.empty else panel


def build_activity_track_geography(
    panel: pd.DataFrame,
    stream_km_lo: float,
    stream_km_hi: float,
    *,
    activity_id: str | None = None,
    donor_id: str | None = None,
    session_type: str | None = "race",
    step_km: float = 0.01,
) -> pd.DataFrame:
    """Dense race/activity FIT GPS on the stream course_km axis for map overlays."""
    work = filter_map_track_panel(
        panel,
        activity_id=activity_id,
        donor_id=donor_id,
        session_type=session_type,
    )
    sub = work[
        (work["course_km"] >= stream_km_lo) & (work["course_km"] <= stream_km_hi)
    ].dropna(subset=["latitude", "longitude"])
    if sub.empty:
        return pd.DataFrame()
    geo = (
        sub.groupby("course_km", as_index=False)
        .agg(latitude=("latitude", "median"), longitude=("longitude", "median"))
        .sort_values("course_km")
    )
    geo = geo.dropna(subset=["latitude", "longitude"])
    if geo.empty or len(geo) < 2:
        return geo
    stream_ticks = np.arange(stream_km_lo, stream_km_hi + step_km * 0.5, step_km)
    km_arr = geo["course_km"].to_numpy(dtype=float)
    return pd.DataFrame(
        {
            "course_km": stream_ticks,
            "latitude": np.interp(stream_ticks, km_arr, geo["latitude"].to_numpy(dtype=float)),
            "longitude": np.interp(stream_ticks, km_arr, geo["longitude"].to_numpy(dtype=float)),
        }
    )


def resolve_default_map_track_activity(
    panel_path: Path,
    terrain_map: dict[str, Any],
    panel: pd.DataFrame,
) -> tuple[str | None, str | None]:
    """Auto map-track FIT for known HITL corridors (SUT_43 race, Tverrfjell training loop)."""
    corridor = terrain_map.get("corridor") or {}
    race_id = str(corridor.get("race_id") or "")

    if race_id == "tverrfjell":
        if "activity_id" in panel.columns:
            for act in sorted(panel["activity_id"].astype(str).unique()):
                if "tverrfjell" in act.lower():
                    donor = None
                    if "donor_id" in panel.columns:
                        sub = panel[panel["activity_id"].astype(str) == act]
                        if not sub.empty:
                            donor = str(sub["donor_id"].iloc[0])
                    return act, donor
        return "Tverrfjell_20260704", "Subject_A"

    if race_id != "SUT_43":
        return None, None
    if "sut43" not in panel_path.as_posix():
        return None, None
    if "activity_id" not in panel.columns:
        return None, DEFAULT_SUT43_MAP_TRACK_DONOR
    if DEFAULT_SUT43_RACE_ACTIVITY_ID in set(panel["activity_id"].astype(str)):
        return DEFAULT_SUT43_RACE_ACTIVITY_ID, DEFAULT_SUT43_MAP_TRACK_DONOR
    return None, None


def plot_sclass_track(
    ax: plt.Axes,
    geo: pd.DataFrame,
    segments: list[dict[str, Any]],
    *,
    km_axis: str = "course_km",
    km_lo: float | None = None,
    km_hi: float | None = None,
    linewidth: float = 3.0,
    alpha: float = 0.92,
    zorder: int = 4,
    policies: list[dict[str, Any]] | None = None,
) -> None:
    """Plot a lat/lon polyline coloured by draft surface class per segment."""
    if km_axis not in geo.columns:
        return
    pts = geo.sort_values(km_axis)
    if len(pts) < 2:
        return
    for i in range(len(pts) - 1):
        row0, row1 = pts.iloc[i], pts.iloc[i + 1]
        km_mid = 0.5 * (float(row0[km_axis]) + float(row1[km_axis]))
        if km_lo is not None and km_mid < km_lo:
            continue
        if km_hi is not None and km_mid > km_hi:
            continue
        cls = surface_class_for_km(segments, km_mid)
        color = SURFACE_COLORS.get(cls, "#888888")
        xs = [row0["longitude"], row1["longitude"]]
        ys = [row0["latitude"], row1["latitude"]]
        if cls == "S1":
            ax.plot(
                xs,
                ys,
                color="#2a2a2a",
                linewidth=linewidth + 1.4,
                alpha=alpha,
                solid_capstyle="round",
                zorder=zorder - 1,
            )
        ax.plot(
            xs,
            ys,
            color=color,
            linewidth=linewidth,
            alpha=alpha,
            solid_capstyle="round",
            zorder=zorder,
        )


def estimate_gpx_stream_offset_km(
    panel: pd.DataFrame,
    gpx_path: Path,
    *,
    offset_panel: pd.DataFrame | None = None,
    stream_km_lo: float | None = None,
    stream_km_hi: float | None = None,
) -> float:
    """
    Median (GPX distance_km − stream course_km) from panel GPS.

    SUT_43 uses stream-distance axis; organiser GPX km labels differ by ~1–1.8 km
    along-track. Used to paint S-class on GPX centerline while profiles stay on stream km.

    When stream_km_lo/hi are set, offset is estimated only inside that window so chunk
    maps do not inherit a corridor-wide median that drifts ~200 m laterally at km 37+.
    """
    work = (offset_panel if offset_panel is not None else panel).dropna(
        subset=["latitude", "longitude", "course_km"]
    )
    if stream_km_lo is not None and stream_km_hi is not None:
        work = work[(work["course_km"] >= stream_km_lo) & (work["course_km"] <= stream_km_hi)]
    if work.empty or not gpx_path.exists():
        return 0.0
    course = load_gpx_course_km(gpx_path)
    step = max(1, len(work) // 400)
    sub = work.iloc[::step]
    snapped = project_course_km(sub, race_id=None, gpx_path=gpx_path)
    gpx_km = snapped["course_km"].to_numpy(dtype=float)
    stream = sub["course_km"].to_numpy(dtype=float)
    valid = np.isfinite(gpx_km) & np.isfinite(stream)
    if not valid.any():
        return 0.0
    return float(np.median(gpx_km[valid] - stream[valid]))


def gpx_geography_for_stream_window(
    gpx_path: Path,
    stream_km_lo: float,
    stream_km_hi: float,
    *,
    gpx_stream_offset_km: float,
) -> pd.DataFrame:
    """Organiser GPX lat/lon in a stream-km window via along-track offset."""
    course = load_gpx_course_km(gpx_path)
    gpx_lo = stream_km_lo + gpx_stream_offset_km
    gpx_hi = stream_km_hi + gpx_stream_offset_km
    sub = course[(course["distance_km"] >= gpx_lo) & (course["distance_km"] <= gpx_hi)].copy()
    if sub.empty:
        return pd.DataFrame()
    sub["course_km"] = sub["distance_km"] - gpx_stream_offset_km
    return sub[["latitude", "longitude", "course_km", "distance_km"]].reset_index(drop=True)


def build_map_track_geography(
    gpx_path: Path,
    stream_km_lo: float,
    stream_km_hi: float,
    panel: pd.DataFrame,
    *,
    step_km: float = 0.01,
    offset_panel: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Dense organiser GPX centerline on the stream course_km axis for map overlays.

    Seeds from sparse GPX vertices (constant stream→GPX offset), then interpolates
    lat/lon at regular stream-km steps — stays on GPX geometry, not panel GPS.
    """
    offset = estimate_gpx_stream_offset_km(
        panel,
        gpx_path,
        offset_panel=offset_panel,
        stream_km_lo=stream_km_lo,
        stream_km_hi=stream_km_hi,
    )
    sparse = gpx_geography_for_stream_window(
        gpx_path, stream_km_lo, stream_km_hi, gpx_stream_offset_km=offset
    )
    if sparse.empty or len(sparse) < 2:
        return sparse
    sparse = sparse.sort_values("course_km")
    stream_ticks = np.arange(stream_km_lo, stream_km_hi + step_km * 0.5, step_km)
    km_arr = sparse["course_km"].to_numpy(dtype=float)
    return pd.DataFrame(
        {
            "course_km": stream_ticks,
            "latitude": np.interp(stream_ticks, km_arr, sparse["latitude"].to_numpy(dtype=float)),
            "longitude": np.interp(stream_ticks, km_arr, sparse["longitude"].to_numpy(dtype=float)),
            "distance_km": np.interp(stream_ticks, km_arr, sparse["distance_km"].to_numpy(dtype=float)),
        }
    )


def _format_course_km_label(km: float) -> str:
    rounded = round(km, 3)
    if abs(rounded - round(rounded)) < 1e-6:
        return f"{int(round(rounded))}"
    return f"{rounded:.1f}".rstrip("0").rstrip(".")


def _interp_latlon_at_km(geo: pd.DataFrame, km: float) -> tuple[float, float] | None:
    if geo.empty or len(geo) < 2 or "course_km" not in geo.columns:
        return None
    g = geo.sort_values("course_km")
    lo = float(g["course_km"].iloc[0])
    hi = float(g["course_km"].iloc[-1])
    if km < lo - 1e-9 or km > hi + 1e-9:
        return None
    lat = float(np.interp(km, g["course_km"].to_numpy(), g["latitude"].to_numpy()))
    lon = float(np.interp(km, g["course_km"].to_numpy(), g["longitude"].to_numpy()))
    return lat, lon


def _regular_km_ticks(km_lo: float, km_hi: float, step: float) -> list[float]:
    start = np.floor(float(km_lo) / step + 1e-9) * step
    ticks: list[float] = []
    km = float(start)
    while km <= float(km_hi) + 1e-9:
        if km >= float(km_lo) - 1e-9:
            ticks.append(round(km, 3))
        km += step
    if ticks and ticks[-1] < float(km_hi) - 1e-9:
        end = round(float(km_hi), 3)
        if end not in ticks:
            ticks.append(end)
    return ticks


def _course_km_marker_ticks(km_lo: float, km_hi: float) -> list[float]:
    span = max(float(km_hi) - float(km_lo), 0.0)
    step = (
        COURSE_KM_MARKER_STEP_SHORT
        if span <= COURSE_KM_MARKER_SHORT_SPAN_KM
        else COURSE_KM_MARKER_STEP_LONG
    )
    return _regular_km_ticks(km_lo, km_hi, step)


def _format_100m_distance_label(km: float) -> str:
    return f"{km:.1f}"


def _track_bearing_deg(geo: pd.DataFrame, km: float, eps: float = 0.05) -> float | None:
    pt0 = _interp_latlon_at_km(geo, km - eps)
    pt1 = _interp_latlon_at_km(geo, km + eps)
    if pt0 is None or pt1 is None:
        return None
    lat0, lon0 = pt0
    lat1, lon1 = pt1
    dlon = lon1 - lon0
    dlat = lat1 - lat0
    if abs(dlon) < 1e-12 and abs(dlat) < 1e-12:
        return None
    return float(np.degrees(np.arctan2(dlon, dlat)))


def _offset_latlon_by_bearing(
    lat: float,
    lon: float,
    bearing_deg: float,
    distance_deg: float,
) -> tuple[float, float]:
    br = np.radians(bearing_deg)
    dlat = distance_deg * np.cos(br)
    dlon = distance_deg * np.sin(br) / max(np.cos(np.radians(lat)), 1e-6)
    return lat + dlat, lon + dlon


def plot_100m_distance_markers(
    ax: plt.Axes,
    geo: pd.DataFrame,
    km_lo: float,
    km_hi: float,
    *,
    map_bounds: tuple[float, float, float, float],
) -> None:
    """Subtle 100 m ticks + labels on the basemap centerline (chunk window)."""
    ticks = _regular_km_ticks(km_lo, km_hi, COURSE_100M_MARKER_STEP)
    if not ticks:
        return
    _, south, _, north = map_bounds
    tick_len = max((north - south) * COURSE_100M_TICK_FRAC, 0.00004)
    label_dist = max((north - south) * COURSE_100M_LABEL_FRAC, 0.00008)
    for km in ticks:
        pt = _interp_latlon_at_km(geo, km)
        if pt is None:
            continue
        lat, lon = pt
        bearing = _track_bearing_deg(geo, km)
        if bearing is not None:
            lat_a, lon_a = _offset_latlon_by_bearing(lat, lon, bearing + 90.0, tick_len)
            lat_b, lon_b = _offset_latlon_by_bearing(lat, lon, bearing - 90.0, tick_len)
            ax.plot(
                [lon_a, lon_b],
                [lat_a, lat_b],
                color="#D8D8D8",
                linewidth=0.45,
                alpha=0.82,
                solid_capstyle="round",
                zorder=7,
            )
            label_lat, label_lon = _offset_latlon_by_bearing(
                lat, lon, bearing - 90.0, label_dist
            )
        else:
            ax.plot(
                [lon, lon],
                [lat - tick_len, lat + tick_len],
                color="#D8D8D8",
                linewidth=0.45,
                alpha=0.82,
                solid_capstyle="round",
                zorder=7,
            )
            label_lat, label_lon = lat - label_dist, lon
        text = ax.text(
            label_lon,
            label_lat,
            _format_100m_distance_label(km),
            ha="center",
            va="top",
            fontsize=COURSE_100M_LABEL_FONTSIZE,
            color="#E8E8E8",
            zorder=8,
        )
        text.set_path_effects(
            [pe.withStroke(linewidth=1.1, foreground="#1A1A1A", alpha=0.75)]
        )


def plot_course_km_markers(
    ax: plt.Axes,
    geo: pd.DataFrame,
    km_lo: float,
    km_hi: float,
    *,
    map_bounds: tuple[float, float, float, float],
    km_step: float | None = None,
) -> None:
    """Small stream-km labels on the panel centerline for chunk ↔ profile correlation."""
    if km_step is not None:
        ticks = _regular_km_ticks(km_lo, km_hi, float(km_step))
    else:
        ticks = _course_km_marker_ticks(km_lo, km_hi)
    if not ticks:
        return
    _, south, _, north = map_bounds
    label_offset = max((north - south) * 0.012, 0.00012)
    for km in ticks:
        pt = _interp_latlon_at_km(geo, km)
        if pt is None:
            continue
        lat, lon = pt
        ax.plot(
            lon,
            lat,
            marker="o",
            markersize=2.4,
            color="#FFFFFF",
            markeredgecolor="#1A1A1A",
            markeredgewidth=0.35,
            zorder=8,
        )
        text = ax.text(
            lon,
            lat + label_offset,
            _format_course_km_label(km),
            ha="center",
            va="bottom",
            fontsize=7.0,
            color="#F5F5F5",
            zorder=9,
        )
        text.set_path_effects(
            [pe.withStroke(linewidth=1.6, foreground="#111111", alpha=0.85)]
        )


def plot_athlete_tracks_faint(
    ax: plt.Axes,
    panel: pd.DataFrame,
    km_lo: float,
    km_hi: float,
    *,
    skip_when_gpx_track: bool = False,
) -> None:
    """Per-donor raw GPS polylines for multi-athlete spread context."""
    if skip_when_gpx_track or "donor_id" not in panel.columns:
        return
    work = panel[(panel["course_km"] >= km_lo) & (panel["course_km"] <= km_hi)]
    for donor in sorted(work["donor_id"].unique()):
        sub = (
            work[work["donor_id"] == donor]
            .dropna(subset=["latitude", "longitude"])
            .sort_values("course_km")
        )
        if len(sub) < 2:
            continue
        ax.plot(
            sub["longitude"],
            sub["latitude"],
            color="#AAAAAA",
            linewidth=0.55,
            alpha=0.38,
            solid_capstyle="round",
            zorder=2,
        )


def render_reference_map(
    ax: plt.Axes,
    panel: pd.DataFrame,
    terrain_map: dict[str, Any],
    *,
    viewport_km: tuple[float, float],
    chunk_km: tuple[float, float] | None = None,
    gpx_path: Path | None = None,
    basemap: BasemapChoice = DEFAULT_BASEMAP_LAYER,
    ml_pred_df: pd.DataFrame | None = None,
    ml_map_alpha: float = ML_MAP_TRACK_ALPHA,
    decision_mode: bool = False,
    assigned_spans: list[dict[str, Any]] | None = None,
    map_track_activity: str | None = None,
    map_track_donor: str | None = None,
    map_display_aspect: float | None = None,
    require_basemap: bool = False,
    lat_offset: float = 0.0,
    lon_offset: float = 0.0,
    show_map_km_markers: bool = True,
    show_fit_track_caption: bool = True,
    map_km_marker_step_km: float | None = None,
) -> tuple[str, bool, bool]:
    """Topo basemap + race FIT or GPX S-class centerline, faint athlete GPS, chunk highlight."""
    panel = offset_panel_gps(panel, lat_offset=lat_offset, lon_offset=lon_offset)
    km_lo, km_hi = viewport_km
    geo_lo, geo_hi = km_lo, km_hi
    if chunk_km is not None:
        geo_lo, geo_hi = float(chunk_km[0]), float(chunk_km[1])
    draft_segments = cluster_segments(terrain_map)
    lock_segments = effective_segments(terrain_map)
    guidance = active_guidance_overrides(terrain_map)
    gaps = variance_gaps(terrain_map)
    draft_policies = draft_preservation_policies(terrain_map)
    map_segments = lock_segments if manual_overrides_by_mode(terrain_map, "lock") else draft_segments
    track_panel = filter_map_track_panel(
        panel,
        activity_id=map_track_activity,
        donor_id=map_track_donor,
        session_type="race" if map_track_activity is None else None,
    )
    geo_full = course_geography(track_panel, geo_lo, geo_hi)
    if geo_full.empty:
        geo_full = course_geography(panel, geo_lo, geo_hi)
    if geo_full.empty and (gpx_path is None or not gpx_path.exists()):
        ax.text(
            0.5,
            0.5,
            "No lat/lon in panel for map overlay",
            transform=ax.transAxes,
            ha="center",
            va="center",
            color="#888",
        )
        ax.set_axis_off()
        return "no geography", False, False

    gpx_offset = 0.0
    gpx_geo = pd.DataFrame()
    allow_gpx = corridor_allows_gpx_overlay(terrain_map)
    use_gpx_track = allow_gpx and gpx_path is not None and gpx_path.exists()
    fit_geo = build_activity_track_geography(
        panel,
        geo_lo,
        geo_hi,
        activity_id=map_track_activity,
        donor_id=map_track_donor,
        session_type="race" if map_track_activity is None else None,
    )
    use_fit_track = not fit_geo.empty
    if use_gpx_track:
        gpx_offset = estimate_gpx_stream_offset_km(
            panel,
            gpx_path,
            offset_panel=track_panel,
            stream_km_lo=geo_lo,
            stream_km_hi=geo_hi,
        )
        gpx_geo = build_map_track_geography(
            gpx_path, geo_lo, geo_hi, panel, offset_panel=track_panel
        )
        if gpx_geo.empty:
            gpx_geo = gpx_geography_for_stream_window(
                gpx_path, geo_lo, geo_hi, gpx_stream_offset_km=gpx_offset
            )

    # Prefer dense race FIT GPS on stream course_km (panel rows in km window).
    if use_fit_track:
        track_geo = fit_geo
        track_label = (
            f"race FIT ({map_track_donor or 'panel'})"
            if map_track_activity or map_track_donor
            else "race FIT"
        )
    elif use_gpx_track and not gpx_geo.empty:
        track_geo = gpx_geo
        track_label = "GPX centerline"
    else:
        track_geo = geo_full
        track_label = "panel GPS"
    bounds_geo = track_geo[(track_geo["course_km"] >= geo_lo) & (track_geo["course_km"] <= geo_hi)]
    if bounds_geo.empty:
        bounds_geo = track_geo if not track_geo.empty else geo_full
    if chunk_km is not None:
        c_lo, c_hi = chunk_km
        chunk_geo = bounds_geo[(bounds_geo["course_km"] >= c_lo) & (bounds_geo["course_km"] <= c_hi)]
        if not chunk_geo.empty:
            bounds_geo = chunk_geo
        pad_frac = CHUNK_MAP_PAD_FRAC
    else:
        pad_frac = VIEWPORT_MAP_PAD_FRAC

    reference_geo = fit_geo if not fit_geo.empty else course_geography(panel, geo_lo, geo_hi)
    reference_label = "race FIT GPS" if not fit_geo.empty else "panel consensus"
    mismatch_track = gpx_geo if (use_gpx_track and not gpx_geo.empty) else track_geo
    mismatch_track_label = "GPX centerline" if mismatch_track is gpx_geo else track_label
    if not mismatch_track.empty and not reference_geo.empty and mismatch_track is not track_geo:
        mismatch_lo, mismatch_hi = geo_lo, geo_hi
        scope = (
            f"km {chunk_km[0]:.0f}–{chunk_km[1]:.0f}"
            if chunk_km is not None
            else f"km {km_lo:.0f}–{km_hi:.0f}"
        )
        report_geo_mismatch_stats(
            mismatch_track,
            reference_geo,
            km_lo=mismatch_lo,
            km_hi=mismatch_hi,
            scope=scope,
            reference_label=reference_label,
            track_label=mismatch_track_label,
        )

    map_bounds = _geo_bounds_with_padding(bounds_geo, pad_frac=pad_frac)
    if map_display_aspect is not None and map_display_aspect > 0:
        if abs(map_display_aspect - 1.0) < 0.05:
            map_bounds = _expand_bounds_to_metric_aspect(map_bounds, map_display_aspect)
        else:
            map_bounds = _expand_bounds_to_display_aspect(map_bounds, map_display_aspect)

    ax.set_facecolor("#141414")
    ax.set_xlim(map_bounds[0], map_bounds[2])
    ax.set_ylim(map_bounds[1], map_bounds[3])
    ax.set_aspect("equal", adjustable="box")
    basemap_layer = normalize_basemap_layer(basemap)
    if basemap_layer == "satellite_flyfoto" and not nib_wmts_token_configured():
        basemap_status = "no (NIB_WMTS_TOKEN required for Kartverket orthophoto)"
    else:
        basemap_status = _try_add_basemap(ax, basemap, map_bounds)
        ax.set_xlim(map_bounds[0], map_bounds[2])
        ax.set_ylim(map_bounds[1], map_bounds[3])
    if basemap_status.startswith("no"):
        scope = (
            f"km {chunk_km[0]:.0f}–{chunk_km[1]:.0f}"
            if chunk_km is not None
            else f"km {km_lo:.0f}–{km_hi:.0f}"
        )
        msg = (
            f"map basemap missing ({scope}): {basemap_status} "
            f"(tiles cache: {TILE_CACHE_ROOT.relative_to(BASE_DIR)})"
        )
        _safe_log_error(msg)
        if require_basemap:
            raise RuntimeError(msg)

    if allow_gpx and gpx_path is not None and gpx_path.exists() and not gpx_geo.empty:
        try:
            g_lat, g_lon = load_gpx_latlon(gpx_path)
            step = max(1, len(g_lat) // 2000)
            ax.plot(
                g_lon[::step],
                g_lat[::step],
                color="#444444",
                linewidth=0.6,
                alpha=0.35,
                solid_capstyle="round",
                zorder=1,
            )
        except (ValueError, OSError):
            pass

    faint_lo, faint_hi = geo_lo, geo_hi
    plot_athlete_tracks_faint(
        ax,
        panel,
        faint_lo,
        faint_hi,
        skip_when_gpx_track=not track_geo.empty and (use_gpx_track or use_fit_track),
    )

    if not decision_mode:
        plot_sclass_track(ax, track_geo, map_segments, linewidth=3.2, zorder=4, policies=draft_policies)
        if guidance:
            plot_guidance_track_overlay(ax, track_geo, guidance, km_lo=km_lo, km_hi=km_hi)

    if chunk_km is not None:
        c_lo, c_hi = chunk_km
        if not decision_mode:
            plot_sclass_track(
                ax,
                track_geo,
                map_segments,
                km_lo=c_lo,
                km_hi=c_hi,
                linewidth=6.0,
                alpha=1.0,
                zorder=6,
                policies=draft_policies,
            )
            if guidance:
                plot_guidance_track_overlay(
                    ax,
                    track_geo,
                    guidance,
                    km_lo=c_lo,
                    km_hi=c_hi,
                )
        chunk_geo = track_geo[(track_geo["course_km"] >= c_lo) & (track_geo["course_km"] <= c_hi)]
        if not chunk_geo.empty:
            pad_m = 60.0
            center_lat = float(chunk_geo["latitude"].mean())
            lon_m_per_deg = 111_320.0 * max(np.cos(np.radians(center_lat)), 1e-6)
            pad_lon = pad_m / lon_m_per_deg
            pad_lat = pad_m / 111_320.0
            west = float(chunk_geo["longitude"].min()) - pad_lon
            east = float(chunk_geo["longitude"].max()) + pad_lon
            south = float(chunk_geo["latitude"].min()) - pad_lat
            north = float(chunk_geo["latitude"].max()) + pad_lat
            rect = Rectangle(
                (west, south),
                east - west,
                north - south,
                fill=False,
                edgecolor="#00E5FF",
                linewidth=2.4,
                linestyle="-",
                zorder=7,
            )
            ax.add_patch(rect)

    ml_km_lo, ml_km_hi = viewport_km
    if chunk_km is not None:
        ml_km_lo, ml_km_hi = chunk_km

    assigned_map_drawn = False
    if decision_mode:
        plot_faint_centerline_track(
            ax,
            track_geo,
            km_lo=ml_km_lo,
            km_hi=ml_km_hi,
        )
        assigned_map_drawn = plot_assigned_gold_track_overlay(
            ax,
            track_geo,
            assigned_spans,
            km_lo=ml_km_lo,
            km_hi=ml_km_hi,
        )
        if assigned_map_drawn:
            plot_assigned_span_labels_on_map(
                ax,
                track_geo,
                assigned_spans,
                km_lo=ml_km_lo,
                km_hi=ml_km_hi,
            )
            plot_gold_class_seam_markers(
                ax,
                track_geo,
                assigned_spans,
                km_lo=ml_km_lo,
                km_hi=ml_km_hi,
            )

    ml_map_drawn = plot_ml_pred_track_overlay(
        ax,
        track_geo,
        ml_pred_df,
        km_lo=ml_km_lo,
        km_hi=ml_km_hi,
        alpha=ml_map_alpha,
        linewidth=ML_MAP_TRACK_LINEWIDTH if decision_mode else 5.0,
        offset_m=ML_MAP_TRACK_OFFSET_M if decision_mode else 0.0,
    )

    if chunk_km is not None and not track_geo.empty and show_map_km_markers:
        c_lo, c_hi = chunk_km
        if map_km_marker_step_km is None:
            plot_100m_distance_markers(
                ax,
                track_geo,
                c_lo,
                c_hi,
                map_bounds=map_bounds,
            )
        plot_course_km_markers(
            ax,
            track_geo,
            c_lo,
            c_hi,
            map_bounds=map_bounds,
            km_step=map_km_marker_step_km,
        )

    ax.set_xticks([])
    ax.set_yticks([])
    plot_metric_scalebar(ax, map_bounds)

    if chunk_km is not None and not track_geo.empty and show_fit_track_caption:
        c_lo, c_hi = chunk_km
        chunk_pts = track_geo[
            (track_geo["course_km"] >= c_lo) & (track_geo["course_km"] <= c_hi)
        ]
        if not chunk_pts.empty:
            clat = float(chunk_pts["latitude"].mean())
            clon = float(chunk_pts["longitude"].mean())
            west, south, east, north = map_bounds
            ax.text(
                west + (east - west) * 0.02,
                south + (north - south) * 0.04,
                f"FIT track {clat:.4f}°N {clon:.4f}°E",
                fontsize=6.5,
                color="#ECEFF1",
                zorder=20,
                va="bottom",
                bbox=dict(
                    boxstyle="round,pad=0.25",
                    facecolor=(0, 0, 0, 0.55),
                    edgecolor="none",
                ),
            )

    return basemap_status, ml_map_drawn, assigned_map_drawn


def plot_spine_athlete_nti_overlays(
    ax: plt.Axes,
    race_work: pd.DataFrame,
    *,
    km_lo: float,
    km_hi: float,
) -> None:
    """Faint per-subject NTI traces on ref_chainage_m axis for cross-athlete QC."""
    if not is_spine_panel(race_work):
        return
    sid_col = subject_id_column(race_work)
    if race_work[sid_col].nunique() < 2:
        return
    for sid in sorted(race_work[sid_col].astype(str).unique()):
        sub = race_work[race_work[sid_col].astype(str) == sid].copy()
        sub["nti"] = compute_nti(sub)
        profile = (
            sub[(sub["course_km"] >= km_lo) & (sub["course_km"] < km_hi)]
            .groupby("course_km", as_index=False)["nti"]
            .median()
        )
        if profile.empty:
            continue
        color = SPINE_ATHLETE_NTI_COLORS.get(sid, "#CCCCCC")
        ax.plot(
            profile["course_km"],
            profile["nti"],
            color=color,
            linewidth=0.85,
            alpha=0.68,
            label=f"{sid} NTI",
        )


def compute_variance_flags(
    panel: pd.DataFrame,
    *,
    threshold: float = DEFAULT_VARIANCE_THRESHOLD,
    session_type: str | None = "race",
) -> list[dict[str, Any]]:
    """
    Flag course metres where cross-athlete NTI std exceeds threshold.

    Uses race sessions by default (training tiles excluded from consensus QC).
    """
    work = panel.copy()
    if session_type and "session_type" in work.columns:
        work = work[work["session_type"] == session_type]
    work["nti"] = compute_nti(work)
    agg = work.groupby("course_m", as_index=False).agg(
        nti_std=("nti", "std"),
        nti_median=("nti", "median"),
        course_km=("course_km", "first"),
        n_athletes=("donor_id", "nunique"),
    )
    hot = agg[(agg["nti_std"] >= threshold) & (agg["n_athletes"] >= 2)].copy()
    flags: list[dict[str, Any]] = []
    for row in hot.itertuples(index=False):
        flags.append(
            {
                "course_m": float(row.course_m),
                "course_km": float(row.course_km),
                "nti_std": float(row.nti_std),
                "nti_median": float(row.nti_median) if pd.notna(row.nti_median) else None,
                "n_athletes": int(row.n_athletes),
                "flag": "high_nti_variance",
                "threshold": threshold,
            }
        )
    return flags


def run_length_flag_segments(
    flags: list[dict[str, Any]],
    *,
    min_span_m: float = 50.0,
) -> list[dict[str, Any]]:
    """Merge adjacent flagged metres into review segments."""
    if not flags:
        return []
    df = pd.DataFrame(flags).sort_values("course_m")
    segments: list[dict[str, Any]] = []
    start_m = float(df.iloc[0]["course_m"])
    end_m = start_m
    max_std = float(df.iloc[0]["nti_std"])
    for row in df.iloc[1:].itertuples(index=False):
        cm = float(row.course_m)
        if cm - end_m <= 1.5:
            end_m = cm
            max_std = max(max_std, float(row.nti_std))
        else:
            if end_m - start_m + 1 >= min_span_m:
                segments.append(
                    {
                        "course_m_start": start_m,
                        "course_m_end": end_m + 1.0,
                        "course_km_start": start_m / 1000.0,
                        "course_km_end": (end_m + 1.0) / 1000.0,
                        "max_nti_std": max_std,
                        "flag": "high_nti_variance",
                    }
                )
            start_m = cm
            end_m = cm
            max_std = float(row.nti_std)
    if end_m - start_m + 1 >= min_span_m:
        segments.append(
            {
                "course_m_start": start_m,
                "course_m_end": end_m + 1.0,
                "course_km_start": start_m / 1000.0,
                "course_km_end": (end_m + 1.0) / 1000.0,
                "max_nti_std": max_std,
                "flag": "high_nti_variance",
            }
        )
    return segments


def build_validation_report(
    terrain_map: dict[str, Any],
    panel: pd.DataFrame,
    *,
    variance_threshold: float = DEFAULT_VARIANCE_THRESHOLD,
    structural_invoice: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble validation dashboard metadata (flags + override protocol)."""
    flags = compute_variance_flags(panel, threshold=variance_threshold)
    segments = run_length_flag_segments(flags)
    race_panel = select_primary_telemetry_panel(panel)
    consensus = aggregate_nti_by_course_m(race_panel) if not race_panel.empty else pd.DataFrame()

    report: dict[str, Any] = {
        "schema_version": "spatial_validation_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "terrain_map_schema": terrain_map.get("schema_version"),
        "hitl_status": terrain_map.get("hitl", {}).get("status", "draft"),
        "calibration_credibility_index": terrain_map.get("calibration_credibility_index", {}).get("index"),
        "variance_threshold": variance_threshold,
        "n_flagged_metres": len(flags),
        "flagged_segments": segments,
        "flagged_metres": flags,
        "override_protocol": OVERRIDE_PROTOCOL.strip(),
        "manual_override_path": "terrain map JSON → hitl.manual_overrides[]",
    }
    if not consensus.empty and "nti_std" in consensus.columns:
        report["consensus_nti_std_median"] = float(consensus["nti_std"].median(skipna=True))
    if structural_invoice:
        report["structural_invoice_ref"] = structural_invoice.get("generated_at")
        report["paradisskaret_invoice"] = {
            donor: data.get("paradisskaret_sector")
            for donor, data in structural_invoice.get("per_donor", {}).items()
        }
    return report


def _normalize_assigned_class(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s or s == "unassigned":
        return None
    return s


def _operator_gold_span_at_km(terrain_map: dict[str, Any], km: float) -> dict[str, Any] | None:
    """Narrowest operator-gold span at km (later span wins ties on overlap)."""
    return _pick_span_at_km(operator_gold_spans(terrain_map), km)


def operator_gold_class_at_km(terrain_map: dict[str, Any], km: float) -> str | None:
    span = _operator_gold_span_at_km(terrain_map, km)
    if span is None:
        return None
    return str(span.get("surface_class", "S2"))


def operator_gold_friction_tier_at_km(terrain_map: dict[str, Any], km: float) -> str | None:
    span = _operator_gold_span_at_km(terrain_map, km)
    if span is None:
        return None
    return _normalize_friction_tier(span.get("friction_tier"))


def friction_spans(terrain_map: dict[str, Any]) -> list[dict[str, Any]]:
    return list(terrain_map.get("hitl", {}).get("friction_spans") or [])


def _normalize_friction_tier(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip().upper()
    return s if s else None


def _span_at_km(spans: list[dict[str, Any]], km: float) -> dict[str, Any] | None:
    """Half-open [start, end) match; interior seams resolve to the downstream span."""
    match: dict[str, Any] | None = None
    for span in spans:
        km0 = float(span["course_km_start"])
        km1 = float(span["course_km_end"])
        if km0 <= km < km1:
            match = span
    if match is not None:
        return match
    for span in reversed(spans):
        if abs(km - float(span["course_km_end"])) < 1e-6:
            return span
    return None


def assigned_friction_tier_at_km(terrain_map: dict[str, Any], km: float) -> str | None:
    """F-tier for Assigned strip: operator gold, then friction_spans sidecar."""
    tier = operator_gold_friction_tier_at_km(terrain_map, km)
    if tier is not None:
        return tier
    span = _span_at_km(friction_spans(terrain_map), km)
    if span is None:
        return None
    return _normalize_friction_tier(span.get("friction_tier"))


def friction_tier_edge_color(tier: str | None) -> str | None:
    if not tier:
        return None
    return FRICTION_TIER_EDGE_COLORS.get(str(tier).strip().upper(), "#B39DDB")


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
    return float(2 * r * np.arcsin(np.sqrt(a)))


def report_geo_mismatch_stats(
    track_geo: pd.DataFrame,
    panel_geo: pd.DataFrame,
    *,
    km_lo: float,
    km_hi: float,
    scope: str,
    reference_label: str = "panel",
    track_label: str = "map track",
) -> None:
    """stderr: reference GPS vs map-track offset (alignment QC)."""
    if track_geo.empty or panel_geo.empty:
        return
    dists: list[float] = []
    km = float(km_lo)
    while km <= float(km_hi) + 1e-9:
        pt_track = _interp_latlon_at_km(track_geo, km)
        pt_panel = _interp_latlon_at_km(panel_geo, km)
        if pt_track is not None and pt_panel is not None:
            dists.append(_haversine_m(pt_track[0], pt_track[1], pt_panel[0], pt_panel[1]))
        km = round(km + 0.1, 3)
    if not dists:
        return
    median_m = float(np.median(dists))
    p95_m = float(np.percentile(dists, 95))
    max_m = float(np.max(dists))
    print(
        f"INFO geo mismatch ({scope}): {reference_label} vs {track_label} "
        f"median={median_m:.1f}m p95={p95_m:.1f}m max={max_m:.1f}m (n={len(dists)})",
        file=sys.stderr,
    )


def count_operator_gold_metres(
    terrain_map: dict[str, Any],
    *,
    km_lo: float | None = None,
    km_hi: float | None = None,
) -> float:
    total = 0.0
    for span in operator_gold_spans(terrain_map):
        s0 = float(span["course_km_start"])
        s1 = float(span["course_km_end"])
        o0, o1 = s0, s1
        if km_lo is not None:
            o0 = max(o0, km_lo)
        if km_hi is not None:
            o1 = min(o1, km_hi)
        if o1 > o0:
            total += o1 - o0
    return total


def count_flagged_segments_in_window(
    flag_segments: list[dict[str, Any]],
    *,
    km_lo: float,
    km_hi: float,
) -> int:
    n = 0
    for seg in flag_segments:
        if seg["course_km_end"] < km_lo or seg["course_km_start"] > km_hi:
            continue
        n += 1
    return n


def resolve_assigned_display_at_km(
    km: float,
    terrain_map: dict[str, Any],
    *,
    v1_row: Any | None = None,
    agreement_row: Any | None = None,
) -> tuple[str | None, str]:
    """Return (surface_class, derivation_kind) for one course km in decision mode."""
    gold_cls = operator_gold_class_at_km(terrain_map, km)
    if gold_cls is not None:
        return gold_cls, "operator_gold"

    if agreement_row is not None:
        if bool(getattr(agreement_row, "is_tie", False)):
            v2 = _normalize_assigned_class(getattr(agreement_row, "majority_class", None))
            return v2, "abstain"
        v1_ag = _normalize_assigned_class(getattr(agreement_row, "effective_class", None))
        v2_ag = _normalize_assigned_class(getattr(agreement_row, "majority_class", None))
        if v1_ag is not None and v2_ag is not None and v1_ag != v2_ag:
            return v1_ag, "review"

    if v1_row is not None:
        src = str(getattr(v1_row, "source_layer", "gmm_cluster"))
        cls = _normalize_assigned_class(getattr(v1_row, "effective_class", None))
        if cls is None:
            return None, "unassigned"
        if src == "accept_draft":
            return cls, "accept_draft"
        if src == "lock":
            return cls, "lock"
        if src == "guidance":
            return cls, "review"
        if src == "gmm_cluster":
            return cls, "gmm_draft"
        return cls, "gmm_draft"

    if is_map_first_operator_gold(terrain_map):
        return None, "unassigned"

    gmm = surface_class_for_km(cluster_segments(terrain_map), km)
    return gmm, "gmm_draft"


def collect_assigned_class_spans(
    terrain_map: dict[str, Any],
    *,
    km_lo: float,
    km_hi: float,
    v1_df: pd.DataFrame | None = None,
    agreement_df: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    """Merge per-metre assigned class + derivation into display spans."""
    if v1_df is None:
        v1_df = pd.DataFrame()
    if agreement_df is None:
        agreement_df = pd.DataFrame()

    v1_by_km: dict[float, Any] = {}
    if not v1_df.empty and "course_km" in v1_df.columns:
        for row in v1_df.itertuples(index=False):
            km = float(row.course_km)
            if km_lo <= km < km_hi:
                v1_by_km[km] = row

    agr_by_km: dict[float, Any] = {}
    if not agreement_df.empty and "course_km" in agreement_df.columns:
        for row in agreement_df.itertuples(index=False):
            km = float(row.course_km)
            if km_lo <= km < km_hi:
                agr_by_km[km] = row

    step = 0.001
    km = round(km_lo, 3)
    rows: list[tuple[float, float, str, str, str]] = []
    while km < km_hi - 1e-9:
        cls, kind = resolve_assigned_display_at_km(
            km,
            terrain_map,
            v1_row=v1_by_km.get(km),
            agreement_row=agr_by_km.get(km),
        )
        ft = assigned_friction_tier_at_km(terrain_map, km) or ""
        rows.append((km, km + step, cls or "", kind, ft))
        km = round(km + step, 3)

    if not rows:
        return []

    ordered = sorted(rows, key=lambda item: (item[0], item[3], item[2] or "", item[4]))
    merged: list[dict[str, Any]] = []
    cur_km0, cur_km1, cur_cls, cur_kind, cur_ft = ordered[0]
    for km0, km1, cls, kind, ft in ordered[1:]:
        if kind == cur_kind and cls == cur_cls and ft == cur_ft and km0 <= cur_km1 + 0.002:
            cur_km1 = max(cur_km1, km1)
        else:
            span: dict[str, Any] = {
                "km0": cur_km0,
                "km1": cur_km1,
                "class": cur_cls or None,
                "kind": cur_kind,
            }
            if cur_ft:
                span["friction_tier"] = cur_ft
            merged.append(span)
            cur_km0, cur_km1, cur_cls, cur_kind, cur_ft = km0, km1, cls, kind, ft
    final_span: dict[str, Any] = {
        "km0": cur_km0,
        "km1": cur_km1,
        "class": cur_cls or None,
        "kind": cur_kind,
    }
    if cur_ft:
        final_span["friction_tier"] = cur_ft
    merged.append(final_span)
    return merged


def collect_ml_pred_spans(
    ml_df: pd.DataFrame | None,
    *,
    km_lo: float,
    km_hi: float,
    pred_col: str = "pred_class",
    km_col: str = "course_km",
) -> list[dict[str, Any]]:
    """Merge per-metre ML predictions into display spans (neutral where absent)."""
    if ml_df is None or ml_df.empty or pred_col not in ml_df.columns or km_col not in ml_df.columns:
        return []

    window = ml_df[(ml_df[km_col] >= km_lo) & (ml_df[km_col] < km_hi)]
    pred_by_km: dict[float, str | None] = {}
    for km, pred in zip(window[km_col].astype(float), window[pred_col]):
        pred_by_km[float(km)] = _normalize_assigned_class(pred)

    rows: list[tuple[float, tuple[str | None, ...]]] = []
    step = 0.001
    km = km_lo
    while km < km_hi - 1e-9:
        cls = pred_by_km.get(round(km, 3))
        rows.append((km, (cls,)))
        km = round(km + step, 3)

    return [
        {"km0": km0, "km1": km1, "class": key[0]}
        for km0, km1, key in _rle_metre_rows(rows)
    ]


def resolve_panel_session_type(panel: pd.DataFrame) -> str | None:
    """Single session_type value when unambiguous; else None (no filter)."""
    if "session_type" not in panel.columns:
        return None
    vals = sorted(str(v) for v in panel["session_type"].dropna().unique())
    if len(vals) == 1:
        return vals[0]
    return None


def resolve_locomotion_df(
    panel: pd.DataFrame,
    terrain_map: dict[str, Any],
    panel_path: Path,
    *,
    sidecar: Path | None = None,
    session_type: str | None = None,
) -> pd.DataFrame | None:
    """Load locomotion sidecar or compute four-gate run/hike tags for the strip."""
    sidecar_path = sidecar or (panel_path.parent / "locomotion_mode_1m.parquet")
    if sidecar_path.exists():
        loaded = pd.read_parquet(sidecar_path)
        if "locomotion_mode" in loaded.columns and "course_km" in loaded.columns:
            return loaded

    from spatial.locomotion_mode import tag_panel_locomotion  # noqa: WPS433

    st = session_type if session_type is not None else resolve_panel_session_type(panel)
    try:
        tagged = tag_panel_locomotion(panel, terrain_map, session_type=st)
    except Exception as exc:
        logging.warning("locomotion_mode computation failed: %s", exc)
        return None
    if tagged.empty or "locomotion_mode" not in tagged.columns:
        return None
    export_cols = ["course_m", "course_km", "locomotion_mode"]
    if "donor_id" in tagged.columns:
        export_cols.insert(2, "donor_id")
    return tagged[[c for c in export_cols if c in tagged.columns]]


def collect_locomotion_spans(
    loco_df: pd.DataFrame | None,
    *,
    km_lo: float,
    km_hi: float,
    mode_col: str = "locomotion_mode",
    km_col: str = "course_km",
) -> list[dict[str, Any]]:
    """Merge per-metre run/hike tags into display spans."""
    if loco_df is None or loco_df.empty or mode_col not in loco_df.columns or km_col not in loco_df.columns:
        return []

    window = loco_df[(loco_df[km_col] >= km_lo) & (loco_df[km_col] < km_hi)]
    mode_by_km: dict[float, str | None] = {}
    for km, mode in zip(window[km_col].astype(float), window[mode_col]):
        mode_by_km[float(km)] = str(mode).lower() if pd.notna(mode) else None

    rows: list[tuple[float, tuple[str | None, ...]]] = []
    step = 0.001
    km = km_lo
    while km < km_hi - 1e-9:
        mode = mode_by_km.get(round(km, 3))
        rows.append((km, (mode,)))
        km = round(km + step, 3)

    return [
        {"km0": km0, "km1": km1, "mode": key[0]}
        for km0, km1, key in _rle_metre_rows(rows)
    ]


def annotate_locomotion_mode_strip(
    ax: plt.Axes,
    spans: list[dict[str, Any]],
    *,
    fill_alpha: float = LOCOMOTION_STRIP_FILL_ALPHA,
) -> None:
    """Locomotion strip — low blue bars (hike), tall yellow bars (run)."""
    y_base = 0.0
    for span in spans:
        km0 = float(span["km0"])
        km1 = float(span["km1"])
        mode = str(span.get("mode", "run")).lower()
        if mode == "hike":
            height = LOCOMOTION_HIKE_BAR_HEIGHT
            color = LOCOMOTION_HIKE_COLOR
        else:
            height = LOCOMOTION_RUN_BAR_HEIGHT
            color = LOCOMOTION_RUN_COLOR
        _solid_yband(
            ax,
            km0,
            km1,
            y_base,
            y_base + height,
            facecolor=color,
            alpha=fill_alpha,
            zorder=4,
        )
    y_max = LOCOMOTION_RUN_BAR_HEIGHT * 1.12
    ax.set_ylim(-0.06, y_max)
    ax.axhline(y_base, color="#444444", linewidth=0.5, zorder=1)


def resolve_cluster_ti_parquet_paths(
    panel_path: Path,
    *,
    subject_a: Path | None = None,
    subject_b: Path | None = None,
) -> dict[str, Path]:
    """Default cluster TI parquets beside panel ontology dir; explicit paths override."""
    ontology_dir = panel_path.parent
    defaults = {
        "Subject_A": ontology_dir / "fit_ti_clusters_Subject_A.parquet",
        "Subject_B": ontology_dir / "fit_ti_clusters_Subject_B.parquet",
    }
    for donor, fallback in (
        ("Subject_A", DEFAULT_CLUSTER_TI_PARQUET_A),
        ("Subject_B", DEFAULT_CLUSTER_TI_PARQUET_B),
    ):
        if not defaults[donor].exists() and fallback.exists():
            defaults[donor] = fallback
    if subject_a is not None:
        defaults["Subject_A"] = subject_a if subject_a.is_absolute() else BASE_DIR / subject_a
    if subject_b is not None:
        defaults["Subject_B"] = subject_b if subject_b.is_absolute() else BASE_DIR / subject_b
    return defaults


def load_cluster_ti_parquets(
    panel_path: Path,
    *,
    subject_a: Path | None = None,
    subject_b: Path | None = None,
) -> dict[str, pd.DataFrame]:
    """Load per-athlete cluster TI rank parquets; skip missing files gracefully."""
    paths = resolve_cluster_ti_parquet_paths(
        panel_path, subject_a=subject_a, subject_b=subject_b
    )
    loaded: dict[str, pd.DataFrame] = {}
    for donor_id, path in paths.items():
        if path.exists():
            loaded[donor_id] = pd.read_parquet(path)
    return loaded


def collect_cluster_ti_rank_spans(
    cluster_df: pd.DataFrame | None,
    *,
    km_lo: float,
    km_hi: float,
    rank_col: str = "cluster_ti_rank",
    km_col: str = "course_km",
) -> list[dict[str, Any]]:
    """Merge per-metre cluster_ti_rank values into display spans."""
    if (
        cluster_df is None
        or cluster_df.empty
        or rank_col not in cluster_df.columns
        or km_col not in cluster_df.columns
    ):
        return []

    window = cluster_df[(cluster_df[km_col] >= km_lo) & (cluster_df[km_col] < km_hi)]
    rank_by_km: dict[float, int | None] = {}
    for km, rank in zip(window[km_col].astype(float), window[rank_col]):
        rank_i = int(rank) if pd.notna(rank) else None
        if rank_i is not None and rank_i < 0:
            rank_i = None
        rank_by_km[float(km)] = rank_i

    rows: list[tuple[float, tuple[int | None, ...]]] = []
    step = 0.001
    km = km_lo
    while km < km_hi - 1e-9:
        rows.append((km, (rank_by_km.get(round(km, 3)),)))
        km = round(km + step, 3)

    return [
        {"km0": km0, "km1": km1, "rank": key[0]}
        for km0, km1, key in _rle_metre_rows(rows)
    ]


def cluster_ti_rank_color(rank: int | None) -> str:
    if rank is None or rank < 0:
        return UNASSIGNED_CLASS_COLOR
    return CLUSTER_TI_RANK_COLORS.get(rank, CLUSTER_TI_RANK_COLORS[CLUSTER_TI_RANK_COUNT - 1])


def annotate_cluster_ti_rank_strip_track(
    ax: plt.Axes,
    spans: list[dict[str, Any]],
    y_center: float,
    *,
    half_height: float = DECISION_TRACK_HALF_HEIGHT,
    fill_alpha: float = CLUSTER_TI_RANK_FILL_ALPHA,
    label_ranks: bool = True,
    min_label_span_km: float = MIN_SEGMENT_LABEL_SPAN_KM,
) -> None:
    """Horizontal cluster_ti_rank strip — sequential green→red; highlight rank ≥ threshold."""
    ylo = y_center - half_height
    yhi = y_center + half_height
    for span in spans:
        km0 = float(span["km0"])
        km1 = float(span["km1"])
        rank = span.get("rank")
        rank_i = int(rank) if rank is not None and pd.notna(rank) and int(rank) >= 0 else None
        color = cluster_ti_rank_color(rank_i)
        span_alpha = fill_alpha
        if rank_i is not None and rank_i >= HIGH_CLUSTER_TI_RANK_THRESHOLD:
            edge = CLUSTER_HIGH_RANK_EDGE_COLOR
            edge_lw = CLUSTER_HIGH_RANK_EDGE_LW
            edge_alpha = CLUSTER_HIGH_RANK_EDGE_ALPHA
        elif rank_i is not None:
            edge = "#333333"
            edge_lw = 0.35
            edge_alpha = 0.55
        else:
            edge = None
            edge_lw = 0.0
            edge_alpha = 0.0
            span_alpha = DECISION_UNLABELED_ALPHA
        _solid_yband(
            ax,
            km0,
            km1,
            ylo,
            yhi,
            facecolor=color,
            alpha=span_alpha,
            zorder=4,
            edgecolor=edge,
            linewidth=edge_lw,
            edge_alpha=edge_alpha,
        )
        if (
            label_ranks
            and rank_i is not None
            and km1 - km0 >= min_label_span_km
        ):
            text = ax.text(
                (km0 + km1) / 2,
                y_center,
                f"R{rank_i}",
                ha="center",
                va="center",
                fontsize=6.5,
                color="#EEEEEE" if rank_i >= 2 else "#1a1a1a",
                zorder=6,
            )
            text.set_path_effects(
                [pe.withStroke(linewidth=1.0, foreground="#1A1A1A", alpha=0.75)]
            )


def annotate_class_strip_track(
    ax: plt.Axes,
    spans: list[dict[str, Any]],
    y_center: float,
    *,
    half_height: float = DECISION_TRACK_HALF_HEIGHT,
    fill_alpha: float = DECISION_TRACK_FILL_ALPHA,
    gold_edge_kinds: frozenset[str] | None = None,
    label_classes: bool = False,
    label_friction_tiers: bool = False,
    min_label_span_km: float = MIN_SEGMENT_LABEL_SPAN_KM,
) -> None:
    """One horizontal class strip — S-class fill; F-tier edge on operator gold when set."""
    ylo = y_center - half_height
    yhi = y_center + half_height
    for span in spans:
        km0 = float(span["km0"])
        km1 = float(span["km1"])
        cls = span.get("class")
        kind = str(span.get("kind", ""))
        friction_tier = span.get("friction_tier")
        if cls:
            color = SURFACE_COLORS.get(str(cls), "#888888")
            alpha = fill_alpha
            ft_edge = friction_tier_edge_color(
                str(friction_tier) if friction_tier is not None else None
            )
            if ft_edge is not None and kind == "operator_gold":
                edge = ft_edge
                edge_lw = FRICTION_TIER_EDGE_LW
                edge_alpha = FRICTION_TIER_EDGE_ALPHA
            elif gold_edge_kinds is not None and kind in gold_edge_kinds:
                edge = OPERATOR_GOLD_EDGE_COLOR
                edge_lw = OPERATOR_GOLD_LINEWIDTH
                edge_alpha = OPERATOR_GOLD_EDGE_ALPHA
            else:
                edge = ASSIGNED_CLASS_EDGE_COLOR
                edge_lw = ASSIGNED_CLASS_EDGE_LW
                edge_alpha = ASSIGNED_CLASS_EDGE_ALPHA
        else:
            color = UNASSIGNED_CLASS_COLOR
            alpha = DECISION_UNLABELED_ALPHA
            edge = None
            edge_lw = 0.0
            edge_alpha = 0.0
        _solid_yband(
            ax,
            km0,
            km1,
            ylo,
            yhi,
            facecolor=color,
            alpha=alpha,
            zorder=4,
            edgecolor=edge,
            linewidth=edge_lw,
            edge_alpha=edge_alpha,
        )
        if label_classes and cls and km1 - km0 >= min_label_span_km:
            label = str(cls)
            if label_friction_tiers and friction_tier:
                label = f"{label}/{friction_tier}"
            text = ax.text(
                (km0 + km1) / 2,
                y_center,
                label,
                ha="center",
                va="center",
                fontsize=6.5,
                color="#EEEEEE" if str(cls) != "S1" else "#1a1a1a",
                zorder=6,
            )
            text.set_path_effects(
                [pe.withStroke(linewidth=1.0, foreground="#1A1A1A", alpha=0.75)]
            )


def annotate_decision_class_tracks(
    ax: plt.Axes,
    gold_spans: list[dict[str, Any]],
    ml_spans: list[dict[str, Any]],
    *,
    cluster_a_spans: list[dict[str, Any]] | None = None,
    cluster_b_spans: list[dict[str, Any]] | None = None,
    ml_fill_alpha: float = DECISION_ML_TRACK_FILL_ALPHA,
) -> None:
    """Decision-mode lower plot: assigned, ML, and optional cluster TI rank strips."""
    annotate_class_strip_track(
        ax,
        gold_spans,
        DECISION_GOLD_TRACK_Y,
        gold_edge_kinds=frozenset({"operator_gold"}),
        label_classes=True,
        label_friction_tiers=True,
    )
    annotate_class_strip_track(
        ax,
        ml_spans,
        DECISION_ML_TRACK_Y,
        fill_alpha=ml_fill_alpha,
        label_classes=True,
        min_label_span_km=MIN_ML_PRED_SEGMENT_LABEL_SPAN_KM,
    )
    track_ys = [DECISION_ML_TRACK_Y, DECISION_GOLD_TRACK_Y]
    track_labels = ["ML predicted", "Assigned (gold)"]
    if cluster_a_spans is not None:
        annotate_cluster_ti_rank_strip_track(
            ax, cluster_a_spans, DECISION_CLUSTER_A_TRACK_Y
        )
        track_ys.append(DECISION_CLUSTER_A_TRACK_Y)
        track_labels.append("Subject_A cluster TI rank")
    if cluster_b_spans is not None:
        annotate_cluster_ti_rank_strip_track(
            ax, cluster_b_spans, DECISION_CLUSTER_B_TRACK_Y
        )
        track_ys.append(DECISION_CLUSTER_B_TRACK_Y)
        track_labels.append("Subject_B cluster TI rank")
    y_pairs = sorted(zip(track_ys, track_labels), key=lambda item: item[0])
    for (y_lo, _), (y_hi, _) in zip(y_pairs, y_pairs[1:]):
        ax.axhline((y_lo + y_hi) / 2.0, color="#444444", linewidth=0.6, zorder=1)
    y_min = min(track_ys) - 0.55
    y_max = max(track_ys) + 0.55
    ax.set_ylim(y_min, y_max)
    ax.set_yticks([y for y, _ in y_pairs])
    ax.set_yticklabels([label for _, label in y_pairs])


def annotate_assigned_class_row(
    ax: plt.Axes,
    spans: list[dict[str, Any]],
    class_to_y: dict[str, int],
) -> None:
    """Single assigned-class row coloured by S-class with derivation encoded in border/hatch."""
    y_max = max(class_to_y.values())
    for span in spans:
        km0 = float(span["km0"])
        km1 = float(span["km1"])
        kind = str(span.get("kind", "gmm_draft"))
        cls = span.get("class")
        style = ASSIGNED_SOURCE_STYLE.get(kind, ASSIGNED_SOURCE_STYLE["gmm_draft"])
        if cls:
            y = class_to_y.get(str(cls), y_max)
            color = SURFACE_COLORS.get(str(cls), "#888888")
        else:
            y = y_max + 0.15
            color = UNASSIGNED_CLASS_COLOR
        edge_color = style["edge_color"] or color
        ylo, yhi = y - 0.35, y + 0.35
        ax.fill_between(
            [km0, km1],
            ylo,
            yhi,
            color=color,
            alpha=float(style["fill_alpha"]),
            zorder=4,
            hatch=style.get("hatch"),
        )
        if float(style["edge_lw"]) > 0:
            rect = Rectangle(
                (km0, ylo),
                km1 - km0,
                yhi - ylo,
                fill=False,
                edgecolor=edge_color,
                linewidth=float(style["edge_lw"]),
                linestyle=str(style["linestyle"]),
                alpha=float(style["edge_alpha"]),
                zorder=5,
            )
            ax.add_patch(rect)
        if cls and km1 - km0 >= MIN_SEGMENT_LABEL_SPAN_KM and kind in ("review", "abstain", "unassigned"):
            ax.text(
                (km0 + km1) / 2,
                y,
                str(cls) if cls else "—",
                ha="center",
                va="center",
                fontsize=6.5,
                color="#EEEEEE" if cls != "S1" else "#1a1a1a",
                zorder=6,
            )


def annotate_review_v2_markers(
    ax: plt.Axes,
    majority_df: pd.DataFrame,
    agreement_df: pd.DataFrame,
    class_to_y: dict[str, int],
    *,
    km_lo: float,
    km_hi: float,
) -> None:
    """Thin v2 majority tick below assigned row on review metres only."""
    if majority_df is None or majority_df.empty or agreement_df is None or agreement_df.empty:
        return
    review_km: set[float] = set()
    for row in agreement_df.itertuples(index=False):
        km = float(row.course_km)
        if km < km_lo or km >= km_hi:
            continue
        tier = str(getattr(row, "agreement_tier", ""))
        if tier == "review" or bool(getattr(row, "is_tie", False)):
            review_km.add(km)
    if not review_km:
        return
    y_min = min(class_to_y.values()) - 0.55
    maj_by_km = {
        float(row.course_km): row
        for row in majority_df.itertuples(index=False)
        if km_lo <= float(row.course_km) < km_hi
    }
    for km in sorted(review_km):
        row = maj_by_km.get(km)
        if row is None:
            continue
        v2 = getattr(row, "majority_class", None)
        if v2 is None or bool(getattr(row, "is_tie", False)):
            continue
        cls = str(v2)
        color = SURFACE_COLORS.get(cls, "#888888")
        ax.plot(
            [km, km + 0.001],
            [y_min, y_min],
            color=color,
            linewidth=2.8,
            solid_capstyle="butt",
            alpha=0.75,
            zorder=3,
        )


def plot_profile_grade_axis(
    ax: plt.Axes,
    race_work: pd.DataFrame,
    *,
    outward_pt: float = 52.0,
) -> plt.Axes | None:
    """Left-offset grade (%) axis for decision-mode profile row."""
    grade_col = "grade_pct" if "grade_pct" in race_work.columns else "grade"
    if grade_col not in race_work.columns:
        return None
    grade = race_work.groupby("course_km", as_index=False)[grade_col].median()
    if grade.empty:
        return None
    ax_grade = ax.twinx()
    ax_grade.axhline(0.0, color="#666", linestyle=":", linewidth=0.8, zorder=0)
    ax_grade.plot(grade["course_km"], grade[grade_col], color="#FFB74D", linewidth=0.9, alpha=0.85)
    ax_grade.set_ylabel("Grade (%)", color="#FFB74D")
    ax_grade.tick_params(axis="y", labelcolor="#FFB74D", labelsize=8)
    ax_grade.spines["right"].set_visible(False)
    ax_grade.yaxis.set_ticks_position("left")
    ax_grade.yaxis.set_label_position("left")
    ax_grade.spines["left"].set_position(("outward", outward_pt))
    ax_grade.spines["left"].set_visible(True)
    ax_grade.patch.set_visible(False)
    ax_grade.set_zorder(ax.get_zorder() - 1)
    return ax_grade


def _legend_class_label(spec_label: str, *, compact: bool) -> str:
    """Shorten long ontology labels for the narrow decision-mode legend column."""
    if not compact:
        return spec_label
    return spec_label.split(" / ")[0]


def render_dashboard_legend(
    ax: plt.Axes,
    *,
    decision_mode: bool = False,
    show_assigned_map_track: bool = False,
    show_ml_map_track: bool = False,
    ml_predictions_mode: MLPredictionsMode = "full",
    show_cluster_ti_rank: bool = False,
    show_locomotion_strip: bool = False,
) -> None:
    """Top-right legend panel — compact decision-mode key or full debug symbology."""
    ax.set_facecolor("#121212")
    ax.set_axis_off()

    handles: list[Any] = []
    labels: list[str] = []

    for cid in SURFACE_CLASS_SPECS:
        spec = SURFACE_CLASS_SPECS[cid]
        handles.append(
            Patch(
                facecolor=SURFACE_COLORS[cid],
                edgecolor="#555555",
                linewidth=0.4,
                alpha=0.9,
            )
        )
        short = _legend_class_label(spec.label, compact=decision_mode)
        labels.append(f"{cid} — {short}")

    if decision_mode:
        sample_cls = "S3"
        sample_color = SURFACE_COLORS[sample_cls]
        handles.append(
            Patch(
                facecolor=sample_color,
                edgecolor=FRICTION_TIER_EDGE_COLORS["F3"],
                linewidth=FRICTION_TIER_EDGE_LW,
                alpha=DECISION_TRACK_FILL_ALPHA,
            )
        )
        labels.append("Assigned — operator gold; F-tier edge (F0–F4); label S#/F#")
        handles.append(
            Patch(
                facecolor=sample_color,
                edgecolor=OPERATOR_GOLD_EDGE_COLOR,
                linewidth=OPERATOR_GOLD_LINEWIDTH,
                alpha=DECISION_TRACK_FILL_ALPHA,
            )
        )
        labels.append("Assigned — operator gold without friction_tier (amber edge)")
        handles.append(
            Patch(
                facecolor=sample_color,
                edgecolor=ASSIGNED_CLASS_EDGE_COLOR,
                linewidth=ASSIGNED_CLASS_EDGE_LW,
                alpha=DECISION_TRACK_FILL_ALPHA,
            )
        )
        labels.append("Assigned — class fill; gray edge (non-operator)")
        ml_strip_alpha, ml_map_alpha = ml_track_alphas(ml_predictions_mode)
        handles.append(
            Patch(
                facecolor=sample_color,
                edgecolor="#555555",
                linewidth=0.4,
                alpha=ml_strip_alpha,
            )
        )
        labels.append(ml_legend_label(ml_predictions_mode))
        handles.append(
            Patch(
                facecolor=UNASSIGNED_CLASS_COLOR,
                edgecolor="#616161",
                linewidth=0.55,
                alpha=DECISION_UNLABELED_ALPHA,
            )
        )
        labels.append("Unlabeled / gap")
        if show_cluster_ti_rank:
            for rank in range(CLUSTER_TI_RANK_COUNT):
                handles.append(
                    Patch(
                        facecolor=CLUSTER_TI_RANK_COLORS[rank],
                        edgecolor="#555555",
                        linewidth=0.4,
                        alpha=CLUSTER_TI_RANK_FILL_ALPHA,
                    )
                )
                labels.append(f"Cluster TI rank {rank} (0=low … {CLUSTER_TI_RANK_COUNT - 1}=high)")
            handles.append(
                Patch(
                    facecolor=CLUSTER_TI_RANK_COLORS[HIGH_CLUSTER_TI_RANK_THRESHOLD],
                    edgecolor=CLUSTER_HIGH_RANK_EDGE_COLOR,
                    linewidth=CLUSTER_HIGH_RANK_EDGE_LW,
                    alpha=CLUSTER_TI_RANK_FILL_ALPHA,
                )
            )
            labels.append(
                f"High TI rank (≥R{HIGH_CLUSTER_TI_RANK_THRESHOLD}) — S4/S6 review priority"
            )
        if show_locomotion_strip:
            handles.append(
                Patch(
                    facecolor=LOCOMOTION_HIKE_COLOR,
                    edgecolor="#555555",
                    linewidth=0.4,
                    alpha=LOCOMOTION_STRIP_FILL_ALPHA,
                )
            )
            labels.append("Hike — low blue bar")
            handles.append(
                Patch(
                    facecolor=LOCOMOTION_RUN_COLOR,
                    edgecolor="#555555",
                    linewidth=0.4,
                    alpha=LOCOMOTION_STRIP_FILL_ALPHA,
                )
            )
            labels.append("Run — tall yellow bar")
        if show_assigned_map_track:
            handles.append(
                Line2D(
                    [0],
                    [0],
                    color=SURFACE_COLORS["S4"],
                    linewidth=ASSIGNED_MAP_TRACK_LINEWIDTH,
                    solid_capstyle="round",
                    alpha=ASSIGNED_MAP_TRACK_ALPHA,
                )
            )
            labels.append("Assigned (map track)")
        if show_ml_map_track:
            handles.append(
                Line2D(
                    [0],
                    [0],
                    color=SURFACE_COLORS["S4"],
                    linewidth=ML_MAP_TRACK_LINEWIDTH,
                    solid_capstyle="round",
                    alpha=ml_map_alpha,
                )
            )
            labels.append(f"{ml_legend_label(ml_predictions_mode)} (map track)")
        legend = ax.legend(
            handles,
            labels,
            loc="upper left",
            ncol=LEGEND_NCOL,
            frameon=False,
            fontsize=LEGEND_FONT_SIZE,
            labelcolor="#CCCCCC",
            handlelength=LEGEND_HANDLELENGTH,
            handletextpad=LEGEND_HANDLETEXTPAD,
            labelspacing=LEGEND_LABELSPACING,
            borderaxespad=LEGEND_BORDERAXESPAD,
            columnspacing=0.9,
        )
        legend.set_clip_on(True)
        return

    handles.append(Patch(facecolor="#888888", edgecolor="none", alpha=0.7))
    labels.append("GMM draft (class row)")

    sample_cls = "S3"
    sample_color = SURFACE_COLORS[sample_cls]
    handles.append(
        Patch(
            facecolor=sample_color,
            edgecolor=sample_color,
            linewidth=0.7,
            alpha=TI_DRAFT_FILL_ALPHA,
        )
    )
    labels.append("TI-band draft (offset track)")

    handles.append(
        Patch(
            facecolor=sample_color,
            edgecolor=sample_color,
            linewidth=0.6,
            alpha=MAJORITY_DRAFT_ALPHA,
        )
    )
    labels.append("v2 majority draft")

    handles.append(
        Patch(
            facecolor=sample_color,
            edgecolor=V1_HITL_EDGE_COLOR,
            linewidth=V1_HITL_LINEWIDTH,
            alpha=V1_HITL_FILL_ALPHA,
        )
    )
    labels.append("v1 HITL (effective ≠ GMM)")

    handles.append(
        Patch(
            facecolor="none",
            edgecolor=V1_HITL_EDGE_COLOR,
            linewidth=V1_HITL_LINEWIDTH,
            linestyle=":",
            alpha=V1_HITL_DEFERRED_EDGE_ALPHA,
        )
    )
    labels.append("v1 deferred intent")

    handles.append(
        Patch(
            facecolor="none",
            edgecolor=OPERATOR_GOLD_EDGE_COLOR,
            linewidth=OPERATOR_GOLD_LINEWIDTH,
            alpha=OPERATOR_GOLD_EDGE_ALPHA,
        )
    )
    labels.append("Operator gold (ML-ready)")

    handles.append(Patch(facecolor=sample_color, edgecolor="none", alpha=0.92))
    labels.append("Lock override")

    handles.append(
        Line2D(
            [0],
            [0],
            color=sample_color,
            linewidth=2.0,
            linestyle="--",
            alpha=GUIDANCE_EDGE_ALPHA,
        )
    )
    labels.append("Active guidance")

    handles.append(
        Line2D(
            [0],
            [0],
            color=sample_color,
            linewidth=2.2,
            linestyle="-",
            alpha=ACCEPT_DRAFT_EDGE_ALPHA,
        )
    )
    labels.append("Accept GMM draft")

    for tier in ("gold", "silver", "bronze", "review", "abstain"):
        color = AGREEMENT_TIER_COLORS[tier]
        handles.append(
            Patch(
                facecolor=color,
                edgecolor=color if tier in ("review", "abstain") else "none",
                linewidth=0.55 if tier in ("review", "abstain") else 0.0,
                alpha=AGREEMENT_TIER_ALPHA[tier],
            )
        )
        labels.append(f"Agreement — {tier}")

    handles.append(
        Patch(
            facecolor=VARIANCE_GAP_COLOR,
            edgecolor="#BDBDBD",
            linewidth=0.6,
            alpha=VARIANCE_GAP_ALPHA,
        )
    )
    labels.append("σ-gap (deferred)")

    handles.append(
        Patch(
            facecolor="#FF1744",
            edgecolor=FLAG_SEGMENT_EDGE,
            linewidth=0.6,
            alpha=FLAG_SEGMENT_ALPHA,
        )
    )
    labels.append("High σ variance flag")

    if show_ml_map_track:
        _, ml_map_alpha = ml_track_alphas(ml_predictions_mode)
        handles.append(
            Line2D(
                [0],
                [0],
                color=SURFACE_COLORS["S4"],
                linewidth=2.6,
                solid_capstyle="round",
                alpha=ml_map_alpha,
            )
        )
        labels.append(f"{ml_legend_label(ml_predictions_mode)} (map track)")

    legend = ax.legend(
        handles,
        labels,
        loc="upper right",
        ncol=LEGEND_NCOL,
        frameon=False,
        fontsize=LEGEND_FONT_SIZE,
        labelcolor="#CCCCCC",
        handlelength=LEGEND_HANDLELENGTH,
        handletextpad=LEGEND_HANDLETEXTPAD,
        labelspacing=LEGEND_LABELSPACING,
        borderaxespad=LEGEND_BORDERAXESPAD,
        columnspacing=0.9,
    )
    legend.set_clip_on(True)


def resolve_viewport_km(
    terrain_map: dict[str, Any],
    panel: pd.DataFrame,
) -> tuple[float, float]:
    """
    Corridor km bounds aligned to panel telemetry.

    Stale corridor metadata (e.g. SUT_160 Dale window on a SUT_43 panel) must not
    drive xlim — off-axis segment spans inflate bbox_inches=\"tight\" exports.
    """
    work = panel.sort_values("course_m")
    p_lo = float(work["course_km"].min())
    p_hi = float(work["course_km"].max())
    corridor = terrain_map.get("corridor") or {}
    c_lo = corridor.get("km_start")
    c_hi = corridor.get("km_end")
    if c_lo is not None and c_hi is not None:
        c_lo, c_hi = float(c_lo), float(c_hi)
        if c_lo <= p_hi + 0.5 and c_hi >= p_lo - 0.5:
            lo, hi = max(c_lo, p_lo), min(c_hi, p_hi)
        else:
            lo, hi = p_lo, p_hi
    else:
        lo, hi = p_lo, p_hi
    pad = max((hi - lo) * 0.01, 0.05)
    return lo - pad, hi + pad


def render_validation_dashboard(
    terrain_map: dict[str, Any],
    panel: pd.DataFrame,
    *,
    output_path: Path,
    variance_threshold: float = DEFAULT_VARIANCE_THRESHOLD,
    structural_invoice: dict[str, Any] | None = None,
    flag_segments: list[dict[str, Any]] | None = None,
    chunk_window: tuple[float, float] | None = None,
    with_map: bool = False,
    gpx_path: Path | None = None,
    map_track_activity: str | None = None,
    map_track_donor: str | None = None,
    ti_draft_segments: list[dict[str, Any]] | None = None,
    show_ti_draft: bool = False,
    agreement_df: pd.DataFrame | None = None,
    majority_df: pd.DataFrame | None = None,
    show_agreement: bool = False,
    show_majority_draft: bool = False,
    gap_class_row_only: bool = False,
    v1_df: pd.DataFrame | None = None,
    show_v1_hitl: bool = True,
    decision_mode: bool = False,
    ml_pred_df: pd.DataFrame | None = None,
    ml_predictions_mode: MLPredictionsMode = "full",
    basemap: BasemapChoice | None = None,
    cluster_ti_dfs: dict[str, pd.DataFrame] | None = None,
    verify_export: bool = False,
    locomotion_df: pd.DataFrame | None = None,
    show_locomotion_strip: bool = False,
) -> Path:
    """Stacked dashboard: map + legend, elevation/grade/NTI profile, assigned or debug class rows."""
    plt.style.use("dark_background")
    if basemap is None:
        basemap = DEFAULT_BASEMAP_LAYER if decision_mode else "opentopomap"
    use_invoice_row = structural_invoice is not None and not decision_mode
    n_profile_rows = 3 if use_invoice_row else 2
    profile_height_ratios = [2.0] + [1.0] * (n_profile_rows - 1)
    if decision_mode:
        profile_height_ratios = [2.25, 1.45 if cluster_ti_dfs else 1.15]
        if show_locomotion_strip:
            profile_height_ratios.append(LOCOMOTION_PROFILE_HEIGHT_RATIO)
            n_profile_rows = len(profile_height_ratios)
        else:
            n_profile_rows = 2
    fig_h = 12.5 if with_map and decision_mode else (12.0 if with_map else FIG_SIZE_IN[1])
    fig_w = DECISION_FIG_WIDTH_IN if with_map and decision_mode else FIG_SIZE_IN[0]
    if with_map:
        fig = plt.figure(figsize=(fig_w, fig_h), facecolor="#0A0A0A")
        top_cols = 2
        top_width_ratios = [TOP_MAP_WIDTH_RATIO, TOP_LEGEND_WIDTH_RATIO]
        n_grid_rows = 1 + n_profile_rows
        map_height = DECISION_TOP_HEIGHT_RATIO if decision_mode else 1.85
        height_ratios: list[float] = [map_height]
        height_ratios.extend(profile_height_ratios)
        gs = fig.add_gridspec(
            n_grid_rows,
            top_cols,
            height_ratios=height_ratios,
            width_ratios=top_width_ratios,
            wspace=0.08,
            hspace=0.22 if decision_mode else 0.24,
        )
        ax_map = fig.add_subplot(gs[0, 0])
        ax_legend = fig.add_subplot(gs[0, 1])
        profile_axes = [
            fig.add_subplot(gs[1 + i, :]) for i in range(n_profile_rows)
        ]
        if n_profile_rows > 1:
            for ax in profile_axes[1:]:
                ax.sharex(profile_axes[0])
    else:
        fig, axes_arr = plt.subplots(
            n_profile_rows,
            1,
            figsize=(FIG_SIZE_IN[0], fig_h),
            sharex=True,
            facecolor="#0A0A0A",
            gridspec_kw={"height_ratios": profile_height_ratios},
        )
        profile_axes = [axes_arr] if n_profile_rows == 1 else list(axes_arr)
        ax_map = None
        ax_legend = None
    axis_label = resolve_axis_label(terrain_map, panel)

    work = panel.sort_values("course_m")
    full_lo, full_hi = resolve_viewport_km(terrain_map, work)
    km_lo, km_hi = full_lo, full_hi
    if chunk_window is not None:
        km_lo, km_hi = float(chunk_window[0]), float(chunk_window[1])
    draft_segments = cluster_segments(terrain_map)
    lock_segments = effective_segments(terrain_map)
    guidance = active_guidance_overrides(terrain_map)
    gaps = variance_gaps(terrain_map)
    lock_ovs = manual_overrides_by_mode(terrain_map, "lock")
    ti_draft = ti_draft_segments if ti_draft_segments is not None else []
    if not ti_draft and show_ti_draft:
        ti_draft = resolve_ti_draft_segments(
            terrain_map,
            panel,
            km_lo=km_lo,
            km_hi=km_hi,
            variance_threshold=variance_threshold,
            enable=True,
        )
    flags = flag_segments or run_length_flag_segments(
        compute_variance_flags(panel, threshold=variance_threshold)
    )

    title_suffix = ""
    if chunk_window is not None:
        title_suffix = f" — km {chunk_window[0]:.0f}–{chunk_window[1]:.0f}"
    title_core = (
        "HITL validation — decision view"
        if decision_mode
        else "Spatial Validation Dashboard — draft classes + variance flags"
    )
    fig.suptitle(
        f"{title_core}{title_suffix}",
        color="white",
        fontsize=14,
        fontweight="bold",
        y=0.98,
    )
    place_label = corridor_geography_label(terrain_map)
    axis_label = resolve_axis_label(terrain_map, panel)
    subtitle = " · ".join(p for p in (place_label, axis_label) if p)
    if subtitle:
        fig.text(
            0.5,
            0.955,
            subtitle,
            ha="center",
            va="top",
            color="#B0BEC5",
            fontsize=9,
        )

    ml_map_drawn = False
    assigned_map_drawn = False
    ml_strip_alpha, ml_map_alpha = ml_track_alphas(ml_predictions_mode)
    assigned_spans_for_map: list[dict[str, Any]] | None = None
    if decision_mode:
        v1_map = resolve_v1_effective_df(
            terrain_map, panel, km_lo=km_lo, km_hi=km_hi, v1_df=v1_df
        )
        agr_map = None
        if agreement_df is not None and not agreement_df.empty:
            agr_map = agreement_df[
                (agreement_df["course_km"] >= km_lo) & (agreement_df["course_km"] < km_hi)
            ]
        assigned_spans_for_map = collect_decision_assigned_spans(
            terrain_map,
            km_lo=km_lo,
            km_hi=km_hi,
            v1_df=v1_map,
            agreement_df=agr_map,
        )
    if with_map and ax_map is not None and ax_legend is not None:
        map_display_aspect = _map_subplot_target_aspect(
            decision_mode=decision_mode,
            with_cluster_ti=bool(cluster_ti_dfs),
            with_locomotion_strip=show_locomotion_strip,
        )
        _, ml_map_drawn, assigned_map_drawn = render_reference_map(
            ax_map,
            panel,
            terrain_map,
            viewport_km=(full_lo, full_hi),
            chunk_km=chunk_window,
            gpx_path=gpx_path,
            basemap=basemap,
            ml_pred_df=ml_pred_df,
            ml_map_alpha=ml_map_alpha,
            decision_mode=decision_mode,
            assigned_spans=assigned_spans_for_map,
            map_track_activity=map_track_activity,
            map_track_donor=map_track_donor,
            map_display_aspect=map_display_aspect,
            require_basemap=decision_mode or chunk_window is not None,
        )
        render_dashboard_legend(
            ax_legend,
            decision_mode=decision_mode,
            show_assigned_map_track=assigned_map_drawn,
            show_ml_map_track=ml_map_drawn,
            ml_predictions_mode=ml_predictions_mode,
            show_cluster_ti_rank=bool(cluster_ti_dfs) and decision_mode,
            show_locomotion_strip=show_locomotion_strip,
        )

    race_work = select_primary_telemetry_panel(work)

    for ax in profile_axes:
        ax.set_xlim(km_lo, km_hi)

    # Row 0 — elevation (left) + consensus NTI (right, twin axis)
    ax0 = profile_axes[0]
    ax0_nti = ax0.twinx()
    ax0_nti.set_facecolor("none")
    ax0_nti.set_zorder(ax0.get_zorder())
    ax0.set_zorder(ax0_nti.get_zorder() + 1)
    ax0.patch.set_visible(False)

    if "altitude_m" in race_work.columns:
        elev = race_work.groupby("course_km", as_index=False)["altitude_m"].median()
        ax0.plot(elev["course_km"], elev["altitude_m"], color="#00E5FF", linewidth=1.2)
    ax0.set_ylabel("Elevation (m)", color="#00E5FF")
    ax0.tick_params(axis="y", labelcolor="#00E5FF")

    if not race_work.empty:
        race_work = race_work.copy()
        race_work["nti"] = compute_nti(race_work)
        consensus = aggregate_nti_by_course_m(race_work)
        if not consensus.empty:
            sigma_alpha = 0.14 if decision_mode else 0.2
            ax0_nti.plot(
                consensus["course_m"] / 1000.0,
                consensus["nti_median"],
                color="#76FF03",
                linewidth=1.2,
                label="consensus NTI median",
            )
            if "nti_std" in consensus.columns:
                ax0_nti.fill_between(
                    consensus["course_m"] / 1000.0,
                    consensus["nti_median"] - consensus["nti_std"],
                    consensus["nti_median"] + consensus["nti_std"],
                    alpha=sigma_alpha,
                    color="#76FF03",
                    label="±1σ across athletes",
                )
            plot_spine_athlete_nti_overlays(
                ax0_nti,
                race_work,
                km_lo=km_lo,
                km_hi=km_hi,
            )
    if decision_mode and not race_work.empty:
        plot_profile_grade_axis(ax0, race_work)
    ax0_nti.axhline(1.0, color="#666", linestyle=":", linewidth=0.8)
    ax0_nti.set_ylabel("NTI", color="#76FF03")
    ax0_nti.tick_params(axis="y", labelcolor="#76FF03")
    ax0_nti.legend(loc="upper right", fontsize=8)

    for seg in flags:
        if seg["course_km_end"] < km_lo or seg["course_km_start"] > km_hi:
            continue
        if decision_mode:
            max_std = float(seg.get("max_nti_std", variance_threshold))
            if max_std >= DECISION_SIGMA_EDGE_THRESHOLD:
                _solid_axvspan(
                    ax0,
                    seg["course_km_start"],
                    seg["course_km_end"],
                    facecolor="#FF1744",
                    alpha=DECISION_SIGMA_FLAG_ALPHA * 2.5,
                    zorder=3,
                )
            else:
                _solid_axvspan(
                    ax0,
                    seg["course_km_start"],
                    seg["course_km_end"],
                    facecolor="#FF1744",
                    alpha=DECISION_SIGMA_FLAG_ALPHA,
                    zorder=3,
                )
        else:
            _solid_axvspan(
                ax0,
                seg["course_km_start"],
                seg["course_km_end"],
                facecolor="#FF1744",
                alpha=FLAG_SEGMENT_ALPHA,
                zorder=4,
                edgecolor=FLAG_SEGMENT_EDGE,
                linewidth=0.6,
                edge_alpha=0.75,
            )
    ax0.grid(color="#2A2A2A", linestyle="--", alpha=0.6)

    row_delta = 1
    if use_invoice_row:
        ax_d = profile_axes[1]
        delta_payload = structural_invoice.get("delta_by_course_m", {})
        for donor_id, rows in delta_payload.items():
            if not rows:
                continue
            km = [r["course_km"] for r in rows if r.get("delta_ti") is not None]
            dt = [r["delta_ti"] for r in rows if r.get("delta_ti") is not None]
            if km:
                ax_d.plot(km, dt, linewidth=1.0, alpha=0.85, label=donor_id)
        ax_d.axhline(0.0, color="#666", linestyle=":", linewidth=0.8)
        ax_d.set_ylabel("ΔTI", color="#A0A0A0")
        ax_d.legend(loc="upper right", fontsize=8)
        _apply_hitl_layers_on_profile_axes(
            ax_d, terrain_map, km_lo=km_lo, km_hi=km_hi, gap_class_row_only=gap_class_row_only
        )
        ax_d.grid(color="#2A2A2A", linestyle="--", alpha=0.6)
        row_delta = 2

    # Surface class row — decision-mode assigned class, or full debug draft stack
    ax2 = profile_axes[row_delta]
    class_to_y = {cid: i for i, cid in enumerate(SURFACE_CLASS_SPECS)}
    v1_window = resolve_v1_effective_df(
        terrain_map, panel, km_lo=km_lo, km_hi=km_hi, v1_df=v1_df
    )

    if decision_mode:
        agr_window = None
        if agreement_df is not None and not agreement_df.empty:
            agr_window = agreement_df[
                (agreement_df["course_km"] >= km_lo) & (agreement_df["course_km"] < km_hi)
            ]
        assigned_spans = collect_decision_assigned_spans(
            terrain_map,
            km_lo=km_lo,
            km_hi=km_hi,
            v1_df=v1_window,
            agreement_df=agr_window,
        )
        ml_spans = collect_ml_pred_spans(ml_pred_df, km_lo=km_lo, km_hi=km_hi)
        cluster_a_spans = None
        cluster_b_spans = None
        if cluster_ti_dfs:
            if "Subject_A" in cluster_ti_dfs:
                cluster_a_spans = collect_cluster_ti_rank_spans(
                    cluster_ti_dfs["Subject_A"], km_lo=km_lo, km_hi=km_hi
                )
            if "Subject_B" in cluster_ti_dfs:
                cluster_b_spans = collect_cluster_ti_rank_spans(
                    cluster_ti_dfs["Subject_B"], km_lo=km_lo, km_hi=km_hi
                )
        annotate_decision_class_tracks(
            ax2,
            assigned_spans,
            ml_spans,
            cluster_a_spans=cluster_a_spans,
            cluster_b_spans=cluster_b_spans,
            ml_fill_alpha=ml_strip_alpha,
        )
        ax2.set_ylabel("Surface class", color="#A0A0A0")
        if show_locomotion_strip and len(profile_axes) > row_delta + 1:
            ax_loco = profile_axes[row_delta + 1]
            loco_spans = collect_locomotion_spans(
                locomotion_df, km_lo=km_lo, km_hi=km_hi
            )
            annotate_locomotion_mode_strip(ax_loco, loco_spans)
            ax_loco.set_ylabel("Locomotion", color="#A0A0A0")
            ax_loco.grid(color="#2A2A2A", linestyle="--", alpha=0.6)
            ax_loco.set_xlabel(axis_label, color="#A0A0A0")
            ax2.set_xlabel("")
        else:
            ax2.set_xlabel(axis_label, color="#A0A0A0")
    else:
        if ti_draft:
            annotate_ti_draft_on_class_axis(
                ax2, ti_draft, class_to_y, km_lo=km_lo, km_hi=km_hi
            )
        for seg in draft_segments:
            cls = seg.get("surface_class", "S2")
            km0 = seg.get("course_km_start", 0)
            km1 = seg.get("course_km_end", km0)
            if km1 < km_lo or km0 > km_hi:
                continue
            y = class_to_y.get(cls, 1)
            ax2.fill_between([km0, km1], y - 0.35, y + 0.35, color=SURFACE_COLORS.get(cls, "#888"), alpha=0.7)
            if km1 - km0 >= MIN_SEGMENT_LABEL_SPAN_KM:
                ax2.text((km0 + km1) / 2, y, cls, ha="center", va="center", fontsize=7, color=("#1a1a1a" if cls == "S1" else "white"))
        if show_v1_hitl:
            annotate_v1_hitl_on_class_axis(
                ax2,
                terrain_map,
                class_to_y,
                km_lo=km_lo,
                km_hi=km_hi,
                v1_df=v1_window,
            )
        if lock_ovs:
            for seg in lock_segments:
                if seg.get("source") != "hitl_override":
                    continue
                cls = seg.get("surface_class", "S2")
                km0 = seg.get("course_km_start", 0)
                km1 = seg.get("course_km_end", km0)
                if km1 < km_lo or km0 > km_hi:
                    continue
                y = class_to_y.get(cls, 1)
                ax2.fill_between(
                    [km0, km1], y - 0.35, y + 0.35, color=SURFACE_COLORS.get(cls, "#888"), alpha=0.92
                )
                if km1 - km0 >= MIN_SEGMENT_LABEL_SPAN_KM:
                    ax2.text((km0 + km1) / 2, y, f"{cls} lock", ha="center", va="center", fontsize=7, color=("#1a1a1a" if cls == "S1" else "white"))
        if guidance:
            annotate_guidance_on_class_axis(ax2, guidance, class_to_y, km_lo=km_lo, km_hi=km_hi)
        if show_majority_draft and majority_df is not None:
            annotate_majority_draft_on_class_axis(
                ax2, majority_df, class_to_y, km_lo=km_lo, km_hi=km_hi
            )
        if show_agreement and agreement_df is not None:
            annotate_agreement_tiers_on_class_axis(
                ax2, agreement_df, class_to_y, km_lo=km_lo, km_hi=km_hi
            )
        if operator_gold_spans(terrain_map):
            annotate_operator_gold_on_class_axis(
                ax2, terrain_map, class_to_y, km_lo=km_lo, km_hi=km_hi
            )
        if gaps and not gap_class_row_only:
            for gap in gaps:
                g0 = float(gap["course_km_start"])
                g1 = float(gap["course_km_end"])
                if g1 < km_lo or g0 > km_hi:
                    continue
                _solid_axvspan(
                    ax2,
                    g0,
                    g1,
                    facecolor=VARIANCE_GAP_COLOR,
                    alpha=VARIANCE_GAP_ALPHA,
                    zorder=2,
                    edgecolor="#BDBDBD",
                    linewidth=0.6,
                    edge_alpha=VARIANCE_GAP_EDGE_ALPHA,
                )
                if g1 - g0 >= MIN_SEGMENT_LABEL_SPAN_KM:
                    ax2.text(
                        (g0 + g1) / 2,
                        max(class_to_y.values()) + 0.55,
                        "deferred — high σ",
                        ha="center",
                        va="bottom",
                        fontsize=6,
                        color="#BDBDBD",
                        style="italic",
                        zorder=9,
                    )
        elif gaps and gap_class_row_only:
            for gap in gaps:
                g0 = float(gap["course_km_start"])
                g1 = float(gap["course_km_end"])
                if g1 < km_lo or g0 > km_hi:
                    continue
                _solid_axvspan(
                    ax2,
                    g0,
                    g1,
                    facecolor=VARIANCE_GAP_COLOR,
                    alpha=VARIANCE_GAP_ALPHA,
                    zorder=2,
                    edgecolor="#BDBDBD",
                    linewidth=0.6,
                    edge_alpha=VARIANCE_GAP_EDGE_ALPHA,
                )
        ylabel = "Draft class"
        if ti_draft:
            ylabel += " (GMM + TI band)"
        if show_majority_draft:
            ylabel += " + v2 majority"
        if show_agreement:
            ylabel += " + agreement"
        if show_v1_hitl:
            ylabel += " + v1 HITL"
        ax2.set_ylabel(ylabel, color="#A0A0A0")
    if not decision_mode:
        ax2.set_yticks(list(class_to_y.values()))
        ax2.set_yticklabels(list(class_to_y.keys()))
    if not (decision_mode and show_locomotion_strip):
        ax2.set_xlabel(axis_label, color="#A0A0A0")
    ax2.grid(color="#2A2A2A", linestyle="--", alpha=0.6)

    if with_map:
        margins = DECISION_MAP_MARGINS if decision_mode else WITH_MAP_MARGINS
        fig.subplots_adjust(**margins)
    else:
        fig.tight_layout(rect=[0, 0.03, 1, 0.96])

    _atomic_savefig(fig, output_path, dpi=FIG_DPI, facecolor="#0A0A0A")
    plt.close(fig)
    if verify_export:
        verify_png_export(output_path)
    return output_path


def write_validation_flags(report: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase D — spatial validation dashboard")
    parser.add_argument(
        "--terrain-map",
        type=Path,
        default=BASE_DIR / "config" / "spatial_terrain_map.json",
    )
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument(
        "--structural-invoice",
        type=Path,
        default=None,
        help="Optional structural_invoice.json from Phase C for ΔTI row",
    )
    parser.add_argument(
        "--variance-threshold",
        type=float,
        default=DEFAULT_VARIANCE_THRESHOLD,
        help=f"NTI std flag threshold (default {DEFAULT_VARIANCE_THRESHOLD})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=VIS_DIR / "spatial_validation_dashboard.png",
    )
    parser.add_argument(
        "--write-flags",
        type=Path,
        default=None,
        help="Write validation flags JSON (e.g. config/spatial_validation_flags.json)",
    )
    parser.add_argument(
        "--print-override-protocol",
        action="store_true",
        help="Print manual override path and exit",
    )
    parser.add_argument(
        "--with-map",
        action="store_true",
        help="Add topo reference map panel with draft S-class track",
    )
    parser.add_argument(
        "--gpx",
        type=Path,
        default=None,
        help="Organiser GPX for map context (default: SUT43 official GPX when race_id is SUT_43)",
    )
    parser.add_argument(
        "--no-gpx",
        action="store_true",
        help="Never load organiser GPX (required for non-SUT stream courses e.g. Tverrfjell)",
    )
    parser.add_argument(
        "--activity",
        default=None,
        help=(
            "Race/activity id for map-track GPS (e.g. SUT43_20260418 Subject_A forward race FIT). "
            "Default: auto for sut43_terrain_ontology HITL exports."
        ),
    )
    parser.add_argument(
        "--map-track-donor",
        default=None,
        help="Donor id for --activity map track (default: Subject_A when --activity auto-resolves)",
    )
    parser.add_argument(
        "--chunk-km",
        type=float,
        default=None,
        help="Review chunk width in km (e.g. 2 for gramstad_band HITL pieces)",
    )
    parser.add_argument(
        "--chunk-index",
        type=int,
        default=None,
        help="0-based chunk index (requires --chunk-km); scopes dashboard to that window",
    )
    parser.add_argument(
        "--km-start",
        type=float,
        default=None,
        help="Chunk export window start km (default: gramstad_band 29.0; upstream dale_paradisskaret_upstream 22.0)",
    )
    parser.add_argument(
        "--km-end",
        type=float,
        default=None,
        help="Chunk export window end km (default: gramstad_band 41.0; upstream dale_paradisskaret_upstream 29.0)",
    )
    parser.add_argument(
        "--export-chunks",
        action="store_true",
        help="Export all chunk PNGs (requires --chunk-km); writes to --output-dir",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_SUT43_HITL_DIR,
        help="Directory for --export-chunks PNG series",
    )
    parser.add_argument(
        "--ti-draft",
        action="store_true",
        help="Overlay TI-band draft (ti_draft_segments[] or compute from panel)",
    )
    parser.add_argument(
        "--agreement",
        action="store_true",
        help="Overlay agreement tiers from hitl_agreement.parquet (v1 vs v2)",
    )
    parser.add_argument(
        "--agreement-parquet",
        type=Path,
        default=None,
        help="Path to hitl_agreement.parquet (default: ontology dir beside panel)",
    )
    parser.add_argument(
        "--majority-draft",
        action="store_true",
        help="Overlay v2 majority-vote draft from hitl_v2_majority.parquet",
    )
    parser.add_argument(
        "--majority-parquet",
        type=Path,
        default=None,
        help="Path to hitl_v2_majority.parquet",
    )
    parser.add_argument(
        "--gap-class-row-only-profile",
        action="store_true",
        help="Show variance-gap tint on surface-class row only (not elevation/NTI rows)",
    )
    parser.add_argument(
        "--decision-mode",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Operator-focused layout (default: on for --chunk-km / --export-chunks)",
    )
    parser.add_argument(
        "--full-overlays",
        action="store_true",
        help="Restore full debug overlays (disables decision mode)",
    )
    parser.add_argument(
        "--debug-mode",
        action="store_true",
        help="Alias for --full-overlays",
    )
    parser.add_argument(
        "--basemap",
        choices=(
            "topo_standard",
            "topo_grayscale",
            "satellite_flyfoto",
            "kartverket-topo",
            "kartverket-gray",
            "opentopomap",
        ),
        default=None,
        help="Map tile layer (registry: topo_standard | topo_grayscale | satellite_flyfoto; "
        "legacy aliases kartverket-topo/gray; maritime layers blocked)",
    )
    parser.add_argument(
        "--ml-predictions",
        "--ml-predictions-parquet",
        dest="ml_predictions_parquet",
        type=Path,
        default=None,
        help="Explicit ML predictions parquet (implies --ml-predictions-mode path)",
    )
    parser.add_argument(
        "--ml-predictions-mode",
        choices=("full", "loocv", "path"),
        default="full",
        help="ML source: full corridor draft guide (default), LOOCV gold QC, or explicit parquet",
    )
    parser.add_argument(
        "--ml-predictions-loocv",
        action="store_true",
        help="Use LOOCV predictions (alias for --ml-predictions-mode loocv)",
    )
    parser.add_argument(
        "--cluster-ti-subject-a",
        type=Path,
        default=None,
        help="Subject_A fit_ti_clusters parquet (default: ontology dir beside panel)",
    )
    parser.add_argument(
        "--cluster-ti-subject-b",
        type=Path,
        default=None,
        help="Subject_B fit_ti_clusters parquet (default: ontology dir beside panel)",
    )
    parser.add_argument(
        "--verify-export",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="PIL-verify PNG after save; exit non-zero on corrupt export (default: on for chunk export)",
    )
    parser.add_argument(
        "--locomotion-sidecar",
        type=Path,
        default=None,
        help="Per-metre locomotion_mode parquet (default: <panel_dir>/locomotion_mode_1m.parquet)",
    )
    parser.add_argument(
        "--no-locomotion-strip",
        action="store_true",
        help="Hide decision-mode locomotion strip (run/hike bars)",
    )
    parser.add_argument(
        "--locomotion-session-type",
        default=None,
        help="session_type filter for on-the-fly locomotion tagging (default: infer from panel)",
    )
    args = parser.parse_args()

    if args.print_override_protocol:
        print(OVERRIDE_PROTOCOL.strip())
        return

    if args.chunk_index is not None and args.chunk_km is None:
        parser.error("--chunk-index requires --chunk-km")
    if args.export_chunks and args.chunk_km is None:
        parser.error("--export-chunks requires --chunk-km")

    verify_export = (
        args.verify_export
        if args.verify_export is not None
        else bool(args.export_chunks or args.chunk_index is not None)
    )

    tmap_path = args.terrain_map if args.terrain_map.is_absolute() else BASE_DIR / args.terrain_map
    panel_path = args.panel if args.panel.is_absolute() else BASE_DIR / args.panel
    out_path = args.output if args.output.is_absolute() else BASE_DIR / args.output
    out_dir = args.output_dir if args.output_dir.is_absolute() else BASE_DIR / args.output_dir

    if not tmap_path.exists():
        raise FileNotFoundError(f"Terrain map not found: {tmap_path}. Run terrain_map_gen.py first.")

    terrain_map = load_terrain_map(tmap_path)
    panel = normalize_panel_axes(pd.read_parquet(panel_path))

    gpx_path = resolve_dashboard_gpx_path(
        terrain_map,
        args.gpx,
        no_gpx=bool(args.no_gpx),
    )

    map_track_activity = args.activity
    map_track_donor = args.map_track_donor
    if map_track_activity is None:
        auto_activity, auto_donor = resolve_default_map_track_activity(
            panel_path, terrain_map, panel
        )
        if auto_activity is not None:
            map_track_activity = auto_activity
            if map_track_donor is None:
                map_track_donor = auto_donor
    elif map_track_donor is None:
        map_track_donor = DEFAULT_SUT43_MAP_TRACK_DONOR

    structural_invoice = None
    if args.structural_invoice:
        inv_path = (
            args.structural_invoice
            if args.structural_invoice.is_absolute()
            else BASE_DIR / args.structural_invoice
        )
        if inv_path.exists():
            structural_invoice = json.loads(inv_path.read_text(encoding="utf-8"))

    report = build_validation_report(
        terrain_map,
        panel,
        variance_threshold=args.variance_threshold,
        structural_invoice=structural_invoice,
    )

    chunk_mode = args.chunk_km is not None
    debug_overlays = args.full_overlays or args.debug_mode
    if debug_overlays:
        decision_mode = False
    elif args.decision_mode is not None:
        decision_mode = args.decision_mode
    else:
        decision_mode = chunk_mode or args.export_chunks
    with_map = args.with_map or chunk_mode or args.export_chunks
    if args.basemap is not None:
        basemap_choice: BasemapChoice = args.basemap
    elif decision_mode or chunk_mode or args.export_chunks:
        basemap_choice = DEFAULT_BASEMAP_LAYER
    else:
        basemap_choice = "opentopomap"
    stored_ti_draft = ti_draft_segments_from_map(terrain_map)
    show_ti_draft = args.ti_draft or bool(stored_ti_draft)
    full_lo, full_hi = resolve_viewport_km(terrain_map, panel.sort_values("course_m"))
    ti_draft_full = resolve_ti_draft_segments(
        terrain_map,
        panel,
        km_lo=full_lo,
        km_hi=full_hi,
        variance_threshold=args.variance_threshold,
        enable=show_ti_draft,
    )

    agreement_df: pd.DataFrame | None = None
    majority_df: pd.DataFrame | None = None
    v1_df: pd.DataFrame | None = None
    v1_path = panel_path.parent / "hitl_v1_effective.parquet"
    if v1_path.exists():
        v1_df = pd.read_parquet(v1_path)
    if args.agreement or args.agreement_parquet is not None or decision_mode:
        agr_path = args.agreement_parquet
        if agr_path is None:
            agr_path = panel_path.parent / "hitl_agreement.parquet"
        else:
            agr_path = agr_path if agr_path.is_absolute() else BASE_DIR / agr_path
        if agr_path.exists():
            agreement_df = pd.read_parquet(agr_path)
    if args.majority_draft or args.majority_parquet is not None or decision_mode:
        maj_path = args.majority_parquet
        if maj_path is None:
            maj_path = panel_path.parent / "hitl_v2_majority.parquet"
        else:
            maj_path = maj_path if maj_path.is_absolute() else BASE_DIR / maj_path
        if maj_path.exists():
            majority_df = pd.read_parquet(maj_path)

    ml_pred_df: pd.DataFrame | None = None
    ml_predictions_mode: MLPredictionsMode = "full"
    if args.ml_predictions_loocv:
        ml_predictions_mode = "loocv"
    elif args.ml_predictions_parquet is not None:
        ml_predictions_mode = "path"
    else:
        ml_predictions_mode = args.ml_predictions_mode  # type: ignore[assignment]
    if ml_predictions_mode == "path" and args.ml_predictions_parquet is None:
        parser.error("--ml-predictions-mode path requires --ml-predictions")

    if decision_mode or with_map:
        if args.ml_predictions_parquet is not None:
            ml_path = resolve_ml_predictions_path(
                mode="path",
                explicit_path=args.ml_predictions_parquet,
            )
            if ml_path.exists():
                ml_pred_df = pd.read_parquet(ml_path)
            else:
                print(f"WARN ML predictions missing: {ml_path.relative_to(BASE_DIR)}")
        elif is_map_first_operator_gold(terrain_map) and not args.ml_predictions_loocv:
            map_first_ml_path = resolve_map_first_ml_predictions_path(panel_path, terrain_map)
            if map_first_ml_path is not None:
                ml_pred_df = pd.read_parquet(map_first_ml_path)
                ml_predictions_mode = "path"
                print(
                    f"INFO map-first ML predictions → {map_first_ml_path.relative_to(BASE_DIR)}"
                )
            else:
                race_id = str((terrain_map.get("corridor") or {}).get("race_id") or "course")
                print(
                    "INFO map-first operator gold — no course ML predictions sidecar "
                    f"(expected {panel_path.parent / f'{race_id}_ml_predictions.parquet'}; "
                    "run export_ml_predictions.py after training gold_suggester)"
                )
        else:
            ml_path = resolve_ml_predictions_path(
                mode=ml_predictions_mode,
                explicit_path=args.ml_predictions_parquet,
            )
            if ml_path.exists():
                ml_pred_df = pd.read_parquet(ml_path)
            elif ml_predictions_mode == "full":
                print(
                    f"WARN full-corridor ML predictions missing: {ml_path.relative_to(BASE_DIR)} "
                    f"(run 07_ML_Models/predict_terrain_full_corridor.py)"
                )

    cluster_ti_dfs: dict[str, pd.DataFrame] | None = None
    if decision_mode:
        cluster_ti_dfs = load_cluster_ti_parquets(
            panel_path,
            subject_a=args.cluster_ti_subject_a,
            subject_b=args.cluster_ti_subject_b,
        )
        if not cluster_ti_dfs:
            cluster_ti_dfs = None

    locomotion_df: pd.DataFrame | None = None
    show_locomotion_strip = decision_mode and not args.no_locomotion_strip
    if show_locomotion_strip:
        sidecar = args.locomotion_sidecar
        if sidecar is not None and not sidecar.is_absolute():
            sidecar = BASE_DIR / sidecar
        locomotion_df = resolve_locomotion_df(
            panel,
            terrain_map,
            panel_path,
            sidecar=sidecar,
            session_type=args.locomotion_session_type,
        )
        if locomotion_df is None or locomotion_df.empty:
            print("WARN locomotion strip — no locomotion_mode data; strip hidden")
            show_locomotion_strip = False
            locomotion_df = None

    def _render_one(
        output: Path,
        chunk_window: tuple[float, float] | None,
    ) -> Path:
        chunk_ti = ti_draft_full
        if chunk_window is not None and ti_draft_full:
            c_lo, c_hi = chunk_window
            chunk_ti = [
                s
                for s in ti_draft_full
                if float(s.get("course_km_end", 0)) >= c_lo
                and float(s.get("course_km_start", 0)) <= c_hi
            ]
        return render_validation_dashboard(
            terrain_map,
            panel,
            output_path=output,
            variance_threshold=args.variance_threshold,
            structural_invoice=structural_invoice,
            flag_segments=report["flagged_segments"],
            chunk_window=chunk_window,
            with_map=with_map,
            gpx_path=gpx_path,
            map_track_activity=map_track_activity,
            map_track_donor=map_track_donor,
            ti_draft_segments=chunk_ti if show_ti_draft and not decision_mode else None,
            show_ti_draft=show_ti_draft and not decision_mode,
            agreement_df=agreement_df,
            majority_df=majority_df,
            show_agreement=(args.agreement or agreement_df is not None) and not decision_mode,
            show_majority_draft=(args.majority_draft or majority_df is not None) and not decision_mode,
            gap_class_row_only=args.gap_class_row_only_profile,
            v1_df=v1_df,
            show_v1_hitl=not decision_mode,
            decision_mode=decision_mode,
            ml_pred_df=ml_pred_df,
            ml_predictions_mode=ml_predictions_mode,
            basemap=basemap_choice,
            cluster_ti_dfs=cluster_ti_dfs,
            verify_export=verify_export,
            locomotion_df=locomotion_df,
            show_locomotion_strip=show_locomotion_strip,
        )

    def _chunk_export_bounds() -> tuple[float, float]:
        km_start = SUT43_PRIMARY_KM_START if args.km_start is None else float(args.km_start)
        km_end = SUT43_PRIMARY_KM_END if args.km_end is None else float(args.km_end)
        work = panel.sort_values("course_m")
        p_lo, p_hi = float(work["course_km"].min()), float(work["course_km"].max())
        return max(km_start, p_lo), min(km_end, p_hi)

    if args.export_chunks:
        km_start, km_end = _chunk_export_bounds()
        chunks = iter_review_chunks(km_start, km_end, chunk_km=float(args.chunk_km))
        out_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        verify_rows: list[tuple[int, str, int, int, int]] = []
        for chunk_i, (idx, lo, hi) in enumerate(chunks):
            fname = f"chunk_{idx:02d}_km{lo:.0f}-{hi:.0f}.png"
            p = _render_one(out_dir / fname, (lo, hi))
            paths.append(p)
            if verify_export:
                nbytes = p.stat().st_size
                from PIL import Image

                with Image.open(p) as im:
                    w, h = im.size
                verify_rows.append((idx, p.name, w, h, nbytes))
                print(f"OK chunk {idx} → {p.relative_to(BASE_DIR)} ({w}x{h}, {nbytes} B)")
            else:
                print(f"OK chunk {idx} → {p.relative_to(BASE_DIR)}")
            if chunk_i + 1 < len(chunks):
                time.sleep(CHUNK_EXPORT_PAUSE_S)
        print(f"OK exported {len(paths)} chunk dashboards → {out_dir.relative_to(BASE_DIR)}")
        if verify_export and verify_rows:
            print("VERIFY chunk export:")
            for idx, name, w, h, nbytes in verify_rows:
                print(f"  chunk_{idx:02d} {name} {w}x{h} {nbytes} B PIL=OK")
    elif args.chunk_index is not None:
        km_start, km_end = _chunk_export_bounds()
        chunks = iter_review_chunks(km_start, km_end, chunk_km=float(args.chunk_km))
        by_idx = {i: (lo, hi) for i, lo, hi in chunks}
        if args.chunk_index not in by_idx:
            raise ValueError(
                f"chunk-index {args.chunk_index} out of range (0..{len(chunks) - 1} for "
                f"km {km_start}–{km_end} @ {args.chunk_km} km chunks)"
            )
        lo, hi = by_idx[args.chunk_index]
        if out_path == VIS_DIR / "spatial_validation_dashboard.png":
            out_path = out_dir / f"chunk_{args.chunk_index:02d}_km{lo:.0f}-{hi:.0f}.png"
        path = _render_one(out_path, (lo, hi))
        print(
            f"OK validation dashboard (chunk {args.chunk_index}, km {lo:.0f}–{hi:.0f}) "
            f"→ {path.relative_to(BASE_DIR)}"
        )
    else:
        path = _render_one(out_path, None)
        print(f"OK validation dashboard → {path.relative_to(BASE_DIR)}")

    print(f"   flagged segments: {len(report['flagged_segments'])} (threshold σ≥{args.variance_threshold})")

    if args.write_flags:
        flags_path = args.write_flags if args.write_flags.is_absolute() else BASE_DIR / args.write_flags
        write_validation_flags(report, flags_path)
        print(f"OK validation flags → {flags_path.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as exc:
        msg = str(exc)
        if "PNG" in msg or "PIL" in msg or "Pillow" in msg:
            print(f"ERROR verify-export failed: {exc}", file=sys.stderr)
            sys.exit(1)
        raise
