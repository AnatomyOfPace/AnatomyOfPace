#!/usr/bin/env python3
"""
Bootstrap Klepp Runde Tier-0 course for map-first HITL (Klepp, Rogaland).

Map-first FIT stream-distance pipeline — not SUT_43 organiser GPX snap.

1. Resolve canonical FIT (filename must contain Klepp + Runde).
2. Wash micro Parquet (stream-distance course axis).
3. Patch manifest + terrain map km_end from FIT stream length.
4. Rebuild 1 m panel.

Usage (from repo root, after placing FIT locally):
    python3 04_Python_Scripts/spatial/bootstrap_klepp_runde_course.py

    python3 04_Python_Scripts/spatial/bootstrap_klepp_runde_course.py \\
        --fit 02_Raw_Data/donors/Subject_A/Klepp_Runde_20260707.fit
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "04_Python_Scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from fit_micro.activity_frame import MICRO_DIR  # noqa: E402

MANIFEST = _REPO / "config" / "spatial_align_manifest_klepp_runde.json"
TERRAIN_MAP = _REPO / "config" / "spatial_terrain_map_klepp_runde.json"
DONOR_ID = "Subject_A"
RACE_ID = "klepp_runde"
DONOR_DIR = _REPO / "02_Raw_Data" / "donors" / DONOR_ID


def _is_klepp_runde_fit(path: Path) -> bool:
    name = path.name.lower()
    return "klepp" in name and "runde" in name


def _iter_fit_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    out: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() == ".fit":
            out.append(path.resolve())
    return sorted(out, key=lambda p: p.stat().st_mtime, reverse=True)


def _discover_fit_candidates() -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()
    for root in (_REPO / "02_Raw_Data", Path.home() / "Downloads", Path.home() / "Desktop"):
        if not root.exists():
            continue
        for path in _iter_fit_files(root):
            if not _is_klepp_runde_fit(path):
                continue
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(path)
    return candidates


def _canonical_fit_path(activity_id: str) -> Path:
    safe = re.sub(r"[^\w.-]+", "_", activity_id)
    return DONOR_DIR / f"{safe}.fit"


def _install_to_canonical(source: Path, activity_id: str) -> Path:
    canonical = _canonical_fit_path(activity_id)
    canonical.parent.mkdir(parents=True, exist_ok=True)
    src = source.resolve()
    if src == canonical.resolve():
        return canonical
    if not canonical.exists():
        print(f"Copying FIT → {canonical.relative_to(_REPO)}")
        shutil.copy2(src, canonical)
    return canonical


def _resolve_fit_path(explicit: Path | None) -> tuple[Path, str]:
    if explicit is not None:
        p = explicit.expanduser()
        p = p if p.is_absolute() else _REPO / p
        if not p.exists():
            raise FileNotFoundError(f"FIT not found: {p}")
        activity_id = p.stem
        return _install_to_canonical(p, activity_id), activity_id

    discovered = _discover_fit_candidates()
    if len(discovered) == 1:
        print(f"Auto-discovered FIT: {discovered[0]}")
        activity_id = discovered[0].stem
        return _install_to_canonical(discovered[0], activity_id), activity_id
    if len(discovered) > 1:
        lines = "\n".join(f"  - {p}" for p in discovered)
        raise FileNotFoundError(
            "Multiple Klepp Runde FIT files found — pass exactly one with --fit:\n" + lines
        )

    raise FileNotFoundError(
        "No Klepp Runde FIT found (filename must contain 'Klepp' and 'Runde').\n\n"
        f"Place under {_REPO / '02_Raw_Data' / 'donors' / DONOR_ID} or pass:\n"
        "  python3 04_Python_Scripts/spatial/bootstrap_klepp_runde_course.py "
        "--fit 02_Raw_Data/donors/Subject_A/YOUR_Klepp_Runde.fit"
    )


def _stream_km_end(micro_path: Path) -> float:
    df = pd.read_parquet(micro_path)
    if "course_km" not in df.columns:
        raise ValueError(f"Micro parquet lacks course_km: {micro_path}")
    mx = float(pd.to_numeric(df["course_km"], errors="coerce").max())
    if not (mx > 0):
        raise ValueError(f"Invalid max course_km in {micro_path}")
    return round(mx + 0.0005, 3)


def _patch_manifest_activity(activity_id: str) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    activities = manifest.get("activities") or []
    if not activities:
        activities = [{}]
    activities[0].update(
        {
            "donor_id": DONOR_ID,
            "activity_id": activity_id,
            "session_type": "training",
            "subject_id": DONOR_ID,
            "align_mode": "stream",
            "note": f"Klepp Runde loop — FIT {activity_id} defines stream-distance course axis.",
        }
    )
    manifest["activities"] = activities
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _patch_km_end(km_end: float, activity_id: str) -> None:
    viewport = round(km_end + 0.1, 3)
    _patch_manifest_activity(activity_id)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["km_analysis_window"] = [0.0, km_end]
    manifest["km_viewport_window"] = [0.0, viewport]
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    tmap = json.loads(TERRAIN_MAP.read_text(encoding="utf-8"))
    tmap["generated_at"] = datetime.now(timezone.utc).isoformat()
    corridor = tmap.get("corridor") or {}
    corridor["km_end"] = km_end
    corridor["notes"] = (
        "Tier 0 map-first local loop (Klepp Runde, Rogaland). "
        f"Stream-distance axis km 0–{km_end:.3f} from Subject_A FIT {activity_id}. "
        "Operator adjudicates substrate from orthophoto."
    )
    tmap["corridor"] = corridor
    tmap["segments"] = [
        {
            "course_km_start": 0.0,
            "course_km_end": km_end,
            "surface_class": "S2",
            "friction_tier": "F2",
            "source": "seed",
            "label": "Gravel / trail tread (placeholder)",
            "confidence": 0.3,
            "operator_note": "Map-first seed — superseded by operator_gold_spans when locked.",
        }
    ]
    TERRAIN_MAP.write_text(json.dumps(tmap, indent=2) + "\n", encoding="utf-8")
    print(f"Patched km_end → {km_end:.3f} in manifest + terrain map")


def _run(cmd: list[str]) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=_REPO, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Klepp Runde map-first HITL course")
    parser.add_argument("--fit", type=Path, default=None, help="Path to Klepp_Runde*.fit")
    parser.add_argument("--skip-wash", action="store_true", help="Reuse existing micro Parquet")
    parser.add_argument("--skip-panel", action="store_true", help="Only wash + patch km_end")
    parser.add_argument(
        "--no-enrich-ti",
        action="store_true",
        help="Skip GAP/TI enrich (use when O₂ anchor FIT is absent)",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="List Klepp Runde FIT candidates and exit",
    )
    args = parser.parse_args()

    if args.discover:
        found = _discover_fit_candidates()
        if found:
            print("Klepp Runde FIT matches:")
            for p in found:
                try:
                    print(f"  {p.relative_to(_REPO)}")
                except ValueError:
                    print(f"  {p}")
        else:
            print("No filename containing both 'Klepp' and 'Runde' found.")
        return 0 if found else 1

    fit_path, activity_id = _resolve_fit_path(args.fit)
    micro_path = MICRO_DIR / DONOR_ID / f"activity_{activity_id}.parquet"

    if not args.skip_wash:
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
            RACE_ID,
            "--project-course",
            "--no-privacy-clip",
        ]
        if not args.no_enrich_ti:
            cmd.append("--enrich-ti")
        _run(cmd)

    if not micro_path.exists():
        print(f"Micro parquet missing after wash: {micro_path}", file=sys.stderr)
        return 1

    km_end = _stream_km_end(micro_path)
    _patch_km_end(km_end, activity_id)

    if not args.skip_panel:
        _run(
            [
                sys.executable,
                str(_SCRIPTS / "spatial" / "corridor_multi_fit.py"),
                "--manifest",
                str(MANIFEST.relative_to(_REPO)),
                "--enrich-if-needed",
            ]
        )

    print(
        "\nOK Klepp Runde bootstrap complete.\n"
        f"  Activity: {activity_id}\n"
        "  Panel: 03_Processed_Data/spatial/klepp_runde_course/panel_1m.parquet\n"
        "  Label:  python3 04_Python_Scripts/spatial/gold_span_editor.py add "
        "--terrain-map config/spatial_terrain_map_klepp_runde.json ...\n"
        "  PNGs:   ./04_Python_Scripts/spatial/export_hitl_chunks_klepp_runde.sh"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
