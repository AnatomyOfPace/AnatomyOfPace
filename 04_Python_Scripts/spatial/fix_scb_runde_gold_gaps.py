#!/usr/bin/env python3
"""
Repair SCB Runde operator gold gaps for map-first pool training.

1. Sync course_m_* from course_km_* (fixes stale metre bounds).
2. Fill known orthophoto holes (e.g. km 0.98–1.0 grass bridge).
3. Extend terminal span when the only gap is at course tail.
4. Bridge any remaining sub-50 m holes via neighbor S/F.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/fix_scb_runde_gold_gaps.py
    python3 04_Python_Scripts/spatial/fix_scb_runde_gold_gaps.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.gold_training_common import (  # noqa: E402
    panel_gold_label_stats,
    span_km_bounds,
    spans_overlap,
)
from spatial.gold_span_editor import sync_gold_local_mirror  # noqa: E402
from spatial.spatial_hitl_overlay import load_terrain_map  # noqa: E402
from spatial.suggest_gold_spans import ungolded_intervals  # noqa: E402
from spatial.validation_dashboard import operator_gold_spans  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RACE_ID = "scb_runde"
TERRAIN_MAP = BASE_DIR / f"config/spatial_terrain_map_{RACE_ID}.json"
MANIFEST = BASE_DIR / f"config/spatial_align_manifest_{RACE_ID}.json"
PANEL = BASE_DIR / f"03_Processed_Data/spatial/{RACE_ID}_course/panel_1m.parquet"
MAX_GAP_M = 50.0

# Orthophoto spans from lock_scb_runde_gold.sh that are sometimes dropped locally.
KNOWN_FILLS: list[tuple[float, float, str, str, str]] = [
    (0.98, 1.0, "S3", "F2", "orthophoto: grass/trail km 0.98–1.0"),
]


def _backup(path: Path) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2(path, path.with_suffix(f".backup_{ts}.json"))


def _load_panel() -> pd.DataFrame:
    panel = pd.read_parquet(PANEL)
    if "course_km" not in panel.columns and "ref_chainage_m" in panel.columns:
        panel = panel.copy()
        panel["course_km"] = panel["ref_chainage_m"] / 1000.0
    if "course_m" not in panel.columns and "ref_chainage_m" in panel.columns:
        panel["course_m"] = panel["ref_chainage_m"]
    return panel


def _panel_max_km(panel: pd.DataFrame) -> float:
    return round(float(panel["course_km"].max()), 3)


def _sync_metre_fields(spans: list[dict]) -> bool:
    changed = False
    for span in spans:
        if span.get("course_km_start") is None or span.get("course_km_end") is None:
            continue
        km0 = float(span["course_km_start"])
        km1 = float(span["course_km_end"])
        want_m0 = round(km0 * 1000.0, 3)
        want_m1 = round(km1 * 1000.0, 3)
        if span.get("course_m_start") != want_m0 or span.get("course_m_end") != want_m1:
            span["course_m_start"] = want_m0
            span["course_m_end"] = want_m1
            changed = True
    return changed


def _neighbor_classes(spans: list[dict], gap_lo: float, gap_hi: float) -> tuple[str, str] | None:
    left: dict | None = None
    right: dict | None = None
    left_end = -1.0
    right_start = 1e9
    for span in spans:
        s0, s1 = span_km_bounds(span)
        if s1 <= gap_lo + 1e-6 and s1 > left_end:
            left = span
            left_end = s1
        if s0 >= gap_hi - 1e-6 and s0 < right_start:
            right = span
            right_start = s0
    for candidate in (left, right):
        if candidate is None:
            continue
        surf = str(candidate.get("surface_class", "")).strip().upper()
        fric = str(candidate.get("friction_tier", "")).strip().upper()
        if surf and fric:
            return surf, fric
    return None


def _append_span(
    spans: list[dict],
    *,
    km_start: float,
    km_end: float,
    surface: str,
    friction: str,
    reason: str,
) -> bool:
    if km_end <= km_start:
        return False
    for span in spans:
        s0, s1 = span_km_bounds(span)
        if spans_overlap(km_start, km_end, s0, s1):
            return False
    locked_at = date.today().isoformat()
    spans.append(
        {
            "course_km_start": round(km_start, 3),
            "course_km_end": round(km_end, 3),
            "course_m_start": round(km_start * 1000.0, 3),
            "course_m_end": round(km_end * 1000.0, 3),
            "surface_class": surface,
            "friction_tier": friction,
            "gold_source": "operator",
            "mode": "operator_gold",
            "locked_at": locked_at,
            "reason": reason,
        }
    )
    return True


def _gap_overlaps(gap: tuple[float, float], lo: float, hi: float) -> bool:
    return gap[0] < hi - 1e-6 and gap[1] > lo + 1e-6


def _patch_km_end(panel_max: float, *, dry_run: bool) -> None:
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        old = float(manifest["km_analysis_window"][1])
        if panel_max > old + 1e-6:
            manifest["km_analysis_window"][1] = panel_max
            manifest["km_viewport_window"][1] = round(panel_max + 0.1, 3)
            if not dry_run:
                _backup(MANIFEST)
                MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(f"  manifest km_end {old:.3f} → {panel_max:.3f}")

    tmap = json.loads(TERRAIN_MAP.read_text(encoding="utf-8"))
    corridor = tmap.setdefault("corridor", {})
    old_c = float(corridor.get("km_end") or 0.0)
    if panel_max > old_c + 1e-6:
        corridor["km_end"] = panel_max
        if not dry_run:
            _backup(TERRAIN_MAP)
            TERRAIN_MAP.write_text(json.dumps(tmap, indent=2) + "\n", encoding="utf-8")
            sync_gold_local_mirror(TERRAIN_MAP, tmap)
        print(f"  corridor km_end {old_c:.3f} → {panel_max:.3f}")


def fix_gaps(*, dry_run: bool = False) -> int:
    if not TERRAIN_MAP.exists() or not PANEL.exists():
        print("Missing terrain map or panel — bootstrap scb_runde first.", file=sys.stderr)
        return 1

    panel = _load_panel()
    panel_max = _panel_max_km(panel)
    panel_max_m = int(round(float(panel["course_m"].max())))

    terrain_map = load_terrain_map(TERRAIN_MAP)
    spans: list[dict] = list(operator_gold_spans(terrain_map))
    if not spans:
        print("No operator gold spans in terrain map.", file=sys.stderr)
        return 1

    stats_before = panel_gold_label_stats(panel, spans)
    print("=== SCB Runde — repair gold gaps ===")
    print(f"  panel max:     km {panel_max} ({panel_max_m} m)")
    print(f"  panel labeled: {stats_before['labeled']}/{stats_before['total']} m")
    gaps_before = ungolded_intervals(0.0, panel_max, spans)
    if gaps_before:
        print("  km gaps:")
        for lo, hi in gaps_before:
            print(f"    km {lo:.3f}–{hi:.3f} ({(hi - lo) * 1000:.0f} m)")
    else:
        print("  km gaps:       none")
    print("")

    if stats_before["unlabeled"] == 0 and not gaps_before:
        print("OK full gold coverage — nothing to do.")
        return 0

    changed = False

    print("━━━ 1/4 Sync course_m_* from course_km_* ━━━")
    if _sync_metre_fields(spans):
        changed = True
        print("  synced metre bounds on existing spans")
    else:
        print("  metre bounds already aligned")

    gaps = ungolded_intervals(0.0, panel_max, spans)
    print("")
    print("━━━ 2/4 Fill known orthophoto holes ━━━")
    for gap_lo, gap_hi in list(gaps):
        for klo, khi, sc, fr, reason in KNOWN_FILLS:
            if not _gap_overlaps((gap_lo, gap_hi), klo, khi):
                continue
            fill_end = min(gap_hi, khi)
            fill_start = max(gap_lo, klo)
            if dry_run:
                print(f"  [dry-run] add km {fill_start:.3f}–{fill_end:.3f} {sc}/{fr}")
            elif _append_span(
                spans,
                km_start=fill_start,
                km_end=fill_end,
                surface=sc,
                friction=fr,
                reason=f"{reason} — gap fill",
            ):
                changed = True
                print(f"  + km {fill_start:.3f}–{fill_end:.3f} {sc}/{fr}")
            break

    gaps = ungolded_intervals(0.0, panel_max, spans)
    print("")
    print("━━━ 3/4 Tail extend + bridge micro-gaps ━━━")
    for gap_lo, gap_hi in list(gaps):
        gap_m = (gap_hi - gap_lo) * 1000.0
        if gap_m > MAX_GAP_M + 1e-6:
            print(f"  skip large gap km {gap_lo:.3f}–{gap_hi:.3f} ({gap_m:.0f} m)")
            continue
        if gap_hi >= panel_max - 0.0005:
            tail_idx = max(range(len(spans)), key=lambda i: span_km_bounds(spans[i])[1])
            tail = spans[tail_idx]
            t0, _t1 = span_km_bounds(tail)
            new_end = round(panel_max + 0.001, 3)
            sc = str(tail.get("surface_class") or "S2")
            fr = str(tail.get("friction_tier") or "F2")
            reason = str(tail.get("reason") or "orthophoto tail")
            if dry_run:
                print(f"  [dry-run] extend tail span [{tail_idx}] km {t0:.3f}–{new_end:.3f} {sc}/{fr}")
            else:
                spans.pop(tail_idx)
                if _append_span(
                    spans,
                    km_start=t0,
                    km_end=new_end,
                    surface=sc,
                    friction=fr,
                    reason=f"{reason} — tail gap closed to panel km {panel_max}",
                ):
                    changed = True
                    print(f"  + tail km {t0:.3f}–{new_end:.3f} {sc}/{fr}")
            continue

        picked = _neighbor_classes(spans, gap_lo, gap_hi)
        if picked is None:
            print(f"  skip gap km {gap_lo:.3f}–{gap_hi:.3f} (no neighbor S/F)")
            continue
        sc, fr = picked
        if dry_run:
            print(f"  [dry-run] bridge km {gap_lo:.3f}–{gap_hi:.3f} {sc}/{fr}")
        elif _append_span(
            spans,
            km_start=gap_lo,
            km_end=gap_hi,
            surface=sc,
            friction=fr,
            reason=f"bridge_gaps <= {MAX_GAP_M:.0f} m ({sc}/{fr} from neighbor)",
        ):
            changed = True
            print(f"  + bridge km {gap_lo:.3f}–{gap_hi:.3f} {sc}/{fr}")

    if changed and not dry_run:
        terrain_map = json.loads(TERRAIN_MAP.read_text(encoding="utf-8"))
        terrain_map.setdefault("hitl", {})["operator_gold_spans"] = spans
        _backup(TERRAIN_MAP)
        TERRAIN_MAP.write_text(json.dumps(terrain_map, indent=2) + "\n", encoding="utf-8")
        sync_gold_local_mirror(TERRAIN_MAP, terrain_map)

    print("")
    print("━━━ 4/4 Patch km_end + verify ━━━")
    if not dry_run:
        _patch_km_end(panel_max, dry_run=False)
        terrain_map = load_terrain_map(TERRAIN_MAP)
        spans = operator_gold_spans(terrain_map)
        stats_after = panel_gold_label_stats(panel, spans)
        print(f"  panel labeled: {stats_after['labeled']}/{stats_after['total']} m")
        gaps_after = ungolded_intervals(0.0, panel_max, spans)
        if stats_after["unlabeled"] == 0 and not gaps_after:
            print("OK full gold coverage")
            return 0
        if gaps_after:
            for lo, hi in gaps_after:
                print(f"  remaining gap km {lo:.3f}–{hi:.3f} ({(hi - lo) * 1000:.0f} m)", file=sys.stderr)
        print("ERROR incomplete gold coverage after repair", file=sys.stderr)
        return 1

    print("  (dry-run — no writes)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair SCB Runde operator gold gaps")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return fix_gaps(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
