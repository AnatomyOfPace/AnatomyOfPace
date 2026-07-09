#!/usr/bin/env python3
"""
LFI Elite Proficiency Ratio (EPR) — Subject_A vs Reference_Elite_A on paired course-km windows.

EPR = mean(TI_athlete) / mean(TI_elite) on the same sub-corridor (docs/theory.md §5).
EPR > 1.0 → athlete pays more terrain tax than reference on that segment.

Requires washed micro Parquets with --race LFI --project-course --enrich-ti.

Usage (repo root):
    python3 04_Python_Scripts/spatial/compute_lfi_epr.py

    python3 04_Python_Scripts/spatial/compute_lfi_epr.py \\
        --corridor neverdalsskaret_descent \\
        --output-json 07_ML_Models/lfi_epr_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from fit_micro.activity_frame import micro_parquet_path, read_parquet  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CORRIDORS_PATH = BASE_DIR / "config" / "race_corridors.json"
DEFAULT_ATHLETE = ("Subject_A", "LFI_20260606")
DEFAULT_ELITE = ("Reference_Elite_A", "18815539842")
DEFAULT_REPORT = BASE_DIR / "07_ML_Models" / "lfi_epr_report.json"
DEFAULT_CSV = BASE_DIR / "03_Processed_Data" / "lfi_epr_by_corridor.csv"
DEFAULT_PNG = BASE_DIR / "06_Visualizations" / "lfi_epr_by_corridor.png"

MIN_SAMPLES = 30
PRIORITY_CORRIDORS = (
    "neverdalsskaret_descent",
    "neverdalsskaret_climb",
    "preikestol_descent",
    "fjord_boulder_field",
    "sognesand_descent",
    "bratteli_descent",
    "post_sognesand",
    "leg_a_technical",
    "asphalt_finish",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_lfi_corridors(path: Path = CORRIDORS_PATH) -> list[dict[str, Any]]:
    reg = json.loads(path.read_text(encoding="utf-8"))
    lfi = reg.get("LFI") or {}
    out: list[dict[str, Any]] = []
    for cid, spec in (lfi.get("sub_corridors") or {}).items():
        out.append(
            {
                "corridor_id": cid,
                "km_start": float(spec["km_start"]),
                "km_end": float(spec["km_end"]),
                "label": spec.get("label") or cid,
            }
        )
    return out


def _ti_series(df: pd.DataFrame) -> pd.Series:
    if "ti" not in df.columns:
        raise ValueError("micro parquet missing ti column — re-wash with --enrich-ti")
    return pd.to_numeric(df["ti"], errors="coerce").replace([np.inf, -np.inf], np.nan)


def window_stats(
    df: pd.DataFrame,
    km_start: float,
    km_end: float,
    *,
    inclusive_end: bool = False,
) -> dict[str, Any]:
    km = pd.to_numeric(df["course_km"], errors="coerce")
    if inclusive_end:
        mask = (km >= km_start) & (km <= km_end)
    else:
        mask = (km >= km_start) & (km < km_end)
    sub = df.loc[mask]
    ti = _ti_series(sub).dropna()
    grade_col = "grade_pct" if "grade_pct" in sub.columns else "grade"
    grade = pd.to_numeric(sub[grade_col], errors="coerce") if grade_col in sub.columns else pd.Series(dtype=float)
    return {
        "n_samples": int(len(ti)),
        "mean_ti": float(ti.mean()) if len(ti) else None,
        "median_ti": float(ti.median()) if len(ti) else None,
        "peak_ti": float(ti.max()) if len(ti) else None,
        "mean_grade_pct": float(grade.mean()) if grade.notna().any() else None,
        "km_start_observed": float(km.loc[mask].min()) if mask.any() else None,
        "km_end_observed": float(km.loc[mask].max()) if mask.any() else None,
    }


def _json_safe(value: Any) -> Any:
    """Coerce numpy scalars for json.dumps."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if np.isnan(value) else float(value)
    return value


def compute_epr_cell(
    athlete: pd.DataFrame,
    elite: pd.DataFrame,
    *,
    corridor_id: str,
    label: str,
    km_start: float,
    km_end: float,
    min_samples: int,
) -> dict[str, Any]:
    a_stats = window_stats(athlete, km_start, km_end)
    e_stats = window_stats(elite, km_start, km_end)
    overlap_lo = max(
        athlete["course_km"].min(),
        elite["course_km"].min(),
        km_start,
    )
    overlap_hi = min(
        athlete["course_km"].max(),
        elite["course_km"].max(),
        km_end,
    )
    paired = (
        a_stats["n_samples"] >= min_samples
        and e_stats["n_samples"] >= min_samples
        and a_stats["mean_ti"] is not None
        and e_stats["mean_ti"] is not None
        and e_stats["mean_ti"] > 0
        and overlap_hi > overlap_lo
    )
    epr_mean = a_stats["mean_ti"] / e_stats["mean_ti"] if paired else None
    epr_median = (
        a_stats["median_ti"] / e_stats["median_ti"]
        if paired
        and a_stats["median_ti"] is not None
        and e_stats["median_ti"] is not None
        and e_stats["median_ti"] > 0
        else None
    )
    if epr_mean is not None:
        if epr_mean > 1.05:
            interpretation = "athlete_higher_tax"
        elif epr_mean < 0.95:
            interpretation = "athlete_more_efficient"
        else:
            interpretation = "parity"
    else:
        interpretation = "insufficient_overlap"

    return {
        "corridor_id": corridor_id,
        "label": label,
        "km_start": km_start,
        "km_end": km_end,
        "overlap_km": [overlap_lo, overlap_hi] if overlap_hi > overlap_lo else None,
        "athlete": a_stats,
        "elite": e_stats,
        "epr_mean": epr_mean,
        "epr_median": epr_median,
        "interpretation": interpretation,
        "paired": bool(paired),
    }


def compute_all_epr(
    athlete: pd.DataFrame,
    elite: pd.DataFrame,
    corridors: list[dict[str, Any]],
    *,
    min_samples: int,
    corridor_filter: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in corridors:
        if corridor_filter and spec["corridor_id"] != corridor_filter:
            continue
        rows.append(
            compute_epr_cell(
                athlete,
                elite,
                corridor_id=spec["corridor_id"],
                label=spec["label"],
                km_start=spec["km_start"],
                km_end=spec["km_end"],
                min_samples=min_samples,
            )
        )
    return rows


def render_epr_chart(rows: list[dict[str, Any]], output_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paired = [r for r in rows if r.get("epr_mean") is not None]
    if not paired:
        return
    paired = sorted(paired, key=lambda r: r["epr_mean"], reverse=True)
    labels = [r["corridor_id"] for r in paired]
    vals = [r["epr_mean"] for r in paired]
    colors = ["#EF5350" if v > 1.05 else "#66BB6A" if v < 0.95 else "#FFB74D" for v in vals]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, max(4, 0.35 * len(paired))))
    fig.patch.set_facecolor("#0A0A0A")
    ax.set_facecolor("#111111")
    ax.barh(labels, vals, color=colors, edgecolor="#333333")
    ax.axvline(1.0, color="#888888", linestyle="--", linewidth=1)
    ax.set_xlabel("EPR (Subject_A TI / Reference_Elite_A TI)")
    ax.set_title("LFI — Elite Proficiency Ratio by sub-corridor", color="white")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_color("#444444")
    fig.tight_layout()
    fig.savefig(output_path, dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute LFI EPR vs Reference_Elite_A.")
    parser.add_argument("--athlete-donor", default=DEFAULT_ATHLETE[0])
    parser.add_argument("--athlete-activity", default=DEFAULT_ATHLETE[1])
    parser.add_argument("--elite-donor", default=DEFAULT_ELITE[0])
    parser.add_argument("--elite-activity", default=DEFAULT_ELITE[1])
    parser.add_argument("--corridor", default=None, help="Single sub_corridor id (default: all)")
    parser.add_argument("--min-samples", type=int, default=MIN_SAMPLES)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output-png", type=Path, default=DEFAULT_PNG)
    parser.add_argument("--no-png", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    athlete_path = micro_parquet_path(args.athlete_donor, args.athlete_activity)
    elite_path = micro_parquet_path(args.elite_donor, args.elite_activity)

    for label, path in [("athlete", athlete_path), ("elite", elite_path)]:
        if not path.exists():
            print(f"Missing {label} micro parquet: {path}", file=sys.stderr)
            if label == "athlete":
                print(
                    "  Wash Subject_A LFI: python3 04_Python_Scripts/15_fit_micro_wash.py "
                    "--donor Subject_A --activity LFI_20260606 --fit <path> "
                    "--race LFI --project-course --enrich-ti",
                    file=sys.stderr,
                )
            return 1

    athlete = read_parquet(args.athlete_donor, args.athlete_activity)
    elite = read_parquet(args.elite_donor, args.elite_activity)
    corridors = load_lfi_corridors()

    rows = compute_all_epr(
        athlete,
        elite,
        corridors,
        min_samples=args.min_samples,
        corridor_filter=args.corridor,
    )

    # Sort: priority corridors first, then paired, then by km
    priority = {c: i for i, c in enumerate(PRIORITY_CORRIDORS)}
    rows.sort(
        key=lambda r: (
            0 if r["paired"] else 1,
            priority.get(r["corridor_id"], 99),
            r["km_start"],
        )
    )

    report = _json_safe(
        {
            "schema_version": "lfi_epr_v0",
            "generated_at": _utc_now(),
            "formula": "EPR = mean(TI_athlete) / mean(TI_elite) on course_km window",
            "interpretation": {
                "epr_gt_1": "athlete pays more terrain tax than reference",
                "epr_lt_1": "athlete more terrain-efficient than reference",
                "parity_band": "0.95–1.05",
            },
            "athlete": {
                "donor_id": args.athlete_donor,
                "activity_id": args.athlete_activity,
                "path": str(athlete_path.relative_to(BASE_DIR)),
                "course_km": [
                    float(athlete["course_km"].min()),
                    float(athlete["course_km"].max()),
                ],
            },
            "elite": {
                "donor_id": args.elite_donor,
                "activity_id": args.elite_activity,
                "path": str(elite_path.relative_to(BASE_DIR)),
                "course_km": [float(elite["course_km"].min()), float(elite["course_km"].max())],
            },
            "axis_note": (
                "LFI course_km is FIT stream distance per course_project STREAM_DISTANCE_RACES. "
                "Sub-corridor windows calibrated from Subject_A LFI_20260606 — cross-edition pairing "
                "assumes comparable stream axis on same race tread."
            ),
            "corridors": rows,
            "paired_count": sum(1 for r in rows if r["paired"]),
        }
    )

    json_path = args.output_json if args.output_json.is_absolute() else BASE_DIR / args.output_json
    csv_path = args.output_csv if args.output_csv.is_absolute() else BASE_DIR / args.output_csv
    png_path = args.output_png if args.output_png.is_absolute() else BASE_DIR / args.output_png
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    flat = []
    for r in rows:
        flat.append(
            {
                "corridor_id": r["corridor_id"],
                "label": r["label"],
                "km_start": r["km_start"],
                "km_end": r["km_end"],
                "epr_mean": r["epr_mean"],
                "epr_median": r["epr_median"],
                "interpretation": r["interpretation"],
                "paired": r["paired"],
                "athlete_n": r["athlete"]["n_samples"],
                "elite_n": r["elite"]["n_samples"],
                "athlete_mean_ti": r["athlete"]["mean_ti"],
                "elite_mean_ti": r["elite"]["mean_ti"],
            }
        )
    pd.DataFrame(flat).to_csv(csv_path, index=False)

    if not args.no_png:
        render_epr_chart(rows, png_path)
        report["output_png"] = str(png_path.relative_to(BASE_DIR))

    report["output_json"] = str(json_path.relative_to(BASE_DIR))
    report["output_csv"] = str(csv_path.relative_to(BASE_DIR))
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"OK LFI EPR — {report['paired_count']}/{len(rows)} corridors paired")
    print(f"  athlete km {report['athlete']['course_km'][0]:.2f}–{report['athlete']['course_km'][1]:.2f}")
    print(f"  elite   km {report['elite']['course_km'][0]:.2f}–{report['elite']['course_km'][1]:.2f}")
    print()
    for r in rows:
        if not r["paired"]:
            print(f"  SKIP {r['corridor_id']}: insufficient overlap/samples")
            continue
        flag = "↑ tax" if r["epr_mean"] > 1.05 else "↓ eff" if r["epr_mean"] < 0.95 else "≈ parity"
        print(
            f"  {r['corridor_id']:28s} km {r['km_start']:5.1f}–{r['km_end']:5.1f}  "
            f"EPR={r['epr_mean']:.3f}  ({flag})  "
            f"n={r['athlete']['n_samples']}/{r['elite']['n_samples']}"
        )
    print()
    print(f"Report → {json_path}")
    print(f"CSV    → {csv_path}")
    if not args.no_png:
        print(f"PNG    → {png_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
