#!/usr/bin/env python3
"""
Bootstrap map-first orphan courses (unwashed Subject_A FIT loops).

Registry: config/map_first_orphan_courses.json

Wash → patch km_end → rebuild 1 m panel → ready for HITL export + operator gold.

Usage (from repo root):
    python3 04_Python_Scripts/spatial/bootstrap_map_first_orphan.py --list
    python3 04_Python_Scripts/spatial/bootstrap_map_first_orphan.py --all
    python3 04_Python_Scripts/spatial/bootstrap_map_first_orphan.py --course selvikstakken
    python3 04_Python_Scripts/spatial/bootstrap_map_first_orphan.py --course scb_runde \\
        --fit 02_Raw_Data/donors/Subject_A/SCB_runden_Eirik_20260525.fit
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "04_Python_Scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from fit_micro.activity_frame import MICRO_DIR  # noqa: E402

import seed_matrix  # noqa: E402
from spatial.map_first_orphan_registry import (  # noqa: E402
    DONOR_DIR,
    DONOR_ID,
    discover_fit_candidates,
    get_orphan_course,
    list_orphan_courses,
    write_course_configs,
)


def _canonical_fit_path(activity_id: str) -> Path:
    safe = re.sub(r"[^\w.-]+", "_", activity_id)
    return DONOR_DIR / f"{safe}.fit"


def _install_to_canonical(source: Path, activity_id: str) -> Path:
    src = source.resolve()
    if DONOR_DIR.resolve() in src.parents or src.parent == DONOR_DIR.resolve():
        return src
    canonical = _canonical_fit_path(activity_id)
    canonical.parent.mkdir(parents=True, exist_ok=True)
    if src == canonical.resolve():
        return canonical
    if not canonical.exists():
        print(f"Copying FIT → {canonical.relative_to(_REPO)}")
        shutil.copy2(src, canonical)
    return canonical


def _resolve_fit_path(course: dict, explicit: Path | None) -> tuple[Path, str]:
    race_id = course["race_id"]
    if explicit is not None:
        p = explicit.expanduser()
        p = p if p.is_absolute() else _REPO / p
        if not p.exists():
            raise FileNotFoundError(f"FIT not found: {p}")
        activity_id = p.stem
        return _install_to_canonical(p, activity_id), activity_id

    discovered = discover_fit_candidates(course)
    donor_root = DONOR_DIR.resolve()
    donor_hits = [p for p in discovered if donor_root in p.parents or p.parent == donor_root]
    if len(donor_hits) == 1:
        print(f"Auto-discovered FIT: {donor_hits[0]}")
        activity_id = donor_hits[0].stem
        return _install_to_canonical(donor_hits[0], activity_id), activity_id
    if len(discovered) == 1:
        print(f"Auto-discovered FIT: {discovered[0]}")
        activity_id = discovered[0].stem
        return _install_to_canonical(discovered[0], activity_id), activity_id
    if len(discovered) > 1:
        lines = "\n".join(f"  - {p}" for p in discovered)
        raise FileNotFoundError(
            f"Multiple FIT files match {race_id!r} — pass Subject_A file with --fit:\n{lines}"
        )
    raise FileNotFoundError(
        f"No FIT found for {race_id!r} ({course.get('display_name')}).\n"
        f"Place under {DONOR_DIR} or pass --fit <path>"
    )


def _stream_km_end(micro_path: Path) -> float:
    df = pd.read_parquet(micro_path)
    if "course_km" not in df.columns:
        raise ValueError(f"Micro parquet lacks course_km: {micro_path}")
    mx = float(pd.to_numeric(df["course_km"], errors="coerce").max())
    if not (mx > 0):
        raise ValueError(f"Invalid max course_km in {micro_path}")
    return round(mx + 0.0005, 3)


def _resolve_o2_anchor() -> Path | None:
    try:
        return seed_matrix.anchor_path(DONOR_ID)
    except FileNotFoundError:
        return seed_matrix.discover_anchor_fit("Stavanger_Halvmaraton.fit")


def _run(cmd: list[str]) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=_REPO, check=True)


def bootstrap_course(
    race_id: str,
    *,
    fit: Path | None = None,
    skip_wash: bool = False,
    skip_panel: bool = False,
    no_enrich_ti: bool = False,
    enrich_ti: bool = False,
) -> int:
    course = get_orphan_course(race_id)
    fit_path, activity_id = _resolve_fit_path(course, fit)
    micro_path = MICRO_DIR / DONOR_ID / f"activity_{activity_id}.parquet"

    if not skip_wash:
        try:
            fit_arg = fit_path.relative_to(_REPO)
        except ValueError:
            fit_arg = fit_path
        cmd = [
            sys.executable,
            str(_SCRIPTS / "15_fit_micro_wash.py"),
            "--donor",
            DONOR_ID,
            "--activity",
            activity_id,
            "--fit",
            str(fit_arg),
            "--race",
            race_id,
            "--project-course",
            "--no-privacy-clip",
        ]
        anchor = _resolve_o2_anchor()
        if enrich_ti:
            if anchor is None:
                raise FileNotFoundError("O₂ anchor Stavanger_Halvmaraton.fit not found for --enrich-ti")
            cmd.append("--enrich-ti")
        elif not no_enrich_ti and anchor is not None:
            rel = anchor.relative_to(_REPO) if anchor.is_relative_to(_REPO) else anchor
            print(f"OK O₂ anchor → {rel}")
            cmd.append("--enrich-ti")
        elif not no_enrich_ti:
            print("WARN Stavanger_Halvmaraton.fit not found — skipping --enrich-ti")
        _run(cmd)

    if not micro_path.exists():
        print(f"Micro parquet missing after wash: {micro_path}", file=sys.stderr)
        return 1

    km_end = _stream_km_end(micro_path)
    write_course_configs(course, activity_id=activity_id, km_end=km_end)
    print(f"Patched configs km_end → {km_end:.3f}")

    manifest = _REPO / "config" / f"spatial_align_manifest_{race_id}.json"
    if not skip_panel:
        _run(
            [
                sys.executable,
                str(_SCRIPTS / "spatial" / "corridor_multi_fit.py"),
                "--manifest",
                str(manifest.relative_to(_REPO)),
                "--enrich-if-needed",
            ]
        )

    print(
        f"\nOK {course.get('display_name')} bootstrap complete.\n"
        f"  race_id: {race_id}\n"
        f"  activity: {activity_id}\n"
        f"  panel: 03_Processed_Data/spatial/{race_id}_course/panel_1m.parquet\n"
        f"  export: ./04_Python_Scripts/spatial/export_hitl_map_first_orphan.sh {race_id}\n"
        f"  label:  python3 04_Python_Scripts/spatial/gold_span_editor.py add "
        f"--terrain-map config/spatial_terrain_map_{race_id}.json ..."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap map-first orphan Subject_A courses")
    parser.add_argument("--list", action="store_true", help="List registry courses and exit")
    parser.add_argument("--all", action="store_true", help="Bootstrap every orphan course")
    parser.add_argument("--course", action="append", default=[], help="race_id from registry (repeatable)")
    parser.add_argument("--fit", type=Path, default=None, help="Explicit FIT path (single --course only)")
    parser.add_argument("--discover", metavar="RACE_ID", help="List FIT candidates for one course")
    parser.add_argument("--skip-wash", action="store_true")
    parser.add_argument("--skip-panel", action="store_true")
    parser.add_argument("--no-enrich-ti", action="store_true")
    parser.add_argument("--enrich-ti", action="store_true")
    args = parser.parse_args()

    if args.list:
        for course in list_orphan_courses():
            print(f"  {course['race_id']:32}  {course.get('display_name')}")
        return 0

    if args.discover:
        course = get_orphan_course(args.discover)
        found = discover_fit_candidates(course)
        if found:
            print(f"FIT candidates for {args.discover}:")
            for p in found:
                try:
                    print(f"  {p.relative_to(_REPO)}")
                except ValueError:
                    print(f"  {p}")
        else:
            print(f"No FIT matches for {args.discover}")
        return 0 if found else 1

    targets: list[str] = []
    if args.all:
        targets = [c["race_id"] for c in list_orphan_courses()]
    elif args.course:
        targets = list(args.course)
    else:
        parser.error("Pass --list, --all, --discover RACE_ID, or --course RACE_ID")

    if args.fit and len(targets) != 1:
        parser.error("--fit requires exactly one --course")

    rc = 0
    for race_id in targets:
        print(f"\n{'=' * 60}\n→ {race_id}\n{'=' * 60}")
        try:
            if bootstrap_course(
                race_id,
                fit=args.fit if len(targets) == 1 else None,
                skip_wash=args.skip_wash,
                skip_panel=args.skip_panel,
                no_enrich_ti=args.no_enrich_ti,
                enrich_ti=args.enrich_ti,
            ):
                rc = 1
        except (FileNotFoundError, ValueError) as exc:
            print(f"FAIL {race_id}: {exc}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
