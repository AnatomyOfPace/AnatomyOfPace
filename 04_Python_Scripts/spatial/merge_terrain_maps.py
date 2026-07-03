#!/usr/bin/env python3
"""
Merge locked sector terrain maps into one full-course operator-gold map.

Concatenates hitl.operator_gold_spans[] from sector JSON files in course-km order,
tags each span with source_sector, validates seam continuity, and writes a lean
unified map (gold spans + corridor metadata — no GMM segment bulk).

Usage (from repo root):
    python3 04_Python_Scripts/spatial/merge_terrain_maps.py \\
        --sector config/spatial_terrain_map_sut43_start.json:0.5:8.0 \\
        --sector config/spatial_terrain_map_sut43_bridge.json:8.0:22.0 \\
        --sector config/spatial_terrain_map_sut43_upstream.json:22.0:29.0 \\
        --sector config/spatial_terrain_map_sut43.json:29.0:41.0 \\
        --output config/spatial_terrain_map_sut43_full.json

SUT_43 finish band (km 41.0–42.5): include
`config/spatial_terrain_map_sut43_finish.json` as fifth --sector when merging full course.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.gold_training_common import span_km_bounds
from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.validation_dashboard import operator_gold_spans

BASE_DIR = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class SectorSpec:
    path: Path
    km_lo: float
    km_hi: float

    @property
    def sector_id(self) -> str:
        return self.path.stem.replace("spatial_terrain_map_sut43_", "").replace("spatial_terrain_map_sut43", "gramstad_band")


def parse_sector(value: str) -> SectorSpec:
    parts = value.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(f"Expected path:km_lo:km_hi, got {value!r}")
    path = Path(parts[0])
    return SectorSpec(path=path, km_lo=float(parts[1]), km_hi=float(parts[2]))


def spans_in_window(spans: list[dict[str, Any]], km_lo: float, km_hi: float) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for span in spans:
        s0, s1 = span_km_bounds(span)
        if s1 <= km_lo + 1e-9 or s0 >= km_hi - 1e-9:
            continue
        kept.append(span)
    return sorted(kept, key=lambda s: span_km_bounds(s)[0])


def gold_to_segment(span: dict[str, Any]) -> dict[str, Any]:
    s0, s1 = span_km_bounds(span)
    return {
        "course_km_start": s0,
        "course_km_end": s1,
        "course_m_start": round(s0 * 1000.0, 3),
        "course_m_end": round(s1 * 1000.0, 3),
        "surface_class": span.get("surface_class"),
        "friction_tier": span.get("friction_tier"),
        "source": "operator_gold",
    }


def check_seams(
    merged: list[dict[str, Any]],
    boundaries: list[float],
) -> list[dict[str, Any]]:
    """Return seam continuity report at sector boundaries."""
    reports: list[dict[str, Any]] = []
    for boundary in boundaries:
        before = [s for s in merged if abs(span_km_bounds(s)[1] - boundary) < 1e-6]
        after = [s for s in merged if abs(span_km_bounds(s)[0] - boundary) < 1e-6]
        gap = None
        if before and after:
            gap = span_km_bounds(after[0])[0] - span_km_bounds(before[-1])[1]
        entry: dict[str, Any] = {
            "boundary_km": boundary,
            "upstream_end": None,
            "downstream_start": None,
            "surface_continuous": False,
            "friction_continuous": False,
            "gap_km": gap,
        }
        if before:
            b = before[-1]
            entry["upstream_end"] = {
                "surface_class": b.get("surface_class"),
                "friction_tier": b.get("friction_tier"),
                "source_sector": b.get("source_sector"),
            }
        if after:
            a = after[0]
            entry["downstream_start"] = {
                "surface_class": a.get("surface_class"),
                "friction_tier": a.get("friction_tier"),
                "source_sector": a.get("source_sector"),
            }
        if before and after:
            entry["surface_continuous"] = before[-1].get("surface_class") == after[0].get("surface_class")
            entry["friction_continuous"] = before[-1].get("friction_tier") == after[0].get("friction_tier")
        reports.append(entry)
    return reports


def check_coverage(spans: list[dict[str, Any]], km_lo: float, km_hi: float) -> list[tuple[float, float]]:
    gaps: list[tuple[float, float]] = []
    cursor = km_lo
    for span in spans:
        s0, s1 = span_km_bounds(span)
        if s0 > cursor + 1e-6:
            gaps.append((cursor, s0))
        cursor = max(cursor, s1)
    if cursor < km_hi - 1e-6:
        gaps.append((cursor, km_hi))
    return gaps


def merge_maps(
    sectors: list[SectorSpec],
    *,
    km_lo: float | None = None,
    km_hi: float | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not sectors:
        raise ValueError("At least one --sector required")
    sectors = sorted(sectors, key=lambda s: s.km_lo)
    course_lo = km_lo if km_lo is not None else sectors[0].km_lo
    course_hi = km_hi if km_hi is not None else sectors[-1].km_hi

    merged_spans: list[dict[str, Any]] = []
    source_sectors: list[dict[str, Any]] = []
    boundaries = [s.km_lo for s in sectors[1:]]

    for spec in sectors:
        terrain_map = load_terrain_map(spec.path)
        corridor = terrain_map.get("corridor", {})
        sector_id = corridor.get("sector_id") or spec.sector_id
        gold = spans_in_window(operator_gold_spans(terrain_map), spec.km_lo, spec.km_hi)
        if not gold:
            raise ValueError(f"No operator_gold_spans in {spec.path} for km {spec.km_lo}–{spec.km_hi}")
        tagged = []
        for span in gold:
            entry = dict(span)
            entry["source_sector"] = sector_id
            tagged.append(entry)
        merged_spans.extend(tagged)
        source_sectors.append(
            {
                "sector_id": sector_id,
                "terrain_map": str(spec.path),
                "km_start": spec.km_lo,
                "km_end": spec.km_hi,
                "span_count": len(gold),
                "hitl_status": terrain_map.get("hitl", {}).get("status"),
            }
        )

    merged_spans.sort(key=lambda s: span_km_bounds(s)[0])
    overlaps: list[str] = []
    for i in range(len(merged_spans) - 1):
        _, e0 = span_km_bounds(merged_spans[i])
        s1, _ = span_km_bounds(merged_spans[i + 1])
        if e0 > s1 + 1e-6:
            overlaps.append(f"overlap @ {s1:.3f}–{e0:.3f}")
        elif s1 > e0 + 1e-6:
            overlaps.append(f"gap @ {e0:.3f}–{s1:.3f}")

    seam_reports = check_seams(merged_spans, boundaries)
    coverage_gaps = check_coverage(merged_spans, course_lo, course_hi)

    first_map = load_terrain_map(sectors[0].path)
    corridor = dict(first_map.get("corridor", {}))
    corridor.update(
        {
            "corridor_id": "sut43_terrain_ontology",
            "sector_id": "sut43_full_course",
            "race_id": "SUT_43",
            "km_start": course_lo,
            "km_end": course_hi,
            "sector_viewport_km_end": course_hi + 0.5,
            "finish_km": 43.0,
            "full_course_window": [0.5, 42.5],
            "course_axis": "stream_distance",
            "gpx_reference": "COURSE_SUT43_official_2027.gpx",
            "notes": (
                f"Unified operator-gold map km {course_lo}–{course_hi} merged from "
                f"{len(sectors)} locked sector maps."
            ),
            "source_sectors": source_sectors,
        }
    )

    unified: dict[str, Any] = {
        "schema_version": "spatial_terrain_map_v0",
        "ontology_version": first_map.get("ontology_version", "s6_v0"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corridor": corridor,
        "segments": [gold_to_segment(s) for s in merged_spans],
        "hitl": {
            "status": "locked",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "reviewer": "merge_terrain_maps.py",
            "authority": "operator_gold",
            "operator_gold_spans": merged_spans,
            "notes": (
                f"Full-course operator gold km {course_lo}–{course_hi} — "
                f"{len(merged_spans)} spans from {len(sectors)} sector maps."
            ),
        },
    }

    report = {
        "span_count": len(merged_spans),
        "sector_span_counts": {s["sector_id"]: s["span_count"] for s in source_sectors},
        "km_start": course_lo,
        "km_end": course_hi,
        "coverage_gaps": [{"km_start": a, "km_end": b} for a, b in coverage_gaps],
        "overlaps": overlaps,
        "seam_checks": seam_reports,
    }
    return unified, report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge sector terrain maps into unified operator-gold map.")
    parser.add_argument(
        "--sector",
        type=parse_sector,
        action="append",
        required=True,
        metavar="PATH:KM_LO:KM_HI",
        help="Sector terrain map and inclusive km bounds (repeatable, course order)",
    )
    parser.add_argument("--km-start", type=float, default=None, help="Override merged corridor km_start")
    parser.add_argument("--km-end", type=float, default=None, help="Override merged corridor km_end")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, default=None, help="Write merge validation report JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    for spec in args.sector:
        if not spec.path.exists():
            print(f"Terrain map not found: {spec.path}", file=sys.stderr)
            return 1

    unified, report = merge_maps(args.sector, km_lo=args.km_start, km_hi=args.km_end)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(unified, indent=2) + "\n", encoding="utf-8")

    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {args.output} — {report['span_count']} operator gold spans")
    if report["coverage_gaps"]:
        print(f"  WARNING: coverage gaps: {report['coverage_gaps']}", file=sys.stderr)
    if report["overlaps"]:
        print(f"  WARNING: overlaps: {report['overlaps']}", file=sys.stderr)
    for seam in report["seam_checks"]:
        b = seam["boundary_km"]
        ok = seam["surface_continuous"] and seam["friction_continuous"] and seam.get("gap_km", 0) == 0
        flag = "OK" if ok else "FAIL"
        up = seam.get("upstream_end") or {}
        dn = seam.get("downstream_start") or {}
        print(
            f"  seam @ {b}: {flag} "
            f"{up.get('surface_class')}/{up.get('friction_tier')} → "
            f"{dn.get('surface_class')}/{dn.get('friction_tier')}"
        )
    return 0 if not report["coverage_gaps"] and not report["overlaps"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
