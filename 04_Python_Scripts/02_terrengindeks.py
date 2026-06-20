#!/usr/bin/env python3
"""
Aerobic Pace Ratio (APR) calculator — iso-HR terrain vs asphalt anchor.

Uses Seed Matrix per-subject anchors (seed_matrix.py).
Subject_B requires locked tartan 5k calibration before terrain APR is valid.

Usage:
    python 02_terrengindeks.py --subject Subject_B --terrain-fit session.fit
    python 02_terrengindeks.py --subject Subject_A
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fitparse
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seed_matrix
from subject_resolve import find_fit, fit_filename_token

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = BASE_DIR / "02_Raw_Data"

HR_ZONE = (140, 150)


def load_fit_data(fit_basename: str) -> pd.DataFrame | None:
    path = RAW_DATA_DIR / fit_basename
    if not path.exists():
        print(f"ERROR: file not found — {path}")
        return None

    try:
        fitfile = fitparse.FitFile(str(path))
        rows = [r.get_values() for r in fitfile.get_messages("record")]
        df = pd.DataFrame(rows)
        if "enhanced_speed" not in df.columns:
            df["enhanced_speed"] = df.get("speed", 0)
        df = df[df["enhanced_speed"] > 0.5].copy()
        cols = [c for c in ["timestamp", "heart_rate", "enhanced_speed"] if c in df.columns]
        df = df[cols].ffill().dropna()
        df["pace_min_km"] = (1000 / df["enhanced_speed"]) / 60
        return df
    except Exception as exc:
        print(f"ERROR processing {fit_basename}: {exc}")
        return None


def mean_pace_in_hr_zone(df: pd.DataFrame, lo: int, hi: int) -> float:
    zone = df[(df["heart_rate"] >= lo) & (df["heart_rate"] <= hi)]
    return float(zone["pace_min_km"].mean())


def run_apr(
    subject_id: str,
    terrain_fit: str | None,
    hr_lo: int,
    hr_hi: int,
) -> None:
    print(f"\nAPR calculator — Seed Matrix anchor for {subject_id}\n")

    if seed_matrix.anchor_status(subject_id) == "awaiting_calibration":
        proto = seed_matrix.subject_status(subject_id).get("calibration_protocol", "")
        print(f"  STATUS: {subject_id} anchor AWAITING calibration ({proto})")
        print("  Run: python 01_vaskemaskinen.py --calibration-5k ... --lock-subject-b")
        print("  Asphalt_Anchor_Proxy synthesis is HALTED.\n")
        return

    try:
        anchor_name = seed_matrix.anchor_fit_basename(subject_id)
        anchor_path = seed_matrix.anchor_path(subject_id)
    except FileNotFoundError as exc:
        print(f"  ERROR: {exc}\n")
        return

    surface = seed_matrix.subject_status(subject_id).get("surface", "asphalt")
    print(f"  Locked anchor: {anchor_name} ({surface})")
    print(f"  Path:          {anchor_path}")

    df_anchor = load_fit_data(anchor_name)
    if df_anchor is None:
        return

    if terrain_fit is None:
        if subject_id == "Subject_B":
            token_b = fit_filename_token("Subject_B")
            terrain_fit = find_fit("Sunderunde", token_b, "20260530")
        else:
            terrain_fit = find_fit("Sunderunde", fit_filename_token("Subject_A"), "20260530")

    print(f"  Terrain session: {terrain_fit}")
    df_terrain = load_fit_data(terrain_fit)
    if df_terrain is None:
        return

    pace_anchor = mean_pace_in_hr_zone(df_anchor, hr_lo, hr_hi)
    pace_terrain = mean_pace_in_hr_zone(df_terrain, hr_lo, hr_hi)
    apr = pace_terrain / pace_anchor if pace_anchor > 0 else float("nan")

    print("\n" + "=" * 55)
    print(f"  AEROBIC PACE RATIO — {subject_id}  (HR {hr_lo}–{hr_hi} bpm)")
    print("=" * 55)
    print(f"  Anchor pace ({surface}):  {pace_anchor:.2f} min/km")
    print(f"  Terrain pace:             {pace_terrain:.2f} min/km")
    print("-" * 55)
    print(f"  APR:                      {apr:.2f}")
    print("=" * 55)
    print("  APR = pace_terrain / pace_anchor @ iso-HR (APR ≠ TI; TI uses GAP)")
    print("=" * 55 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="APR vs Seed Matrix anchor @ iso-HR")
    parser.add_argument("--subject", default="Subject_B", help="Clinical subject ID")
    parser.add_argument("--terrain-fit", help="Terrain .fit basename (default: Sunderunde)")
    parser.add_argument("--hr-lo", type=int, default=HR_ZONE[0])
    parser.add_argument("--hr-hi", type=int, default=HR_ZONE[1])
    args = parser.parse_args()
    run_apr(args.subject, args.terrain_fit, args.hr_lo, args.hr_hi)


if __name__ == "__main__":
    main()
