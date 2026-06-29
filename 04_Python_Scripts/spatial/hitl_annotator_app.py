#!/usr/bin/env python3
"""
Interactive HITL terrain annotator — local Streamlit app.

Loads RPS triage queue, race panel telemetry, HMM draft blocks, and terrain map
JSON; renders Plotly profile with cross-athlete σ heatmap.

Usage (from repo root):
    streamlit run 04_Python_Scripts/spatial/hitl_annotator_app.py --server.headless true

    streamlit run 04_Python_Scripts/spatial/hitl_annotator_app.py -- \\
        --triage-queue 03_Processed_Data/spatial/sut43_terrain_ontology/ground_truth_review/triage_queue_sut43.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.corridor_scope import SUT43_FULL_KM_END, SUT43_FULL_KM_START
from spatial.spatial_hitl_overlay import SURFACE_COLORS, load_terrain_map
from spatial.terrain_map_gen import aggregate_nti_by_course_m, compute_nti

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
QUEUE_COLORS = {"RED": "#EF5350", "YELLOW": "#FFB74D", "GREEN": "#66BB6A"}


def _parse_cli_defaults() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--terrain-map", type=Path, default=DEFAULT_TERRAIN_MAP)
    parser.add_argument("--triage-queue", type=Path, default=DEFAULT_TRIAGE_QUEUE)
    parser.add_argument("--hmm-draft", type=Path, default=DEFAULT_HMM_DRAFT)
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1 :]
    else:
        argv = []
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
    per_m = race.groupby("course_m", as_index=False).agg(
        course_km=("course_km", "first"),
        speed_median=("speed_mps", "median"),
        grade_pct_median=("grade_pct", "median"),
        cadence_median=("cadence_spm", "median"),
        ti_median=("ti", "median"),
        ti_raw_median=("ti_raw", "median"),
    )
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


def _class_strip_y(cls: str | None) -> float:
    if cls in SURFACE_CLASSES:
        return float(SURFACE_CLASSES.index(cls))
    return float("nan")


def build_plotly_figure(
    profile: pd.DataFrame,
    *,
    km_lo: float,
    km_hi: float,
    subject_profiles: dict[str, pd.DataFrame] | None = None,
    hmm_blocks: list[dict[str, Any]] | None = None,
    queue_label: str = "",
) -> go.Figure:
    view = profile[(profile["course_km"] >= km_lo) & (profile["course_km"] < km_hi)].copy()
    if view.empty:
        fig = go.Figure()
        fig.update_layout(title="No panel rows in selected window")
        return fig

    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.22, 0.22, 0.30, 0.14],
        subplot_titles=("Raw TI trace", "Cross-athlete σ (NTI)", "Speed (m/s)", "HMM draft blocks"),
    )

    ti_col = "ti_median" if "ti_median" in view.columns else "ti_raw_median"
    fig.add_trace(
        go.Scatter(
            x=view["course_km"],
            y=view[ti_col],
            mode="lines",
            name="raw TI",
            line=dict(color="#CE93D8", width=1.5),
            hovertemplate="course_km=%{x:.3f}<br>TI=%{y:.3f}<extra></extra>",
        ),
        row=1,
        col=1,
    )

    if "nti_std" in view.columns:
        fig.add_trace(
            go.Heatmap(
                x=view["course_km"],
                y=["σ"],
                z=[view["nti_std"].fillna(0).to_numpy()],
                colorscale="YlOrRd",
                showscale=True,
                colorbar=dict(title="NTI σ", len=0.25, y=0.55),
                hovertemplate="course_km=%{x:.3f}<br>σ=%{z:.3f}<extra></extra>",
                name="cross-athlete σ",
            ),
            row=2,
            col=1,
        )

    fig.add_trace(
        go.Scatter(
            x=view["course_km"],
            y=view["speed_median"],
            mode="lines",
            name="consensus speed",
            line=dict(color="#00E5FF", width=1.5),
            hovertemplate="course_km=%{x:.3f}<br>speed=%{y:.2f} m/s<extra></extra>",
        ),
        row=3,
        col=1,
    )

    if subject_profiles:
        palette = {"Subject_A": "#4FC3F7", "Subject_B": "#81C784"}
        for sid, sub_df in subject_profiles.items():
            sub_view = sub_df[(sub_df["course_km"] >= km_lo) & (sub_df["course_km"] < km_hi)]
            if sub_view.empty:
                continue
            fig.add_trace(
                go.Scatter(
                    x=sub_view["course_km"],
                    y=sub_view["speed_mps"],
                    mode="lines",
                    name=f"{sid} speed",
                    line=dict(color=palette.get(sid, "#AAA"), width=0.9, dash="dot"),
                    opacity=0.75,
                ),
                row=3,
                col=1,
            )

    for span in hmm_blocks or []:
        s0 = float(span["course_km_start"])
        s1 = float(span["course_km_end"])
        if s1 < km_lo or s0 > km_hi:
            continue
        cls = str(span.get("surface_class", "S2"))
        color = SURFACE_COLORS.get(cls, "#888888")
        y0 = _class_strip_y(cls)
        fig.add_shape(
            type="rect",
            x0=max(s0, km_lo),
            x1=min(s1, km_hi),
            y0=y0 - 0.4,
            y1=y0 + 0.4,
            fillcolor=color,
            opacity=0.75,
            line_width=0,
            row=4,
            col=1,
        )

    fig.update_yaxes(title_text="TI", row=1, col=1)
    fig.update_yaxes(showticklabels=False, row=2, col=1)
    fig.update_yaxes(title_text="m/s", row=3, col=1)
    fig.update_yaxes(
        tickvals=list(range(len(SURFACE_CLASSES))),
        ticktext=list(SURFACE_CLASSES),
        row=4,
        col=1,
    )
    fig.update_xaxes(title_text="course_km", row=4, col=1)
    title = f"HITL Annotator — km {km_lo:.1f}–{km_hi:.1f}"
    if queue_label:
        title += f" · {queue_label}"
    fig.update_layout(
        height=860,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=50, r=20, t=60, b=40),
        title=title,
    )
    return fig


def append_operator_gold_span(
    terrain_map_path: Path,
    *,
    km_start: float,
    km_end: float,
    surface_class: str,
    friction_tier: str,
    reason: str,
) -> dict[str, Any]:
    if km_end <= km_start:
        raise ValueError("course_km_end must exceed course_km_start")
    terrain_map = load_terrain_map(terrain_map_path)
    hitl = terrain_map.setdefault("hitl", {})
    spans: list[dict[str, Any]] = list(hitl.get("operator_gold_spans") or [])
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
    spans.append(entry)
    hitl["operator_gold_spans"] = spans
    terrain_map_path.write_text(json.dumps(terrain_map, indent=2) + "\n", encoding="utf-8")
    return entry


@st.cache_data(show_spinner=False)
def load_panel_cached(path: str) -> pd.DataFrame:
    return pd.read_parquet(Path(path))


@st.cache_data(show_spinner=False)
def load_map_cached(path: str) -> dict[str, Any]:
    return load_terrain_map(Path(path))


@st.cache_data(show_spinner=False)
def load_triage_cached(path: str) -> pd.DataFrame:
    return pd.read_csv(Path(path))


@st.cache_data(show_spinner=False)
def load_hmm_cached(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


def main() -> None:
    cli = _parse_cli_defaults()
    st.set_page_config(page_title="HITL Terrain Annotator", layout="wide")
    st.title("HITL Terrain Annotator")
    st.caption("RPS triage queue · Subject_A / Subject_B telemetry · Dr. Anatomy Pace laboratory")

    with st.sidebar:
        st.header("Data sources")
        panel_path = st.text_input("Panel parquet", value=str(cli.panel))
        terrain_map_path = st.text_input("Terrain map JSON", value=str(cli.terrain_map))
        triage_path = st.text_input("Triage queue CSV", value=str(cli.triage_queue))
        hmm_path = st.text_input("HMM draft parquet", value=str(cli.hmm_draft))

        if not Path(panel_path).exists():
            st.error(f"Panel not found: {panel_path}")
            st.stop()
        if not Path(terrain_map_path).exists():
            st.error(f"Terrain map not found: {terrain_map_path}")
            st.stop()

        panel = load_panel_cached(panel_path)
        terrain_map = load_map_cached(terrain_map_path)
        hmm_draft = load_hmm_cached(hmm_path)
        profile = build_consensus_profile(panel)
        subject_profiles = per_subject_profiles(panel)

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
            km_min = float(profile["course_km"].min())
            km_max = float(profile["course_km"].max())
            view_lo = st.slider("course_km_start", km_min, km_max, max(km_min, SUT43_FULL_KM_START), step=0.1)
            view_hi = st.slider("course_km_end", km_min, km_max, min(km_max, SUT43_FULL_KM_END), step=0.1)
            queue_label = ""

        if view_hi <= view_lo:
            view_hi = min(view_lo + 1.0, float(profile["course_km"].max()))

        show_athletes = st.checkbox("Athlete overlay (Subject_A / Subject_B)", value=True)

        st.header("Lock span")
        lock_start = st.number_input("course_km_start (lock)", value=float(view_lo), step=0.01, format="%.3f")
        lock_end = st.number_input("course_km_end (lock)", value=float(view_hi), step=0.01, format="%.3f")
        surface_class = st.selectbox("surface_class", SURFACE_CLASSES, index=2)
        friction_tier = st.selectbox("friction_tier", FRICTION_TIERS, index=2)
        reason = st.text_area("reason", placeholder="Clinical lock rationale…")
        save_clicked = st.button("Save Lock", type="primary")

    if save_clicked:
        try:
            entry = append_operator_gold_span(
                Path(terrain_map_path),
                km_start=float(lock_start),
                km_end=float(lock_end),
                surface_class=surface_class,
                friction_tier=friction_tier,
                reason=reason,
            )
            load_map_cached.clear()
            st.success(
                f"Promoted {entry['surface_class']}/{entry['friction_tier']} "
                f"km {entry['course_km_start']:.3f}–{entry['course_km_end']:.3f}"
            )
            terrain_map = load_map_cached(terrain_map_path)
        except Exception as exc:
            st.error(str(exc))

    hmm_blocks = hmm_blocks_in_window(hmm_draft, float(view_lo), float(view_hi))
    fig = build_plotly_figure(
        profile,
        km_lo=float(view_lo),
        km_hi=float(view_hi),
        subject_profiles=subject_profiles if show_athletes else None,
        hmm_blocks=hmm_blocks,
        queue_label=queue_label,
    )
    st.plotly_chart(fig, use_container_width=True)

    gold_count = len(terrain_map.get("hitl", {}).get("operator_gold_spans") or [])
    st.info(
        f"Map: `{Path(terrain_map_path).name}` · operator_gold_spans: {gold_count} · "
        f"HITL status: {terrain_map.get('hitl', {}).get('status', 'draft')}"
    )


if __name__ == "__main__":
    main()
