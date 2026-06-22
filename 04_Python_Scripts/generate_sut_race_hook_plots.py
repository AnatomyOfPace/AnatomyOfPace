#!/usr/bin/env python3
"""
Hook plots for SUT_160 race telemetry (pace-only — no HR in Strava stream).

Usage:
    python 04_Python_Scripts/generate_sut_race_hook_plots.py
    python 04_Python_Scripts/generate_sut_race_hook_plots.py --activity 18159079828
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import Normalize
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import donor_io

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "docs" / "outreach" / "plots" / "sut2026_race"
CORRIDORS_PATH = BASE_DIR / "config" / "race_corridors.json"

DONOR_ID = "Reference_Elite_D"
SUT_RACE_ACTIVITY = "18159079828"
LOOP_KM = 43.0

BG = "#0A0A0A"
GRID = "#2A2A2A"
TEXT = "#A0A0A0"
CYAN = "#00E5FF"
AMBER = "#FFB300"
MAGENTA = "#FF0055"
WHITE = "#FFFFFF"
FIG_W, FIG_H = 10.0, 4.2
DPI = 180

_spec = importlib.util.spec_from_file_location(
    "gap_engine", Path(__file__).parent / "11_gap_engine.py"
)
_gap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gap)


def _style_axes(ax: plt.Axes) -> None:
    ax.set_facecolor(BG)
    ax.tick_params(colors=TEXT, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.grid(color=GRID, linestyle="--", linewidth=0.5, alpha=0.75)
    ax.xaxis.label.set_color(TEXT)
    ax.yaxis.label.set_color(TEXT)
    ax.title.set_color(WHITE)


def _save(fig: plt.Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return path


def donor_json(donor_id: str, activity_id: str) -> Path:
    path = donor_io.DONOR_DIR / donor_id / f"activity_{activity_id}.strava.json"
    if not path.exists():
        path = donor_io.INBOX_DIR / donor_id / f"activity_{activity_id}.strava.json"
    if not path.exists():
        raise FileNotFoundError(f"No telemetry for {donor_id} activity {activity_id}")
    return path


def load_race_session(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    streams = payload.get("streams", {})
    n = len(streams["time"]["data"])
    start = pd.Timestamp(payload.get("start_date"))
    times = streams["time"]["data"]
    df = pd.DataFrame(
        {
            "timestamp": start + pd.to_timedelta(times, unit="s"),
            "distance": streams.get("distance", {}).get("data", [0.0] * n),
            "altitude": streams.get("altitude", {}).get("data"),
            "enhanced_speed": streams.get("velocity_smooth", {}).get("data"),
            "time_s": times,
        }
    )
    df = df[df["enhanced_speed"] > _gap.MIN_SPEED_M_S].copy()
    df["speed_m_s"] = df["enhanced_speed"]
    df["pace_min_km"] = (1000 / df["speed_m_s"]) / 60
    df["distance_km"] = df["distance"] / 1000
    df = donor_io.apply_privacy_clip(df)
    return df.ffill().dropna(subset=["pace_min_km", "altitude"])


def enrich_pace_only(df: pd.DataFrame, *, use_cegap: bool = True) -> pd.DataFrame:
    """Grade + GAP + pace-only TI (flat ref from fresh early-race GAP pace)."""
    out = _gap.apply_barometric_shift(df.copy())
    out["grade"] = _gap.compute_grade(out)
    out["grade_pct"] = out["grade"] * 100

    pf = out["grade"].apply(lambda g: _gap.pace_factor(g, use_cegap=use_cegap))
    out["pace_gap_flat"] = out["pace_min_km"] / pf

    fresh = out[out["distance_km"] <= 25.0]
    flat_ref = float(fresh["pace_gap_flat"].median())
    out["pace_expected"] = flat_ref * pf
    out["ti"] = out["pace_min_km"] / out["pace_expected"].replace(0, np.nan)
    out = _gap.apply_ti_smoothing(out)
    out["braking_tax"] = np.where(
        out["grade_pct"] < -5.0,
        out["ti"] - 1.0,
        0.0,
    )
    return out


def loop_corridor_spans(
    corridors: dict[str, dict],
    total_km: float,
    loop_km: float = LOOP_KM,
) -> list[tuple[str, float, float, str]]:
    """Repeat SUT_43 corridor windows across full ultra distance."""
    spans: list[tuple[str, float, float, str]] = []
    n_loops = int(np.ceil(total_km / loop_km)) + 1
    highlight = {
        "mattirudla_descent": MAGENTA,
        "dale_descent": AMBER,
        "mid_race_descent": "#AA66FF",
        "late_braking": "#FF6644",
    }
    for key, corr in corridors.items():
        color = highlight.get(key, "#334455")
        label = corr.get("label", key)
        for lap in range(n_loops):
            start = corr["km_start"] + lap * loop_km
            end = corr["km_end"] + lap * loop_km
            if start > total_km:
                break
            short = label.split("(")[0].strip()[:18]
            lap_tag = f"{short}" if lap == 0 else f"{short} L{lap + 1}"
            spans.append((lap_tag, start, min(end, total_km), color))
    return spans


def km_bins(df: pd.DataFrame, bin_km: float = 1.0) -> pd.DataFrame:
    rows = []
    km_max = int(df["distance_km"].max()) + 1
    for km in range(km_max):
        seg = df[(df["distance_km"] >= km) & (df["distance_km"] < km + bin_km)]
        if len(seg) < 20:
            continue
        t0, t1 = seg["time_s"].iloc[0], seg["time_s"].iloc[-1]
        rows.append(
            {
                "km": km + bin_km / 2,
                "pace": float(seg["pace_min_km"].median()),
                "ti": float(seg["ti"].median()),
                "grade_pct": float(seg["grade_pct"].mean()),
                "time_s": float(t1 - t0),
                "dist_m": float(seg["distance"].iloc[-1] - seg["distance"].iloc[0]),
            }
        )
    return pd.DataFrame(rows)


def plot_pace_fingerprint(
    bins: pd.DataFrame,
    spans: list[tuple[str, float, float, str]],
    out: Path,
) -> Path:
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), facecolor=BG)
    ax.set_facecolor(BG)

    for _, start, end, color in spans:
        if start > bins["km"].max():
            continue
        ax.axvspan(start, end, color=color, alpha=0.10, linewidth=0)

    ax.plot(bins["km"], bins["pace"], color=CYAN, linewidth=1.4, alpha=0.95, label="Pace (median/km)")
    ax.fill_between(bins["km"], bins["pace"], bins["pace"].max() + 1, color=CYAN, alpha=0.06)
    ax.invert_yaxis()
    ax.set_xlabel("Distance (km)")
    ax.set_ylabel("Pace (min/km)")
    ax.set_title(
        "SUT 160 km 2026 — Pace fingerprint with corridors",
        fontsize=12,
        fontweight="bold",
        pad=10,
    )
    _style_axes(ax)
    ax.legend(
        handles=[
            Patch(facecolor=MAGENTA, alpha=0.35, label="Mattirudlå descent"),
            Patch(facecolor=AMBER, alpha=0.35, label="Dalevatn descent"),
            Patch(facecolor=CYAN, alpha=0.5, label="Pace per km"),
        ],
        loc="lower right",
        facecolor="#1A1A1A",
        edgecolor=GRID,
        labelcolor=TEXT,
        fontsize=7,
    )
    ax.text(
        0.02,
        0.04,
        "3rd place · 30:09 · corridors repeat ~4× over 161 km",
        transform=ax.transAxes,
        color=TEXT,
        fontsize=8,
        va="bottom",
    )
    return _save(fig, out)


def plot_braking_tax(df: pd.DataFrame, corridors: dict, out: Path) -> Path:
    desc = df[df["grade_pct"] < -8.0].copy()
    if desc.empty:
        raise ValueError("No descent samples for braking tax plot")

    sectors = [
        ("Mattirudla", corridors["mattirudla_descent"], MAGENTA),
        ("Dalevatn", corridors["dale_descent"], AMBER),
        ("Mid-race", corridors["mid_race_descent"], "#AA66FF"),
        ("Late braking", corridors["late_braking"], "#FF6644"),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(FIG_W, FIG_H), facecolor=BG)
    ax0, ax1 = axes
    for ax in axes:
        ax.set_facecolor(BG)

    scatter = ax0.scatter(
        desc["grade_pct"],
        desc["braking_tax"],
        c=desc["distance_km"],
        cmap="plasma",
        s=4,
        alpha=0.45,
        edgecolors="none",
    )
    ax0.axhline(0, color="#666666", linestyle="--", linewidth=1)
    ax0.set_xlabel("Descent grade (%)")
    ax0.set_ylabel("Braking tax (TI − 1)")
    ax0.set_title("Eccentric descent — pointwise braking tax", fontsize=11, fontweight="bold", pad=8)
    _style_axes(ax0)
    cbar = fig.colorbar(scatter, ax=ax0, pad=0.02, fraction=0.046)
    cbar.set_label("km", color=TEXT)
    cbar.ax.tick_params(colors=TEXT, labelsize=8)

    labels, means, colors = [], [], []
    total_km = df["distance_km"].max()
    n_loops = int(np.ceil(total_km / LOOP_KM))
    for name, corr, color in sectors:
        vals = []
        for lap in range(n_loops):
            s = corr["km_start"] + lap * LOOP_KM
            e = corr["km_end"] + lap * LOOP_KM
            seg = df[(df["distance_km"] >= s) & (df["distance_km"] <= e) & (df["grade_pct"] < -5)]
            if len(seg) >= 15:
                vals.append(float(seg["ti"].mean()))
        if vals:
            labels.append(name)
            means.append(float(np.mean(vals)))
            colors.append(color)

    x = np.arange(len(labels))
    bars = ax1.bar(x, [m - 1.0 for m in means], color=colors, alpha=0.9, edgecolor=BG)
    peak = int(np.argmax(means)) if means else 0
    if means:
        bars[peak].set_edgecolor(WHITE)
        bars[peak].set_linewidth(1.5)
    ax1.axhline(0, color="#666666", linestyle="--", linewidth=1)
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=12, ha="right")
    ax1.set_ylabel("Avg. braking tax (TI − 1)")
    ax1.set_title("Corridor comparison — all laps", fontsize=11, fontweight="bold", pad=8)
    _style_axes(ax1)

    fig.suptitle(
        "Quad-Smash — braking tax on steep descents",
        fontsize=12,
        fontweight="bold",
        color=WHITE,
        y=1.02,
    )
    fig.tight_layout()
    return _save(fig, out)


def plot_cumulative_debt(df: pd.DataFrame, out: Path) -> Path:
    work = df.sort_values("distance_km").copy()
    work["dt"] = work["time_s"].diff().fillna(0)
    work["d_dist"] = work["distance"].diff().fillna(0)
    work["t_expected"] = work["d_dist"] / (
        1000 / (work["pace_expected"] * 60)
    ).replace(0, np.nan)
    work["debt_s"] = work["dt"] - work["t_expected"].fillna(0)
    work["cum_debt_min"] = work["debt_s"].cumsum() / 60

    step = max(1, len(work) // 800)
    plot_df = work.iloc[::step]

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), facecolor=BG)
    ax.set_facecolor(BG)
    ax.fill_between(
        plot_df["distance_km"],
        0,
        plot_df["cum_debt_min"],
        where=plot_df["cum_debt_min"] >= 0,
        color=MAGENTA,
        alpha=0.35,
        interpolate=True,
    )
    ax.plot(
        plot_df["distance_km"],
        plot_df["cum_debt_min"],
        color=AMBER,
        linewidth=1.6,
        label="Cumulative time debt",
    )
    ax.axhline(0, color="#666666", linestyle="--", linewidth=1)
    ax.set_xlabel("Distance (km)")
    ax.set_ylabel("Cumulative debt (min)")
    ax.set_title(
        "SUT 160 km 2026 — Cumulative terrain tax (pace vs. expected)",
        fontsize=12,
        fontweight="bold",
        pad=10,
    )
    _style_axes(ax)
    final_debt = float(work["cum_debt_min"].iloc[-1])
    ax.text(
        0.98,
        0.95,
        f"≈ {final_debt:+.0f} min vs. fresh reference pace",
        transform=ax.transAxes,
        color=AMBER,
        fontsize=9,
        ha="right",
        va="top",
    )
    ax.legend(facecolor="#1A1A1A", edgecolor=GRID, labelcolor=TEXT, fontsize=8, loc="upper left")
    return _save(fig, out)


def plot_race_xray(df: pd.DataFrame, out: Path) -> Path:
    step = max(1, len(df) // 5000)
    d = df.iloc[::step].copy()
    ti = d["ti"].replace([np.inf, -np.inf], np.nan).fillna(1.0)
    vmin, vmax = float(np.percentile(ti, 5)), float(np.percentile(ti, 95))
    norm = Normalize(vmin=max(vmin, 0.8), vmax=max(vmax, 1.5))
    cmap = plt.cm.plasma

    fig, axes = plt.subplots(2, 1, figsize=(FIG_W, FIG_H * 1.35), facecolor=BG, height_ratios=[1.2, 1])
    ax0, ax1 = axes
    for ax in axes:
        ax.set_facecolor(BG)

    points = np.array([d["distance_km"], d["altitude"]]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    lc = plt.matplotlib.collections.LineCollection(
        segments, cmap=cmap, norm=norm, linewidths=1.8, alpha=0.95
    )
    lc.set_array(ti.iloc[:-1].to_numpy())
    ax0.add_collection(lc)
    ax0.autoscale()
    ax0.set_ylabel("Elevation (m)")
    ax0.set_title(
        "Race x-ray — pace color-coded by Terrain Index (TI)",
        fontsize=12,
        fontweight="bold",
        pad=10,
    )
    _style_axes(ax0)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax0, pad=0.01, fraction=0.025)
    cbar.set_label("TI (1.0 = neutral)", color=TEXT)
    cbar.ax.tick_params(colors=TEXT, labelsize=8)

    seg_km = 2.0
    km_max = int(df["distance_km"].max())
    mids, ti_vals = [], []
    km = 0.0
    while km < km_max:
        seg = df[(df["distance_km"] >= km) & (df["distance_km"] < km + seg_km)]
        if len(seg) >= 30:
            mids.append(km + seg_km / 2)
            ti_vals.append(float(seg["ti"].median()))
        km += seg_km

    colors = [cmap(norm(v)) for v in ti_vals]
    ax1.bar(mids, ti_vals, width=seg_km * 0.92, color=colors, edgecolor=BG)
    ax1.axhline(1.0, color="#666666", linestyle="--", linewidth=1)
    peak_i = int(np.argmax(ti_vals)) if ti_vals else 0
    if ti_vals:
        ax1.bar(mids[peak_i], ti_vals[peak_i], width=seg_km * 0.92, color=MAGENTA, edgecolor=BG)
    ax1.set_xlabel("Distance (km)")
    ax1.set_ylabel("TI (2 km bins)")
    ax1.set_title("Black hole probe — peak terrain tax per segment", fontsize=11, fontweight="bold", pad=8)
    _style_axes(ax1)

    fig.tight_layout()
    return _save(fig, out)


def generate_all(
    donor_id: str = DONOR_ID,
    activity_id: str = SUT_RACE_ACTIVITY,
    out_dir: Path = OUT_DIR,
) -> list[Path]:
    corridors = json.loads(CORRIDORS_PATH.read_text(encoding="utf-8"))["SUT_43"]["sub_corridors"]
    df = enrich_pace_only(load_race_session(donor_json(donor_id, activity_id)))
    bins = km_bins(df)
    spans = loop_corridor_spans(corridors, df["distance_km"].max())

    created = [
        plot_pace_fingerprint(bins, spans, out_dir / "01_pace_fingerprint.png"),
        plot_braking_tax(df, corridors, out_dir / "02_braking_tax.png"),
        plot_cumulative_debt(df, out_dir / "03_cumulative_debt.png"),
        plot_race_xray(df, out_dir / "04_race_xray.png"),
    ]
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="SUT_160 race hook plots for donor pack")
    parser.add_argument("--donor", default=DONOR_ID)
    parser.add_argument("--activity", default=SUT_RACE_ACTIVITY)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    paths = generate_all(args.donor, args.activity, args.out_dir)
    print(f"Generated {len(paths)} plots in {args.out_dir}:")
    for p in paths:
        print(f"  {p.name} ({p.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
