#!/usr/bin/env python3
"""
HITL manual-override consistency check against consensus NTI telemetry.

Compares hitl.manual_overrides[] surface classes to cross-athlete NTI in the
panel, flagging high-variance spans (median σ ≥ threshold or >50% hot metres).
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

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "04_Python_Scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "04_Python_Scripts"))

from spatial.surface_ontology import SURFACE_CLASS_SPECS, expected_ti_band
from spatial.terrain_map_gen import compute_nti

DEFAULT_VARIANCE_THRESHOLD = 0.30
MARGINAL_BAND_PAD = 0.15
MIN_GAP_SPAN_KM = 0.3
MIN_VARIANCE_GAP_KM = 0.1
VARIANCE_GAP_MERGE_TOLERANCE_KM = 0.15
VARIANCE_GAP_REASON = (
    "inter-athlete NTI σ elevated (median σ ≥ threshold or >50% hot metres) — "
    "operator guidance deferred pending GPS revisit or second-athlete agreement"
)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def per_metre_nti_stats(
    panel: pd.DataFrame,
    *,
    session_type: str | None = "race",
) -> pd.DataFrame:
    work = panel.copy()
    if session_type and "session_type" in work.columns:
        work = work[work["session_type"] == session_type]
    work["nti"] = compute_nti(work)
    agg = work.groupby("course_m", as_index=False).agg(
        nti_mean=("nti", "mean"),
        nti_median=("nti", "median"),
        nti_std=("nti", "std"),
        course_km=("course_km", "first"),
        n_athletes=("donor_id", "nunique"),
    )
    agg["nti_std"] = agg["nti_std"].fillna(0.0)
    return agg


def span_mask(agg: pd.DataFrame, km_start: float, km_end: float) -> pd.Series:
    return (agg["course_km"] >= km_start) & (agg["course_km"] < km_end)


def classify_nti_vs_band(
    mean_nti: float,
    surface_class: str,
    *,
    marginal_pad: float = MARGINAL_BAND_PAD,
) -> str:
    lo, hi = expected_ti_band(surface_class)
    if lo <= mean_nti <= hi:
        return "consistent"
    if (lo - marginal_pad) <= mean_nti < lo or hi < mean_nti <= (hi + marginal_pad):
        return "marginal"
    return "inconsistent"


def analyze_hitl_span(
    override: dict[str, Any],
    agg: pd.DataFrame,
    *,
    variance_threshold: float,
) -> dict[str, Any]:
    km_start = float(override["course_km_start"])
    km_end = float(override["course_km_end"])
    surface_class = str(override["surface_class"])
    mask = span_mask(agg, km_start, km_end)
    span = agg.loc[mask]
    n_metres = int(len(span))

    spec = SURFACE_CLASS_SPECS[surface_class]
    lo, hi = spec.ti_band
    mode = override.get("mode") or ("lock" if override.get("locked") else "guidance")
    locked = bool(override.get("locked", False)) or mode == "lock"

    if n_metres == 0:
        return {
            "course_km_start": km_start,
            "course_km_end": km_end,
            "surface_class": surface_class,
            "mode": mode,
            "locked": locked,
            "n_metres": 0,
            "mean_consensus_nti": None,
            "median_nti_std": None,
            "mean_nti_std": None,
            "pct_metres_high_variance": None,
            "expected_ti_band": [lo, hi],
            "ti_target": spec.ti_target,
            "high_variance": True,
            "classification": "excluded (high σ)",
            "reason": "no panel metres in span",
        }

    hot = (span["nti_std"] >= variance_threshold) & (span["n_athletes"] >= 2)
    pct_hot = float(hot.mean()) * 100.0
    median_std = float(span["nti_std"].median())
    high_variance = median_std >= variance_threshold or pct_hot > 50.0

    mean_consensus = float(span["nti_median"].mean())

    if high_variance:
        classification = "excluded (high σ)"
    else:
        classification = classify_nti_vs_band(mean_consensus, surface_class)

    return {
        "course_km_start": km_start,
        "course_km_end": km_end,
        "surface_class": surface_class,
        "mode": mode,
        "locked": locked,
        "n_metres": n_metres,
        "mean_consensus_nti": round(mean_consensus, 3),
        "median_nti_std": round(median_std, 3),
        "mean_nti_std": round(float(span["nti_std"].mean()), 3),
        "pct_metres_high_variance": round(pct_hot, 1),
        "expected_ti_band": [lo, hi],
        "ti_target": spec.ti_target,
        "high_variance": high_variance,
        "classification": classification,
        "delta_from_target": round(mean_consensus - spec.ti_target, 3),
    }


def _merge_km_intervals(
    intervals: list[tuple[float, float]],
    *,
    tolerance_km: float,
) -> list[tuple[float, float]]:
    if not intervals:
        return []
    rows = sorted(intervals, key=lambda t: t[0])
    merged: list[tuple[float, float]] = [rows[0]]
    for start, end in rows[1:]:
        prev_start, prev_end = merged[-1]
        if start - prev_end <= tolerance_km:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def subtract_km_intervals(
    km_start: float,
    km_end: float,
    blockers: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Return sub-intervals of [km_start, km_end) not covered by blockers."""
    if km_end <= km_start:
        return []
    blockers = _merge_km_intervals(blockers, tolerance_km=0.0)
    kept: list[tuple[float, float]] = []
    cursor = km_start
    for b0, b1 in blockers:
        if b1 <= cursor or b0 >= km_end:
            continue
        if b0 > cursor:
            kept.append((cursor, min(b0, km_end)))
        cursor = max(cursor, b1)
    if cursor < km_end:
        kept.append((cursor, km_end))
    return [(s, e) for s, e in kept if e - s > 1e-6]


def overlap_km_intervals(
    km_start: float,
    km_end: float,
    blockers: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Return sub-intervals of [km_start, km_end) covered by blockers."""
    overlaps: list[tuple[float, float]] = []
    for b0, b1 in blockers:
        o0, o1 = max(km_start, b0), min(km_end, b1)
        if o1 > o0:
            overlaps.append((o0, o1))
    return _merge_km_intervals(overlaps, tolerance_km=0.0)


def compute_variance_gaps(
    agg: pd.DataFrame,
    *,
    km_start: float,
    km_end: float,
    variance_threshold: float = DEFAULT_VARIANCE_THRESHOLD,
    min_span_km: float = MIN_VARIANCE_GAP_KM,
    merge_tolerance_km: float = VARIANCE_GAP_MERGE_TOLERANCE_KM,
) -> list[dict[str, Any]]:
    """
    Aggregate contiguous high-variance spans on the panel axis.

    A span qualifies when analyze_hitl_span reports high_variance (median σ ≥
    threshold or >50% hot metres). Greedy per-metre growth, then merge nearby spans.
    """
    sub = agg[(agg["course_km"] >= km_start) & (agg["course_km"] < km_end)].sort_values(
        "course_km"
    )
    if sub.empty:
        return []

    kms = sub["course_km"].tolist()
    raw: list[tuple[float, float, dict[str, Any]]] = []
    i = 0
    while i < len(kms):
        start = kms[i]
        j = i
        last_end: float | None = None
        last_row: dict[str, Any] | None = None
        while j < len(kms) and kms[j] < km_end:
            end = kms[j] + 0.001
            row = analyze_hitl_span(
                {"course_km_start": start, "course_km_end": end, "surface_class": "S2"},
                agg,
                variance_threshold=variance_threshold,
            )
            if row["high_variance"]:
                last_end = end
                last_row = row
                j += 1
            else:
                break
        if last_end is not None and (last_end - start) >= min_span_km and last_row is not None:
            raw.append((start, last_end, last_row))
            while i < len(kms) and kms[i] < last_end:
                i += 1
        else:
            i += 1

    merged: list[tuple[float, float, dict[str, Any]]] = []
    for start, end, row in raw:
        if merged and start - merged[-1][1] <= merge_tolerance_km:
            prev_start, _, _ = merged[-1]
            combined = analyze_hitl_span(
                {"course_km_start": prev_start, "course_km_end": end, "surface_class": "S2"},
                agg,
                variance_threshold=variance_threshold,
            )
            if combined["high_variance"]:
                merged[-1] = (prev_start, end, combined)
                continue
        merged.append((start, end, row))

    gaps: list[dict[str, Any]] = []
    for start, end, row in merged:
        gaps.append(
            {
                "course_km_start": round(start, 3),
                "course_km_end": round(end, 3),
                "median_sigma": row["median_nti_std"],
                "pct_metres_high_variance": row["pct_metres_high_variance"],
                "reason": VARIANCE_GAP_REASON,
            }
        )
    return gaps


def defer_manual_overrides(
    overrides: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    agg: pd.DataFrame,
    *,
    variance_threshold: float = DEFAULT_VARIANCE_THRESHOLD,
) -> list[dict[str, Any]]:
    """
    Trim or defer guidance overrides that overlap variance gaps.

    Full-span high σ → single entry with deferred:true. Partial overlap → active
    fragments on non-gap km plus deferred fragments on gap overlap (audit trail).
    Lock-mode overrides are never deferred.
    """
    gap_intervals = [(float(g["course_km_start"]), float(g["course_km_end"])) for g in gaps]
    if not gap_intervals:
        return [dict(ov) for ov in overrides]

    result: list[dict[str, Any]] = []
    for ov in overrides:
        ov_copy = dict(ov)
        mode = ov_copy.get("mode") or ("lock" if ov_copy.get("locked") else "guidance")
        km0 = float(ov_copy["course_km_start"])
        km1 = float(ov_copy["course_km_end"])
        if mode == "lock":
            result.append(ov_copy)
            continue

        span_row = analyze_hitl_span(ov_copy, agg, variance_threshold=variance_threshold)
        if span_row["high_variance"]:
            ov_copy["deferred"] = True
            ov_copy["defer_reason"] = VARIANCE_GAP_REASON
            result.append(ov_copy)
            continue

        kept = subtract_km_intervals(km0, km1, gap_intervals)
        overlaps = overlap_km_intervals(km0, km1, gap_intervals)
        if not overlaps:
            result.append(ov_copy)
            continue

        for o0, o1 in overlaps:
            if o1 - o0 < 0.01:
                continue
            deferred = dict(ov_copy)
            deferred["course_km_start"] = round(o0, 3)
            deferred["course_km_end"] = round(o1, 3)
            deferred["deferred"] = True
            deferred["defer_reason"] = VARIANCE_GAP_REASON
            result.append(deferred)
        for k0, k1 in kept:
            if k1 - k0 < 0.01:
                continue
            active = dict(ov_copy)
            active["course_km_start"] = round(k0, 3)
            active["course_km_end"] = round(k1, 3)
            active.pop("deferred", None)
            active.pop("defer_reason", None)
            result.append(active)
    return result


def apply_variance_gaps_to_terrain_map(
    terrain_map: dict[str, Any],
    panel: pd.DataFrame,
    *,
    km_start: float,
    km_end: float,
    variance_threshold: float = DEFAULT_VARIANCE_THRESHOLD,
) -> dict[str, Any]:
    """Compute variance_gaps[] and defer/trim manual_overrides in-place copy."""
    updated = dict(terrain_map)
    hitl = dict(updated.get("hitl") or {})
    agg = per_metre_nti_stats(panel)
    gaps = compute_variance_gaps(
        agg,
        km_start=km_start,
        km_end=km_end,
        variance_threshold=variance_threshold,
    )
    overrides = hitl.get("manual_overrides") or []
    hitl["variance_gaps"] = gaps
    hitl["manual_overrides"] = defer_manual_overrides(
        overrides, gaps, agg, variance_threshold=variance_threshold
    )
    updated["hitl"] = hitl
    return updated


def merge_cluster_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not segments:
        return []
    rows = sorted(segments, key=lambda s: float(s["course_km_start"]))
    merged: list[dict[str, Any]] = [dict(rows[0])]
    for seg in rows[1:]:
        prev = merged[-1]
        if (
            seg.get("surface_class") == prev.get("surface_class")
            and float(seg["course_km_start"]) <= float(prev["course_km_end"]) + 0.05
        ):
            prev["course_km_end"] = max(float(prev["course_km_end"]), float(seg["course_km_end"]))
            prev["course_m_end"] = max(float(prev["course_m_end"]), float(seg["course_m_end"]))
        else:
            merged.append(dict(seg))
    return merged


def gaps_between_hitl(
    km_lo: float,
    km_hi: float,
    overrides: list[dict[str, Any]],
) -> list[tuple[float, float]]:
    spans = sorted(
        (float(o["course_km_start"]), float(o["course_km_end"])) for o in overrides
    )
    gaps: list[tuple[float, float]] = []
    cursor = km_lo
    for start, end in spans:
        if start > cursor + 0.01:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < km_hi - 0.01:
        gaps.append((cursor, km_hi))
    return gaps


def dominant_cluster_class(
    segments: list[dict[str, Any]],
    km_start: float,
    km_end: float,
) -> tuple[str | None, float]:
    """Length-weighted modal S-class from cluster segments overlapping [km_start, km_end)."""
    weights: dict[str, float] = {}
    for seg in segments:
        s0 = float(seg["course_km_start"])
        s1 = float(seg["course_km_end"])
        o0, o1 = max(s0, km_start), min(s1, km_end)
        span = o1 - o0
        if span <= 0:
            continue
        cls = str(seg["surface_class"])
        weights[cls] = weights.get(cls, 0.0) + span
    if not weights:
        return None, 0.0
    best = max(weights.items(), key=lambda kv: kv[1])
    total = sum(weights.values())
    return best[0], best[1] / total if total > 0 else 0.0


def resolve_panel_km_range(
    terrain_map: dict[str, Any],
    agg: pd.DataFrame,
) -> tuple[float, float]:
    """Use panel bounds when corridor metadata is off-axis (e.g. SUT_160 on SUT_43 panel)."""
    p_lo = float(agg["course_km"].min())
    p_hi = float(agg["course_km"].max())
    corridor = terrain_map.get("corridor") or {}
    c_lo, c_hi = corridor.get("km_start"), corridor.get("km_end")
    if c_lo is not None and c_hi is not None:
        c_lo, c_hi = float(c_lo), float(c_hi)
        if c_lo <= p_hi + 0.5 and c_hi >= p_lo - 0.5:
            return max(c_lo, p_lo), min(c_hi, p_hi)
    return p_lo, p_hi


def analyze_cluster_gaps(
    terrain_map: dict[str, Any],
    agg: pd.DataFrame,
    overrides: list[dict[str, Any]],
    *,
    variance_threshold: float,
    min_span_km: float = MIN_GAP_SPAN_KM,
) -> list[dict[str, Any]]:
    km_lo, km_hi = resolve_panel_km_range(terrain_map, agg)
    gaps = gaps_between_hitl(km_lo, km_hi, overrides)
    cluster_segs = [
        s for s in terrain_map.get("segments", []) if s.get("source") in ("cluster", "gmm")
    ]
    results: list[dict[str, Any]] = []
    for gap_start, gap_end in gaps:
        if (gap_end - gap_start) < min_span_km:
            continue
        dominant, dominant_frac = dominant_cluster_class(cluster_segs, gap_start, gap_end)
        if dominant is None:
            continue
        pseudo = {
            "course_km_start": gap_start,
            "course_km_end": gap_end,
            "surface_class": dominant,
            "mode": "cluster_draft",
            "locked": False,
        }
        row = analyze_hitl_span(pseudo, agg, variance_threshold=variance_threshold)
        row["source"] = "cluster"
        row["dominant_cluster_fraction"] = round(dominant_frac, 3)
        row["note"] = "non-HITL gap; GMM class is length-weighted modal over micro-segments"
        results.append(row)
    return results


def markdown_table(rows: list[dict[str, Any]], *, title: str) -> str:
    lines = [
        f"### {title}",
        "",
        "| km span | S-class | mean NTI | med σ | % hot m | band | classification |",
        "|---------|---------|----------|-------|---------|------|----------------|",
    ]
    for r in rows:
        span = f"{r['course_km_start']:.1f}–{r['course_km_end']:.1f}"
        band = r.get("expected_ti_band")
        band_s = f"{band[0]:.2f}–{band[1]:.2f}" if band else "—"
        mean_nti = r.get("mean_consensus_nti")
        mean_s = f"{mean_nti:.3f}" if mean_nti is not None else "—"
        med_std = r.get("median_nti_std")
        std_s = f"{med_std:.3f}" if med_std is not None else "—"
        pct = r.get("pct_metres_high_variance")
        pct_s = f"{pct:.1f}%" if pct is not None else "—"
        lines.append(
            f"| {span} | {r['surface_class']} | {mean_s} | {std_s} | {pct_s} | {band_s} | {r['classification']} |"
        )
    return "\n".join(lines)


def run_consistency_check(
    terrain_map_path: Path,
    panel_path: Path,
    output_path: Path,
    *,
    variance_threshold: float = DEFAULT_VARIANCE_THRESHOLD,
    include_gaps: bool = True,
) -> dict[str, Any]:
    terrain_map = _load_json(terrain_map_path)
    panel = pd.read_parquet(panel_path)
    overrides = terrain_map.get("hitl", {}).get("manual_overrides") or []
    agg = per_metre_nti_stats(panel)

    hitl_rows = [
        analyze_hitl_span(ov, agg, variance_threshold=variance_threshold) for ov in overrides
    ]
    gap_rows: list[dict[str, Any]] = []
    if include_gaps:
        gap_rows = analyze_cluster_gaps(
            terrain_map, agg, overrides, variance_threshold=variance_threshold
        )

    summary = {
        "consistent": [r for r in hitl_rows if r["classification"] == "consistent"],
        "marginal": [r for r in hitl_rows if r["classification"] == "marginal"],
        "inconsistent": [r for r in hitl_rows if r["classification"] == "inconsistent"],
        "excluded_high_variance": [
            r for r in hitl_rows if r["classification"] == "excluded (high σ)"
        ],
    }

    report: dict[str, Any] = {
        "schema_version": "hitl_nti_consistency_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "terrain_map": str(terrain_map_path),
        "panel": str(panel_path),
        "variance_threshold": variance_threshold,
        "donors": sorted(panel["donor_id"].unique().tolist()),
        "panel_km_range": [
            float(panel["course_km"].min()),
            float(panel["course_km"].max()),
        ],
        "hitl_spans": hitl_rows,
        "cluster_gap_spans": gap_rows,
        "summary": {
            "n_hitl": len(hitl_rows),
            "n_consistent": len(summary["consistent"]),
            "n_marginal": len(summary["marginal"]),
            "n_inconsistent": len(summary["inconsistent"]),
            "n_excluded_high_variance": len(summary["excluded_high_variance"]),
            "n_cluster_gaps_checked": len(gap_rows),
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="HITL vs NTI consistency check")
    parser.add_argument(
        "--terrain-map",
        type=Path,
        default=_REPO_ROOT / "config/spatial_terrain_map_sut43.json",
    )
    parser.add_argument(
        "--panel",
        type=Path,
        default=_REPO_ROOT / "03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_REPO_ROOT
        / "03_Processed_Data/spatial/sut43_terrain_ontology/hitl_nti_consistency.json",
    )
    parser.add_argument(
        "--variance-threshold",
        type=float,
        default=DEFAULT_VARIANCE_THRESHOLD,
    )
    parser.add_argument("--no-gaps", action="store_true")
    parser.add_argument(
        "--apply-gaps",
        action="store_true",
        help="Write hitl.variance_gaps[] and defer/trim manual_overrides in --terrain-map",
    )
    parser.add_argument(
        "--km-start",
        type=float,
        default=None,
        help="Variance-gap scan start km (default: panel min)",
    )
    parser.add_argument(
        "--km-end",
        type=float,
        default=None,
        help="Variance-gap scan end km (default: panel max)",
    )
    args = parser.parse_args()

    if args.apply_gaps:
        terrain_map = _load_json(args.terrain_map)
        panel = pd.read_parquet(args.panel)
        agg = per_metre_nti_stats(panel)
        km_lo = float(args.km_start) if args.km_start is not None else float(agg["course_km"].min())
        km_hi = float(args.km_end) if args.km_end is not None else float(agg["course_km"].max())
        updated = apply_variance_gaps_to_terrain_map(
            terrain_map,
            panel,
            km_start=km_lo,
            km_end=km_hi,
            variance_threshold=args.variance_threshold,
        )
        with args.terrain_map.open("w", encoding="utf-8") as fh:
            json.dump(updated, fh, indent=2)
            fh.write("\n")
        gaps = updated.get("hitl", {}).get("variance_gaps") or []
        deferred = [
            ov
            for ov in updated.get("hitl", {}).get("manual_overrides") or []
            if ov.get("deferred")
        ]
        print(f"Applied {len(gaps)} variance gap spans ({km_lo:.1f}–{km_hi:.1f} km)")
        for g in gaps:
            print(
                f"  gap {g['course_km_start']:.3f}–{g['course_km_end']:.3f} "
                f"medσ={g['median_sigma']:.3f}"
            )
        print(f"Deferred/trimmed {len(deferred)} override fragment(s)")
        for ov in deferred:
            print(
                f"  deferred {ov['course_km_start']:.3f}–{ov['course_km_end']:.3f} "
                f"{ov.get('surface_class')}"
            )
        print(f"Wrote {args.terrain_map}")
        return

    report = run_consistency_check(
        args.terrain_map,
        args.panel,
        args.output,
        variance_threshold=args.variance_threshold,
        include_gaps=not args.no_gaps,
    )

    print(markdown_table(report["hitl_spans"], title="HITL manual overrides"))
    if report["cluster_gap_spans"]:
        print()
        print(
            markdown_table(
                report["cluster_gap_spans"][:15],
                title="Cluster draft spans in non-HITL gaps (first 15)",
            )
        )
        if len(report["cluster_gap_spans"]) > 15:
            print(f"\n… {len(report['cluster_gap_spans']) - 15} more gap spans in JSON.")

    s = report["summary"]
    print(
        f"\nSummary: {s['n_consistent']} consistent, {s['n_marginal']} marginal, "
        f"{s['n_inconsistent']} inconsistent, {s['n_excluded_high_variance']} excluded (high σ)"
    )
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
