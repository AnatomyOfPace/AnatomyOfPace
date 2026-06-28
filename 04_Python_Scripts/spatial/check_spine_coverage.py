#!/usr/bin/env python3
"""
Report ref_chainage_m spine coverage for training (or race) panel activities.

Computes per-activity and union coverage within a km window, lists missing
ref_chainage_m ranges, and optional cross_track_m QC stats.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/check_spine_coverage.py \\
        --manifest config/spatial_align_manifest_sut43.example.json

    python3 04_Python_Scripts/spatial/check_spine_coverage.py \\
        --panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_training_1m_spine.parquet \\
        --km-start 29 --km-end 41 --min-gap-m 50
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.corridor_scope import (  # noqa: E402
    SUT43_CORRIDOR_ID,
    SUT43_PRIMARY_KM_END,
    SUT43_PRIMARY_KM_START,
)
from spatial.spatial_align import load_manifest, spatial_output_dir  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _km_window_from_manifest(manifest: dict[str, Any]) -> tuple[float, float]:
    window = manifest.get("km_analysis_window")
    if window and len(window) >= 2:
        return float(window[0]), float(window[1])
    return SUT43_PRIMARY_KM_START, SUT43_PRIMARY_KM_END


def _default_panel_path(
    manifest: dict[str, Any] | None,
    *,
    session_type: str,
) -> Path:
    corridor_id = (manifest or {}).get("corridor_id", SUT43_CORRIDOR_ID)
    suffix = f"panel_{session_type}_1m_spine.parquet"
    return spatial_output_dir(corridor_id) / suffix


def _merge_missing_ranges(
    missing: list[int],
    *,
    min_gap_m: int,
) -> list[tuple[int, int, int]]:
    """Return [(start_m, end_m_exclusive, length_m), ...] for gaps >= min_gap_m."""
    if not missing:
        return []
    ranges: list[tuple[int, int, int]] = []
    start = missing[0]
    prev = missing[0]
    for m in missing[1:]:
        if m == prev + 1:
            prev = m
        else:
            end_excl = prev + 1
            length = end_excl - start
            if length >= min_gap_m:
                ranges.append((start, end_excl, length))
            start = m
            prev = m
    end_excl = prev + 1
    length = end_excl - start
    if length >= min_gap_m:
        ranges.append((start, end_excl, length))
    return ranges


def _activity_stats(
    panel: pd.DataFrame,
    *,
    window_start_m: int,
    window_end_m: int,
) -> dict[str, Any]:
    window_len = window_end_m - window_start_m
    expected = set(range(window_start_m, window_end_m))
    activities = sorted(panel["activity_id"].dropna().unique())
    per_activity: list[dict[str, Any]] = []
    union: set[int] = set()

    for act in activities:
        sub = panel[panel["activity_id"] == act]
        chainages = set(
            int(v)
            for v in pd.to_numeric(sub["ref_chainage_m"], errors="coerce").dropna().astype(int)
            if window_start_m <= int(v) < window_end_m
        )
        union |= chainages
        covered = len(chainages)
        pct = 100.0 * covered / window_len if window_len else 0.0
        row: dict[str, Any] = {
            "activity_id": act,
            "covered_m": covered,
            "coverage_pct": round(pct, 2),
        }
        if chainages:
            row["ref_chainage_km_min"] = round(min(chainages) / 1000.0, 3)
            row["ref_chainage_km_max"] = round(max(chainages) / 1000.0, 3)
        if "cross_track_m" in sub.columns and chainages:
            xt = pd.to_numeric(sub["cross_track_m"], errors="coerce").dropna()
            if not xt.empty:
                row["cross_track_m_median"] = round(float(xt.median()), 2)
                row["cross_track_m_max"] = round(float(xt.max()), 2)
        per_activity.append(row)

    missing = sorted(expected - union)
    return {
        "window_len_m": window_len,
        "union_covered_m": len(union),
        "union_coverage_pct": round(100.0 * len(union) / window_len, 2) if window_len else 0.0,
        "missing_m": len(missing),
        "per_activity": per_activity,
        "missing_chainages": missing,
    }


def check_spine_coverage(
    panel: pd.DataFrame,
    *,
    km_start: float,
    km_end: float,
    min_gap_m: int = 50,
) -> dict[str, Any]:
    if "ref_chainage_m" not in panel.columns:
        raise ValueError("Panel missing ref_chainage_m — run reproject_to_spine.py first")

    window_start_m = int(round(km_start * 1000))
    window_end_m = int(round(km_end * 1000))
    in_window = panel[
        (pd.to_numeric(panel["ref_chainage_m"], errors="coerce") >= window_start_m)
        & (pd.to_numeric(panel["ref_chainage_m"], errors="coerce") < window_end_m)
    ]
    stats = _activity_stats(in_window, window_start_m=window_start_m, window_end_m=window_end_m)
    gaps = _merge_missing_ranges(stats.pop("missing_chainages"), min_gap_m=min_gap_m)
    stats["gaps"] = [
        {
            "ref_chainage_m_start": g[0],
            "ref_chainage_m_end": g[1],
            "length_m": g[2],
            "ref_chainage_km_start": round(g[0] / 1000.0, 3),
            "ref_chainage_km_end": round(g[1] / 1000.0, 3),
            "length_km": round(g[2] / 1000.0, 3),
        }
        for g in gaps
    ]
    stats["km_start"] = km_start
    stats["km_end"] = km_end
    stats["min_gap_m"] = min_gap_m
    return stats


def _print_report(report: dict[str, Any]) -> None:
    print(f"Spine coverage window: km {report['km_start']:.1f}–{report['km_end']:.1f}")
    print(f"Window length: {report['window_len_m']} m")
    print(
        f"Union coverage: {report['union_covered_m']} / {report['window_len_m']} m "
        f"({report['union_coverage_pct']:.1f}%)"
    )
    print(f"Missing metres (union): {report['missing_m']}")
    print()
    print("Per activity:")
    for row in report["per_activity"]:
        parts = [
            f"  {row['activity_id']}: {row['covered_m']} m ({row['coverage_pct']:.1f}%)",
        ]
        if "ref_chainage_km_min" in row:
            parts.append(f"km {row['ref_chainage_km_min']:.3f}–{row['ref_chainage_km_max']:.3f}")
        if "cross_track_m_median" in row:
            parts.append(f"cross_track median {row['cross_track_m_median']:.1f} m")
        print(" — ".join(parts))
    print()
    print(f"Gap ranges (ref_chainage_m, min length {report['min_gap_m']} m):")
    if not report["gaps"]:
        print("  (none)")
    else:
        for g in report["gaps"]:
            print(
                f"  {g['ref_chainage_m_start']}–{g['ref_chainage_m_end']} m "
                f"({g['ref_chainage_km_start']:.3f}–{g['ref_chainage_km_end']:.3f} km, "
                f"{g['length_km']:.3f} km)"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Report spine ref_chainage_m coverage for a panel.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=BASE_DIR / "config" / "spatial_align_manifest_sut43.example.json",
        help="Manifest for default km window and panel path",
    )
    parser.add_argument(
        "--panel",
        type=Path,
        default=None,
        help="Spine panel parquet (default: panel_training_1m_spine.parquet from manifest corridor)",
    )
    parser.add_argument("--session-type", choices=("training", "race"), default="training")
    parser.add_argument("--km-start", type=float, default=None)
    parser.add_argument("--km-end", type=float, default=None)
    parser.add_argument(
        "--min-gap-m",
        type=int,
        default=50,
        help="Minimum contiguous missing span to report as a gap (default 50 m)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report to stdout")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest) if args.manifest.exists() else {}
    km_start = args.km_start if args.km_start is not None else _km_window_from_manifest(manifest)[0]
    km_end = args.km_end if args.km_end is not None else _km_window_from_manifest(manifest)[1]

    panel_path = args.panel or _default_panel_path(manifest, session_type=args.session_type)
    if not panel_path.exists():
        raise FileNotFoundError(f"Panel not found: {panel_path}")

    panel = pd.read_parquet(panel_path)
    report = check_spine_coverage(panel, km_start=km_start, km_end=km_end, min_gap_m=args.min_gap_m)
    report["panel"] = str(panel_path)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Panel: {panel_path}")
        _print_report(report)


if __name__ == "__main__":
    main()
