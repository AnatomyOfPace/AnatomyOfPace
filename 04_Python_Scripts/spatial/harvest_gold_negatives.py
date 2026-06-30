#!/usr/bin/env python3
"""
Harvest operator-rejected ML REVISE spans for negative reinforcement training.

Reads suggestion CSV(s) and optional QC adjudication log; joins window-median
features from the panel/HMM stack; writes span-level negative export.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/harvest_gold_negatives.py \\
        --suggest-csv 03_Processed_Data/spatial/suggested_locks_sut43*.csv \\
        --qc-csv 03_Processed_Data/spatial/sut43_window_centroid_qc.csv \\
        --terrain-map config/spatial_terrain_map_sut43.json \\
        --output 03_Processed_Data/spatial/gold_training_negatives_sut43.parquet

    # Export low-confidence REVISE rows for operator review (no QC match required):
    python3 04_Python_Scripts/spatial/harvest_gold_negatives.py \\
        --reject-revise --suggest-csv 03_Processed_Data/spatial/suggested_locks_sut43.csv

    # Export every REVISE row:
    python3 04_Python_Scripts/spatial/harvest_gold_negatives.py \\
        --all-revise --suggest-csv 03_Processed_Data/spatial/suggested_locks_sut43*.csv
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.gold_training_common import (
    DEFAULT_HMM_DRAFT,
    DEFAULT_PANEL,
    DEFAULT_TERRAIN_MAP,
    FEATURE_COLUMNS,
    build_training_frame,
    span_km_bounds,
    spans_overlap,
)
from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.validation_dashboard import operator_gold_spans

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUTPUT = BASE_DIR / "03_Processed_Data" / "spatial" / "gold_training_negatives_sut43.parquet"

CONFIDENCE_RANK = {"LOW": 0, "MED": 1, "HIGH": 2}
DEFAULT_LOW_CONF = frozenset({"LOW"})

OUTPUT_COLUMNS = [
    "course_km_start",
    "course_km_end",
    "gold_surface",
    "gold_friction",
    "pred_surface",
    "pred_friction",
    "confidence",
    "surface_proba",
    "friction_proba",
    "reject_reason",
    "source_chunk",
    "harvest_source",
]

# QC note patterns — each tuple is (regex, km_groups, sf_groups) with 1-based group indices.
_QC_PATTERNS: list[tuple[re.Pattern[str], tuple[int, int], tuple[int, int]]] = [
    (
        re.compile(
            r"REJECTS?\s+ML\s+(S\d)/(F\d)\s+REVISE\s+km\s+(\d+\.?\d*)-(\d+\.?\d*)",
            re.IGNORECASE,
        ),
        (3, 4),
        (1, 2),
    ),
    (
        re.compile(
            r"REJECTS?\s+ML\s+REVISE\s+km\s+(\d+\.?\d*)-(\d+\.?\d*)\s+"
            r"(S\d)/(F\d)(?:\s+to\s+(S\d)/(F\d))?",
            re.IGNORECASE,
        ),
        (1, 2),
        (3, 4),
    ),
    (
        re.compile(
            r"ML\s+REVISE\s+km\s+(\d+\.?\d*)-(\d+\.?\d*)\s+(S\d)/(F\d)\s+\w+\s+p=[\d.]+\s+rejected",
            re.IGNORECASE,
        ),
        (1, 2),
        (3, 4),
    ),
]
_QC_AND_KM = re.compile(r"and\s+km\s+(\d+\.?\d*)-(\d+\.?\d*)", re.IGNORECASE)
_SF_LABEL = re.compile(r"^S[1-6]$")
_F_LABEL = re.compile(r"^F[0-4]$")


def _infer_reject_reason(notes: str, sector_label: str) -> str:
    text = f"{sector_label} {notes}".lower()
    if "loen_underpass" in text or "variance_gap" in text or "multipath" in text:
        return "variance_gap_gps"
    if "upstream gravel pull" in text or "before pin" in text:
        return "upstream_transition_pull"
    if "f-tier drift" in text or "f1" in text and "f2" in text and "drift" in text:
        return "friction_tier_drift"
    if "grade-inflated" in text or "downhill" in text and "ti_med" in text:
        return "grade_inflated_ti"
    if "s4" in text and ("asphalt" in text or "s1/f0" in text):
        return "surface_class_misroute"
    if "micro-flip" in text or ("s5" in text and "s4" in text):
        return "surface_micro_flip"
    if "reject" in text:
        return "qc_operator_reject"
    return "qc_operator_reject"


def _parse_qc_reject_spans(qc_df: pd.DataFrame) -> list[dict[str, Any]]:
    """Extract rejected REVISE spans from operator QC notes."""
    rows: list[dict[str, Any]] = []
    for _, rec in qc_df.iterrows():
        notes = str(rec.get("notes") or "")
        sector = str(rec.get("sector_label") or "")
        if "reject" not in notes.lower():
            continue
        reason = _infer_reject_reason(notes, sector)
        window_start = float(rec.get("window_km_start", 0))
        window_end = float(rec.get("window_km_end", 0))

        parsed_any = False
        for pattern, km_idx, sf_idx in _QC_PATTERNS:
            for m in pattern.finditer(notes):
                parsed_any = True
                km_start = float(m.group(km_idx[0]))
                km_end = float(m.group(km_idx[1]))
                pred_s = m.group(sf_idx[0])
                pred_f = m.group(sf_idx[1])
                if m.lastindex and m.lastindex >= 6 and m.group(5) and m.group(6):
                    pred_s, pred_f = m.group(5), m.group(6)
                rows.append(
                    _qc_span_row(km_start, km_end, pred_s, pred_f, reason, sector, window_start, window_end)
                )
                tail = notes[m.end() : m.end() + 120]
                and_m = _QC_AND_KM.search(tail)
                if and_m:
                    km2_start, km2_end = float(and_m.group(1)), float(and_m.group(2))
                    pred2_s, pred2_f = pred_s, pred_f
                    to_m = re.search(r"to\s+(S\d)/(F\d)", tail[and_m.end() : and_m.end() + 40], re.IGNORECASE)
                    if to_m:
                        pred2_s, pred2_f = to_m.group(1), to_m.group(2)
                    rows.append(
                        _qc_span_row(
                            km2_start,
                            km2_end,
                            pred2_s,
                            pred2_f,
                            reason,
                            sector,
                            window_start,
                            window_end,
                        )
                    )

        if not parsed_any:
            chunk_m = re.search(r"chunk_(\d+)", notes, re.IGNORECASE)
            rows.append(
                {
                    "course_km_start": window_start,
                    "course_km_end": window_end,
                    "pred_surface": None,
                    "pred_friction": None,
                    "reject_reason": reason,
                    "source_chunk": f"chunk_{chunk_m.group(1)}" if chunk_m else None,
                    "harvest_source": "qc_window",
                    "qc_sector": sector,
                    "qc_window_start": window_start,
                    "qc_window_end": window_end,
                }
            )
    return rows


def _expand_qc_to_all_suggestions(
    qc_spans: list[dict[str, Any]],
    suggest_revise: pd.DataFrame,
) -> list[dict[str, Any]]:
    """For each QC reject, emit every overlapping REVISE suggestion row."""
    if suggest_revise.empty:
        return qc_spans
    expanded: list[dict[str, Any]] = []
    for span in qc_spans:
        qs = float(span["course_km_start"])
        qe = float(span["course_km_end"])
        chunk = span.get("source_chunk")
        matches: list[dict[str, Any]] = []
        for _, s in suggest_revise.iterrows():
            if chunk and str(s.get("chunk_id")) != str(chunk):
                continue
            if not spans_overlap(qs, qe, float(s["km_start"]), float(s["km_end"])):
                continue
            matches.append(s.to_dict())
        if not matches:
            expanded.append(span)
            continue
        for suggestion in matches:
            row = dict(span)
            row = _enrich_from_suggestion(row, suggestion)
            row["harvest_source"] = "qc_notes+suggest_csv"
            expanded.append(row)
    return expanded


def _qc_span_row(
    km_start: float,
    km_end: float,
    pred_s: str,
    pred_f: str,
    reason: str,
    sector: str,
    window_start: float,
    window_end: float,
) -> dict[str, Any]:
    return {
        "course_km_start": km_start,
        "course_km_end": km_end,
        "pred_surface": pred_s,
        "pred_friction": pred_f,
        "reject_reason": reason,
        "source_chunk": None,
        "harvest_source": "qc_notes",
        "qc_sector": sector,
        "qc_window_start": window_start,
        "qc_window_end": window_end,
    }


def _variance_gap_rejects(terrain_map: dict[str, Any], suggest_revise: pd.DataFrame) -> list[dict[str, Any]]:
    """Flag REVISE rows overlapping annotated variance_gaps (e.g. loen_underpass)."""
    hitl = terrain_map.get("hitl") or {}
    gaps = hitl.get("variance_gaps") or []
    if not gaps or suggest_revise.empty:
        return []
    rows: list[dict[str, Any]] = []
    for gap in gaps:
        g0 = float(gap["course_km_start"])
        g1 = float(gap["course_km_end"])
        anchor = str(gap.get("anchor_id") or gap.get("note") or "variance_gap")
        for _, s in suggest_revise.iterrows():
            if not spans_overlap(g0, g1, float(s["km_start"]), float(s["km_end"])):
                continue
            rows.append(
                {
                    "course_km_start": float(s["km_start"]),
                    "course_km_end": float(s["km_end"]),
                    "pred_surface": s["surface_class"],
                    "pred_friction": s["friction_tier"],
                    "gold_surface": s.get("gold_surface"),
                    "gold_friction": s.get("gold_friction"),
                    "confidence": s.get("confidence"),
                    "surface_proba": s.get("surface_proba"),
                    "friction_proba": s.get("friction_proba"),
                    "reject_reason": "variance_gap_gps",
                    "source_chunk": s.get("chunk_id"),
                    "harvest_source": f"variance_gap:{anchor}",
                }
            )
    return rows


def _load_suggestions(paths: list[Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in paths:
        if not path.exists():
            print(f"Suggestion CSV not found (skipped): {path}", file=sys.stderr)
            continue
        df = pd.read_csv(path)
        if "action" not in df.columns:
            continue
        df = df[df["action"] == "REVISE"].copy()
        if df.empty:
            continue
        df["suggest_source"] = str(path)
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _span_key(row: dict[str, Any]) -> tuple:
    return (
        round(float(row["course_km_start"]), 3),
        round(float(row["course_km_end"]), 3),
        str(row.get("pred_surface") or ""),
        str(row.get("pred_friction") or ""),
    )


def _overlap_match(
    qc_span: dict[str, Any],
    suggest_revise: pd.DataFrame,
    *,
    min_overlap_frac: float = 0.3,
) -> dict[str, Any] | None:
    """Best overlapping REVISE suggestion row for a QC reject span."""
    if suggest_revise.empty:
        return None
    best: dict[str, Any] | None = None
    best_score = -1.0
    qs, qe = float(qc_span["course_km_start"]), float(qc_span["course_km_end"])
    qlen = max(qe - qs, 1e-6)
    pred_s = qc_span.get("pred_surface")
    pred_f = qc_span.get("pred_friction")
    for _, s in suggest_revise.iterrows():
        ss, se = float(s["km_start"]), float(s["km_end"])
        if not spans_overlap(qs, qe, ss, se):
            continue
        overlap = min(qe, se) - max(qs, ss)
        frac = overlap / qlen
        if frac < min_overlap_frac:
            continue
        score = frac
        if pred_s and str(s["surface_class"]) == str(pred_s):
            score += 0.5
        if pred_f and str(s["friction_tier"]) == str(pred_f):
            score += 0.5
        if score > best_score:
            best_score = score
            best = s.to_dict()
    return best


def _enrich_from_suggestion(base: dict[str, Any], suggestion: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(base)
    if suggestion is None:
        return out
    for col in (
        "gold_surface",
        "gold_friction",
        "confidence",
        "surface_proba",
        "friction_proba",
        "chunk_id",
        "km_start",
        "km_end",
        "surface_class",
        "friction_tier",
    ):
        if col in suggestion and pd.notna(suggestion[col]):
            out[col] = suggestion[col]
    if out.get("source_chunk") is None and suggestion.get("chunk_id"):
        out["source_chunk"] = suggestion["chunk_id"]
    if out.get("pred_surface") is None:
        out["pred_surface"] = suggestion.get("surface_class")
    if out.get("pred_friction") is None:
        out["pred_friction"] = suggestion.get("friction_tier")
    if suggestion.get("km_start") is not None:
        out["course_km_start"] = float(suggestion["km_start"])
        out["course_km_end"] = float(suggestion["km_end"])
    return out


def _gold_at_km(gold_spans: list[dict[str, Any]], km: float) -> tuple[str | None, str | None]:
    mid = km + 1e-6
    for span in gold_spans:
        s0, s1 = span_km_bounds(span)
        if s0 <= mid < s1:
            return span.get("surface_class"), span.get("friction_tier")
    return None, None


def _attach_gold_labels(rows: list[dict[str, Any]], gold_spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        rec = dict(row)
        if not rec.get("gold_surface") or not rec.get("gold_friction"):
            mid = (float(rec["course_km_start"]) + float(rec["course_km_end"])) / 2.0
            gs, gf = _gold_at_km(gold_spans, mid)
            rec.setdefault("gold_surface", gs)
            rec.setdefault("gold_friction", gf)
        out.append(rec)
    return out


def _window_median_features(
    km_start: float,
    km_end: float,
    *,
    panel_path: Path,
    terrain_map_path: Path,
    hmm_path: Path,
    feature_cols: tuple[str, ...] = FEATURE_COLUMNS,
) -> dict[str, float]:
    frame = build_training_frame(
        panel_path=panel_path,
        terrain_map_path=terrain_map_path,
        hmm_path=hmm_path,
        km_lo=km_start,
        km_hi=km_end,
    )
    if frame.empty:
        return {}
    present = [c for c in feature_cols if c in frame.columns]
    medians = frame[present].median(numeric_only=True)
    return {k: float(v) if pd.notna(v) else np.nan for k, v in medians.items()}


def _valid_pred_labels(pred_s: str | None, pred_f: str | None) -> bool:
    return bool(pred_s and pred_f and _SF_LABEL.match(str(pred_s)) and _F_LABEL.match(str(pred_f)))


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep richest record per span key (prefer QC + suggestion enrichment)."""
    rows = [r for r in rows if _valid_pred_labels(r.get("pred_surface"), r.get("pred_friction"))]
    by_key: dict[tuple, dict[str, Any]] = {}
    for row in rows:
        key = _span_key(row)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = row
            continue
        score_existing = sum(
            1
            for c in ("gold_surface", "confidence", "surface_proba", "friction_proba", "reject_reason")
            if existing.get(c) is not None and not (isinstance(existing.get(c), float) and np.isnan(existing.get(c)))
        )
        score_new = sum(
            1
            for c in ("gold_surface", "confidence", "surface_proba", "friction_proba", "reject_reason")
            if row.get(c) is not None and not (isinstance(row.get(c), float) and np.isnan(row.get(c)))
        )
        if score_new >= score_existing:
            by_key[key] = row
    return list(by_key.values())


def _rows_from_reject_revise(
    suggest_revise: pd.DataFrame,
    *,
    all_revise: bool,
    low_conf: frozenset[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, s in suggest_revise.iterrows():
        conf = str(s.get("confidence") or "").upper()
        if not all_revise and conf not in low_conf:
            continue
        rows.append(
            {
                "course_km_start": float(s["km_start"]),
                "course_km_end": float(s["km_end"]),
                "gold_surface": s.get("gold_surface"),
                "gold_friction": s.get("gold_friction"),
                "pred_surface": s["surface_class"],
                "pred_friction": s["friction_tier"],
                "confidence": conf,
                "surface_proba": s.get("surface_proba"),
                "friction_proba": s.get("friction_proba"),
                "reject_reason": "export_all_revise" if all_revise else "low_conf_reject_revise",
                "source_chunk": s.get("chunk_id"),
                "harvest_source": "suggest_csv",
            }
        )
    return rows


def _expand_glob(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in paths:
        if any(ch in raw for ch in "*?[]"):
            out.extend(sorted(Path().glob(raw)))
        else:
            out.append(Path(raw))
    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest operator-rejected ML REVISE spans for negative training.")
    parser.add_argument(
        "--suggest-csv",
        action="append",
        default=None,
        help="Suggestion CSV path or glob (repeatable)",
    )
    parser.add_argument("--qc-csv", type=Path, default=None, help="Operator QC adjudication CSV")
    parser.add_argument("--terrain-map", type=Path, default=DEFAULT_TERRAIN_MAP)
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--hmm-draft", type=Path, default=DEFAULT_HMM_DRAFT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-json", type=Path, default=None)
    parser.add_argument(
        "--reject-revise",
        action="store_true",
        help="Also harvest LOW-confidence REVISE rows from suggestion CSV(s)",
    )
    parser.add_argument(
        "--all-revise",
        action="store_true",
        help="Harvest all REVISE rows from suggestion CSV(s) (operator review export)",
    )
    parser.add_argument(
        "--include-med",
        action="store_true",
        help="With --reject-revise, include MED confidence rows",
    )
    parser.add_argument("--skip-features", action="store_true", help="Skip panel feature join (faster)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    suggest_paths = _expand_glob(args.suggest_csv or [])
    if not suggest_paths and not args.qc_csv:
        print("Provide --suggest-csv and/or --qc-csv.", file=sys.stderr)
        return 1

    suggest_revise = _load_suggestions(suggest_paths)
    harvested: list[dict[str, Any]] = []

    if args.qc_csv and args.qc_csv.exists():
        qc_df = pd.read_csv(args.qc_csv)
        qc_spans = _parse_qc_reject_spans(qc_df)
        qc_spans = _expand_qc_to_all_suggestions(qc_spans, suggest_revise)
        harvested.extend(qc_spans)
    elif args.qc_csv:
        print(f"QC CSV not found (skipped): {args.qc_csv}", file=sys.stderr)

    if args.terrain_map.exists():
        terrain_map = load_terrain_map(args.terrain_map)
        gold_spans = list(operator_gold_spans(terrain_map))
        harvested = _attach_gold_labels(harvested, gold_spans)
        if suggest_revise is not None and not suggest_revise.empty:
            harvested.extend(_variance_gap_rejects(terrain_map, suggest_revise))
    else:
        gold_spans = []
        print(f"Terrain map not found (skipped gold lookup): {args.terrain_map}", file=sys.stderr)

    low_conf = DEFAULT_LOW_CONF | ({"MED"} if args.include_med else frozenset())
    if args.reject_revise or args.all_revise:
        harvested.extend(
            _rows_from_reject_revise(
                suggest_revise,
                all_revise=args.all_revise,
                low_conf=low_conf if not args.all_revise else frozenset({"LOW", "MED", "HIGH"}),
            )
        )
        harvested = _attach_gold_labels(harvested, gold_spans)

    harvested = _dedupe_rows(harvested)
    if not harvested:
        print("No negative spans harvested.", file=sys.stderr)
        return 1

    if not args.skip_features and args.panel.exists():
        for row in harvested:
            feats = _window_median_features(
                float(row["course_km_start"]),
                float(row["course_km_end"]),
                panel_path=args.panel,
                terrain_map_path=args.terrain_map,
                hmm_path=args.hmm_draft,
            )
            row.update(feats)

    out_df = pd.DataFrame(harvested)
    for col in OUTPUT_COLUMNS:
        if col not in out_df.columns:
            out_df[col] = None
    feature_cols_present = [c for c in FEATURE_COLUMNS if c in out_df.columns]
    export_cols = OUTPUT_COLUMNS + feature_cols_present
    out_df = out_df[[c for c in export_cols if c in out_df.columns]]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(args.output, index=False)

    reason_counts = out_df["reject_reason"].value_counts(dropna=False).to_dict()
    source_counts = out_df["harvest_source"].value_counts(dropna=False).to_dict()
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_parquet": str(args.output),
        "n_negatives": len(out_df),
        "reject_reason_counts": reason_counts,
        "harvest_source_counts": source_counts,
        "suggest_csvs": [str(p) for p in suggest_paths],
        "qc_csv": str(args.qc_csv) if args.qc_csv else None,
        "reject_revise": args.reject_revise,
        "all_revise": args.all_revise,
        "feature_columns": feature_cols_present,
    }
    summary_path = args.summary_json or args.output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {len(out_df)} negative span(s) → {args.output}")
    print("Reject reason counts:")
    for reason, count in sorted(reason_counts.items(), key=lambda x: (-x[1], str(x[0]))):
        print(f"  {reason}: {count}")
    print(f"Summary → {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
