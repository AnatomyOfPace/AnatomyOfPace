#!/usr/bin/env python3
"""
Portfolio audit — operator gold coverage and HITL status across all terrain maps.

Use before publication or TRF re-runs when map overlays must match locked gold.

Usage (repo root):
    python3 04_Python_Scripts/spatial/audit_operator_gold_portfolio.py
    python3 04_Python_Scripts/spatial/audit_operator_gold_portfolio.py --json 03_Processed_Data/spatial/gold_portfolio_audit.json
    python3 04_Python_Scripts/spatial/audit_operator_gold_portfolio.py --fail-on-gaps
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.gold_training_common import resolve_gold_training_defaults  # noqa: E402
from spatial.report_gold_coverage import report_coverage  # noqa: E402
from spatial.spatial_hitl_overlay import load_terrain_map  # noqa: E402
from spatial.validation_dashboard import is_map_first_operator_gold, operator_gold_spans  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"


def _terrain_map_paths(config_dir: Path) -> list[Path]:
    paths = sorted(config_dir.glob("spatial_terrain_map_*.json"))
    return [p for p in paths if p.name != "spatial_terrain_map.schema.json"]


def _gold_extent(spans: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    if not spans:
        return None, None
    starts = [float(s.get("course_km_start", s.get("course_m_start", 0) / 1000.0)) for s in spans]
    ends = [float(s.get("course_km_end", s.get("course_m_end", 0) / 1000.0)) for s in spans]
    return min(starts), max(ends)


def _span_at_km(spans: list[dict[str, Any]], km: float) -> dict[str, Any] | None:
    for span in spans:
        s0 = float(span.get("course_km_start", span.get("course_m_start", 0) / 1000.0))
        s1 = float(span.get("course_km_end", span.get("course_m_end", s0) / 1000.0))
        if s0 - 1e-9 <= km < s1 + 1e-9:
            return span
    return None


def audit_map(path: Path) -> dict[str, Any]:
    tmap = load_terrain_map(path)
    corridor = tmap.get("corridor") or {}
    hitl = tmap.get("hitl") or {}
    spans = operator_gold_spans(tmap)
    gold_lo, gold_hi = _gold_extent(spans)
    km_start = float(corridor.get("km_start") or 0.0)
    km_end = float(corridor.get("km_end") or 0.0)

    resolved = resolve_gold_training_defaults(path)
    panel_path = resolved.get("panel") if resolved else None
    if panel_path is not None and not Path(panel_path).is_absolute():
        panel_path = BASE_DIR / panel_path

    coverage: dict[str, Any] | None = None
    if panel_path is not None and Path(panel_path).exists() and km_end > km_start + 1e-6:
        coverage = report_coverage(path, panel_path=Path(panel_path), km_start=km_start, km_end=km_end)

    window_lo = km_start if km_end > km_start else (gold_lo or 0.0)
    window_hi = km_end if km_end > km_start else (gold_hi or 0.0)
    entry_span = _span_at_km(spans, window_lo) if window_hi > window_lo else None

    missing_tier = sum(
        1 for s in spans if str(s.get("surface_class", "")).strip() and not str(s.get("friction_tier", "")).strip()
    )

    row: dict[str, Any] = {
        "terrain_map": str(path.relative_to(BASE_DIR)),
        "race_id": str(corridor.get("race_id") or path.stem.replace("spatial_terrain_map_", "")),
        "sector_id": corridor.get("sector_id"),
        "hitl_status": hitl.get("status", "unknown"),
        "operator_gold_spans": len(spans),
        "gold_km_start": gold_lo,
        "gold_km_end": gold_hi,
        "corridor_km_start": km_start,
        "corridor_km_end": km_end,
        "spans_missing_friction_tier": missing_tier,
        "first_span_at_corridor_start": None,
        "labeled_pct": None,
        "unlabeled_metres": None,
        "gap_count": None,
        "panel": str(panel_path.relative_to(BASE_DIR)) if panel_path and Path(panel_path).exists() else None,
        "needs_review": False,
        "review_reasons": [],
    }

    if entry_span:
        row["first_span_at_corridor_start"] = {
            "km_start": float(entry_span.get("course_km_start", 0)),
            "km_end": float(entry_span.get("course_km_end", 0)),
            "surface_class": entry_span.get("surface_class"),
            "friction_tier": entry_span.get("friction_tier"),
        }

    if coverage:
        row["labeled_pct"] = coverage["labeled_pct"]
        row["unlabeled_metres"] = coverage["unlabeled_metres"]
        row["gap_count"] = coverage["gap_count"]

    reasons: list[str] = []
    if hitl.get("status") != "locked":
        reasons.append(f"hitl.status={hitl.get('status', 'unknown')}")
    if is_map_first_operator_gold(tmap) and not spans:
        reasons.append("map-first course has zero operator_gold_spans")
    if coverage and coverage["unlabeled_metres"] > 0:
        reasons.append(f"{coverage['unlabeled_metres']} m unlabeled")
    if missing_tier:
        reasons.append(f"{missing_tier} span(s) missing friction_tier")
    if gold_lo is not None and km_end > km_start and gold_lo > km_start + 0.05:
        reasons.append(f"gold starts at km {gold_lo:.2f} (corridor km {km_start:.2f})")
    row["needs_review"] = bool(reasons)
    row["review_reasons"] = reasons
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit operator gold across all terrain maps")
    parser.add_argument("--config-dir", type=Path, default=CONFIG_DIR)
    parser.add_argument("--json", type=Path, default=None, help="Write machine-readable portfolio report")
    parser.add_argument("--fail-on-gaps", action="store_true", help="Exit 1 if any map needs review")
    args = parser.parse_args()

    maps = _terrain_map_paths(args.config_dir)
    if not maps:
        print("No terrain maps found.", file=sys.stderr)
        return 1

    rows = [audit_map(p) for p in maps]
    needs = [r for r in rows if r["needs_review"]]

    print("=== Operator gold portfolio audit ===\n")
    for row in rows:
        flag = "REVIEW" if row["needs_review"] else "ok"
        pct = f"{row['labeled_pct']:.1f}%" if row["labeled_pct"] is not None else "n/a"
        print(
            f"[{flag:6}] {row['terrain_map']}\n"
            f"         race={row['race_id']}  hitl={row['hitl_status']}  "
            f"spans={row['operator_gold_spans']}  labeled={pct}"
        )
        if row["first_span_at_corridor_start"]:
            fs = row["first_span_at_corridor_start"]
            print(
                f"         corridor start km {row['corridor_km_start']:.2f} → "
                f"{fs['surface_class']}/{fs.get('friction_tier') or '?'}"
                f" (km {fs['km_start']:.2f}–{fs['km_end']:.2f})"
            )
        if row["review_reasons"]:
            print(f"         reasons: {'; '.join(row['review_reasons'])}")
        print()

    print(f"Summary: {len(rows)} maps, {len(needs)} need review before publication lock.")

    sut43_blog_note = (
        "\nBlog composite (km 25–41): use config/spatial_terrain_map_sut43_full.json so km 25–29 "
        "shows merged upstream operator gold — not GMM draft bleed from gramstad-only map."
    )
    print(sut43_blog_note)

    if args.json:
        out = args.json if args.json.is_absolute() else BASE_DIR / args.json
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {"maps": rows, "needs_review_count": len(needs)}
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {out.relative_to(BASE_DIR)}")

    if args.fail_on_gaps and needs:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
