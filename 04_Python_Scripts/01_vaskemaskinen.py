#!/usr/bin/env python3
"""
Data Pipeline (Vaskemaskinen) — ingest and clean .fit telemetry.

Usage:
    python 01_vaskemaskinen.py --fit 02_Raw_Data/session.fit
    python 01_vaskemaskinen.py --calibration-5k --subject-b-fit calibration_b.fit --subject-a-fit pacer_a.fit
    python 01_vaskemaskinen.py --calibration-5k --subject-b-fit calibration_b.fit --lock-subject-b
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
PROCESSED_DATA_DIR = BASE_DIR / "03_Processed_Data"

RECORD_FIELDS = (
    "timestamp",
    "distance",
    "heart_rate",
    "altitude",
    "enhanced_altitude",
    "cadence",
    "speed",
    "enhanced_speed",
)


def wash_fit_file(fit_basename: str) -> Path | None:
    """Clean one .fit file; write CSV to 03_Processed_Data/. Returns output path."""
    print(f"Washing: {fit_basename}")
    file_path = RAW_DATA_DIR / fit_basename
    if not file_path.exists():
        print(f"  ERROR: not found — {file_path}")
        return None

    fit = fitparse.FitFile(str(file_path))
    rows = []
    for record in fit.get_messages("record"):
        d = record.get_values()
        rows.append({k: d.get(k) for k in RECORD_FIELDS})

    df = pd.DataFrame(rows)
    if df.empty:
        print("  WARNING: no record messages in file.")
        return None

    if "enhanced_speed" not in df.columns or df["enhanced_speed"].isna().all():
        df["enhanced_speed"] = df.get("speed")
    if "enhanced_altitude" not in df.columns or df["enhanced_altitude"].isna().all():
        df["enhanced_altitude"] = df.get("altitude")

    df.dropna(subset=["timestamp"], inplace=True)
    df.ffill(inplace=True)

    PROCESSED_DATA_DIR.mkdir(exist_ok=True)
    output_name = fit_basename.replace(".fit", "_CLEAN.csv")
    output_path = PROCESSED_DATA_DIR / output_name
    df.to_csv(output_path, index=False)
    print(f"  OK → {output_name} ({len(df)} samples)")
    return output_path


def _load_washed_series(fit_basename: str) -> pd.DataFrame:
    path = RAW_DATA_DIR / fit_basename
    fit = fitparse.FitFile(str(path))
    rows = [r.get_values() for r in fit.get_messages("record")]
    df = pd.DataFrame(rows)
    if "enhanced_speed" not in df.columns:
        df["enhanced_speed"] = df.get("speed", 0)
    if "enhanced_altitude" not in df.columns:
        df["enhanced_altitude"] = df.get("altitude")
    df = df[df["enhanced_speed"] > 0.5].copy()
    df["pace_min_km"] = (1000 / df["enhanced_speed"]) / 60
    return df.ffill()


def validate_tartan_calibration(df: pd.DataFrame, max_gain_m: float = 5.0) -> dict:
    """Sanity-check near-zero elevation tartan surface."""
    alt = df["enhanced_altitude"].dropna()
    if alt.empty:
        return {"valid": False, "reason": "no altitude data"}
    gain = float(alt.max() - alt.min())
    dist_km = float(df["distance"].max() / 1000) if "distance" in df.columns else 0.0
    hr = df["heart_rate"].dropna()
    pace = df["pace_min_km"].dropna()
    return {
        "valid": gain <= max_gain_m,
        "elevation_gain_m": round(gain, 1),
        "distance_km": round(dist_km, 2),
        "mean_hr": round(float(hr.mean()), 1) if not hr.empty else None,
        "median_pace_min_km": round(float(pace.median()), 2) if not pace.empty else None,
        "sample_count": len(df),
    }


def run_calibration_5k(
    subject_b_fit: str,
    subject_a_fit: str | None,
    lock_subject_b: bool,
) -> None:
    """Ingest paired 5k tartan calibration (Subject_B effort + optional Subject_A pacer)."""
    protocol = seed_matrix.calibration_protocol("5k_stavanger_stadion")
    max_gain = float(protocol.get("max_elevation_gain_m", 5))

    print("\n" + "=" * 60)
    print("  5K TARTAN CALIBRATION — Seed Matrix (Subject_B)")
    print("=" * 60)
    if seed_matrix.proxy_generation_halted():
        print("  Proxy generation: HALTED (real tartan telemetry required)")
    print(f"  Venue:     {protocol.get('venue', 'Stavanger Stadion')}")
    print(f"  Pacer:     {protocol.get('pacer_subject', 'Subject_A')}")
    print(f"  Calibrate: {protocol.get('calibration_subject', 'Subject_B')}")
    print("-" * 60)

    b_out = wash_fit_file(subject_b_fit)
    if b_out is None:
        return

    if subject_a_fit:
        wash_fit_file(subject_a_fit)

    stats = validate_tartan_calibration(_load_washed_series(subject_b_fit), max_gain)
    print("\n  Subject_B tartan validation:")
    for k, v in stats.items():
        print(f"    {k}: {v}")

    if not stats.get("valid"):
        print("\n  WARNING: Elevation gain exceeds tartan threshold.")
        print("  Anchor NOT locked — review telemetry before --lock-subject-b.")
        return

    print("\n  Candidate anchor pace (median): "
          f"{stats.get('median_pace_min_km')} min/km @ mean HR {stats.get('mean_hr')} bpm")

    if lock_subject_b:
        seed_matrix.lock_anchor(
            "Subject_B",
            subject_b_fit,
            surface="tartan",
            protocol="5k_stavanger_stadion",
            notes="5k Stavanger Stadion — mechanical pacer Subject_A",
        )
        print(f"\n  LOCKED: Subject_B anchor → {subject_b_fit}")
        print("  All APR/TI pipelines will use this baseline for Subject_B.")
    else:
        print("\n  Anchor not locked. Re-run with --lock-subject-b after review.")

    print("=" * 60 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Wash .fit telemetry to cleaned CSV")
    parser.add_argument("--fit", help="Single .fit basename or path under 02_Raw_Data/")
    parser.add_argument(
        "--calibration-5k",
        action="store_true",
        help="Ingest Subject_B 5k tartan calibration (+ optional Subject_A pacer)",
    )
    parser.add_argument(
        "--subject-b-fit",
        help="Subject_B calibration .fit (tartan 5k)",
    )
    parser.add_argument(
        "--subject-a-fit",
        help="Subject_A pacer .fit (optional paired reference)",
    )
    parser.add_argument(
        "--lock-subject-b",
        action="store_true",
        help="Lock Subject_B tartan file as definitive Seed Matrix anchor",
    )
    parser.add_argument(
        "--auto-find",
        action="store_true",
        help="Auto-find calibration files by date tokens in 02_Raw_Data/",
    )
    parser.add_argument("--date", help="YYYYMMDD token for --auto-find")
    args = parser.parse_args()

    if args.calibration_5k:
        b_fit = args.subject_b_fit
        a_fit = args.subject_a_fit
        if args.auto_find and args.date:
            token_b = fit_filename_token("Subject_B")
            token_a = fit_filename_token("Subject_A")
            if not b_fit:
                b_fit = find_fit(args.date, token_b)
            if not a_fit:
                try:
                    a_fit = find_fit(args.date, token_a)
                except FileNotFoundError:
                    a_fit = None
        if not b_fit:
            parser.error("--subject-b-fit required (or --auto-find --date YYYYMMDD)")
        run_calibration_5k(b_fit, a_fit, args.lock_subject_b)
        return

    if args.fit:
        name = Path(args.fit).name
        wash_fit_file(name)
        return

    # Default: wash any pending Subject_A LFI + generic LFI if present
    token_a = fit_filename_token("Subject_A")
    try:
        wash_fit_file(find_fit("LFI", token_a, "20260606"))
    except FileNotFoundError:
        pass
    try:
        wash_fit_file("LFI_2026.fit")
    except Exception as exc:
        print(f"Note: {exc}")


if __name__ == "__main__":
    main()
