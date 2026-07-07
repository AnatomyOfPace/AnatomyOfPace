#!/usr/bin/env python3
"""
Interactive HITL terrain annotator — local Streamlit app (v0.3.1).

Loads RPS triage queue, race panel telemetry, HMM draft blocks, and terrain map
JSON; renders Plotly profile with cross-athlete σ heatmap, dual-layer TI/HMM view,
coordinate-locked zoom, crosshair readout, and click-to-set lock bounds.

Usage (from repo root):
    streamlit run 04_Python_Scripts/spatial/hitl_annotator_app.py --server.headless true

    streamlit run 04_Python_Scripts/spatial/hitl_annotator_app.py -- \\
        --triage-queue 03_Processed_Data/spatial/sut43_terrain_ontology/ground_truth_review/triage_queue_sut43.csv \\
        --lat-offset 0.00012 --lon-offset -0.00008

Dry-run safety test (no Streamlit, no production JSON):
    python3 04_Python_Scripts/spatial/hitl_annotator_app.py --dry-run-test
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Literal

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MPLCONFIGDIR = _REPO_ROOT / ".mplconfig"
_MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPLCONFIGDIR))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

plotly_events = None  # type: ignore[misc, assignment]
_PLOTLY_EVENTS_PKG = "none"
# Custom plotly_events can hang hard-refresh until the component mounts; native st.plotly_chart is stable.
USE_PLOTLY_EVENTS = os.environ.get("HITL_ENABLE_PLOTLY_EVENTS", "").strip().lower() in (
    "1",
    "true",
    "yes",
)
if os.environ.get("HITL_DISABLE_PLOTLY_EVENTS", "").strip().lower() in ("1", "true", "yes"):
    USE_PLOTLY_EVENTS = False

# Only streamlit-plotly-events2 is supported on Streamlit 1.58+.
# Legacy streamlit-plotly-events registers a broken component and can blank the page.
if USE_PLOTLY_EVENTS:
    try:
        from streamlit_plotly_events2 import plotly_events as _plotly_events_fn

        plotly_events = _plotly_events_fn
        _PLOTLY_EVENTS_PKG = "streamlit-plotly-events2"
    except ImportError:
        pass

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.corridor_scope import SUT43_FULL_KM_END, SUT43_FULL_KM_START
from spatial.spatial_hitl_overlay import SURFACE_COLORS, load_terrain_map
from spatial.terrain_map_gen import aggregate_nti_by_course_m, compute_nti
from spatial.validation_dashboard import (
    DEFAULT_BASEMAP_LAYER,
    DEFAULT_SUT43_GPX,
    FRICTION_TIER_EDGE_COLORS,
    HITL_BASEMAP_LAYER_LABELS,
    assert_basemap_not_maritime,
    corridor_allows_gpx_overlay,
    nib_wmts_token_configured,
    normalize_basemap_layer,
    offset_panel_gps,
    operator_gold_class_at_km,
    operator_gold_friction_tier_at_km,
    operator_gold_spans,
    pick_metric_scalebar_length_m,
    plotly_geo_scalebar_annotations,
    resolve_axis_label,
    resolve_default_map_track_activity,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_PANEL = BASE_DIR / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "panel_1m.parquet"
DEFAULT_TERRAIN_MAP = BASE_DIR / "config" / "spatial_terrain_map_sut43.json"
DEFAULT_TRIAGE_QUEUE = (
    BASE_DIR
    / "03_Processed_Data"
    / "spatial"
    / "sut43_terrain_ontology"
    / "ground_truth_review"
    / "triage_queue_sut43.csv"
)
DEFAULT_HMM_DRAFT = BASE_DIR / "07_ML_Models" / "terrain_hmm_sut43_draft_predictions.parquet"

SURFACE_CLASSES = ("S1", "S2", "S3", "S4", "S5", "S6")
FRICTION_TIERS = ("F0", "F1", "F2", "F3", "F4")
SUBJECT_LABELS = ("Subject_A", "Subject_B")
SUBJECT_LEGEND_SHORT = {"Subject_A": "A", "Subject_B": "B"}
QUEUE_COLORS = {"RED": "#EF5350", "YELLOW": "#FFB74D", "GREEN": "#66BB6A"}
DEFAULT_BASEMAP = DEFAULT_BASEMAP_LAYER
BasemapLayerId = Literal["topo_standard", "topo_grayscale", "satellite_flyfoto"]
BASEMAP_LAYER_OPTIONS: list[tuple[str, BasemapLayerId]] = [
    (HITL_BASEMAP_LAYER_LABELS[layer_id], layer_id)
    for layer_id in ("topo_standard", "topo_grayscale", "satellite_flyfoto")
]
TOPO_MAP_SIZE_IN = 7.2
TOPO_MAP_DPI = 130
TOPO_MAP_DISPLAY_ASPECT = 1.0
TOPO_MAP_MAX_DISPLAY_PX = 720
PROFILE_CHART_WIDTH_PX = 800
PROFILE_CHART_HEIGHT_PX = 1020
PROFILE_ROW_COUNT = 6
ROW_TI = 1
ROW_NTI = 2
ROW_SPEED = 3
ROW_GRADE = 4
ROW_PACE = 5
ROW_CAT = 6
PANEL_WINDOW_BUFFER_KM = 0.5
TI_COLORSCALE = "Plasma"
VizMode = Literal["continuous", "categorical"]
PlotlyRerunScope = Literal["none", "fragment", "full"]
APP_VERSION = "0.3.1"


def contextily_available() -> bool:
    try:
        import contextily  # noqa: F401

        return True
    except ImportError:
        return False


def panel_has_geography(panel: pd.DataFrame, km_lo: float, km_hi: float) -> bool:
    if "latitude" not in panel.columns or "longitude" not in panel.columns:
        return False
    win = panel[(panel["course_km"] >= km_lo) & (panel["course_km"] <= km_hi)]
    if win.empty:
        return False
    return bool(win[["latitude", "longitude"]].notna().any().all())


def topo_basemap_available(panel: pd.DataFrame, km_lo: float, km_hi: float) -> bool:
    return contextily_available() and panel_has_geography(panel, km_lo, km_hi)


def spans_overlap(km_start_a: float, km_end_a: float, km_start_b: float, km_end_b: float) -> bool:
    return km_start_a < km_end_b and km_start_b < km_end_a


def find_overlapping_gold_spans(
    existing_spans: list[dict[str, Any]],
    km_start: float,
    km_end: float,
) -> list[dict[str, Any]]:
    overlaps: list[dict[str, Any]] = []
    for span in existing_spans:
        s0 = float(span.get("course_km_start", span.get("course_m_start", 0) / 1000.0))
        s1 = float(span.get("course_km_end", span.get("course_m_end", s0) / 1000.0))
        if spans_overlap(km_start, km_end, s0, s1):
            overlaps.append(span)
    return overlaps


def _png_pixel_size(png_bytes: bytes) -> tuple[int, int]:
    """Read native width/height from PNG IHDR without decoding pixels."""
    if len(png_bytes) < 24 or png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    width = int.from_bytes(png_bytes[16:20], "big")
    height = int.from_bytes(png_bytes[20:24], "big")
    return width, height


def _force_square_axes(ax: plt.Axes, fig: plt.Figure, *, margin_frac: float = 0.06) -> None:
    """Centre a square axes region inside the figure (prevents letterbox stretch)."""
    fig_w, fig_h = fig.get_size_inches()
    side_frac = min(1.0 - 2 * margin_frac, (1.0 - 2 * margin_frac) * (fig_h / fig_w))
    if fig_w < fig_h:
        side_frac = min(1.0 - 2 * margin_frac, (1.0 - 2 * margin_frac) * (fig_w / fig_h))
    left = (1.0 - side_frac) / 2.0
    bottom = (1.0 - side_frac) / 2.0
    ax.set_position([left, bottom, side_frac, side_frac])


def _ensure_square_png(png_bytes: bytes) -> bytes:
    """Pad non-square PNG exports to a square canvas (centre-paste)."""
    nat_w, nat_h = _png_pixel_size(png_bytes)
    if nat_w == nat_h:
        return png_bytes
    try:
        from PIL import Image
    except ImportError:
        return png_bytes
    side = max(nat_w, nat_h)
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    bg = (14, 17, 23, 255)
    canvas = Image.new("RGBA", (side, side), bg)
    canvas.paste(img, ((side - nat_w) // 2, (side - nat_h) // 2), img)
    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


def display_aspect_locked_image(
    png_bytes: bytes,
    *,
    caption: str = "",
    max_width_px: int = TOPO_MAP_MAX_DISPLAY_PX,
) -> None:
    """Show topo PNG at locked 1:1 display aspect — no Streamlit width stretch."""
    nat_w, nat_h = _png_pixel_size(png_bytes)
    disp_w = min(nat_w, max_width_px)
    b64 = base64.b64encode(png_bytes).decode("ascii")
    # aspect-ratio + object-fit prevents wide-layout column squeeze (max-width alone squashes).
    html = (
        f'<div style="width:100%;display:flex;justify-content:center;margin:0 auto;">'
        f'<img src="data:image/png;base64,{b64}" '
        f'style="width:min({disp_w}px,100%);height:auto;aspect-ratio:{nat_w}/{nat_h};'
        f'object-fit:contain;display:block;" alt="topo basemap" />'
        f"</div>"
    )
    st.html(html)
    if caption:
        st.caption(caption)
    if nat_w != nat_h:
        st.caption(f"PNG native {nat_w}×{nat_h}px (aspect {nat_w / nat_h:.2f}:1) — expected square 1:1")


def operator_gold_assigned_spans(
    terrain_map: dict[str, Any],
    km_lo: float,
    km_hi: float,
) -> list[dict[str, Any]]:
    """Convert hitl.operator_gold_spans[] to decision-mode assigned_spans for map overlay."""
    assigned: list[dict[str, Any]] = []
    for span in operator_gold_spans(terrain_map):
        s0 = float(span.get("course_km_start", span.get("course_m_start", 0) / 1000.0))
        s1 = float(span.get("course_km_end", span.get("course_m_end", s0) / 1000.0))
        if s1 <= km_lo or s0 >= km_hi:
            continue
        entry: dict[str, Any] = {
            "km0": max(s0, km_lo),
            "km1": min(s1, km_hi),
            "class": str(span.get("surface_class", "S2")),
            "kind": "operator_gold",
        }
        tier = str(span.get("friction_tier", "")).strip().upper()
        if tier:
            entry["friction_tier"] = tier
        assigned.append(entry)
    return assigned


def draft_gold_disagreement_pct(
    hmm_draft: pd.DataFrame,
    terrain_map: dict[str, Any],
    km_lo: float,
    km_hi: float,
) -> float | None:
    """Share (0–100) of window metres where HMM draft S-class != operator gold S-class."""
    if hmm_draft is None or hmm_draft.empty or "draft_class" not in hmm_draft.columns:
        return None
    if not operator_gold_spans(terrain_map):
        return None
    win = hmm_draft[(hmm_draft["course_km"] >= km_lo) & (hmm_draft["course_km"] < km_hi)]
    if win.empty:
        return None
    disagree = 0
    compared = 0
    for _, row in win.iterrows():
        km = float(row["course_km"])
        gold = operator_gold_class_at_km(terrain_map, km)
        if gold is None:
            continue
        compared += 1
        if str(row["draft_class"]) != gold:
            disagree += 1
    if compared == 0:
        return None
    return 100.0 * disagree / compared


@st.cache_data(show_spinner="Rendering topo basemap…")
def render_topo_basemap_png(
    panel_path: str,
    terrain_map_path: str,
    km_lo: float,
    km_hi: float,
    *,
    basemap: BasemapLayerId = DEFAULT_BASEMAP,
    lat_offset: float = 0.0,
    lon_offset: float = 0.0,
    map_track_operator_gold: bool = False,
) -> tuple[bytes | None, str]:
    """Matplotlib topo panel aligned to the Plotly course_km window (validation_dashboard pipeline)."""
    from spatial.validation_dashboard import course_geography, render_reference_map

    assert_basemap_not_maritime(basemap)
    layer_id = normalize_basemap_layer(basemap)
    if layer_id == "opentopomap":
        layer_id = DEFAULT_BASEMAP_LAYER

    panel = load_panel_window_cached(panel_path, km_lo, km_hi, buffer_km=PANEL_WINDOW_BUFFER_KM)
    panel = offset_panel_gps(panel, lat_offset=lat_offset, lon_offset=lon_offset)
    terrain_map = load_terrain_map(Path(terrain_map_path))
    geo = course_geography(panel, km_lo, km_hi)
    if geo.empty:
        return None, "no geography in panel for selected window"

    gpx_path: Path | None = None
    if corridor_allows_gpx_overlay(terrain_map) and DEFAULT_SUT43_GPX.exists():
        gpx_path = DEFAULT_SUT43_GPX
    map_track_activity, map_track_donor = resolve_default_map_track_activity(
        Path(panel_path), terrain_map, panel
    )

    fig, ax = plt.subplots(figsize=(TOPO_MAP_SIZE_IN, TOPO_MAP_SIZE_IN), dpi=TOPO_MAP_DPI)
    fig.patch.set_facecolor("#0e1117")
    _force_square_axes(ax, fig)
    assigned_spans: list[dict[str, Any]] | None = None
    if map_track_operator_gold:
        assigned_spans = operator_gold_assigned_spans(terrain_map, km_lo, km_hi)

    try:
        try:
            status, _, _ = render_reference_map(
                ax,
                panel,
                terrain_map,
                viewport_km=(km_lo, km_hi),
                chunk_km=(km_lo, km_hi),
                gpx_path=gpx_path,
                basemap=layer_id,  # type: ignore[arg-type]
                decision_mode=map_track_operator_gold,
                assigned_spans=assigned_spans,
                map_track_activity=map_track_activity,
                map_track_donor=map_track_donor,
                map_display_aspect=TOPO_MAP_DISPLAY_ASPECT,
                lat_offset=0.0,
                lon_offset=0.0,
            )
        except (BrokenPipeError, OSError, RuntimeError) as exc:
            return None, f"no (basemap render failed: {type(exc).__name__}: {exc})"
        buf = io.BytesIO()
        try:
            fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), dpi=TOPO_MAP_DPI)
        except (BrokenPipeError, OSError) as exc:
            return None, f"no (PNG export failed: {type(exc).__name__}: {exc})"
        return _ensure_square_png(buf.getvalue()), status
    finally:
        plt.close(fig)


def _parse_cli_defaults() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--terrain-map", type=Path, default=DEFAULT_TERRAIN_MAP)
    parser.add_argument("--triage-queue", type=Path, default=DEFAULT_TRIAGE_QUEUE)
    parser.add_argument("--hmm-draft", type=Path, default=DEFAULT_HMM_DRAFT)
    parser.add_argument("--lat-offset", type=float, default=0.0, dest="lat_offset")
    parser.add_argument("--lon-offset", type=float, default=0.0, dest="lon_offset")
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1 :]
    else:
        argv = [a for a in sys.argv[1:] if not a.startswith("--server.") and a != "run"]
    return parser.parse_args(argv)


def _race_panel(panel: pd.DataFrame) -> pd.DataFrame:
    work = panel.copy()
    if "course_km" not in work.columns and "ref_chainage_m" in work.columns:
        work["course_km"] = work["ref_chainage_m"] / 1000.0
    if "course_m" not in work.columns and "ref_chainage_m" in work.columns:
        work["course_m"] = work["ref_chainage_m"]
    if "session_type" in work.columns:
        work = work[work["session_type"] == "race"]
    return work.sort_values(["course_m", "donor_id"])


def build_consensus_profile(panel: pd.DataFrame) -> pd.DataFrame:
    race = _race_panel(panel)
    race = race.copy()
    race["nti"] = compute_nti(race)
    consensus = aggregate_nti_by_course_m(race, use_consensus=True)
    per_m_aggs: dict[str, tuple[str, str]] = {
        "course_km": ("course_km", "first"),
        "speed_median": ("speed_mps", "median"),
        "grade_pct_median": ("grade_pct", "median"),
        "cadence_median": ("cadence_spm", "median"),
        "ti_median": ("ti", "median"),
        "ti_raw_median": ("ti_raw", "median"),
    }
    if "pace_expected" in race.columns:
        per_m_aggs["pace_expected_median"] = ("pace_expected", "median")
    per_m = race.groupby("course_m", as_index=False).agg(**per_m_aggs)
    if "course_km" not in consensus.columns and "course_m" in consensus.columns:
        consensus = consensus.merge(per_m[["course_m", "course_km"]], on="course_m", how="left")
    profile = per_m.merge(
        consensus[["course_m", "consensus_nti", "nti_std", "nti_median"]],
        on="course_m",
        how="left",
    )
    profile["nti_display"] = profile.get("consensus_nti", profile.get("nti_median"))
    return profile.sort_values("course_m").reset_index(drop=True)


def per_subject_profiles(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    race = _race_panel(panel)
    race = race.copy()
    race["nti"] = compute_nti(race)
    out: dict[str, pd.DataFrame] = {}
    for donor in SUBJECT_LABELS:
        sub = race[race["donor_id"] == donor]
        if sub.empty:
            continue
        agg = sub.groupby("course_m", as_index=False).agg(
            course_km=("course_km", "first"),
            speed_mps=("speed_mps", "median"),
            grade_pct=("grade_pct", "median"),
            ti=("ti", "median"),
            nti=("nti", "median"),
        )
        out[donor] = agg.sort_values("course_m")
    return out


def hmm_blocks_in_window(hmm_draft: pd.DataFrame, km_lo: float, km_hi: float) -> list[dict[str, Any]]:
    if hmm_draft is None or hmm_draft.empty:
        return []
    win = hmm_draft[(hmm_draft["course_km"] >= km_lo) & (hmm_draft["course_km"] < km_hi)].copy()
    if win.empty or "draft_class" not in win.columns:
        return []
    win = win.sort_values("course_km")
    blocks: list[dict[str, Any]] = []
    cur_cls = str(win.iloc[0]["draft_class"])
    start_km = float(win.iloc[0]["course_km"])
    for _, row in win.iloc[1:].iterrows():
        cls = str(row["draft_class"])
        if cls != cur_cls:
            blocks.append({"course_km_start": start_km, "course_km_end": float(row["course_km"]), "surface_class": cur_cls})
            cur_cls = cls
            start_km = float(row["course_km"])
    blocks.append({"course_km_start": start_km, "course_km_end": float(win.iloc[-1]["course_km"]) + 0.001, "surface_class": cur_cls})
    return blocks


def operator_gold_blocks_in_window(
    terrain_map: dict[str, Any],
    km_lo: float,
    km_hi: float,
) -> list[dict[str, Any]]:
    spans = list(terrain_map.get("hitl", {}).get("operator_gold_spans") or [])
    blocks: list[dict[str, Any]] = []
    for span in spans:
        s0 = float(span.get("course_km_start", 0))
        s1 = float(span.get("course_km_end", s0))
        if s1 < km_lo or s0 > km_hi:
            continue
        blocks.append(
            {
                "course_km_start": s0,
                "course_km_end": s1,
                "surface_class": str(span.get("surface_class", "S2")),
                "friction_tier": str(span.get("friction_tier", "")),
            }
        )
    return blocks


def nearest_metre_km(profile: pd.DataFrame, course_km: float) -> float:
    if profile.empty or "course_km" not in profile.columns:
        return course_km
    idx = (profile["course_km"] - course_km).abs().idxmin()
    return float(profile.loc[idx, "course_km"])


def hmm_draft_class_at_km(hmm_draft: pd.DataFrame, km: float) -> str | None:
    if hmm_draft is None or hmm_draft.empty or "draft_class" not in hmm_draft.columns:
        return None
    win = hmm_draft[(hmm_draft["course_km"] >= km - 0.0005) & (hmm_draft["course_km"] < km + 0.001)]
    if not win.empty:
        return str(win.iloc[0]["draft_class"])
    idx = (hmm_draft["course_km"] - km).abs().idxmin()
    return str(hmm_draft.loc[idx, "draft_class"])


def class_label_at_km(
    terrain_map: dict[str, Any],
    hmm_draft: pd.DataFrame,
    km: float,
) -> str:
    s_cls = operator_gold_class_at_km(terrain_map, km)
    f_tier = operator_gold_friction_tier_at_km(terrain_map, km)
    if s_cls and f_tier:
        return f"{s_cls}/{f_tier}"
    if s_cls:
        return s_cls
    draft = hmm_draft_class_at_km(hmm_draft, km)
    if draft:
        return f"{draft}/—"
    return "—"


def crosshair_snapshot(
    profile: pd.DataFrame,
    terrain_map: dict[str, Any],
    hmm_draft: pd.DataFrame,
    course_km: float,
) -> dict[str, Any]:
    km = nearest_metre_km(profile, course_km)
    row = profile.loc[(profile["course_km"] - km).abs().idxmin()]
    ti_col = "ti_median" if "ti_median" in row.index else "ti_raw_median"
    ti_val = row.get(ti_col)
    ti = float(ti_val) if ti_val is not None and pd.notna(ti_val) else float("nan")
    return {
        "course_km": km,
        "ti": ti,
        "class_label": class_label_at_km(terrain_map, hmm_draft, km),
    }


def _crosshair_matches_snap(snap: dict[str, Any]) -> bool:
    """True when session crosshair already matches snap (avoids hover rerun storms)."""
    cur_km = st.session_state.get("crosshair_km")
    if cur_km is None:
        return False
    if round(float(cur_km), 3) != round(float(snap["course_km"]), 3):
        return False
    if str(st.session_state.get("crosshair_class", "")) != str(snap["class_label"]):
        return False
    cur_ti = st.session_state.get("crosshair_ti")
    snap_ti = snap["ti"]
    if snap_ti is None or (isinstance(snap_ti, float) and not np.isfinite(snap_ti)):
        return cur_ti is None or (isinstance(cur_ti, float) and not np.isfinite(cur_ti))
    if cur_ti is None or (isinstance(cur_ti, float) and not np.isfinite(cur_ti)):
        return False
    return bool(np.isclose(float(cur_ti), float(snap_ti), rtol=0.0, atol=1e-3))


def plotly_events_usable() -> bool:
    """True when the custom plotly_events component should be attempted."""
    if not USE_PLOTLY_EVENTS or plotly_events is None:
        return False
    return not bool(st.session_state.get("_plotly_events_disabled"))


def _selection_points_to_events(selection: Any) -> list[dict[str, Any]]:
    """Map native st.plotly_chart selection state to plotly_events-style dicts."""
    if selection is None:
        return []
    points = selection.get("points") if isinstance(selection, dict) else getattr(selection, "points", None)
    if not points:
        return []
    events: list[dict[str, Any]] = []
    for pt in points:
        if isinstance(pt, dict):
            x_val = pt.get("x")
        else:
            x_val = getattr(pt, "x", None)
        if x_val is not None:
            events.append({"x": x_val})
    return events


def render_plotly_profile_chart(
    fig: go.Figure,
    *,
    profile_event_key: str,
) -> list[dict[str, Any]] | None:
    """Render profile figure with click/hover when available; always show the chart."""
    if plotly_events_usable():
        try:
            return plotly_events(
                fig,
                click_event=True,
                hover_event=True,
                override_height=PROFILE_CHART_HEIGHT_PX,
                override_width=PROFILE_CHART_WIDTH_PX,
                key=profile_event_key,
            )
        except Exception as exc:
            st.session_state["_plotly_events_disabled"] = True
            st.warning(
                f"Interactive Plotly component unavailable ({type(exc).__name__}: {exc}). "
                "Falling back to native chart — click-to-set uses point selection; hover crosshair disabled."
            )

    chart_state = st.plotly_chart(
        fig,
        width=PROFILE_CHART_WIDTH_PX,
        key=f"{profile_event_key}_native",
        on_select="rerun",
        selection_mode=("points",),
    )
    if plotly_events is None:
        st.caption(
            "Click-to-set uses point selection (click a trace point, then use toolbar if needed). "
            "Install `streamlit-plotly-events2` for hover crosshair: "
            "`pip install streamlit-plotly-events2`"
        )
    elif st.session_state.get("_plotly_events_disabled"):
        st.caption(
            "Hover crosshair disabled in fallback mode. "
            "Re-enable the custom component: `pip install --upgrade streamlit-plotly-events2` "
            "and restart Streamlit."
        )
    return _selection_points_to_events(getattr(chart_state, "selection", None))


def process_plotly_interaction(
    events: list[dict[str, Any]] | None,
    *,
    profile: pd.DataFrame,
    terrain_map: dict[str, Any],
    hmm_draft: pd.DataFrame,
) -> PlotlyRerunScope:
    """Apply Plotly hover/click events; return rerun scope (fragment for crosshair-only)."""
    if not events:
        return "none"
    scope: PlotlyRerunScope = "none"
    for ev in events:
        if "x" not in ev:
            continue
        snap = crosshair_snapshot(profile, terrain_map, hmm_draft, float(ev["x"]))
        pick_mode = st.session_state.get("lock_pick_mode")
        if pick_mode == "start":
            st.session_state["lock_start_km"] = round(snap["course_km"], 3)
            st.session_state["lock_pick_mode"] = None
            st.session_state["crosshair_km"] = snap["course_km"]
            st.session_state["crosshair_ti"] = snap["ti"]
            st.session_state["crosshair_class"] = snap["class_label"]
            scope = "full"
            continue
        if pick_mode == "end":
            st.session_state["lock_end_km"] = round(snap["course_km"], 3)
            st.session_state["lock_pick_mode"] = None
            st.session_state["crosshair_km"] = snap["course_km"]
            st.session_state["crosshair_ti"] = snap["ti"]
            st.session_state["crosshair_class"] = snap["class_label"]
            scope = "full"
            continue
        if _crosshair_matches_snap(snap):
            continue
        st.session_state["crosshair_km"] = snap["course_km"]
        st.session_state["crosshair_ti"] = snap["ti"]
        st.session_state["crosshair_class"] = snap["class_label"]
        if scope != "full":
            scope = "fragment"
    return scope


def _seed_crosshair_at_km(
    profile: pd.DataFrame,
    terrain_map: dict[str, Any],
    hmm_draft: pd.DataFrame,
    course_km: float,
) -> None:
    snap = crosshair_snapshot(profile, terrain_map, hmm_draft, course_km)
    st.session_state["crosshair_km"] = snap["course_km"]
    st.session_state["crosshair_ti"] = snap["ti"]
    st.session_state["crosshair_class"] = snap["class_label"]


def _init_interaction_state(
    view_lo: float,
    view_hi: float,
    *,
    profile: pd.DataFrame,
    terrain_map: dict[str, Any],
    hmm_draft: pd.DataFrame,
) -> None:
    chunk_key = f"{view_lo:.3f}_{view_hi:.3f}"
    if st.session_state.get("chunk_window_key") != chunk_key:
        st.session_state["chunk_window_key"] = chunk_key
        st.session_state["lock_start_km"] = float(view_lo)
        st.session_state["lock_end_km"] = float(view_hi)
        st.session_state["lock_pick_mode"] = None
        if not profile.empty:
            _seed_crosshair_at_km(profile, terrain_map, hmm_draft, float(view_lo))
        else:
            st.session_state["crosshair_km"] = float(view_lo)
            st.session_state["crosshair_ti"] = float("nan")
            st.session_state["crosshair_class"] = "—"
    for key, default in (
        ("crosshair_km", float(view_lo)),
        ("crosshair_ti", float("nan")),
        ("crosshair_class", "—"),
        ("lock_pick_mode", None),
        ("lock_start_km", float(view_lo)),
        ("lock_end_km", float(view_hi)),
    ):
        st.session_state.setdefault(key, default)
    ch_ti = st.session_state.get("crosshair_ti")
    if not profile.empty and (ch_ti is None or (isinstance(ch_ti, float) and not np.isfinite(ch_ti))):
        km = float(st.session_state.get("crosshair_km", view_lo))
        _seed_crosshair_at_km(profile, terrain_map, hmm_draft, km)


def merge_hmm_per_metre(
    profile: pd.DataFrame,
    hmm_draft: pd.DataFrame,
    km_lo: float,
    km_hi: float,
) -> pd.DataFrame:
    view = profile[(profile["course_km"] >= km_lo) & (profile["course_km"] < km_hi)].copy()
    if view.empty or hmm_draft is None or hmm_draft.empty:
        view["hmm_class"] = None
        view["hmm_confidence"] = np.nan
        return view
    hmm_win = hmm_draft[(hmm_draft["course_km"] >= km_lo) & (hmm_draft["course_km"] < km_hi)][
        ["course_km", "draft_class", "hmm_confidence"]
    ].rename(columns={"draft_class": "hmm_class"})
    merged = view.merge(hmm_win, on="course_km", how="left")
    return merged


def _class_strip_y(cls: str | None) -> float:
    if cls in SURFACE_CLASSES:
        return float(SURFACE_CLASSES.index(cls))
    return float("nan")


def _speed_display_values(values: pd.Series | np.ndarray) -> np.ndarray:
    """Mask halt/standing zeros so speed row shows running gait only."""
    arr = np.asarray(values, dtype=float).copy()
    arr[~np.isfinite(arr) | (arr <= 0.0)] = np.nan
    return arr


def _padded_y_range(values: pd.Series | np.ndarray, *, min_pad: float = 0.08, pad_frac: float = 0.12) -> tuple[float, float] | None:
    """Tight padded y-range so traces use the full subplot height (not squashed at top)."""
    arr = np.asarray(values, dtype=float)
    vals = arr[np.isfinite(arr)]
    if vals.size == 0:
        return None
    lo = float(vals.min())
    hi = float(vals.max())
    if hi <= lo:
        return lo - min_pad, lo + min_pad
    pad = max(min_pad, (hi - lo) * pad_frac)
    return lo - pad, hi + pad


def _speed_y_range(*arrays: pd.Series | np.ndarray) -> tuple[float, float] | None:
    """Padded m/s range for speed row — fixedrange prevents y-zoom hiding traces."""
    chunks = [_speed_display_values(a) for a in arrays if a is not None]
    if not chunks:
        return None
    padded = _padded_y_range(np.concatenate(chunks), min_pad=0.05, pad_frac=0.12)
    if padded is None:
        return None
    lo, hi = padded
    return max(0.0, lo), hi


def _pace_display_values(values: pd.Series | np.ndarray) -> np.ndarray:
    """Mask invalid / halt paces; panel pace_expected is already min/km."""
    arr = np.asarray(values, dtype=float).copy()
    arr[~np.isfinite(arr) | (arr <= 0.0) | (arr > 60.0)] = np.nan
    return arr


def _add_ti_gradient_line(
    fig: go.Figure,
    x: np.ndarray,
    y: np.ndarray,
    ti: np.ndarray,
    *,
    customdata: np.ndarray,
    row: int,
    col: int,
    cmin: float,
    cmax: float,
) -> None:
    """Plasma TI trace — colorscale markers + high-contrast connector line."""
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="lines+markers",
            name="TI",
            line=dict(color="#ECEFF1", width=1.4),
            marker=dict(
                size=5,
                color=ti,
                colorscale=TI_COLORSCALE,
                cmin=cmin,
                cmax=cmax,
                line=dict(width=0.5, color="#263238"),
                colorbar=dict(title="TI", len=0.18, y=0.92, thickness=12),
                showscale=True,
            ),
            customdata=customdata,
            hovertemplate=(
                "course_km=%{x:.3f}<br>TI=%{y:.3f}<br>Class=%{customdata[2]}"
                "<br>HMM=%{customdata[0]}<br>p=%{customdata[1]:.2f}<extra></extra>"
            ),
            legendgroup="ti",
            showlegend=True,
        ),
        row=row,
        col=col,
    )


def _add_nti_sigma_trace(
    fig: go.Figure,
    x: np.ndarray,
    sigma: np.ndarray,
    *,
    row: int,
    col: int,
) -> None:
    """Cross-athlete σ strip — filled scatter (heatmap 1×N renders as solid block in subplots)."""
    sigma_arr = np.asarray(sigma, dtype=float)
    sigma_arr = np.where(np.isfinite(sigma_arr), sigma_arr, 0.0)
    fig.add_trace(
        go.Scatter(
            x=x,
            y=sigma_arr,
            mode="lines",
            name="NTI σ",
            fill="tozeroy",
            line=dict(color="rgba(255,167,38,0.95)", width=1.0),
            fillcolor="rgba(255,183,77,0.40)",
            hovertemplate="course_km=%{x:.3f}<br>σ=%{y:.3f}<extra></extra>",
        ),
        row=row,
        col=col,
    )


def _add_hmm_background_shapes(
    fig: go.Figure,
    hmm_blocks: list[dict[str, Any]],
    *,
    km_lo: float,
    km_hi: float,
    row: int,
    y0: float,
    y1: float,
    opacity: float = 0.22,
) -> None:
    for span in hmm_blocks or []:
        s0 = float(span["course_km_start"])
        s1 = float(span["course_km_end"])
        if s1 < km_lo or s0 > km_hi:
            continue
        cls = str(span.get("surface_class", "S2"))
        color = SURFACE_COLORS.get(cls, "#888888")
        fig.add_shape(
            type="rect",
            x0=max(s0, km_lo),
            x1=min(s1, km_hi),
            y0=y0,
            y1=y1,
            fillcolor=color,
            opacity=opacity,
            line_width=0,
            row=row,
            col=1,
            layer="below",
        )


def _add_categorical_spans(
    fig: go.Figure,
    spans: list[dict[str, Any]],
    *,
    km_lo: float,
    km_hi: float,
    row: int,
    opacity: float = 0.78,
    show_friction_edge: bool = True,
) -> None:
    for span in spans or []:
        s0 = float(span["course_km_start"])
        s1 = float(span["course_km_end"])
        if s1 < km_lo or s0 > km_hi:
            continue
        cls = str(span.get("surface_class", "S2"))
        tier = str(span.get("friction_tier", "")).strip().upper()
        color = SURFACE_COLORS.get(cls, "#888888")
        y0 = _class_strip_y(cls)
        edge_color = FRICTION_TIER_EDGE_COLORS.get(tier, "#888888") if show_friction_edge and tier else color
        edge_width = 2.0 if tier else 0.0
        fig.add_shape(
            type="rect",
            x0=max(s0, km_lo),
            x1=min(s1, km_hi),
            y0=y0 - 0.42,
            y1=y0 + 0.42,
            fillcolor=color,
            opacity=opacity,
            line=dict(color=edge_color, width=edge_width),
            row=row,
            col=1,
        )


def build_plotly_figure(
    profile: pd.DataFrame,
    *,
    km_lo: float,
    km_hi: float,
    viz_mode: VizMode = "continuous",
    show_hmm_overlay: bool = True,
    subject_profiles: dict[str, pd.DataFrame] | None = None,
    hmm_blocks: list[dict[str, Any]] | None = None,
    operator_gold: list[dict[str, Any]] | None = None,
    hmm_draft: pd.DataFrame | None = None,
    terrain_map: dict[str, Any] | None = None,
    crosshair_km: float | None = None,
    queue_label: str = "",
) -> go.Figure:
    hmm_work = hmm_draft if hmm_draft is not None else pd.DataFrame()
    terrain_work = terrain_map if terrain_map is not None else {}
    view = merge_hmm_per_metre(profile, hmm_work, km_lo, km_hi)
    if view.empty:
        fig = go.Figure()
        fig.update_layout(title="No panel rows in selected window")
        return fig

    ti_col = "ti_median" if "ti_median" in view.columns else "ti_raw_median"
    ti_vals = view[ti_col].to_numpy(dtype=float)
    hmm_classes = view.get("hmm_class", pd.Series([None] * len(view))).astype(str).replace("nan", "—")
    hmm_conf = view.get("hmm_confidence", pd.Series([np.nan] * len(view)))
    class_labels = np.array(
        [class_label_at_km(terrain_work, hmm_work, float(k)) for k in view["course_km"]],
        dtype=object,
    )
    custom = np.column_stack([hmm_classes.to_numpy(), hmm_conf.to_numpy(), class_labels])

    if viz_mode == "continuous":
        ti_title = "TI gradient + HMM overlay" if show_hmm_overlay else "TI gradient"
        cat_subtitle = (
            "Operator gold + HMM draft (reference)"
            if operator_gold
            else "HMM draft blocks"
        )
        fig = make_subplots(
            rows=PROFILE_ROW_COUNT,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.028,
            row_heights=[0.20, 0.12, 0.16, 0.13, 0.13, 0.10],
            subplot_titles=(
                ti_title,
                "Cross-athlete σ (NTI)",
                "Speed (m/s)",
                "Grade (%)",
                "Pace expected (min/km)",
                cat_subtitle,
            ),
        )
        ti_row = ROW_TI
        cat_row = ROW_CAT
    else:
        fig = make_subplots(
            rows=PROFILE_ROW_COUNT,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.028,
            row_heights=[0.14, 0.12, 0.14, 0.12, 0.12, 0.20],
            subplot_titles=(
                "TI trace (context)",
                "Cross-athlete σ (NTI)",
                "Speed (m/s)",
                "Grade (%)",
                "Pace expected (min/km)",
                "F-tier / S-class overlay",
            ),
        )
        ti_row = ROW_TI
        cat_row = ROW_CAT

    ti_y0 = float(np.nanmin(ti_vals)) if np.isfinite(ti_vals).any() else 0.0
    ti_y1 = float(np.nanmax(ti_vals)) if np.isfinite(ti_vals).any() else 1.0
    if ti_y1 <= ti_y0:
        ti_y1 = ti_y0 + 0.5
    if viz_mode == "continuous" and show_hmm_overlay:
        _add_hmm_background_shapes(
            fig,
            hmm_blocks,
            km_lo=km_lo,
            km_hi=km_hi,
            row=ti_row,
            y0=ti_y0,
            y1=ti_y1,
            opacity=0.24,
        )

    if viz_mode == "continuous":
        ti_cmin = float(np.nanmin(ti_vals))
        ti_cmax = float(np.nanmax(ti_vals))
        if ti_cmax <= ti_cmin:
            ti_cmax = ti_cmin + 0.01
        _add_ti_gradient_line(
            fig,
            view["course_km"].to_numpy(),
            ti_vals,
            ti_vals,
            customdata=custom,
            row=ti_row,
            col=1,
            cmin=ti_cmin,
            cmax=ti_cmax,
        )
    else:
        fig.add_trace(
            go.Scatter(
                x=view["course_km"],
                y=view[ti_col],
                mode="lines",
                name="TI",
                line=dict(color="#CE93D8", width=1.2),
                customdata=custom,
                hovertemplate=(
                    "course_km=%{x:.3f}<br>TI=%{y:.3f}<br>Class=%{customdata[2]}"
                    "<br>HMM=%{customdata[0]}<br>p=%{customdata[1]:.2f}<extra></extra>"
                ),
            ),
            row=ti_row,
            col=1,
        )

    nti_range: tuple[float, float] | None = None
    if "nti_std" in view.columns:
        nti_sigma = view["nti_std"].to_numpy(dtype=float)
        _add_nti_sigma_trace(
            fig,
            view["course_km"].to_numpy(dtype=float),
            nti_sigma,
            row=ROW_NTI,
            col=1,
        )
        nti_range = _padded_y_range(np.where(np.isfinite(nti_sigma), nti_sigma, 0.0), min_pad=0.02, pad_frac=0.12)
        if nti_range is not None and nti_range[0] < 0.0:
            nti_range = (0.0, nti_range[1])

    speed_x = view["course_km"].to_numpy(dtype=float)
    speed_source = view["speed_median"] if "speed_median" in view.columns else pd.Series(np.nan, index=view.index)
    consensus_speed = _speed_display_values(speed_source)
    speed_arrays: list[np.ndarray] = [consensus_speed]
    fig.add_trace(
        go.Scatter(
            x=speed_x,
            y=consensus_speed,
            mode="lines",
            name="consensus spd",
            connectgaps=False,
            line=dict(color="#00E5FF", width=2.0),
            hovertemplate="course_km=%{x:.3f}<br>speed=%{y:.2f} m/s<extra></extra>",
        ),
        row=ROW_SPEED,
        col=1,
    )

    if subject_profiles:
        palette = {"Subject_A": "#4FC3F7", "Subject_B": "#81C784"}
        for sid, sub_df in subject_profiles.items():
            sub_view = sub_df[(sub_df["course_km"] >= km_lo) & (sub_df["course_km"] < km_hi)]
            if sub_view.empty:
                continue
            sub_speed = _speed_display_values(sub_view["speed_mps"])
            speed_arrays.append(sub_speed)
            fig.add_trace(
                go.Scatter(
                    x=sub_view["course_km"].to_numpy(dtype=float),
                    y=sub_speed,
                    mode="lines",
                    name=f"{SUBJECT_LEGEND_SHORT.get(sid, sid)} spd",
                    connectgaps=False,
                    line=dict(color=palette.get(sid, "#AAA"), width=1.0, dash="dot"),
                    opacity=0.85,
                ),
                row=ROW_SPEED,
                col=1,
            )

    speed_range = _speed_y_range(*speed_arrays)

    if "grade_pct_median" in view.columns:
        grade_vals = view["grade_pct_median"].to_numpy(dtype=float)
        fig.add_trace(
            go.Scatter(
                x=speed_x,
                y=grade_vals,
                mode="lines",
                name="grade",
                line=dict(color="#FFB74D", width=1.4),
                hovertemplate="course_km=%{x:.3f}<br>grade=%{y:.1f}%<extra></extra>",
            ),
            row=ROW_GRADE,
            col=1,
        )
        fig.add_hline(y=0.0, line_dash="dot", line_color="#666666", line_width=0.8, row=ROW_GRADE, col=1)
        grade_range = _padded_y_range(grade_vals, min_pad=1.0, pad_frac=0.08)
    else:
        grade_range = None

    pace_range: tuple[float, float] | None = None
    if "pace_expected_median" in view.columns:
        pace_vals = _pace_display_values(view["pace_expected_median"])
        if np.isfinite(pace_vals).any():
            fig.add_trace(
                go.Scatter(
                    x=speed_x,
                    y=pace_vals,
                    mode="lines",
                    name="pace expected",
                    connectgaps=False,
                    line=dict(color="#CE93D8", width=1.4),
                    hovertemplate="course_km=%{x:.3f}<br>pace=%{y:.2f} min/km<extra></extra>",
                ),
                row=ROW_PACE,
                col=1,
            )
            pace_range = _padded_y_range(pace_vals, min_pad=0.25, pad_frac=0.08)

    if viz_mode == "categorical":
        _add_categorical_spans(
            fig,
            operator_gold,
            km_lo=km_lo,
            km_hi=km_hi,
            row=cat_row,
            opacity=0.82,
            show_friction_edge=True,
        )
        _add_categorical_spans(
            fig,
            hmm_blocks,
            km_lo=km_lo,
            km_hi=km_hi,
            row=cat_row,
            opacity=0.35,
            show_friction_edge=False,
        )
    else:
        if operator_gold:
            _add_categorical_spans(
                fig,
                operator_gold,
                km_lo=km_lo,
                km_hi=km_hi,
                row=cat_row,
                opacity=0.82,
                show_friction_edge=True,
            )
            _add_categorical_spans(
                fig,
                hmm_blocks,
                km_lo=km_lo,
                km_hi=km_hi,
                row=cat_row,
                opacity=0.30,
                show_friction_edge=False,
            )
        else:
            _add_categorical_spans(
                fig,
                hmm_blocks,
                km_lo=km_lo,
                km_hi=km_hi,
                row=cat_row,
                opacity=0.75,
                show_friction_edge=False,
            )

    ti_pad = max(0.08, (ti_y1 - ti_y0) * 0.06)
    fig.update_yaxes(title_text="TI", range=[ti_y0 - ti_pad, ti_y1 + ti_pad], row=ti_row, col=1)
    nti_y_kwargs: dict[str, Any] = {"title_text": "σ", "showgrid": True}
    if nti_range is not None:
        nti_y_kwargs["range"] = list(nti_range)
        nti_y_kwargs["fixedrange"] = True
    fig.update_yaxes(row=ROW_NTI, col=1, **nti_y_kwargs)
    speed_y_kwargs: dict[str, Any] = {"title_text": "m/s", "showgrid": True}
    if speed_range is not None:
        speed_y_kwargs["range"] = list(speed_range)
        speed_y_kwargs["fixedrange"] = True
    else:
        speed_y_kwargs["range"] = [0.0, 3.0]
        speed_y_kwargs["fixedrange"] = True
    fig.update_yaxes(row=ROW_SPEED, col=1, **speed_y_kwargs)
    grade_y_kwargs: dict[str, Any] = {"title_text": "%"}
    if grade_range is not None:
        grade_y_kwargs["range"] = list(grade_range)
        grade_y_kwargs["fixedrange"] = True
    fig.update_yaxes(row=ROW_GRADE, col=1, **grade_y_kwargs)
    pace_y_kwargs: dict[str, Any] = {"title_text": "min/km"}
    if pace_range is not None:
        pace_y_kwargs["range"] = list(pace_range)
        pace_y_kwargs["fixedrange"] = True
    fig.update_yaxes(row=ROW_PACE, col=1, **pace_y_kwargs)
    fig.update_yaxes(
        tickvals=list(range(len(SURFACE_CLASSES))),
        ticktext=list(SURFACE_CLASSES),
        range=[-0.55, len(SURFACE_CLASSES) - 0.45],
        fixedrange=True,
        row=cat_row,
        col=1,
    )
    fig.update_xaxes(title_text="course_km", row=cat_row, col=1)
    x_range = [float(km_lo), float(km_hi)]
    for row_idx in range(1, cat_row + 1):
        fig.update_xaxes(
            type="linear",
            range=x_range,
            autorange=False,
            fixedrange=False,
            constrain="domain",
            row=row_idx,
            col=1,
        )
    if crosshair_km is not None and km_lo <= float(crosshair_km) <= km_hi:
        for row_idx in range(1, cat_row + 1):
            fig.add_vline(
                x=float(crosshair_km),
                line_width=1,
                line_color="rgba(255,255,255,0.35)",
                row=row_idx,
                col=1,
            )
    title_suffix = f" · queue {queue_label}" if queue_label else ""
    # Profile rows share course_km on x but y units differ (TI, σ, m/s, grade, pace, S-class index).
    # Do NOT set scaleanchor on yaxis* — that would force 1 data-unit = 1 km and squash TI rows.
    # Map squash is fixed in matplotlib topo PNG (square canvas + display_aspect_locked_image).
    fig.update_layout(
        width=PROFILE_CHART_WIDTH_PX,
        height=PROFILE_CHART_HEIGHT_PX,
        dragmode="zoom",
        hovermode="x unified",
        uirevision=f"profile_v2_{km_lo:.3f}_{km_hi:.3f}_{viz_mode}",
        title=dict(text=f"Visualization: {viz_mode}{title_suffix}", font=dict(size=13)),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.03,
            xanchor="center",
            x=0.5,
            font=dict(size=10),
            tracegroupgap=6,
            itemwidth=36,
        ),
        margin=dict(l=50, r=60, t=48, b=140),
    )
    return fig


def validate_gold_span(
    terrain_map: dict[str, Any],
    *,
    km_start: float,
    km_end: float,
) -> list[dict[str, Any]]:
    if km_end <= km_start:
        raise ValueError("course_km_end must exceed course_km_start")
    existing = list(terrain_map.get("hitl", {}).get("operator_gold_spans") or [])
    return find_overlapping_gold_spans(existing, km_start, km_end)


def append_operator_gold_span(
    terrain_map_path: Path,
    *,
    km_start: float,
    km_end: float,
    surface_class: str,
    friction_tier: str,
    reason: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    terrain_map = load_terrain_map(terrain_map_path)
    overlaps = validate_gold_span(terrain_map, km_start=km_start, km_end=km_end)
    if overlaps:
        first = overlaps[0]
        raise ValueError(
            f"Lock range km {km_start:.3f}–{km_end:.3f} overlaps existing operator gold "
            f"km {float(first['course_km_start']):.3f}–{float(first['course_km_end']):.3f} "
            f"({first.get('surface_class', '?')}/{first.get('friction_tier', '?')})"
        )
    locked_at = date.today().isoformat()
    entry: dict[str, Any] = {
        "course_km_start": round(km_start, 3),
        "course_km_end": round(km_end, 3),
        "surface_class": surface_class,
        "friction_tier": friction_tier,
        "gold_source": "operator",
        "mode": "operator_gold",
        "locked_at": locked_at,
        "reason": reason.strip() or f"operator gold lock {locked_at} via hitl_annotator_app",
    }
    if dry_run:
        return entry
    hitl = terrain_map.setdefault("hitl", {})
    spans: list[dict[str, Any]] = list(hitl.get("operator_gold_spans") or [])
    spans.append(entry)
    hitl["operator_gold_spans"] = spans
    terrain_map_path.write_text(json.dumps(terrain_map, indent=2) + "\n", encoding="utf-8")
    return entry


@st.cache_data(show_spinner=False)
def panel_km_extent(path: str) -> tuple[float, float]:
    df = pd.read_parquet(Path(path), columns=["course_km"])
    if "course_km" not in df.columns and "ref_chainage_m" in df.columns:
        df["course_km"] = df["ref_chainage_m"] / 1000.0
    return float(df["course_km"].min()), float(df["course_km"].max())


@st.cache_data(show_spinner=False)
def load_panel_window_cached(path: str, km_lo: float, km_hi: float, buffer_km: float = PANEL_WINDOW_BUFFER_KM) -> pd.DataFrame:
    lo = max(0.0, float(km_lo) - buffer_km)
    hi = float(km_hi) + buffer_km
    panel = pd.read_parquet(Path(path))
    if "course_km" not in panel.columns and "ref_chainage_m" in panel.columns:
        panel["course_km"] = panel["ref_chainage_m"] / 1000.0
    return panel[(panel["course_km"] >= lo) & (panel["course_km"] <= hi)].copy()


@st.cache_data(show_spinner=False)
def load_map_cached(path: str) -> dict[str, Any]:
    return load_terrain_map(Path(path))


@st.cache_data(show_spinner=False)
def load_triage_cached(path: str) -> pd.DataFrame:
    return pd.read_csv(Path(path))


@st.cache_data(show_spinner=False)
def load_hmm_window_cached(path: str, km_lo: float, km_hi: float, buffer_km: float = PANEL_WINDOW_BUFFER_KM) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    lo = max(0.0, float(km_lo) - buffer_km)
    hi = float(km_hi) + buffer_km
    hmm = pd.read_parquet(p)
    return hmm[(hmm["course_km"] >= lo) & (hmm["course_km"] <= hi)].copy()


@st.fragment
def _render_profile_interaction(
    *,
    profile: pd.DataFrame,
    terrain_map: dict[str, Any],
    hmm_draft: pd.DataFrame,
    profile_event_key: str,
    view_lo: float,
    view_hi: float,
    viz_mode: VizMode,
    show_hmm_overlay: bool,
    subject_profiles: dict[str, pd.DataFrame] | None,
    hmm_blocks: list[dict[str, Any]],
    operator_gold: list[dict[str, Any]],
    queue_label: str,
) -> None:
    """Plotly profile + hover crosshair; fragment rerun avoids full-page reload on hover."""
    crosshair_km = st.session_state.get("crosshair_km")
    ch_km_main = float(crosshair_km) if crosshair_km is not None else float(view_lo)
    ch_ti_main = st.session_state.get("crosshair_ti", float("nan"))
    ch_cls_main = str(st.session_state.get("crosshair_class", "—"))

    xc1, xc2, xc3 = st.columns(3)
    xc1.metric("course_km", f"{ch_km_main:.3f}")
    ti_main = f"{float(ch_ti_main):.3f}" if ch_ti_main is not None and pd.notna(ch_ti_main) else "—"
    xc2.metric("TI", ti_main)
    xc3.metric("Class", ch_cls_main)

    fig = build_plotly_figure(
        profile,
        km_lo=float(view_lo),
        km_hi=float(view_hi),
        viz_mode=viz_mode,
        show_hmm_overlay=show_hmm_overlay,
        subject_profiles=subject_profiles,
        hmm_blocks=hmm_blocks,
        operator_gold=operator_gold,
        hmm_draft=hmm_draft,
        terrain_map=terrain_map,
        crosshair_km=ch_km_main,
        queue_label=queue_label,
    )

    events = render_plotly_profile_chart(fig, profile_event_key=profile_event_key)
    scope = process_plotly_interaction(
        events,
        profile=profile,
        terrain_map=terrain_map,
        hmm_draft=hmm_draft,
    )
    if scope == "full":
        st.rerun()
    elif scope == "fragment":
        st.rerun(scope="fragment")


@st.dialog("Confirm operator gold lock")
def confirm_save_dialog(
    *,
    terrain_map_path: str,
    km_start: float,
    km_end: float,
    surface_class: str,
    friction_tier: str,
    reason: str,
) -> None:
    st.markdown("**Pre-save confirmation** — review span before JSON write.")
    st.markdown(
        f"| Field | Value |\n|-------|-------|\n"
        f"| **course_km window** | {km_start:.3f} – {km_end:.3f} |\n"
        f"| **surface_class** | {surface_class} |\n"
        f"| **friction_tier** | {friction_tier} |\n"
        f"| **target file** | `{Path(terrain_map_path).name}` |"
    )
    if reason.strip():
        st.caption(f"Reason: {reason.strip()}")
    col_confirm, col_cancel = st.columns(2)
    with col_confirm:
        if st.button("Confirm write", type="primary", width="stretch"):
            try:
                entry = append_operator_gold_span(
                    Path(terrain_map_path),
                    km_start=km_start,
                    km_end=km_end,
                    surface_class=surface_class,
                    friction_tier=friction_tier,
                    reason=reason,
                )
                load_map_cached.clear()
                st.session_state["last_save_entry"] = entry
                st.session_state["save_confirmed"] = True
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with col_cancel:
        if st.button("Cancel", width="stretch"):
            st.session_state.pop("pending_lock", None)
            st.rerun()


def main() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(BASE_DIR / ".env")
    except ImportError:
        pass

    cli = _parse_cli_defaults()
    try:
        st.set_page_config(page_title="HITL Terrain Annotator", layout="wide")
    except st.errors.StreamlitAPIException:
        pass  # already configured on rerun
    st.title("HITL Terrain Annotator")
    st.caption("RPS triage queue · Subject_A / Subject_B telemetry · Dr. Anatomy Pace laboratory")

    if st.session_state.pop("save_confirmed", False):
        entry = st.session_state.pop("last_save_entry", {})
        st.success(
            f"Promoted {entry.get('surface_class', '?')}/{entry.get('friction_tier', '?')} "
            f"km {entry.get('course_km_start', 0):.3f}–{entry.get('course_km_end', 0):.3f}"
        )

    with st.sidebar:
        with st.expander("Data sources", expanded=False):
            panel_path = st.text_input("Panel parquet", value=str(cli.panel), key="panel_path_input")
            terrain_map_path = st.text_input("Terrain map JSON", value=str(cli.terrain_map), key="terrain_map_path_input")
            triage_path = st.text_input("Triage queue CSV", value=str(cli.triage_queue), key="triage_path_input")
            hmm_path = st.text_input("HMM draft parquet", value=str(cli.hmm_draft), key="hmm_path_input")

        paths_ok = True
        if not Path(panel_path).exists():
            st.error(f"Panel not found: `{panel_path}`")
            paths_ok = False
        if not Path(terrain_map_path).exists():
            st.error(f"Terrain map not found: `{terrain_map_path}`")
            paths_ok = False
        if not paths_ok:
            st.warning(
                "Fix panel parquet and terrain map paths above — triage, visualization, "
                "and lock controls stay disabled until both files resolve."
            )

        save_clicked = False
        if paths_ok:
            triage_df = pd.DataFrame()
            if Path(triage_path).exists():
                triage_df = load_triage_cached(triage_path)
            else:
                st.warning(f"Triage queue not found: {triage_path}")

            st.header("Triage queue")
            queue_filter = st.selectbox("Queue filter", ["RED", "YELLOW", "GREEN", "ALL"], index=0)
            filtered = triage_df.copy()
            if not filtered.empty and queue_filter != "ALL":
                filtered = filtered[filtered["queue"] == queue_filter]
            chunk_row = None
            km_min, km_max = panel_km_extent(panel_path)
            if not filtered.empty:
                filtered = filtered.sort_values("RPS", ascending=False).reset_index(drop=True)
                options = [
                    f"{row['chunk_id']} km {row['km_start']:.1f}–{row['km_end']:.1f} "
                    f"RPS={row['RPS']:.3f} [{row['queue']}]"
                    for _, row in filtered.iterrows()
                ]
                selected = st.selectbox("Chunk (sorted by RPS ↓)", options, index=0)
                sel_idx = options.index(selected)
                chunk_row = filtered.iloc[sel_idx]
                view_lo = float(chunk_row["km_start"])
                view_hi = float(chunk_row["km_end"])
                queue_label = str(chunk_row["queue"])
                st.metric("RPS", f"{chunk_row['RPS']:.3f}")
                st.caption(f"A={chunk_row['A']:.3f} · B={chunk_row['B']:.3f} · C={chunk_row['C']:.3f}")
            else:
                view_lo = max(km_min, SUT43_FULL_KM_START)
                view_hi = min(km_max, SUT43_FULL_KM_END)
                queue_label = ""

            st.header("View window")
            if chunk_row is not None:
                st.caption(f"Chunk window: km {view_lo:.1f}–{view_hi:.1f}")
                manual_window = st.checkbox("Manual km override", value=False)
            else:
                manual_window = True
            if manual_window:
                view_lo = st.slider("course_km_start", km_min, km_max, float(view_lo), step=0.1)
                view_hi = st.slider("course_km_end", km_min, km_max, float(view_hi), step=0.1)

            if view_hi <= view_lo:
                view_hi = min(view_lo + 1.0, km_max)

            panel = load_panel_window_cached(panel_path, float(view_lo), float(view_hi))
            terrain_map = load_map_cached(terrain_map_path)
            hmm_draft = load_hmm_window_cached(hmm_path, float(view_lo), float(view_hi))
            profile = build_consensus_profile(panel)
            subject_profiles = per_subject_profiles(panel)

            st.header("Visualization")
            viz_mode_label = st.radio(
                "Profile mode",
                ["Continuous TI gradient", "Categorical F-tier / S-class"],
                index=0,
                help="Continuous: dual-layer TI + HMM strip for deep dive. "
                "Categorical: operator gold + F-tier edges for lock validation.",
            )
            viz_mode: VizMode = "continuous" if viz_mode_label.startswith("Continuous") else "categorical"
            show_hmm_overlay = st.checkbox(
                "HMM class overlay (row 1)",
                value=True,
                disabled=viz_mode != "continuous",
                help="Dual layer on TI panel: plasma gradient + semi-transparent S1–S6 HMM draft strip.",
            )
            show_athletes = st.checkbox("Athlete overlay (Subject_A / Subject_B)", value=True)

            st.header("Basemap")
            if "lat_offset" not in st.session_state:
                st.session_state["lat_offset"] = float(cli.lat_offset)
            if "lon_offset" not in st.session_state:
                st.session_state["lon_offset"] = float(cli.lon_offset)
            lat_offset = st.number_input(
                "Latitude offset (°)",
                step=0.00001,
                format="%.6f",
                key="lat_offset",
                help="GPS drift correction for topo alignment (CLI default via --lat-offset).",
            )
            lon_offset = st.number_input(
                "Longitude offset (°)",
                step=0.00001,
                format="%.6f",
                key="lon_offset",
                help="GPS drift correction for topo alignment (CLI default via --lon-offset).",
            )
            topo_ready = topo_basemap_available(panel, float(view_lo), float(view_hi))
            basemap_labels = [label for label, _ in BASEMAP_LAYER_OPTIONS]
            basemap_label_to_id = {label: layer_id for label, layer_id in BASEMAP_LAYER_OPTIONS}
            default_basemap_label = HITL_BASEMAP_LAYER_LABELS[DEFAULT_BASEMAP]
            basemap_choice_label = st.radio(
                "Basemap Layer",
                basemap_labels,
                index=basemap_labels.index(default_basemap_label),
                disabled=not topo_ready,
                help="Standard / Greyscale / Satellite (Sjøkart maritime tiles blocked). "
                "Orthophoto may require NIB_WMTS_TOKEN env var.",
            )
            basemap_layer: BasemapLayerId = basemap_label_to_id[basemap_choice_label]
            show_topo = st.checkbox(
                "Show topo basemap",
                value=False,
                disabled=not topo_ready,
                help="Chunk-window reference map with 1:1 lon/lat aspect lock and metric scalebar. "
                "Off by default so the profile chart loads first (tile fetch can be slow).",
            )
            operator_gold_preview = operator_gold_blocks_in_window(terrain_map, float(view_lo), float(view_hi))
            has_gold_in_window = bool(operator_gold_preview)
            map_gold_window_key = f"{view_lo:.3f}_{view_hi:.3f}"
            if st.session_state.get("map_gold_window_key") != map_gold_window_key:
                st.session_state["map_gold_window_key"] = map_gold_window_key
                st.session_state["map_track_operator_gold"] = has_gold_in_window
            map_track_operator_gold = st.checkbox(
                "Map track: Operator gold",
                help="When ON, topo track colours follow hitl.operator_gold_spans[] (decision overlay). "
                "When OFF, GMM draft segments[] from terrain map JSON.",
                key="map_track_operator_gold",
            )
            if not has_gold_in_window and map_track_operator_gold:
                st.caption("No operator gold spans in current window — map shows GMM draft segments.")
            if not contextily_available():
                st.caption("contextily not installed — `pip install contextily` or use requirements.txt")
            elif not panel_has_geography(panel, float(view_lo), float(view_hi)):
                st.caption("Panel lacks lat/lon rows in the current view window.")
            elif show_topo:
                layer_caption = HITL_BASEMAP_LAYER_LABELS[basemap_layer]
                st.caption(
                    f"Topo ({layer_caption}): km {view_lo:.1f}–{view_hi:.1f} · 1:1 aspect · metric scalebar · "
                    "static (no Plotly zoom follow)"
                )
                if basemap_layer == "satellite_flyfoto" and not nib_wmts_token_configured():
                    st.warning(
                        "Orthophoto requires `NIB_WMTS_TOKEN`. Generate a token at "
                        "services.norgeibilder.no/token and `export NIB_WMTS_TOKEN=…` before launch. "
                        "Standard / greyscale work without a token."
                    )

            st.header("Crosshair")
            _init_interaction_state(
                float(view_lo),
                float(view_hi),
                profile=profile,
                terrain_map=terrain_map,
                hmm_draft=hmm_draft,
            )
            ch_km = float(st.session_state.get("crosshair_km", view_lo))
            ch_ti = st.session_state.get("crosshair_ti", float("nan"))
            ch_cls = str(st.session_state.get("crosshair_class", "—"))
            cx1, cx2, cx3 = st.columns(3)
            cx1.metric("km", f"{ch_km:.3f}")
            ti_display = f"{float(ch_ti):.3f}" if ch_ti is not None and pd.notna(ch_ti) else "—"
            cx2.metric("TI", ti_display)
            cx3.metric("Class", ch_cls)
            pick_col1, pick_col2 = st.columns(2)
            with pick_col1:
                if st.button("Set Start", width="stretch", help="Then click the profile to set course_km_start"):
                    st.session_state["lock_pick_mode"] = "start"
            with pick_col2:
                if st.button("Set End", width="stretch", help="Then click the profile to set course_km_end"):
                    st.session_state["lock_pick_mode"] = "end"
            pick_mode = st.session_state.get("lock_pick_mode")
            if pick_mode == "start":
                st.info("Click profile → sets **course_km_start**.")
            elif pick_mode == "end":
                st.info("Click profile → sets **course_km_end**.")
            if not plotly_events_usable():
                st.warning(
                    "Interactive profile uses native point selection. "
                    "For hover crosshair + click-to-set, install in the project venv: "
                    "`pip install streamlit-plotly-events2` and restart via "
                    "`.venv/bin/python -m streamlit run ...`"
                )

            st.header("Lock span")
            lock_start = st.number_input(
                "course_km_start (lock)",
                step=0.01,
                format="%.3f",
                key="lock_start_km",
            )
            lock_end = st.number_input(
                "course_km_end (lock)",
                step=0.01,
                format="%.3f",
                key="lock_end_km",
            )
            surface_class = st.selectbox("surface_class", SURFACE_CLASSES, index=2)
            friction_tier = st.selectbox("friction_tier", FRICTION_TIERS, index=2)
            reason = st.text_area("reason", placeholder="Clinical lock rationale…", height=68)

            st.header("Safety")
            dry_run_lock = st.checkbox(
                "Dry-run Save Lock (preview only — no JSON write)",
                value=True,
                help="Uncheck only when ready to append operator gold. Overlap guard + confirmation modal still apply.",
            )
            save_clicked = st.button("Save Lock", type="primary", width="stretch")

    if not paths_ok:
        return

    if save_clicked:
        try:
            overlaps = validate_gold_span(
                terrain_map,
                km_start=float(lock_start),
                km_end=float(lock_end),
            )
            if overlaps:
                first = overlaps[0]
                st.error(
                    f"Overlap blocked: km {lock_start:.3f}–{lock_end:.3f} intersects existing gold "
                    f"km {float(first['course_km_start']):.3f}–{float(first['course_km_end']):.3f}"
                )
            elif dry_run_lock:
                entry = append_operator_gold_span(
                    Path(terrain_map_path),
                    km_start=float(lock_start),
                    km_end=float(lock_end),
                    surface_class=surface_class,
                    friction_tier=friction_tier,
                    reason=reason,
                    dry_run=True,
                )
                st.warning(
                    f"[DRY-RUN] Would append {entry['surface_class']}/{entry['friction_tier']} "
                    f"km {entry['course_km_start']:.3f}–{entry['course_km_end']:.3f} → "
                    f"`{Path(terrain_map_path).name}`"
                )
            else:
                confirm_save_dialog(
                    terrain_map_path=terrain_map_path,
                    km_start=float(lock_start),
                    km_end=float(lock_end),
                    surface_class=surface_class,
                    friction_tier=friction_tier,
                    reason=reason,
                )
        except ValueError as exc:
            st.error(str(exc))

    view_caption = f"km {view_lo:.1f}–{view_hi:.1f}"
    if queue_label:
        view_caption += f" · queue {queue_label}"
    st.caption(
        f"Telemetry profile · {view_caption} · panel rows {len(panel):,} · "
        f"v{APP_VERSION} · drag-zoom syncs all profile rows on course_km"
    )

    hmm_blocks = hmm_blocks_in_window(hmm_draft, float(view_lo), float(view_hi))
    operator_gold = operator_gold_blocks_in_window(terrain_map, float(view_lo), float(view_hi))

    disagree_pct = draft_gold_disagreement_pct(hmm_draft, terrain_map, float(view_lo), float(view_hi))
    if disagree_pct is not None and operator_gold and hmm_blocks:
        st.caption(
            f"Draft vs gold: **{disagree_pct:.1f}%** of gold-covered metres disagree "
            f"(HMM draft S-class ≠ operator gold) in km {view_lo:.1f}–{view_hi:.1f}"
        )
    _plot_pad, plot_col, _plot_pad2 = st.columns([1, 2, 1])
    with plot_col:
        profile_event_key = f"hitl_profile_{view_lo:.3f}_{view_hi:.3f}_{viz_mode}"
        _render_profile_interaction(
            profile=profile,
            terrain_map=terrain_map,
            hmm_draft=hmm_draft,
            profile_event_key=profile_event_key,
            view_lo=float(view_lo),
            view_hi=float(view_hi),
            viz_mode=viz_mode,
            show_hmm_overlay=show_hmm_overlay,
            subject_profiles=subject_profiles if show_athletes else None,
            hmm_blocks=hmm_blocks,
            operator_gold=operator_gold,
            queue_label=queue_label,
        )

    if show_topo:
        try:
            topo_png, topo_status = render_topo_basemap_png(
                panel_path,
                terrain_map_path,
                float(view_lo),
                float(view_hi),
                basemap=basemap_layer,
                lat_offset=float(lat_offset),
                lon_offset=float(lon_offset),
                map_track_operator_gold=map_track_operator_gold,
            )
        except (BrokenPipeError, OSError, RuntimeError) as exc:
            st.error(f"Topo basemap unavailable ({type(exc).__name__}); profile plots remain above.")
            topo_png, topo_status = None, f"no ({exc})"
        else:
            if topo_png:
                layer_label = HITL_BASEMAP_LAYER_LABELS[basemap_layer]
                _topo_pad, topo_col, _topo_pad2 = st.columns([1, 2, 1])
                with topo_col:
                    track_label = "operator gold" if map_track_operator_gold else "GMM draft"
                    display_aspect_locked_image(
                        topo_png,
                        caption=(
                            f"Topo reference · {layer_label} · km {view_lo:.1f}–{view_hi:.1f} · "
                            f"track: {track_label}"
                        ),
                        max_width_px=TOPO_MAP_MAX_DISPLAY_PX,
                    )
                if topo_status.startswith("no"):
                    st.warning(f"Basemap tiles unavailable: {topo_status}")
                else:
                    st.caption(topo_status)
            else:
                st.warning(f"Topo panel skipped: {topo_status}")

    gold_count = len(terrain_map.get("hitl", {}).get("operator_gold_spans") or [])
    st.info(
        f"Map: `{Path(terrain_map_path).name}` · operator_gold_spans: {gold_count} · "
        f"HITL status: {terrain_map.get('hitl', {}).get('status', 'draft')}"
    )


def run_import_test() -> None:
    """Verify module imports and core helpers without Streamlit runtime."""
    assert spans_overlap(0.0, 1.0, 0.5, 1.5)
    assert not spans_overlap(0.0, 1.0, 1.0, 2.0)
    dummy_map = {"hitl": {"operator_gold_spans": [{"course_km_start": 10.0, "course_km_end": 11.0, "surface_class": "S3", "friction_tier": "F2"}]}}
    overlaps = validate_gold_span(dummy_map, km_start=10.5, km_end=11.5)
    assert len(overlaps) == 1
    assert validate_gold_span(dummy_map, km_start=12.0, km_end=13.0) == []
    assert nearest_metre_km(
        pd.DataFrame({"course_km": [34.0, 34.641, 34.7]}),
        34.64,
    ) == 34.641
    assert class_label_at_km(dummy_map, pd.DataFrame(), 10.5) == "S3/F2"

    assert normalize_basemap_layer("kartverket-topo") == "topo_standard"
    assert normalize_basemap_layer("topo_grayscale") == "topo_grayscale"
    assert normalize_basemap_layer("satellite_flyfoto") == "satellite_flyfoto"
    try:
        assert_basemap_not_maritime("sjokartraster")
        raise AssertionError("maritime guard expected ValueError")
    except ValueError:
        pass
    bar_m, label = pick_metric_scalebar_length_m(800.0)
    assert bar_m in (100.0, 200.0, 250.0) and "m" in label
    bounds = (6.0, 59.0, 6.01, 59.01)
    assert len(plotly_geo_scalebar_annotations(bounds)) == 2

    panel_path = DEFAULT_PANEL
    terrain_map = load_terrain_map(DEFAULT_TERRAIN_MAP) if DEFAULT_TERRAIN_MAP.exists() else dummy_map
    if panel_path.exists():
        panel = pd.read_parquet(panel_path)
        profile = build_consensus_profile(panel)
        hmm = pd.read_parquet(DEFAULT_HMM_DRAFT) if DEFAULT_HMM_DRAFT.exists() else pd.DataFrame()
        km_lo, km_hi = 34.0, 35.0
        snap = crosshair_snapshot(profile, terrain_map, hmm, 34.64)
        print(
            f"chunk_05_calibration: km={snap['course_km']:.3f} "
            f"TI={snap['ti']:.3f} class={snap['class_label']}"
        )
        snap_start = crosshair_snapshot(profile, terrain_map, hmm, 34.0)
        assert np.isfinite(snap_start["ti"]), "crosshair TI must seed at chunk start without hover"
        assert snap_start["class_label"] != "—" or not operator_gold_blocks_in_window(terrain_map, 34.0, 35.0), (
            "crosshair class should resolve from gold/HMM at chunk start"
        )
        print(
            f"crosshair_seed_test: km={snap_start['course_km']:.3f} "
            f"TI={snap_start['ti']:.3f} class={snap_start['class_label']}"
        )
        blocks = hmm_blocks_in_window(hmm, km_lo, km_hi)
        gold = operator_gold_blocks_in_window(terrain_map, km_lo, km_hi)
        fig_on = build_plotly_figure(
            profile,
            km_lo=km_lo,
            km_hi=km_hi,
            viz_mode="continuous",
            show_hmm_overlay=True,
            hmm_blocks=blocks,
            operator_gold=gold,
            hmm_draft=hmm,
            terrain_map=terrain_map,
            crosshair_km=34.64,
        )
        fig_off = build_plotly_figure(
            profile,
            km_lo=km_lo,
            km_hi=km_hi,
            viz_mode="continuous",
            show_hmm_overlay=False,
            hmm_blocks=blocks,
            operator_gold=gold,
            hmm_draft=hmm,
            terrain_map=terrain_map,
        )
        assert fig_on.layout.dragmode == "zoom"
        assert fig_on.layout.uirevision == f"profile_v2_{km_lo:.3f}_{km_hi:.3f}_continuous"
        assert list(fig_on.layout.xaxis.range) == [km_lo, km_hi]
        assert len(fig_on.layout.shapes or []) > len(fig_off.layout.shapes or [])
        assert len(fig_on.data) < 25, f"figure trace budget exceeded: {len(fig_on.data)}"
        print(
            f"figure_test: OK (dragmode={fig_on.layout.dragmode}, shapes on={len(fig_on.layout.shapes or [])} "
            f"off={len(fig_off.layout.shapes or [])}, traces={len(fig_on.data)})"
        )

        ch08_lo, ch08_hi = 37.0, 38.0
        panel_win = load_panel_window_cached(str(panel_path), ch08_lo, ch08_hi)
        profile_win = build_consensus_profile(panel_win)
        view08 = profile_win[(profile_win["course_km"] >= ch08_lo) & (profile_win["course_km"] < ch08_hi)]
        assert len(view08) >= 900, f"chunk_08 expected ~1000 rows, got {len(view08)}"
        assert bool(view08["ti_median"].notna().all()), "chunk_08 TI must not be all-NaN"
        snap08 = crosshair_snapshot(profile_win, terrain_map, hmm, ch08_lo)
        assert np.isfinite(snap08["ti"]), "chunk_08 crosshair TI must seed at window start"
        blocks08 = hmm_blocks_in_window(hmm, ch08_lo, ch08_hi)
        gold08 = operator_gold_blocks_in_window(terrain_map, ch08_lo, ch08_hi)
        assigned08 = operator_gold_assigned_spans(terrain_map, ch08_lo, ch08_hi)
        assert assigned08, "chunk_08 must have operator gold assigned spans for map overlay"
        disagree08 = draft_gold_disagreement_pct(hmm, terrain_map, ch08_lo, ch08_hi)
        assert disagree08 is not None, "chunk_08 draft vs gold metric must resolve"
        fig08 = build_plotly_figure(
            profile_win,
            km_lo=ch08_lo,
            km_hi=ch08_hi,
            viz_mode="continuous",
            show_hmm_overlay=True,
            hmm_blocks=blocks08,
            operator_gold=gold08,
            hmm_draft=hmm,
            terrain_map=terrain_map,
            crosshair_km=ch08_lo,
        )
        fig08_cat = build_plotly_figure(
            profile_win,
            km_lo=ch08_lo,
            km_hi=ch08_hi,
            viz_mode="categorical",
            hmm_blocks=blocks08,
            operator_gold=gold08,
            hmm_draft=hmm,
            terrain_map=terrain_map,
            crosshair_km=ch08_lo,
        )
        assert fig08_cat.layout.annotations[5].text.startswith("F-tier"), (
            "chunk_08 categorical row 6 must be F-tier / S-class overlay"
        )
        png08_gold, status08_gold = render_topo_basemap_png(
            str(panel_path),
            str(DEFAULT_TERRAIN_MAP),
            ch08_lo,
            ch08_hi,
            map_track_operator_gold=True,
        )
        png08_draft, status08_draft = render_topo_basemap_png(
            str(panel_path),
            str(DEFAULT_TERRAIN_MAP),
            ch08_lo,
            ch08_hi,
            map_track_operator_gold=False,
        )
        ti_traces = [t for t in fig08.data if getattr(t, "name", None) == "TI"]
        assert len(ti_traces) == 1, f"chunk_08 TI must be single trace, got {len(ti_traces)}"
        assert ti_traces[0].type == "scatter", "chunk_08 TI must be scatter trace"
        heatmaps = [t for t in fig08.data if t.type == "heatmap"]
        assert not heatmaps, f"chunk_08 must not use heatmap (renders solid block), got {len(heatmaps)}"
        nti_traces = [t for t in fig08.data if getattr(t, "name", None) == "NTI σ"]
        assert len(nti_traces) == 1, f"chunk_08 NTI σ must be single scatter trace, got {len(nti_traces)}"
        nti_y = np.asarray(nti_traces[0].y, dtype=float)
        assert int(np.isfinite(nti_y).sum()) >= 900, "chunk_08 NTI σ must have >=900 finite points"
        assert fig08.layout.yaxis2.range is not None, "chunk_08 NTI y-axis must have explicit range"
        ti_x = np.asarray(ti_traces[0].x, dtype=float)
        assert float(ti_x.min()) >= ch08_lo and float(ti_x.max()) < ch08_hi + 0.01, (
            f"chunk_08 TI x out of window: [{ti_x.min():.3f}, {ti_x.max():.3f}]"
        )
        for ax_name in ("xaxis", "xaxis2", "xaxis3", "xaxis4", "xaxis5", "xaxis6"):
            ax = getattr(fig08.layout, ax_name)
            assert list(ax.range) == [ch08_lo, ch08_hi], f"{ax_name}.range={ax.range}"
            assert ax.autorange is False, f"{ax_name}.autorange must be False"
        spd08 = [t for t in fig08.data if "spd" in str(getattr(t, "name", "")).lower()]
        assert spd08, "chunk_08 must include speed trace"
        spd_y = np.asarray(spd08[0].y, dtype=float)
        assert int(np.isfinite(spd_y).sum()) >= 900, "chunk_08 consensus speed must have >=900 finite points"
        grade08 = [t for t in fig08.data if getattr(t, "name", None) == "grade"]
        assert grade08 and int(np.isfinite(np.asarray(grade08[0].y)).sum()) >= 900, (
            "chunk_08 grade trace must have >=900 finite points"
        )
        pace08 = [t for t in fig08.data if getattr(t, "name", None) == "pace expected"]
        assert pace08 and int(np.isfinite(np.asarray(pace08[0].y)).sum()) >= 900, (
            "chunk_08 pace expected trace must have >=900 finite points"
        )
        assert fig08.layout.yaxis3.range is not None, "chunk_08 speed y-axis must have explicit range"
        y0_08, y1_08 = (float(fig08.layout.yaxis3.range[0]), float(fig08.layout.yaxis3.range[1]))
        assert y1_08 > y0_08, f"chunk_08 speed y-axis invalid: [{y0_08}, {y1_08}]"
        assert (y1_08 - y0_08) < 2.5, f"chunk_08 speed y-axis should be tight: [{y0_08}, {y1_08}]"
        assert fig08.layout.uirevision == f"profile_v2_{ch08_lo:.3f}_{ch08_hi:.3f}_continuous"
        assert len(fig08.data) < 25, f"chunk_08 figure trace budget exceeded: {len(fig08.data)}"
        print(
            f"chunk_08_vassfjellet: rows={len(view08)} "
            f"ti=[{view08['ti_median'].min():.3f}, {view08['ti_median'].max():.3f}] "
            f"crosshair TI={snap08['ti']:.3f} class={snap08['class_label']} "
            f"gold_spans={len(gold08)} draft_vs_gold={disagree08:.1f}% "
            f"map_gold={'OK' if png08_gold else status08_gold} "
            f"map_draft={'OK' if png08_draft else status08_draft} "
            f"traces={len(fig08.data)}"
        )

        ch00_lo, ch00_hi = 22.0, 23.0
        upstream_map = (
            load_terrain_map(BASE_DIR / "config/spatial_terrain_map_sut43_upstream.json")
            if (BASE_DIR / "config/spatial_terrain_map_sut43_upstream.json").exists()
            else terrain_map
        )
        panel00 = load_panel_window_cached(str(panel_path), ch00_lo, ch00_hi)
        profile00 = build_consensus_profile(panel00)
        subs00 = per_subject_profiles(panel00)
        view00 = profile00[(profile00["course_km"] >= ch00_lo) & (profile00["course_km"] < ch00_hi)]
        assert len(view00) >= 900, f"chunk_00 expected ~1000 rows, got {len(view00)}"
        assert int(view00["speed_median"].notna().sum()) >= 900, (
            f"chunk_00 speed_median coverage low: {view00['speed_median'].notna().sum()}"
        )
        first_speed_km = float(view00.loc[view00["speed_median"].notna(), "course_km"].iloc[0])
        assert first_speed_km <= ch00_lo + 0.01, (
            f"chunk_00 speed should start near km {ch00_lo}, first at {first_speed_km:.3f}"
        )
        snap00 = crosshair_snapshot(profile00, upstream_map, hmm, ch00_lo + 0.001)
        assert np.isfinite(snap00["ti"]), "chunk_00 crosshair TI must resolve from km 22.001"
        blocks00 = hmm_blocks_in_window(hmm, ch00_lo, ch00_hi)
        gold00 = operator_gold_blocks_in_window(upstream_map, ch00_lo, ch00_hi)
        fig00 = build_plotly_figure(
            profile00,
            km_lo=ch00_lo,
            km_hi=ch00_hi,
            viz_mode="continuous",
            show_hmm_overlay=True,
            subject_profiles=subs00,
            hmm_blocks=blocks00,
            operator_gold=gold00,
            hmm_draft=hmm,
            terrain_map=upstream_map,
            crosshair_km=ch00_lo,
            queue_label="RED",
        )
        spd_traces = [t for t in fig00.data if "spd" in str(getattr(t, "name", "")).lower()]
        assert len(spd_traces) >= 3, f"chunk_00 expected consensus + athlete speed traces, got {len(spd_traces)}"
        for trace in spd_traces:
            y = np.asarray(trace.y, dtype=float)
            finite = int(np.isfinite(y).sum())
            assert finite >= 900, f"chunk_00 {trace.name} must have >=900 finite speed points, got {finite}"
        grade00 = [t for t in fig00.data if getattr(t, "name", None) == "grade"]
        assert grade00 and int(np.isfinite(np.asarray(grade00[0].y)).sum()) >= 900, (
            "chunk_00 grade trace must have >=900 finite points"
        )
        pace00 = [t for t in fig00.data if getattr(t, "name", None) == "pace expected"]
        assert pace00 and int(np.isfinite(np.asarray(pace00[0].y)).sum()) >= 900, (
            "chunk_00 pace expected trace must have >=900 finite points"
        )
        assert fig00.layout.yaxis3.range is not None, "chunk_00 speed y-axis must have explicit range"
        y0, y1 = (float(fig00.layout.yaxis3.range[0]), float(fig00.layout.yaxis3.range[1]))
        assert y1 > y0, f"chunk_00 speed y-axis invalid: [{y0}, {y1}]"
        assert (y1 - y0) < 2.5, f"chunk_00 speed y-axis should be tight: [{y0}, {y1}]"
        for ax_name in ("xaxis", "xaxis2", "xaxis3", "xaxis4", "xaxis5", "xaxis6"):
            ax = getattr(fig00.layout, ax_name)
            assert list(ax.range) == [ch00_lo, ch00_hi], f"chunk_00 {ax_name}.range={ax.range}"
        assert fig00.layout.uirevision == f"profile_v2_{ch00_lo:.3f}_{ch00_hi:.3f}_continuous"
        print(
            f"chunk_00_upstream: rows={len(view00)} "
            f"speed_start_km={first_speed_km:.3f} "
            f"crosshair TI={snap00['ti']:.3f} class={snap00['class_label']} "
            f"speed_traces={len(spd_traces)} yaxis3={list(fig00.layout.yaxis3.range)}"
        )

        for km_lo, km_hi in ((34.0, 35.0), (37.0, 38.0)):
            for layer_id in ("topo_standard", "topo_grayscale", "satellite_flyfoto"):
                for map_gold in (False, True):
                    png, status = render_topo_basemap_png(
                        str(panel_path),
                        str(DEFAULT_TERRAIN_MAP),
                        km_lo,
                        km_hi,
                        basemap=layer_id,  # type: ignore[arg-type]
                        map_track_operator_gold=map_gold,
                    )
                    mode_tag = "gold" if map_gold else "draft"
                    if layer_id == "satellite_flyfoto" and not nib_wmts_token_configured():
                        assert "NIB_WMTS_TOKEN" in status
                        print(
                            f"basemap_render_test: {layer_id} km {km_lo:.0f}-{km_hi:.0f} "
                            f"{mode_tag} -> token gate OK ({status})"
                        )
                    else:
                        ok = png is not None and not status.startswith("no")
                        if ok and png is not None:
                            w, h = _png_pixel_size(png)
                            assert abs(w / h - 1.0) < 0.05, (
                                f"topo PNG must be square 1:1, got {w}x{h} km {km_lo:.0f}-{km_hi:.0f}"
                            )
                            print(
                                f"basemap_render_test: {layer_id} km {km_lo:.0f}-{km_hi:.0f} {mode_tag} -> "
                                f"OK {w}x{h}px"
                            )
                        else:
                            print(
                                f"basemap_render_test: {layer_id} km {km_lo:.0f}-{km_hi:.0f} {mode_tag} -> "
                                f"{'OK' if ok else status}"
                            )
    else:
        print("figure_test: skipped — panel parquet missing")

    print("import_test: OK")


def run_safety_dry_run_test(test_json: Path | None = None) -> int:
    """Dry-run append + overlap gate; writes temp_test.json only."""
    run_import_test()
    out = test_json or (BASE_DIR / "temp_test.json")
    if out.resolve() == DEFAULT_TERRAIN_MAP.resolve():
        print("dry_run_test: refused — target is production terrain map", file=sys.stderr)
        return 1
    template = {"hitl": {"status": "draft", "operator_gold_spans": [{"course_km_start": 99.0, "course_km_end": 100.0, "surface_class": "S3", "friction_tier": "F2", "gold_source": "operator", "mode": "operator_gold", "locked_at": "2026-06-29", "reason": "seed"}]}}
    out.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")

    try:
        append_operator_gold_span(
            out,
            km_start=99.5,
            km_end=100.5,
            surface_class="S4",
            friction_tier="F3",
            reason="overlap probe",
        )
        print("dry_run_test: FAIL — overlap gate did not block", file=sys.stderr)
        return 1
    except ValueError as exc:
        if "overlaps" not in str(exc).lower():
            print(f"dry_run_test: FAIL — unexpected error: {exc}", file=sys.stderr)
            return 1
        print(f"dry_run_test: overlap gate OK ({exc})")

    entry = append_operator_gold_span(
        out,
        km_start=101.0,
        km_end=102.0,
        surface_class="S3",
        friction_tier="F2",
        reason="dry-run write probe",
        dry_run=False,
    )
    saved = json.loads(out.read_text(encoding="utf-8"))
    spans = saved.get("hitl", {}).get("operator_gold_spans") or []
    if len(spans) != 2 or spans[-1]["course_km_start"] != entry["course_km_start"]:
        print("dry_run_test: FAIL — append count mismatch", file=sys.stderr)
        return 1
    print(f"dry_run_test: append OK → {out.name} ({len(spans)} spans)")
    return 0


if __name__ == "__main__":
    if "--dry-run-test" in sys.argv:
        raise SystemExit(run_safety_dry_run_test())
    if "--import-test" in sys.argv:
        run_import_test()
        raise SystemExit(0)
    main()
