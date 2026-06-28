"""
GAP / TI enrichment for ActivityFrame Parquet (Minetti 2002 via 11_gap_engine).

Adds pace_gap_flat, pace_expected, ti, grade columns; optional corridor metrics JSON.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import seed_matrix
from fit_micro.activity_frame import micro_meta_path, micro_parquet_path, read_parquet, write_parquet

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_ANCHOR = BASE_DIR / "02_Raw_Data" / "Stavanger_Halvmaraton.fit"
MIN_SPEED_M_S = 0.5

_spec = importlib.util.spec_from_file_location(
    "gap_engine",
    Path(__file__).resolve().parent.parent / "11_gap_engine.py",
)
_gap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gap)


def _resolve_anchor(subject_id: str | None, anchor_path: Path | None) -> Path:
    if anchor_path is not None:
        p = Path(anchor_path)
        return p if p.is_absolute() else BASE_DIR / p
    if subject_id:
        return seed_matrix.anchor_path_or_default(subject_id, DEFAULT_ANCHOR)
    return DEFAULT_ANCHOR


def activity_frame_to_gap_input(frame: pd.DataFrame) -> pd.DataFrame:
    """Map ActivityFrame columns to 11_gap_engine contract."""
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    out["altitude"] = pd.to_numeric(out["altitude_m"], errors="coerce")
    out["heart_rate"] = pd.to_numeric(out["heart_rate"], errors="coerce")
    out["speed_m_s"] = pd.to_numeric(out["speed_mps"], errors="coerce")

    if out["course_km"].notna().any():
        out["distance"] = pd.to_numeric(out["course_km"], errors="coerce") * 1000.0
    else:
        out["distance"] = pd.to_numeric(out["distance_m"], errors="coerce")
    out["distance_km"] = out["distance"] / 1000.0

    out = out[out["speed_m_s"] > MIN_SPEED_M_S].copy()
    out["pace_min_km"] = (1000.0 / out["speed_m_s"]) / 60.0
    return out.dropna(subset=["pace_min_km", "altitude"])


_GAP_OUTPUT_COLS = frozenset(
    {"grade", "grade_pct", "pace_gap_flat", "pace_expected", "ti", "ti_raw"}
)


def merge_gap_columns(frame: pd.DataFrame, gap_df: pd.DataFrame) -> pd.DataFrame:
    """Join GAP/TI outputs back onto the full ActivityFrame by timestamp."""
    cols = ["timestamp", "grade", "grade_pct", "pace_gap_flat", "pace_expected", "ti"]
    if "ti_raw" in gap_df.columns:
        cols.append("ti_raw")
    slim = gap_df[cols].copy()
    slim["timestamp"] = pd.to_datetime(slim["timestamp"], utc=True, errors="coerce")
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    drop = [c for c in out.columns if c in _GAP_OUTPUT_COLS or c.startswith("grade_")]
    if drop:
        out = out.drop(columns=drop)
    return out.merge(slim, on="timestamp", how="left")


def corridor_ti_stats(
    frame: pd.DataFrame,
    km_start: float,
    km_end: float,
    *,
    axis: str = "course_km",
) -> dict[str, Any]:
    """Mean and peak TI within a course-km window."""
    km_col = axis if axis in frame.columns else "distance_m"
    if km_col == "distance_m":
        km = pd.to_numeric(frame["distance_m"], errors="coerce") / 1000.0
    else:
        km = pd.to_numeric(frame[km_col], errors="coerce")

    lo, hi = min(km_start, km_end), max(km_start, km_end)
    sub = frame[(km >= lo) & (km <= hi) & frame["ti"].notna()]
    if sub.empty:
        return {
            "km_start": lo,
            "km_end": hi,
            "n": 0,
            "mean_ti": None,
            "peak_ti": None,
            "median_ti": None,
        }
    ti = sub["ti"].replace([np.inf, -np.inf], np.nan).dropna()
    return {
        "km_start": lo,
        "km_end": hi,
        "n": int(len(ti)),
        "mean_ti": float(ti.mean()),
        "peak_ti": float(ti.max()),
        "median_ti": float(ti.median()),
    }


def enrich_ti(
    frame: pd.DataFrame,
    *,
    subject_id: str | None = "Subject_A",
    anchor_path: Path | None = None,
    barometric_shift: bool = True,
    ti_smoothing: bool = True,
    use_cegap: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Compute GAP/TI on ActivityFrame; return enriched frame + summary metadata."""
    anchor_fit = _gap.load_fit(_resolve_anchor(subject_id, anchor_path))
    gap_input = activity_frame_to_gap_input(frame)
    gap_out = _gap.apply_gap(
        gap_input,
        anchor_fit,
        barometric_shift=barometric_shift,
        ti_smoothing=ti_smoothing,
        use_cegap=use_cegap,
    )
    enriched = merge_gap_columns(frame, gap_out)
    ti = gap_out["ti"].replace([np.inf, -np.inf], np.nan).dropna()
    meta = {
        "subject_id": subject_id,
        "anchor": str(_resolve_anchor(subject_id, anchor_path).name),
        "n_gap_samples": int(len(gap_out)),
        "mean_ti": float(ti.mean()) if len(ti) else None,
        "median_ti": float(ti.median()) if len(ti) else None,
        "barometric_shift": barometric_shift,
        "ti_smoothing_s": _gap.TI_ROLLING_SECONDS if ti_smoothing else None,
        "use_cegap": use_cegap,
    }
    return enriched, meta


def enrich_parquet(
    donor_id: str,
    activity_id: str,
    *,
    subject_id: str | None = None,
    project_course: bool = False,
    race_id: str | None = None,
    gpx_path: Path | None = None,
    write_metrics: bool = True,
    **ti_kwargs: Any,
) -> Path:
    """Read micro Parquet, optionally project course, enrich TI, rewrite."""
    from fit_micro.course_project import project_course_km

    subject_id = subject_id or donor_id
    frame = read_parquet(donor_id, activity_id)

    if project_course or frame["course_km"].isna().all():
        meta_path = micro_meta_path(donor_id, activity_id)
        rid = race_id
        if rid is None and meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            rid = meta.get("race_id")
        frame = project_course_km(frame, race_id=rid, gpx_path=gpx_path)

    enriched, ti_meta = enrich_ti(frame, subject_id=subject_id, **ti_kwargs)
    out = write_parquet(enriched, donor_id, activity_id)

    if write_metrics:
        metrics_path = micro_parquet_path(donor_id, activity_id).with_suffix(".ti_metrics.json")
        metrics_path.write_text(json.dumps(ti_meta, indent=2), encoding="utf-8")
    return out


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Enrich ActivityFrame Parquet with GAP/TI")
    parser.add_argument("--donor", required=True)
    parser.add_argument("--activity", required=True)
    parser.add_argument("--subject", default=None, help="Anchor subject (default: --donor)")
    parser.add_argument("--project-course", action="store_true")
    parser.add_argument("--race", default=None)
    parser.add_argument("--gpx", type=Path, default=None)
    parser.add_argument("--no-barometric-shift", action="store_true")
    parser.add_argument("--no-ti-smoothing", action="store_true")
    parser.add_argument("--corridor", nargs=2, type=float, metavar=("KM_START", "KM_END"))
    args = parser.parse_args()

    out = enrich_parquet(
        args.donor,
        args.activity,
        subject_id=args.subject or args.donor,
        project_course=args.project_course,
        race_id=args.race,
        gpx_path=args.gpx,
        barometric_shift=not args.no_barometric_shift,
        ti_smoothing=not args.no_ti_smoothing,
    )
    print(f"OK → {out}")

    if args.corridor:
        frame = read_parquet(args.donor, args.activity)
        stats = corridor_ti_stats(frame, args.corridor[0], args.corridor[1])
        print(
            f"Corridor km {stats['km_start']:.1f}–{stats['km_end']:.1f}: "
            f"n={stats['n']} mean_ti={stats['mean_ti']:.3f} peak_ti={stats['peak_ti']:.3f}"
            if stats["mean_ti"] is not None
            else f"Corridor: no TI samples (n=0)"
        )


if __name__ == "__main__":
    main()
