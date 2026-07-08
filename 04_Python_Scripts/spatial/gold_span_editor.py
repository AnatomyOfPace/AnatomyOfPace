#!/usr/bin/env python3
"""
CLI editor for sparse operator gold spans in terrain map JSON.

List, add, or delete entries in hitl.operator_gold_spans[] with overlap validation
and timestamped backup before write.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/gold_span_editor.py list
    python3 04_Python_Scripts/spatial/gold_span_editor.py add \\
        --km-start 37.5 --km-end 37.6 --surface S3 --friction F3 \\
        --reason "test span"
    python3 04_Python_Scripts/spatial/gold_span_editor.py delete --index 0
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.gold_training_common import span_km_bounds, spans_overlap
from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.validation_dashboard import operator_gold_spans

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_TERRAIN_MAP = BASE_DIR / "config" / "spatial_terrain_map_sut43.json"

SURFACE_CLASSES = ("S1", "S2", "S3", "S4", "S5", "S6")
FRICTION_TIERS = ("F0", "F1", "F2", "F3", "F4")


def find_overlapping_spans(
    spans: list[dict[str, Any]],
    km_start: float,
    km_end: float,
) -> list[tuple[int, dict[str, Any]]]:
    hits: list[tuple[int, dict[str, Any]]] = []
    for idx, span in enumerate(spans):
        s0, s1 = span_km_bounds(span)
        if spans_overlap(km_start, km_end, s0, s1):
            hits.append((idx, span))
    return hits


def backup_terrain_map(path: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_suffix(f".backup_{ts}.json")
    shutil.copy2(path, backup)
    return backup


def sync_gold_local_mirror(path: Path, terrain_map: dict[str, Any]) -> Path | None:
    """Write gitignored operator-gold mirror beside terrain map (survives git restore)."""
    mirror = path.with_name(f"{path.stem}.gold_local.json")
    mirror.write_text(json.dumps(terrain_map, indent=2) + "\n", encoding="utf-8")
    return mirror


def write_terrain_map(path: Path, terrain_map: dict[str, Any], *, dry_run: bool = False) -> None:
    if dry_run:
        return
    backup_terrain_map(path)
    path.write_text(json.dumps(terrain_map, indent=2) + "\n", encoding="utf-8")
    sync_gold_local_mirror(path, terrain_map)


def cmd_list(args: argparse.Namespace) -> int:
    terrain_map = load_terrain_map(args.terrain_map)
    spans = operator_gold_spans(terrain_map)
    if not spans:
        print("(no operator gold spans)")
        return 0
    for idx, span in enumerate(spans):
        s0, s1 = span_km_bounds(span)
        sc = span.get("surface_class", "?")
        ft = span.get("friction_tier", "?")
        reason = str(span.get("reason", ""))[:60]
        print(f"[{idx:3d}] km {s0:.3f}–{s1:.3f}  {sc}/{ft}  {reason}")
    print(f"Total: {len(spans)} span(s)")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    km_start = float(args.km_start)
    km_end = float(args.km_end)
    if km_end <= km_start:
        print("Error: --km-end must exceed --km-start", file=sys.stderr)
        return 1
    if args.surface not in SURFACE_CLASSES:
        print(f"Error: --surface must be one of {SURFACE_CLASSES}", file=sys.stderr)
        return 1
    if args.friction not in FRICTION_TIERS:
        print(f"Error: --friction must be one of {FRICTION_TIERS}", file=sys.stderr)
        return 1

    terrain_map = load_terrain_map(args.terrain_map)
    hitl = terrain_map.setdefault("hitl", {})
    spans: list[dict[str, Any]] = list(hitl.get("operator_gold_spans") or [])
    overlaps = find_overlapping_spans(spans, km_start, km_end)
    if overlaps:
        idx, span = overlaps[0]
        s0, s1 = span_km_bounds(span)
        print(
            f"Error: overlaps existing span [{idx}] km {s0:.3f}–{s1:.3f} "
            f"({span.get('surface_class')}/{span.get('friction_tier')})",
            file=sys.stderr,
        )
        return 1

    locked_at = date.today().isoformat()
    entry: dict[str, Any] = {
        "course_km_start": round(km_start, 3),
        "course_km_end": round(km_end, 3),
        "surface_class": args.surface,
        "friction_tier": args.friction,
        "gold_source": "operator",
        "mode": "operator_gold",
        "locked_at": locked_at,
        "reason": (args.reason or "").strip() or f"operator gold lock {locked_at} via gold_span_editor",
    }
    if args.dry_run:
        print(json.dumps(entry, indent=2))
        return 0

    spans.append(entry)
    hitl["operator_gold_spans"] = spans
    write_terrain_map(args.terrain_map, terrain_map)
    mirror = args.terrain_map.with_name(f"{args.terrain_map.stem}.gold_local.json")
    print(f"Appended span km {km_start:.3f}–{km_end:.3f} {args.surface}/{args.friction}")
    print(f"Mirror → {mirror}")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    terrain_map = load_terrain_map(args.terrain_map)
    hitl = terrain_map.setdefault("hitl", {})
    spans: list[dict[str, Any]] = list(hitl.get("operator_gold_spans") or [])
    idx = int(args.index)
    if idx < 0 or idx >= len(spans):
        print(f"Error: index {idx} out of range (0–{len(spans) - 1})", file=sys.stderr)
        return 1
    removed = spans.pop(idx)
    s0, s1 = span_km_bounds(removed)
    if args.dry_run:
        print(f"Would delete [{idx}] km {s0:.3f}–{s1:.3f}")
        return 0
    hitl["operator_gold_spans"] = spans
    write_terrain_map(args.terrain_map, terrain_map)
    print(f"Deleted [{idx}] km {s0:.3f}–{s1:.3f} {removed.get('surface_class')}/{removed.get('friction_tier')}")
    return 0


def cmd_clear_window(args: argparse.Namespace) -> int:
    """Remove all operator gold spans overlapping [km-start, km-end)."""
    km_start = float(args.km_start)
    km_end = float(args.km_end)
    if km_end <= km_start:
        print("Error: --km-end must exceed --km-start", file=sys.stderr)
        return 1

    terrain_map = load_terrain_map(args.terrain_map)
    hitl = terrain_map.setdefault("hitl", {})
    spans: list[dict[str, Any]] = list(hitl.get("operator_gold_spans") or [])
    kept: list[dict[str, Any]] = []
    removed: list[tuple[int, dict[str, Any]]] = []
    for idx, span in enumerate(spans):
        s0, s1 = span_km_bounds(span)
        if spans_overlap(km_start, km_end, s0, s1):
            removed.append((idx, span))
        else:
            kept.append(span)

    if not removed:
        print(f"No spans overlap km {km_start:.3f}–{km_end:.3f}")
        return 0

    for idx, span in removed:
        s0, s1 = span_km_bounds(span)
        print(f"  - [{idx}] km {s0:.3f}–{s1:.3f} {span.get('surface_class')}/{span.get('friction_tier')}")

    if args.dry_run:
        print(f"Would remove {len(removed)} span(s); keep {len(kept)}")
        return 0

    hitl["operator_gold_spans"] = kept
    write_terrain_map(args.terrain_map, terrain_map)
    print(f"Cleared {len(removed)} overlapping span(s); {len(kept)} remain")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    """Copy operator_gold_spans from gitignored .gold_local.json into terrain map."""
    path = Path(args.terrain_map)
    mirror = path.with_name(f"{path.stem}.gold_local.json")
    if not mirror.exists():
        print(f"No gold_local mirror: {mirror}", file=sys.stderr)
        return 1
    local = json.loads(mirror.read_text(encoding="utf-8"))
    local_spans = local.get("hitl", {}).get("operator_gold_spans") or []
    if not local_spans:
        print(f"Mirror has no operator_gold_spans: {mirror}", file=sys.stderr)
        return 1
    terrain_map = json.loads(path.read_text(encoding="utf-8"))
    terrain_map.setdefault("hitl", {})["operator_gold_spans"] = local_spans
    if args.dry_run:
        print(f"Would restore {len(local_spans)} span(s) from {mirror.name}")
        return 0
    write_terrain_map(path, terrain_map)
    print(f"Restored {len(local_spans)} span(s) from {mirror.name}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argv_list = list(argv) if argv is not None else sys.argv[1:]
    dry_run_flag = "--dry-run" in argv_list
    if dry_run_flag:
        argv_list = [token for token in argv_list if token != "--dry-run"]

    parser = argparse.ArgumentParser(description="Edit sparse operator gold spans in terrain map JSON.")
    parser.add_argument("--terrain-map", type=Path, default=DEFAULT_TERRAIN_MAP)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without writing JSON (may appear before or after subcommand)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all operator gold spans with index")

    add_p = sub.add_parser("add", help="Append a non-overlapping gold span")
    add_p.add_argument("--km-start", type=float, required=True)
    add_p.add_argument("--km-end", type=float, required=True)
    add_p.add_argument("--surface", type=str, required=True, help="S1–S6")
    add_p.add_argument("--friction", type=str, required=True, help="F0–F4")
    add_p.add_argument("--reason", type=str, default="")

    del_p = sub.add_parser("delete", help="Remove span by list index")
    del_p.add_argument("--index", type=int, required=True)

    clear_p = sub.add_parser(
        "clear-window",
        help="Remove all spans overlapping a km window (before clean orthophoto locks)",
    )
    clear_p.add_argument("--km-start", type=float, required=True)
    clear_p.add_argument("--km-end", type=float, required=True)

    sub.add_parser("restore", help="Restore operator_gold_spans from .gold_local.json mirror")

    args = parser.parse_args(argv_list)
    if dry_run_flag:
        args.dry_run = True
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.terrain_map.exists():
        print(f"Terrain map not found: {args.terrain_map}", file=sys.stderr)
        return 1
    if args.command == "list":
        return cmd_list(args)
    if args.command == "add":
        return cmd_add(args)
    if args.command == "delete":
        return cmd_delete(args)
    if args.command == "clear-window":
        return cmd_clear_window(args)
    if args.command == "restore":
        return cmd_restore(args)
    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
