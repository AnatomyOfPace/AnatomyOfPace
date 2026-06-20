"""
Kinematic_Scan v1 — GAP/TI donor report.

Input:  one Garmin .fit file
Output: multi-panel PNG in 06_Visualizations/

Uses 11_gap_engine.py (Minetti GAP + barometric shift + 30 s TI smoothing).

Usage:
    python 08_kinematic_scan.py --fit 02_Raw_Data/Subject_A_session.fit --subject Subject_A
    python 08_kinematic_scan.py --fit 02_Raw_Data/session.fit --legacy-apr
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import Normalize

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = BASE_DIR / "02_Raw_Data"
VIZ_DIR = BASE_DIR / "06_Visualizations"
DEFAULT_ANCHOR = "Stavanger_Halvmaraton.fit"
SCAN_VERSION = "v1.0"
MIN_SEGMENT_SAMPLES = 20
PRIVACY_CLIP_M = 500
COLLAPSE_WINDOW = 60

_spec = importlib.util.spec_from_file_location(
    "gap_engine",
    Path(__file__).parent / "11_gap_engine.py",
)
_gap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gap)


def apply_privacy_clip(df: pd.DataFrame) -> pd.DataFrame:
    """Remove first and last 500 m from third-party telemetry."""
    if df.empty:
        return df
    d_min, d_max = df["distance"].min(), df["distance"].max()
    return df[
        (df["distance"] >= d_min + PRIVACY_CLIP_M)
        & (df["distance"] <= d_max - PRIVACY_CLIP_M)
    ].copy()


def build_segment_table_ti(df: pd.DataFrame, segment_km: float) -> pd.DataFrame:
    """Per-segment Terrain Index from GAP pipeline output."""
    max_km = int(df["distance_km"].max()) + 1
    segments = []
    for km in range(max_km):
        seg = df[(df["distance_km"] >= km) & (df["distance_km"] < km + segment_km)]
        if len(seg) < MIN_SEGMENT_SAMPLES:
            continue
        segments.append(
            {
                "start_km": float(km),
                "end_km": km + segment_km,
                "mid_km": km + segment_km / 2,
                "mean_ti": float(seg["ti"].mean()),
                "mean_pace": float(seg["pace_min_km"].mean()),
                "mean_gap_flat": float(seg["pace_gap_flat"].mean()),
                "mean_grade_pct": float(seg["grade_pct"].mean()),
                "mean_hr": float(seg["heart_rate"].mean()),
                "altitude_m": float(seg["altitude"].mean()),
                "n_samples": len(seg),
            }
        )
    return pd.DataFrame(segments)


def build_segment_table_apr(
    df: pd.DataFrame, anchor_df: pd.DataFrame, segment_km: float
) -> pd.DataFrame:
    """Legacy APR segments (v0)."""
    df = df.copy()
    df["segment_id"] = (df["distance_km"] // segment_km).astype(int)
    segments = []
    for seg_id, group in df.groupby("segment_id"):
        if len(group) < MIN_SEGMENT_SAMPLES:
            continue
        start_km = seg_id * segment_km
        mean_hr = group["heart_rate"].mean()
        mean_pace = group["pace_min_km"].mean()
        anchor_pace = _gap.anchor_pace_at_hr(anchor_df, mean_hr)
        segments.append(
            {
                "start_km": start_km,
                "end_km": start_km + segment_km,
                "mid_km": start_km + segment_km / 2,
                "mean_ti": mean_pace / anchor_pace if anchor_pace > 0 else np.nan,
                "mean_pace": mean_pace,
                "mean_gap_flat": np.nan,
                "mean_grade_pct": np.nan,
                "mean_hr": mean_hr,
                "altitude_m": group["altitude"].mean(),
                "n_samples": len(group),
            }
        )
    return pd.DataFrame(segments)


def detect_collapse_points_v1(df: pd.DataFrame, window: int = COLLAPSE_WINDOW) -> pd.DataFrame:
    """
    Collapse: pace slows while flat-equivalent GAP effort stays stable (Eccentric Downfall proxy).
    """
    if len(df) < window * 3 or "pace_gap_flat" not in df.columns:
        return pd.DataFrame()

    rolling = df.copy()
    rolling["pace_roll"] = rolling["pace_min_km"].rolling(window, center=True).mean()
    rolling["gap_roll"] = rolling["pace_gap_flat"].rolling(window, center=True).mean()
    rolling["pace_floor"] = rolling["pace_roll"].rolling(window * 2, center=True).min()
    rolling["gap_change"] = rolling["gap_roll"].pct_change(window // 2).abs()

    mask = (rolling["pace_roll"] > rolling["pace_floor"] * 1.12) & (rolling["gap_change"] < 0.06)
    hits = rolling.loc[mask, ["distance_km", "pace_min_km", "pace_gap_flat", "ti"]].copy()
    if hits.empty:
        return hits

    hits["km_bin"] = hits["distance_km"].astype(int)
    return hits.groupby("km_bin", as_index=False).first()


def detect_collapse_points_apr(df: pd.DataFrame, window: int = COLLAPSE_WINDOW) -> pd.DataFrame:
    """Legacy v0: pace slows while heart rate stays stable."""
    if len(df) < window * 3:
        return pd.DataFrame()

    rolling = df.copy()
    rolling["pace_roll"] = rolling["pace_min_km"].rolling(window, center=True).mean()
    rolling["pace_floor"] = rolling["pace_roll"].rolling(window * 3, center=True).min()
    rolling["hr_std"] = rolling["heart_rate"].rolling(window, center=True).std()

    mask = (rolling["pace_roll"] > rolling["pace_floor"] * 1.18) & (rolling["hr_std"] < 2.5)
    hits = rolling.loc[mask, ["distance_km", "pace_min_km", "heart_rate"]].copy()
    if hits.empty:
        return hits

    hits["km_bin"] = hits["distance_km"].astype(int)
    return hits.groupby("km_bin", as_index=False).first()


def render_scan(
    df: pd.DataFrame,
    segments: pd.DataFrame,
    collapse: pd.DataFrame,
    subject_id: str,
    output_path: Path,
    use_ti: bool = True,
) -> None:
    """Render Kinematic_Scan multi-panel PNG."""
    plt.style.use("dark_background")
    fig, axes = plt.subplots(3, 1, figsize=(14, 12), facecolor="#0A0A0A")
    for ax in axes:
        ax.set_facecolor("#0A0A0A")

    metric = "mean_ti"
    metric_label = "TI" if use_ti else "APR"
    cmap = plt.cm.plasma
    ti_min = segments[metric].min()
    ti_max = segments[metric].max()
    norm = Normalize(vmin=ti_min, vmax=ti_max)
    black_hole = segments.loc[segments[metric].idxmax()]

    # Panel 1 — altitude color-coded by segment TI
    ax0 = axes[0]
    if "altitude" in df.columns and df["altitude"].notna().any():
        for _, seg in segments.iterrows():
            seg_data = df[
                (df["distance_km"] >= seg["start_km"]) & (df["distance_km"] < seg["end_km"])
            ]
            if seg_data.empty:
                continue
            ax0.plot(
                seg_data["distance_km"],
                seg_data["altitude"],
                color=cmap(norm(seg[metric])),
                linewidth=2,
            )
        ax0.set_ylabel("Altitude (m)", color="#A0A0A0")
    else:
        ax0.text(
            0.5, 0.5, "Altitude data unavailable",
            transform=ax0.transAxes, ha="center", color="#A0A0A0",
        )

    heatmap_title = (
        "Terrain Profile — TI Color Scale (Terrain Index heatmap)"
        if use_ti
        else "Terrain Profile — APR Color Scale (interim heatmap)"
    )
    ax0.set_title(heatmap_title, color="white", fontsize=13, fontweight="bold", pad=10)
    ax0.grid(color="#2A2A2A", linestyle="--", linewidth=0.5)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax0, pad=0.01, fraction=0.02)
    cbar.set_label(f"Segment {metric_label}", color="#A0A0A0")

    # Panel 2 — TI bar chart + black hole
    ax1 = axes[1]
    bars = ax1.bar(
        segments["mid_km"], segments[metric],
        width=0.8, color="#00E5FF", alpha=0.85, edgecolor="#0A0A0A",
    )
    bh_idx = segments[metric].idxmax()
    bars[segments.index.get_loc(bh_idx)].set_color("#FF0055")
    ax1.axhline(1.0, color="#666666", linestyle="--", linewidth=1, label=f"Neutral ({metric_label}=1.0)")
    ax1.set_xlabel("Distance (km)", color="#A0A0A0")
    ax1.set_ylabel(metric_label, color="#A0A0A0")
    ax1.set_title(
        f"Segment {metric_label} Profile — Black Hole: km {black_hole['start_km']:.0f}"
        f"–{black_hole['end_km']:.0f} ({metric_label} {black_hole[metric]:.2f})",
        color="white", fontsize=13, fontweight="bold", pad=10,
    )
    ax1.grid(axis="y", color="#2A2A2A", linestyle="--", linewidth=0.5)
    ax1.legend(facecolor="#1A1A1A", edgecolor="#2A2A2A", labelcolor="#A0A0A0")

    # Panel 3 — pace vs GAP (v1) or pace vs HR (legacy)
    ax2 = axes[2]
    ax2.plot(df["distance_km"], df["pace_min_km"], color="#00E5FF", linewidth=1, alpha=0.8, label="Actual pace")
    ax2_twin = ax2.twinx()
    if use_ti and "pace_gap_flat" in df.columns:
        ax2_twin.plot(
            df["distance_km"], df["pace_gap_flat"],
            color="#FFB300", linewidth=1, alpha=0.7, label="GAP flat-equivalent",
        )
        ax2_twin.set_ylabel("GAP pace (min/km)", color="#FFB300")
        panel3_title = "Pace vs GAP — Collapse (pace drops, GAP stable)"
    else:
        ax2_twin.plot(
            df["distance_km"], df["heart_rate"],
            color="#FFB300", linewidth=1, alpha=0.7, label="Heart rate",
        )
        ax2_twin.set_ylabel("Heart rate (bpm)", color="#FFB300")
        panel3_title = "Pace / Heart Rate Divergence (collapse indicator — interim)"

    if not collapse.empty:
        ax2.scatter(
            collapse["distance_km"], collapse["pace_min_km"],
            color="#FF0055", s=40, zorder=5, label="Collapse signal",
        )

    ax2.invert_yaxis()
    ax2.set_xlabel("Distance (km)", color="#A0A0A0")
    ax2.set_ylabel("Pace (min/km)", color="#00E5FF")
    ax2.set_title(panel3_title, color="white", fontsize=13, fontweight="bold", pad=10)
    ax2.grid(color="#2A2A2A", linestyle="--", linewidth=0.5)

    lines_l, labels_l = ax2.get_legend_handles_labels()
    lines_r, labels_r = ax2_twin.get_legend_handles_labels()
    ax2.legend(
        lines_l + lines_r, labels_l + labels_r,
        loc="upper right", facecolor="#1A1A1A", edgecolor="#2A2A2A", labelcolor="#A0A0A0",
    )

    mean_metric = segments[metric].mean()
    fig.suptitle(
        f"KINEMATIC_SCAN {SCAN_VERSION} — {subject_id}",
        color="white", fontsize=16, fontweight="bold", y=0.98,
    )
    footer = (
        f"Mean segment {metric_label}: {mean_metric:.2f} | "
        f"Algorithm indicates max terrain tax at km {black_hole['start_km']:.0f}"
        f"–{black_hole['end_km']:.0f}"
    )
    if use_ti:
        footer += " | TI = friction beyond grade (Minetti GAP)"
    fig.text(0.5, 0.01, footer, ha="center", color="#666666", fontsize=9)

    plt.tight_layout(rect=[0, 0.03, 1, 0.96])
    output_path.parent.mkdir(exist_ok=True)
    plt.savefig(output_path, dpi=200, bbox_inches="tight", facecolor="#0A0A0A")
    plt.close(fig)


def run_scan(
    fit_path: Path,
    subject_id: str,
    anchor_name: str,
    segment_km: float,
    privacy_clip: bool,
    output_path: Path | None,
    legacy_apr: bool = False,
) -> None:
    anchor_path = RAW_DATA_DIR / anchor_name
    try:
        anchor_df = _gap.load_fit(anchor_path)
    except (ValueError, FileNotFoundError):
        print(f"ERROR: Asphalt anchor not found: {anchor_path}")
        print(f"       Place {anchor_name} in 02_Raw_Data/ or pass --anchor.")
        return

    try:
        session_df = _gap.load_fit(fit_path)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return

    if privacy_clip:
        session_df = apply_privacy_clip(session_df)
        if session_df.empty:
            print("ERROR: Privacy clip removed all samples.")
            return

    use_ti = not legacy_apr
    if use_ti:
        session_df = _gap.apply_gap(session_df, anchor_df)
        segments = build_segment_table_ti(session_df, segment_km)
        collapse = detect_collapse_points_v1(session_df)
        version_note = "TI report (GAP pipeline: Minetti + barometric shift + 30 s smooth)"
    else:
        segments = build_segment_table_apr(session_df, anchor_df, segment_km)
        collapse = detect_collapse_points_apr(session_df)
        version_note = "Legacy APR-era report (--legacy-apr)"

    if segments.empty:
        print("ERROR: Not enough data to build segments. Try a longer activity or smaller --segment-km.")
        return

    if output_path is None:
        suffix = "" if use_ti else "_apr"
        output_path = VIZ_DIR / f"kinematic_scan_{subject_id}{suffix}.png"

    render_scan(session_df, segments, collapse, subject_id, output_path, use_ti=use_ti)

    black_hole = segments.loc[segments["mean_ti"].idxmax()]
    metric_label = "TI" if use_ti else "APR"
    print("\n" + "=" * 55)
    print(f"  KINEMATIC_SCAN {SCAN_VERSION} — COMPLETE")
    print("=" * 55)
    print(f"  Subject ID:     {subject_id}")
    print(f"  Session:        {fit_path.name}")
    print(f"  Mean {metric_label}:       {segments['mean_ti'].mean():.2f}")
    print(f"  Black hole:     km {black_hole['start_km']:.0f}–{black_hole['end_km']:.0f}"
          f"  ({metric_label} {black_hole['mean_ti']:.2f})")
    print(f"  Collapse flags: {len(collapse)}")
    print(f"  Output:         {output_path}")
    print("=" * 55)
    print(f"  {version_note}")
    print("=" * 55 + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kinematic_Scan v1 — GAP/TI donor report from a single .fit file."
    )
    parser.add_argument("--fit", required=True, help="Path to session .fit file")
    parser.add_argument(
        "--subject", default="Subject_A",
        help="Clinical subject ID for chart labels (default: Subject_A)",
    )
    parser.add_argument(
        "--anchor", default=DEFAULT_ANCHOR,
        help=f"Asphalt anchor filename in 02_Raw_Data/ (default: {DEFAULT_ANCHOR})",
    )
    parser.add_argument(
        "--segment-km", type=float, default=1.0,
        help="Segment length in km (default: 1.0)",
    )
    parser.add_argument(
        "--privacy-clip", action="store_true",
        help="Clip first/last 500 m (recommended for third-party donors)",
    )
    parser.add_argument("--output", default=None, help="Output PNG path")
    parser.add_argument(
        "--legacy-apr", action="store_true",
        help="Use v0 APR-era metrics instead of TI",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    fit_path = Path(args.fit)
    if not fit_path.is_absolute():
        fit_path = BASE_DIR / fit_path
    output = Path(args.output) if args.output else None

    run_scan(
        fit_path=fit_path,
        subject_id=args.subject,
        anchor_name=args.anchor,
        segment_km=args.segment_km,
        privacy_clip=args.privacy_clip,
        output_path=output,
        legacy_apr=args.legacy_apr,
    )
