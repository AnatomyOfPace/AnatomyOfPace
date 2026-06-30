#!/usr/bin/env python3
"""
Auto-lock operator gold spans via ML suggester (gaps-first, no revise unless flagged).

Runs ML gap-fill suggestions, auto-accepts HIGH-confidence NEW rows, optionally
validates existing gold via HIGH-confidence KEEP rows, appends non-overlapping spans
through the same contract as gold_span_editor, and promotes hitl.status → locked
when the scoped corridor is fully golded.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/auto_lock_gold_spans.py --preset sut43
    python3 04_Python_Scripts/spatial/auto_lock_gold_spans.py \\
        --terrain-map config/spatial_terrain_map_sut43.json \\
        --km-start 29 --km-end 41
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

import joblib
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.corridor_scope import (
    SUT43_PRIMARY_KM_END,
    SUT43_PRIMARY_KM_START,
    SUT43_UPSTREAM_KM_END,
    SUT43_UPSTREAM_KM_START,
)
from spatial.gold_training_common import build_training_frame, span_km_bounds, spans_overlap
from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.suggest_gold_spans import (
    MIN_SPAN_KM,
    _predict_bundle,
    find_overlapping_gold_spans,
    operator_gold_spans,
    suggest_ml_gaps,
    suggest_ml_keep_summary,
    suggest_ml_revise,
    ungolded_intervals,
)
from spatial.validation_dashboard import operator_gold_spans as validation_operator_gold_spans

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_PANEL = BASE_DIR / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "panel_1m.parquet"
DEFAULT_GRAMSTAD_MAP = BASE_DIR / "config" / "spatial_terrain_map_sut43.json"
DEFAULT_UPSTREAM_MAP = BASE_DIR / "config" / "spatial_terrain_map_sut43_upstream.json"
DEFAULT_MODEL = BASE_DIR / "07_ML_Models" / "spatial" / "gold_suggester_v0.joblib"
DEFAULT_HMM_DRAFT = BASE_DIR / "07_ML_Models" / "terrain_hmm_sut43_draft_predictions.parquet"
DEFAULT_LOG_DIR = BASE_DIR / "03_Processed_Data" / "spatial"

SURFACE_CLASSES = ("S1", "S2", "S3", "S4", "S5", "S6")
FRICTION_TIERS = ("F0", "F1", "F2", "F3", "F4")
AUTO_ACCEPT_CONFIDENCE = "HIGH"
KM_EPS = 1e-6


@dataclass
class SectorSpec:
    name: str
    terrain_map: Path
    km_start: float
    km_end: float


SUT43_PRESET: list[SectorSpec] = [
    SectorSpec(
        name="dale_paradisskaret_upstream",
        terrain_map=DEFAULT_UPSTREAM_MAP,
        km_start=SUT43_UPSTREAM_KM_START,
        km_end=SUT43_UPSTREAM_KM_END,
    ),
    SectorSpec(
        name="gramstad_band",
        terrain_map=DEFAULT_GRAMSTAD_MAP,
        km_start=SUT43_PRIMARY_KM_START,
        km_end=SUT43_PRIMARY_KM_END,
    ),
]


@dataclass
class AutoLockResult:
    sector: str
    terrain_map: Path
    km_start: float
    km_end: float
    spans_added: list[dict[str, Any]] = field(default_factory=list)
    spans_blocked: list[dict[str, Any]] = field(default_factory=list)
    keep_validated: list[dict[str, Any]] = field(default_factory=list)
    revise_skipped: list[dict[str, Any]] = field(default_factory=list)
    coverage_pct: float = 0.0
    ungolded_km: float = 0.0
    hitl_status_before: str = ""
    hitl_status_after: str = ""
    panel_gap_note: str = ""


def panel_km_extent(panel_path: Path) -> tuple[float, float]:
    panel = pd.read_parquet(panel_path)
    if "course_km" not in panel.columns and "ref_chainage_m" in panel.columns:
        panel["course_km"] = panel["ref_chainage_m"] / 1000.0
    if "session_type" in panel.columns:
        panel = panel[panel["session_type"] == "race"]
    if panel.empty:
        return 0.0, 0.0
    return float(panel["course_km"].min()), float(panel["course_km"].max())


def clip_scope_to_panel(
    km_start: float,
    km_end: float,
    panel_lo: float,
    panel_hi: float,
) -> tuple[float, float, str]:
    note = ""
    eff_start = max(km_start, panel_lo)
    eff_end = min(km_end, panel_hi)
    if km_start < panel_lo:
        note = f"km {km_start:.1f}–{panel_lo:.1f} has no panel coverage (scoped to panel)"
    if eff_end <= eff_start:
        return eff_start, eff_end, note or "empty scope after panel clip"
    return eff_start, eff_end, note


def backup_terrain_map(path: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_suffix(f".backup_{ts}.json")
    shutil.copy2(path, backup)
    return backup


def merge_contiguous_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    ordered = sorted(rows, key=lambda r: (float(r["km_start"]), float(r["km_end"])))
    merged: list[dict[str, Any]] = []
    for row in ordered:
        if (
            merged
            and merged[-1]["surface_class"] == row["surface_class"]
            and merged[-1]["friction_tier"] == row["friction_tier"]
            and abs(float(merged[-1]["km_end"]) - float(row["km_start"])) <= KM_EPS
        ):
            merged[-1]["km_end"] = row["km_end"]
            merged[-1]["rationale"] = (
                f"{merged[-1].get('rationale', '')}; merged contiguous {row.get('action', 'NEW')}"
            ).strip("; ")
        else:
            merged.append(dict(row))
    return merged


def collect_ml_suggestions(
    *,
    panel_path: Path,
    terrain_map_path: Path,
    model_path: Path,
    hmm_path: Path,
    km_lo: float,
    km_hi: float,
    chunk_id: str,
    allow_revise: bool,
) -> pd.DataFrame:
    bundle = joblib.load(model_path)
    frame = build_training_frame(
        panel_path=panel_path,
        terrain_map_path=terrain_map_path,
        hmm_path=hmm_path,
        km_lo=km_lo,
        km_hi=km_hi,
    )
    predicted = _predict_bundle(frame, bundle)
    gold_spans = operator_gold_spans(load_terrain_map(terrain_map_path))

    rows: list[dict[str, Any]] = []
    rows.extend(
        suggest_ml_gaps(
            predicted,
            gold_spans,
            km_lo,
            km_hi,
            chunk_id=chunk_id,
            min_span_km=MIN_SPAN_KM,
        )
    )
    gaps_after = ungolded_intervals(km_lo, km_hi, gold_spans)
    has_ungolded = any((b - a) >= MIN_SPAN_KM - 1e-9 for a, b in gaps_after)
    if has_ungolded or not gaps_after:
        rows.extend(
            suggest_ml_keep_summary(
                predicted,
                gold_spans,
                km_lo,
                km_hi,
                chunk_id=chunk_id,
            )
        )
    if has_ungolded and allow_revise:
        rows.extend(
            suggest_ml_revise(
                predicted,
                gold_spans,
                km_lo,
                km_hi,
                chunk_id=chunk_id,
                min_span_km=MIN_SPAN_KM,
            )
        )
    return pd.DataFrame(rows)


def filter_auto_accept(
    suggestions: pd.DataFrame,
    *,
    allow_revise: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    to_add: list[dict[str, Any]] = []
    keep_validated: list[dict[str, Any]] = []
    revise_skipped: list[dict[str, Any]] = []
    if suggestions.empty:
        return to_add, keep_validated, revise_skipped

    for row in suggestions.to_dict(orient="records"):
        action = str(row.get("action", "NEW"))
        confidence = str(row.get("confidence", "")).upper()
        if action == "NEW" and confidence == AUTO_ACCEPT_CONFIDENCE:
            to_add.append(row)
        elif action == "KEEP" and confidence == AUTO_ACCEPT_CONFIDENCE:
            keep_validated.append(row)
        elif action == "REVISE":
            if allow_revise and confidence == AUTO_ACCEPT_CONFIDENCE:
                to_add.append(row)
            else:
                revise_skipped.append(row)
    return to_add, keep_validated, revise_skipped


def append_gold_span(
    terrain_map: dict[str, Any],
    *,
    km_start: float,
    km_end: float,
    surface: str,
    friction: str,
    reason: str,
) -> dict[str, Any] | None:
    if surface not in SURFACE_CLASSES or friction not in FRICTION_TIERS:
        return None
    hitl = terrain_map.setdefault("hitl", {})
    spans: list[dict[str, Any]] = list(hitl.get("operator_gold_spans") or [])
    overlaps = find_overlapping_gold_spans(spans, km_start, km_end)
    if overlaps:
        span = overlaps[0]
        s0, s1 = span_km_bounds(span)
        return {
            "km_start": km_start,
            "km_end": km_end,
            "surface_class": surface,
            "friction_tier": friction,
            "blocked_by": f"km {s0:.3f}–{s1:.3f} {span.get('surface_class')}/{span.get('friction_tier')}",
        }

    locked_at = date.today().isoformat()
    entry: dict[str, Any] = {
        "course_km_start": round(km_start, 3),
        "course_km_end": round(km_end, 3),
        "surface_class": surface,
        "friction_tier": friction,
        "gold_source": "operator",
        "mode": "operator_gold",
        "locked_at": locked_at,
        "reason": reason,
    }
    spans.append(entry)
    hitl["operator_gold_spans"] = spans
    return entry


def coverage_stats(
    terrain_map_path: Path,
    km_lo: float,
    km_hi: float,
) -> tuple[float, float, list[tuple[float, float]]]:
    gold = operator_gold_spans(load_terrain_map(terrain_map_path))
    total = km_hi - km_lo
    gaps = ungolded_intervals(km_lo, km_hi, gold)
    ungolded = sum(b - a for a, b in gaps)
    pct = 100.0 * (1.0 - ungolded / total) if total > 0 else 100.0
    return pct, ungolded, gaps


def auto_lock_sector(
    spec: SectorSpec,
    *,
    panel_path: Path,
    model_path: Path,
    hmm_path: Path,
    allow_revise: bool,
    dry_run: bool,
    set_locked: bool,
) -> AutoLockResult:
    panel_lo, panel_hi = panel_km_extent(panel_path)
    km_start, km_end, panel_note = clip_scope_to_panel(spec.km_start, spec.km_end, panel_lo, panel_hi)
    terrain_map = load_terrain_map(spec.terrain_map)
    hitl = terrain_map.get("hitl", {})
    result = AutoLockResult(
        sector=spec.name,
        terrain_map=spec.terrain_map,
        km_start=km_start,
        km_end=km_end,
        hitl_status_before=str(hitl.get("status", "")),
        panel_gap_note=panel_note,
    )

    if km_end <= km_start:
        result.hitl_status_after = result.hitl_status_before
        return result

    suggestions = collect_ml_suggestions(
        panel_path=panel_path,
        terrain_map_path=spec.terrain_map,
        model_path=model_path,
        hmm_path=hmm_path,
        km_lo=km_start,
        km_hi=km_end,
        chunk_id=spec.name,
        allow_revise=allow_revise,
    )
    to_add, keep_validated, revise_skipped = filter_auto_accept(suggestions, allow_revise=allow_revise)
    result.keep_validated = keep_validated
    result.revise_skipped = revise_skipped

    merged = merge_contiguous_rows(to_add)
    modified = False
    for row in merged:
        action = str(row.get("action", "NEW"))
        reason_tag = "ml_auto_lock: HIGH confidence gap-fill"
        if action == "REVISE":
            reason_tag = "ml_auto_lock: HIGH confidence revise (explicit flag)"
        reason = f"{reason_tag}; {row.get('rationale', '')}".strip()
        outcome = append_gold_span(
            terrain_map,
            km_start=float(row["km_start"]),
            km_end=float(row["km_end"]),
            surface=str(row["surface_class"]),
            friction=str(row["friction_tier"]),
            reason=reason,
        )
        if outcome is None:
            continue
        if "blocked_by" in outcome:
            result.spans_blocked.append(outcome)
            continue
        result.spans_added.append(outcome)
        modified = True

    pct, ungolded, _ = coverage_stats(spec.terrain_map, km_start, km_end)
    result.coverage_pct = pct
    result.ungolded_km = ungolded

    if set_locked and ungolded <= KM_EPS and result.hitl_status_before != "locked":
        terrain_map.setdefault("hitl", {})["status"] = "locked"
        modified = True
        result.hitl_status_after = "locked"
    else:
        result.hitl_status_after = str(terrain_map.get("hitl", {}).get("status", result.hitl_status_before))

    if modified and not dry_run:
        backup_terrain_map(spec.terrain_map)
        spec.terrain_map.write_text(json.dumps(terrain_map, indent=2) + "\n", encoding="utf-8")
    elif dry_run:
        result.hitl_status_after = (
            "locked"
            if set_locked and ungolded <= KM_EPS
            else result.hitl_status_before
        )

    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ML-assisted auto-lock of operator gold spans.")
    parser.add_argument("--preset", choices=("sut43",), default=None, help="Run bundled SUT_43 sectors")
    parser.add_argument("--terrain-map", type=Path, default=None)
    parser.add_argument("--km-start", type=float, default=None)
    parser.add_argument("--km-end", type=float, default=None)
    parser.add_argument("--sector-name", type=str, default="custom", help="Label for single-map run")
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--hmm-draft", type=Path, default=DEFAULT_HMM_DRAFT)
    parser.add_argument(
        "--allow-revise",
        action="store_true",
        help="Auto-accept HIGH-confidence REVISE rows (overwrites via new non-overlapping spans only)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report actions without writing terrain maps")
    parser.add_argument("--no-set-locked", action="store_true", help="Do not promote hitl.status to locked")
    parser.add_argument("--log-json", type=Path, default=None, help="Audit log path (default: timestamped under spatial/)")
    parser.add_argument("--rebuild-training", action="store_true", help="Rebuild gold training export after lock")
    return parser.parse_args(argv)


def resolve_sectors(args: argparse.Namespace) -> list[SectorSpec]:
    if args.preset == "sut43":
        return list(SUT43_PRESET)
    if args.terrain_map is None:
        raise ValueError("Specify --preset sut43 or --terrain-map with --km-start/--km-end")
    if args.km_start is None or args.km_end is None:
        raise ValueError("--km-start and --km-end required for single-map runs")
    return [
        SectorSpec(
            name=args.sector_name,
            terrain_map=args.terrain_map,
            km_start=float(args.km_start),
            km_end=float(args.km_end),
        )
    ]


def combined_panel_coverage(
    panel_path: Path,
    sector_results: list[AutoLockResult],
) -> dict[str, Any]:
    panel_lo, panel_hi = panel_km_extent(panel_path)
    all_gold: list[dict[str, Any]] = []
    for res in sector_results:
        all_gold.extend(validation_operator_gold_spans(load_terrain_map(res.terrain_map)))
    gaps = ungolded_intervals(panel_lo, panel_hi, all_gold)
    ungolded = sum(b - a for a, b in gaps)
    total = panel_hi - panel_lo
    return {
        "panel_km_start": panel_lo,
        "panel_km_end": panel_hi,
        "combined_coverage_pct": round(100.0 * (1.0 - ungolded / total), 2) if total else 100.0,
        "combined_ungolded_km": round(ungolded, 4),
        "combined_gaps": [(round(a, 3), round(b, 3)) for a, b in gaps],
        "km_0_22_note": "No panel below km 22 — auto-lock scoped to panel-covered range only"
        if panel_lo >= 22.0
        else None,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.panel.exists():
        print(f"Panel not found: {args.panel}", file=sys.stderr)
        return 1
    if not args.model.exists():
        print(f"Model not found: {args.model}", file=sys.stderr)
        return 1

    try:
        sectors = resolve_sectors(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    results: list[AutoLockResult] = []
    for spec in sectors:
        if not spec.terrain_map.exists():
            print(f"Terrain map not found: {spec.terrain_map}", file=sys.stderr)
            return 1
        res = auto_lock_sector(
            spec,
            panel_path=args.panel,
            model_path=args.model,
            hmm_path=args.hmm_draft,
            allow_revise=args.allow_revise,
            dry_run=args.dry_run,
            set_locked=not args.no_set_locked,
        )
        results.append(res)

    combined = combined_panel_coverage(args.panel, results)
    log_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "allow_revise": args.allow_revise,
        "panel": str(args.panel),
        "model": str(args.model),
        "sectors": [
            {
                "sector": r.sector,
                "terrain_map": str(r.terrain_map),
                "km_start": r.km_start,
                "km_end": r.km_end,
                "spans_added": r.spans_added,
                "spans_blocked": r.spans_blocked,
                "keep_validated_count": len(r.keep_validated),
                "revise_skipped_count": len(r.revise_skipped),
                "coverage_pct": round(r.coverage_pct, 2),
                "ungolded_km": round(r.ungolded_km, 4),
                "hitl_status_before": r.hitl_status_before,
                "hitl_status_after": r.hitl_status_after,
                "panel_gap_note": r.panel_gap_note,
            }
            for r in results
        ],
        "combined_panel": combined,
    }

    log_path = args.log_json
    if log_path is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path = DEFAULT_LOG_DIR / f"auto_lock_sut43_{ts}.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(log_payload, indent=2) + "\n", encoding="utf-8")

    for r in results:
        print(
            f"[{r.sector}] added={len(r.spans_added)} blocked={len(r.spans_blocked)} "
            f"keep_validated={len(r.keep_validated)} coverage={r.coverage_pct:.1f}% "
            f"status {r.hitl_status_before}→{r.hitl_status_after}"
        )
        if r.panel_gap_note:
            print(f"  note: {r.panel_gap_note}")
        for span in r.spans_added:
            print(
                f"  + km {span['course_km_start']:.3f}–{span['course_km_end']:.3f} "
                f"{span['surface_class']}/{span['friction_tier']}"
            )
        for blocked in r.spans_blocked:
            print(f"  ! blocked km {blocked['km_start']:.3f}–{blocked['km_end']:.3f}: {blocked['blocked_by']}")

    print(
        f"Combined panel km {combined['panel_km_start']:.1f}–{combined['panel_km_end']:.1f}: "
        f"coverage={combined['combined_coverage_pct']:.1f}% "
        f"ungolded={combined['combined_ungolded_km']:.3f} km"
    )
    if combined.get("km_0_22_note"):
        print(f"  {combined['km_0_22_note']}")
    print(f"Audit log → {log_path}")

    if args.rebuild_training and not args.dry_run:
        from spatial.build_gold_training_set import main as build_main

        build_argv = [
            "--panel",
            str(args.panel),
            "--terrain-map",
            str(DEFAULT_GRAMSTAD_MAP),
            "--extra-terrain-map",
            str(DEFAULT_UPSTREAM_MAP),
            "--km-start",
            str(combined["panel_km_start"]),
            "--km-end",
            str(combined["panel_km_end"]),
        ]
        print("Rebuilding gold training set (full panel window)…")
        rc = build_main(build_argv)
        if rc != 0:
            return rc

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
