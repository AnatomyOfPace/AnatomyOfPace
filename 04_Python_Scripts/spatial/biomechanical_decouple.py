#!/usr/bin/env python3
"""
Phase C — biomechanical decoupling: race TI minus training-mean TI per metre.

Computes ΔTI = TI_race − TI_training_mean along the SUT corridor grid.
Positive ΔTI is the Structural Invoice — terrain friction paid on race day
beyond what training tiles predict at the same course km.

Inputs:
  - Phase A aligned panel or glob with session_type column (race | training)

Outputs:
  - structural_invoice.json — per-donor and corridor-level ΔTI summary
  - Optional ΔTI heatmap PNG under 06_Visualizations/

Usage:
    python3 04_Python_Scripts/spatial/biomechanical_decouple.py \\
        --panel 03_Processed_Data/spatial/dale_to_paradisskaret_stress_test/panel_1m.parquet

    python3 04_Python_Scripts/spatial/biomechanical_decouple.py \\
        --aligned-glob '03_Processed_Data/spatial/dale_to_paradisskaret_stress_test/aligned_*.parquet' \\
        --heatmap
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.corridor_scope import (  # noqa: E402
    PARADISSKARET_DOWNHILL_END_KM,
    STRESS_TEST_CORRIDOR_ID,
    load_stress_test_window,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SPATIAL_DIR = BASE_DIR / "03_Processed_Data" / "spatial"
VIS_DIR = BASE_DIR / "06_Visualizations"
DEFAULT_INVOICE_PATH = (
    SPATIAL_DIR / STRESS_TEST_CORRIDOR_ID / "structural_invoice.json"
)

SessionType = Literal["race", "training"]
VALID_SESSION_TYPES: tuple[SessionType, ...] = ("race", "training")

# Paradisskaret descent core — primary Structural Invoice sector (course km).
PARADISSKARET_SECTOR_KM_START = 154.95
PARADISSKARET_SECTOR_KM_END = PARADISSKARET_DOWNHILL_END_KM


def _require_session_type(panel: pd.DataFrame) -> pd.DataFrame:
    work = panel.copy()
    if "session_type" not in work.columns:
        raise ValueError(
            "Panel lacks session_type column — re-run spatial_align.py with v2 manifest "
            "(session_type: race | training)"
        )
    invalid = set(work["session_type"].dropna().unique()) - set(VALID_SESSION_TYPES)
    if invalid:
        raise ValueError(f"Invalid session_type values: {sorted(invalid)}")
    return work


def per_donor_session_profile(
    panel: pd.DataFrame,
    donor_id: str,
    session_type: SessionType,
    *,
    ti_col: str = "ti",
) -> pd.DataFrame:
    """Median TI per course_m for one donor and session type (pooled across tile activities)."""
    work = _require_session_type(panel)
    sub = work[(work["donor_id"] == donor_id) & (work["session_type"] == session_type)]
    if sub.empty:
        return pd.DataFrame(columns=["course_m", "course_km", ti_col])

  # Pool multiple training tiles via median at each metre.
    agg = sub.groupby("course_m", as_index=False).agg(
        **{ti_col: (ti_col, "median")},
        course_km=("course_km", "first"),
        n_sessions=("activity_id", "nunique"),
    )
    return agg


def compute_delta_ti_profile(
    panel: pd.DataFrame,
    donor_id: str,
    *,
    ti_col: str = "ti",
) -> pd.DataFrame:
    """
    ΔTI profile for one donor: race median TI minus training-mean TI per course_m.
    """
    race = per_donor_session_profile(panel, donor_id, "race", ti_col=ti_col)
    train = per_donor_session_profile(panel, donor_id, "training", ti_col=ti_col)
    if race.empty:
        raise ValueError(f"No race sessions for donor {donor_id!r} in panel")
    if train.empty:
        raise ValueError(f"No training sessions for donor {donor_id!r} in panel")

    merged = race.merge(
        train[["course_m", ti_col]],
        on="course_m",
        how="left",
        suffixes=("_race", "_training_mean"),
    )
    merged["delta_ti"] = merged[f"{ti_col}_race"] - merged[f"{ti_col}_training_mean"]
    merged["donor_id"] = donor_id
    return merged


def sector_mask(
    df: pd.DataFrame,
    km_start: float,
    km_end: float,
    *,
    km_col: str = "course_km",
) -> pd.Series:
    lo, hi = min(km_start, km_end), max(km_start, km_end)
    km = pd.to_numeric(df[km_col], errors="coerce")
    return (km >= lo) & (km <= hi)


def summarize_structural_invoice(
    delta_profiles: dict[str, pd.DataFrame],
    *,
    corridor_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate ΔTI into per-donor and corridor Structural Invoice metrics."""
    _, _, default_corridor = load_stress_test_window()
    corridor = corridor_meta or default_corridor

    per_donor: dict[str, Any] = {}
    for donor_id, prof in delta_profiles.items():
        valid = prof["delta_ti"].dropna()
        paradisskaret = prof.loc[
            sector_mask(prof, PARADISSKARET_SECTOR_KM_START, PARADISSKARET_SECTOR_KM_END)
        ]
        p_valid = paradisskaret["delta_ti"].dropna()

        peak_idx = valid.idxmax() if not valid.empty else None
        per_donor[donor_id] = {
            "n_course_m": int(valid.count()),
            "mean_delta_ti": float(valid.mean()) if not valid.empty else None,
            "mean_abs_delta_ti": float(valid.abs().mean()) if not valid.empty else None,
            "positive_invoice_sum": float(valid.clip(lower=0).sum()) if not valid.empty else None,
            "peak_delta_ti": float(valid.max()) if not valid.empty else None,
            "peak_course_km": (
                float(prof.loc[peak_idx, "course_km"]) if peak_idx is not None else None
            ),
            "paradisskaret_sector": {
                "km_start": PARADISSKARET_SECTOR_KM_START,
                "km_end": PARADISSKARET_SECTOR_KM_END,
                "mean_delta_ti": float(p_valid.mean()) if not p_valid.empty else None,
                "positive_invoice_sum": float(p_valid.clip(lower=0).sum()) if not p_valid.empty else None,
                "peak_delta_ti": float(p_valid.max()) if not p_valid.empty else None,
            },
        }

    return {
        "schema_version": "structural_invoice_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corridor": corridor,
        "formula": "delta_ti = ti_race - ti_training_mean",
        "paradisskaret_sector_km": [PARADISSKARET_SECTOR_KM_START, PARADISSKARET_SECTOR_KM_END],
        "per_donor": per_donor,
        "panel_donors": sorted(delta_profiles.keys()),
    }


def build_delta_ti_payload(
    panel: pd.DataFrame,
    *,
    donors: list[str] | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Compute all donor ΔTI profiles and structural invoice summary."""
    work = _require_session_type(panel)
    donor_list = donors or sorted(work["donor_id"].dropna().unique())

    profiles: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    for donor_id in donor_list:
        try:
            profiles[donor_id] = compute_delta_ti_profile(work, donor_id)
        except ValueError as exc:
            errors[donor_id] = str(exc)

    if not profiles:
        raise ValueError(
            "No ΔTI profiles computed — each donor needs ≥1 race and ≥1 training session. "
            f"Errors: {errors}"
        )

    summary = summarize_structural_invoice(profiles)
    summary["skipped_donors"] = errors
    summary["delta_by_course_m"] = {
        donor_id: [
            {
                "course_m": float(row.course_m),
                "course_km": float(row.course_km),
                "ti_race": float(row.ti_race) if pd.notna(row.ti_race) else None,
                "ti_training_mean": float(row.ti_training_mean) if pd.notna(row.ti_training_mean) else None,
                "delta_ti": float(row.delta_ti) if pd.notna(row.delta_ti) else None,
            }
            for row in prof.itertuples(index=False)
        ]
        for donor_id, prof in profiles.items()
    }
    return profiles, summary


def write_structural_invoice(payload: dict[str, Any], path: Path | None = None) -> Path:
    out = path or DEFAULT_INVOICE_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def render_delta_ti_heatmap(
    profiles: dict[str, pd.DataFrame],
    *,
    output_path: Path,
    corridor_meta: dict[str, Any] | None = None,
) -> Path:
    """Multi-donor ΔTI heatmap with Paradisskaret sector highlight."""
    _, _, corridor = load_stress_test_window()
    meta = corridor_meta or corridor

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(14, 5), facecolor="#0A0A0A")
    fig.suptitle(
        "Structural Invoice — ΔTI (race − training mean)",
        color="white",
        fontsize=13,
        fontweight="bold",
    )

    donors = sorted(profiles.keys())
    # Build matrix: rows = donors, cols = course_m (shared grid from first profile).
    ref = profiles[donors[0]].sort_values("course_m")
    course_km = ref["course_km"].to_numpy()
    matrix = np.full((len(donors), len(ref)), np.nan)
    for i, donor_id in enumerate(donors):
        prof = profiles[donor_id].set_index("course_m").reindex(ref["course_m"])
        matrix[i, :] = prof["delta_ti"].to_numpy()

    im = ax.imshow(
        matrix,
        aspect="auto",
        cmap="RdYlGn_r",
        vmin=np.nanpercentile(matrix, 5) if np.isfinite(matrix).any() else -0.5,
        vmax=np.nanpercentile(matrix, 95) if np.isfinite(matrix).any() else 1.5,
        extent=[course_km.min(), course_km.max(), len(donors) - 0.5, -0.5],
    )
    ax.set_yticks(range(len(donors)))
    ax.set_yticklabels(donors)
    ax.set_xlabel("Course km (SUT_160)", color="#A0A0A0")
    ax.set_ylabel("Donor", color="#A0A0A0")
    ax.axvspan(
        PARADISSKARET_SECTOR_KM_START,
        PARADISSKARET_SECTOR_KM_END,
        alpha=0.15,
        color="#FF7043",
        label="Paradisskaret sector",
    )
    cbar = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
    cbar.set_label("ΔTI", color="#A0A0A0")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(color="#2A2A2A", linestyle="--", alpha=0.4)

    fig.text(
        0.02,
        0.02,
        f"Corridor km {meta.get('km_start')}–{meta.get('km_end')} | "
        f"Positive ΔTI = race-day structural tax above training expectation",
        color="#888",
        fontsize=9,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="#0A0A0A")
    plt.close(fig)
    return output_path


def load_panel(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def load_aligned_glob(pattern: str) -> pd.DataFrame:
    paths = sorted(Path(BASE_DIR).glob(pattern))
    if not paths:
        raise FileNotFoundError(f"No aligned Parquet matched: {pattern}")
    return pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase C — biomechanical decoupling (ΔTI Structural Invoice)",
    )
    parser.add_argument("--panel", type=Path, help="Stacked panel_1m.parquet from Phase A")
    parser.add_argument(
        "--aligned-glob",
        default=None,
        help="Glob under repo root for aligned_*.parquet (alternative to --panel)",
    )
    parser.add_argument(
        "--donors",
        nargs="*",
        default=None,
        help="Subset of donor IDs (default: all in panel with race+training)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_INVOICE_PATH,
        help="structural_invoice.json path",
    )
    parser.add_argument(
        "--heatmap",
        action="store_true",
        help="Write ΔTI heatmap PNG to 06_Visualizations/",
    )
    parser.add_argument(
        "--heatmap-output",
        type=Path,
        default=VIS_DIR / "structural_invoice_delta_ti_heatmap.png",
    )
    args = parser.parse_args()

    if args.panel:
        panel = load_panel(args.panel if args.panel.is_absolute() else BASE_DIR / args.panel)
    elif args.aligned_glob:
        panel = load_aligned_glob(args.aligned_glob)
    else:
        default_panel = SPATIAL_DIR / STRESS_TEST_CORRIDOR_ID / "panel_1m.parquet"
        if not default_panel.exists():
            parser.error("Provide --panel or --aligned-glob; default panel not found")
        panel = load_panel(default_panel)

    profiles, summary = build_delta_ti_payload(panel, donors=args.donors)
    out = write_structural_invoice(
        summary,
        args.output if args.output.is_absolute() else BASE_DIR / args.output,
    )
    print(f"OK structural invoice → {out.relative_to(BASE_DIR)} (donors={len(profiles)})")

    if args.heatmap:
        hm_path = args.heatmap_output if args.heatmap_output.is_absolute() else BASE_DIR / args.heatmap_output
        render_delta_ti_heatmap(profiles, output_path=hm_path)
        print(f"OK ΔTI heatmap → {hm_path.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()
