#!/usr/bin/env python3
"""
GAP Engine — Phase 1–3 (Minetti + Barometric Shift + TI smoothing)

Computes Grade Adjusted Pace (GAP) and Terrain Index (TI) from FIT telemetry.

TI = pace_actual / pace_expected_on_grade
  (pace_expected from asphalt anchor @ iso-HR + Minetti grade cost)

Phase 2: altitude shifted shift(-3) before grade — barometric lag compensation
Phase 3: 30 s rolling mean on TI — GPS noise filter (docs/theory.md §5)

Usage:
    python 11_gap_engine.py --fit 02_Raw_Data/Stavanger_Halvmaraton.fit
    python 11_gap_engine.py --batch
    python 11_gap_engine.py --fit 02_Raw_Data/Subject_B_session.fit --no-ti-smoothing
"""

from __future__ import annotations

import argparse
from pathlib import Path

import fitparse
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "02_Raw_Data"
PROCESSED_DIR = BASE_DIR / "03_Processed_Data"
DEFAULT_ANCHOR = RAW_DIR / "Stavanger_Halvmaraton.fit"

MIN_SPEED_M_S = 0.5
HR_BAND_BPM = 5
GRADE_SMOOTH_SAMPLES = 15
GRADE_CAP = 0.45
C_FLAT = 3.6
MIN_SEGMENT_SAMPLES = 20
BAROMETRIC_SHIFT_SAMPLES = 3
TI_ROLLING_SECONDS = 30
TI_ROLLING_MIN_PERIODS = 5


def minetti_cost(gradient: float) -> float:
    """Metabolic cost of running (J/kg/m) at gradient g = rise/run."""
    g = float(np.clip(gradient, -GRADE_CAP, GRADE_CAP))
    return (
        155.4 * g**5
        - 30.4 * g**4
        - 43.3 * g**3
        + 46.3 * g**2
        + 19.5 * g
        + C_FLAT
    )


def pace_factor(gradient: float) -> float:
    """Multiplicative pace cost vs flat: pace_on_grade = pace_flat * factor."""
    return minetti_cost(gradient) / C_FLAT


def load_fit(path: Path) -> pd.DataFrame:
    fitfile = fitparse.FitFile(str(path))
    rows = [r.get_values() for r in fitfile.get_messages("record")]
    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError(f"No records in {path.name}")

    if "enhanced_speed" not in df.columns:
        df["enhanced_speed"] = df.get("speed", 0)
    if "altitude" not in df.columns and "enhanced_altitude" in df.columns:
        df["altitude"] = df["enhanced_altitude"]

    df = df[df["enhanced_speed"] > MIN_SPEED_M_S].copy()
    df["speed_m_s"] = df["enhanced_speed"]
    df["pace_min_km"] = (1000 / df["speed_m_s"]) / 60

    if "distance" not in df.columns or df["distance"].isna().all():
        dt = df["timestamp"].diff().dt.total_seconds().fillna(0)
        df["distance"] = (df["speed_m_s"] * dt).cumsum()

    df["distance_km"] = df["distance"] / 1000
    return df.ffill().dropna(subset=["pace_min_km", "heart_rate", "altitude"])


def apply_barometric_shift(df: pd.DataFrame, lag_samples: int = BAROMETRIC_SHIFT_SAMPLES) -> pd.DataFrame:
    """
    Compensate for barometric altimeter lag on steep grade changes.

    Uses shift(-N): current sample borrows altitude from N records ahead so
    grade aligns with horizontal position (master_plan §7).
    """
    out = df.copy()
    out["altitude_raw"] = out["altitude"]
    out["altitude"] = out["altitude"].shift(-lag_samples).bfill().ffill()
    return out


def compute_grade(df: pd.DataFrame, window: int = GRADE_SMOOTH_SAMPLES) -> pd.Series:
    """Grade (rise/run) from smoothed altitude over rolling horizontal distance."""
    alt = df["altitude"].rolling(window, center=True, min_periods=3).mean()
    dist = df["distance"]
    delta_alt = alt.diff(window)
    delta_dist = dist.diff(window)
    grade = delta_alt / delta_dist.replace(0, np.nan)
    return grade.clip(-GRADE_CAP, GRADE_CAP).fillna(0.0)


def anchor_pace_at_hr(anchor: pd.DataFrame, hr: float, band: int = HR_BAND_BPM) -> float:
    subset = anchor[
        (anchor["heart_rate"] >= hr - band) & (anchor["heart_rate"] <= hr + band)
    ]
    if len(subset) < MIN_SEGMENT_SAMPLES:
        subset = anchor
    return float(subset["pace_min_km"].median())


def apply_ti_smoothing(
    df: pd.DataFrame,
    window_seconds: int = TI_ROLLING_SECONDS,
) -> pd.DataFrame:
    """
    Apply time-based rolling mean to pointwise TI (Phase 3).

    Reduces GPS/pace spike noise per docs/theory.md §5 (30 s window).
    """
    out = df.sort_values("timestamp").copy()
    out["ti_raw"] = out["ti"]
    ti = out["ti_raw"].replace([np.inf, -np.inf], np.nan)
    ti.index = pd.to_datetime(out["timestamp"])
    smoothed = ti.rolling(
        f"{window_seconds}s",
        center=True,
        min_periods=TI_ROLLING_MIN_PERIODS,
    ).mean()
    out["ti"] = smoothed.to_numpy()
    out["ti"] = out["ti"].bfill().ffill()
    return out


def apply_gap(
    df: pd.DataFrame,
    anchor: pd.DataFrame,
    barometric_shift: bool = True,
    ti_smoothing: bool = True,
) -> pd.DataFrame:
    """
    Add grade, GAP, and TI columns.

    pace_gap_flat: Minetti flat-equivalent of actual pace (what flat pace = same effort)
    pace_expected: expected pace on this grade @ same HR from asphalt anchor
    ti: pace_actual / pace_expected — friction/technique beyond grade (>1 = terrain tax)
    """
    out = df.copy()
    if barometric_shift:
        out = apply_barometric_shift(out)
    out["grade"] = compute_grade(out)
    out["grade_pct"] = out["grade"] * 100

    pf = out["grade"].apply(pace_factor)
    out["pace_gap_flat"] = out["pace_min_km"] / pf

    out["pace_expected"] = out["heart_rate"].apply(
        lambda hr: anchor_pace_at_hr(anchor, hr)
    ) * pf

    out["ti"] = out["pace_min_km"] / out["pace_expected"].replace(0, np.nan)
    out["speed_gap_m_s"] = out["speed_m_s"] * pf

    if ti_smoothing:
        out = apply_ti_smoothing(out)
    return out


def segment_summary(df: pd.DataFrame, km_start: int, km_end: int) -> pd.DataFrame:
    rows = []
    for km in range(km_start, km_end):
        seg = df[(df["distance_km"] >= km) & (df["distance_km"] < km + 1)]
        if len(seg) < MIN_SEGMENT_SAMPLES:
            continue
        rows.append(
            {
                "km": km,
                "label": f"{km}–{km + 1}",
                "mean_grade_pct": seg["grade_pct"].mean(),
                "mean_pace": seg["pace_min_km"].mean(),
                "mean_pace_gap_flat": seg["pace_gap_flat"].mean(),
                "mean_ti": seg["ti"].mean(),
                "mean_hr": seg["heart_rate"].mean(),
                "alt_gain_m": seg["altitude"].iloc[-1] - seg["altitude"].iloc[0],
            }
        )
    return pd.DataFrame(rows)


def phase_label(barometric_shift: bool, ti_smoothing: bool) -> str:
    parts = ["Phase 1 — Minetti GAP"]
    if barometric_shift:
        parts.append("Phase 2 — barometric shift")
    if ti_smoothing:
        parts.append("Phase 3 — 30 s TI smoothing")
    return " | ".join(parts)


def print_validation(
    name: str,
    df: pd.DataFrame,
    segments: pd.DataFrame | None = None,
    barometric_shift: bool = True,
    ti_smoothing: bool = True,
) -> None:
    ti = df["ti"].replace([np.inf, -np.inf], np.nan).dropna()
    print(f"\n{'=' * 58}")
    print(f"  GAP VALIDATION — {name}")
    print(f"  {phase_label(barometric_shift, ti_smoothing)}")
    print(f"{'=' * 58}")
    print(f"  Samples:        {len(df):,}")
    print(f"  Distance:       {df['distance_km'].max():.2f} km")
    print(f"  Mean grade:     {df['grade_pct'].mean():+.2f} %")
    print(f"  Mean pace:      {df['pace_min_km'].mean():.2f} min/km")
    print(f"  Mean GAP pace:  {df['pace_gap_flat'].mean():.2f} min/km (flat equivalent)")
    print(f"  Mean TI:        {ti.mean():.3f}  (target ≈ 1.0 on asphalt anchor)")
    print(f"  TI median:      {ti.median():.3f}")
    print(f"  TI p10–p90:     {ti.quantile(0.1):.3f} – {ti.quantile(0.9):.3f}")
    if "ti_raw" in df.columns and ti_smoothing:
        raw = df["ti_raw"].replace([np.inf, -np.inf], np.nan).dropna()
        print(f"  TI raw mean:    {raw.mean():.3f}  (pre-smoothing)")
        print(f"  TI raw p90:     {raw.quantile(0.9):.3f}")

    if segments is not None and not segments.empty:
        print(f"\n  {'km':<8} {'Grade%':>7} {'Pace':>7} {'GAP':>7} {'TI':>6} {'Δalt':>6}")
        print(f"  {'-' * 48}")
        for _, r in segments.iterrows():
            print(
                f"  {r['label']:<8} {r['mean_grade_pct']:>+6.1f} "
                f"{r['mean_pace']:>7.2f} {r['mean_pace_gap_flat']:>7.2f} "
                f"{r['mean_ti']:>6.2f} {r['alt_gain_m']:>+5.0f}m"
            )
    print(f"{'=' * 58}\n")


def save_csv(df: pd.DataFrame, path: Path) -> None:
    cols = [
        "timestamp",
        "distance_km",
        "altitude",
        "heart_rate",
        "pace_min_km",
        "grade_pct",
        "pace_gap_flat",
        "pace_expected",
        "ti",
        "ti_raw",
        "speed_m_s",
        "speed_gap_m_s",
    ]
    available = [c for c in cols if c in df.columns]
    path.parent.mkdir(parents=True, exist_ok=True)
    df[available].to_csv(path, index=False)
    print(f"Saved: {path}")


def run(
    fit_path: Path,
    anchor_path: Path,
    validate: bool,
    save: bool,
    barometric_shift: bool = True,
    ti_smoothing: bool = True,
) -> pd.DataFrame:
    anchor = load_fit(anchor_path)
    session = load_fit(fit_path)
    result = apply_gap(
        session, anchor, barometric_shift=barometric_shift, ti_smoothing=ti_smoothing
    )

    max_km = int(result["distance_km"].max()) + 1
    segments = segment_summary(result, 0, max_km)

    if validate:
        print_validation(
            fit_path.stem, result, segments,
            barometric_shift=barometric_shift, ti_smoothing=ti_smoothing,
        )

    if save:
        out_name = fit_path.stem + "_GAP.csv"
        save_csv(result, PROCESSED_DIR / out_name)

    return result


def run_batch_summary(
    anchor_path: Path,
    barometric_shift: bool = True,
    ti_smoothing: bool = True,
) -> pd.DataFrame:
    """Summarise all sessions in 02_Raw_Data/."""
    anchor = load_fit(anchor_path)
    rows = []
    for fit in sorted(RAW_DIR.glob("*.fit")):
        try:
            df = apply_gap(
                load_fit(fit), anchor,
                barometric_shift=barometric_shift,
                ti_smoothing=ti_smoothing,
            )
            ti = df["ti"].replace([np.inf, -np.inf], np.nan).dropna()
            max_km = int(df["distance_km"].max()) + 1
            segs = segment_summary(df, 0, max_km)
            bh = segs.loc[segs["mean_ti"].idxmax()] if not segs.empty else None
            rows.append(
                {
                    "file": fit.stem,
                    "km": round(df["distance_km"].max(), 1),
                    "mean_ti": round(float(ti.mean()), 2),
                    "median_ti": round(float(ti.median()), 2),
                    "bh_km": bh["label"] if bh is not None else "—",
                    "bh_ti": round(float(bh["mean_ti"]), 2) if bh is not None else None,
                }
            )
        except Exception as exc:
            rows.append({"file": fit.stem, "error": str(exc)})
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="GAP Engine — Minetti 2002 + barometric shift")
    parser.add_argument("--fit", help="Path to session .fit file")
    parser.add_argument(
        "--anchor",
        default=str(DEFAULT_ANCHOR),
        help="Asphalt anchor .fit for iso-HR reference",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Write GAP CSV to 03_Processed_Data/",
    )
    parser.add_argument(
        "--no-barometric-shift",
        action="store_true",
        help="Disable Phase 2 altitude shift (compare against raw barometer)",
    )
    parser.add_argument(
        "--no-ti-smoothing",
        action="store_true",
        help="Disable Phase 3 rolling 30 s TI smooth",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Summarise all .fit files in 02_Raw_Data/",
    )
    args = parser.parse_args()

    anchor_path = Path(args.anchor)
    if not anchor_path.is_absolute():
        anchor_path = BASE_DIR / anchor_path

    baro = not args.no_barometric_shift
    smooth = not args.no_ti_smoothing

    if args.batch:
        res = run_batch_summary(
            anchor_path, barometric_shift=baro, ti_smoothing=smooth,
        )
        print(f"\nGAP BATCH — {phase_label(baro, smooth)}")
        print("=" * 72)
        for _, r in res.iterrows():
            if "error" in r and pd.notna(r.get("error")):
                print(f"  FAIL {r['file']}: {r['error']}")
            else:
                print(
                    f"  {r['file']:<35} {r['km']:>5} km  "
                    f"TI={r['mean_ti']:.2f} (med {r['median_ti']:.2f})  "
                    f"BH km {r['bh_km']} TI={r['bh_ti']}"
                )
        errors = int(res["error"].notna().sum()) if "error" in res.columns else 0
        print("=" * 72)
        print(f"OK: {len(res) - errors}/{len(res)}\n")
        return

    if not args.fit:
        parser.error("--fit is required unless --batch is used")

    fit_path = Path(args.fit)
    if not fit_path.is_absolute():
        fit_path = BASE_DIR / fit_path

    run(
        fit_path, anchor_path, validate=True, save=args.save,
        barometric_shift=baro, ti_smoothing=smooth,
    )


if __name__ == "__main__":
    main()
