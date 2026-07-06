#!/usr/bin/env python3
"""
Bootstrap Tverrfjell Tier-0 course for map-first HITL (not SUT_43).

1. Normalize legacy FIT filename (drops personal token from basename).
2. Wash micro Parquet (stream-distance course axis).
3. Patch manifest + terrain map km_end from FIT stream length.
4. Rebuild 1 m panel.

Usage (from repo root, after placing FIT locally):
    python3 04_Python_Scripts/spatial/bootstrap_tverrfjell_course.py

    python3 04_Python_Scripts/spatial/bootstrap_tverrfjell_course.py \\
        --fit 02_Raw_Data/donors/Subject_A/Tverrfjell_20260704.fit
"""

from __future__ import annotations

import argparse
import json
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

DEFAULT_CANONICAL = _REPO / "02_Raw_Data" / "donors" / "Subject_A" / "Tverrfjell_20260704.fit"
LEGACY_GLOB = "Tverrfjell_*_20260704.fit"
MANIFEST = _REPO / "config" / "spatial_align_manifest_tverrfjell.json"
TERRAIN_MAP = _REPO / "config" / "spatial_terrain_map_tverrfjell.json"
ACTIVITY_ID = "Tverrfjell_20260704"
DONOR_ID = "Subject_A"
RACE_ID = "tverrfjell"


def _resolve_fit_path(explicit: Path | None) -> Path:
    if explicit is not None:
        p = explicit if explicit.is_absolute() else _REPO / explicit
        if not p.exists():
            raise FileNotFoundError(f"FIT not found: {p}")
        return p

    if DEFAULT_CANONICAL.exists():
        return DEFAULT_CANONICAL

    donor_dir = DEFAULT_CANONICAL.parent
    if donor_dir.exists():
        for candidate in sorted(donor_dir.glob(LEGACY_GLOB)):
            if candidate.name != DEFAULT_CANONICAL.name:
                print(f"Renaming legacy FIT → {DEFAULT_CANONICAL.name}")
                candidate.rename(DEFAULT_CANONICAL)
                return DEFAULT_CANONICAL

    raise FileNotFoundError(
        f"No FIT found. Place canonical file at:\n  {DEFAULT_CANONICAL}\n"
        f"Or pass --fit with path to Tverrfjell_*_20260704.fit"
    )


def _stream_km_end(micro_path: Path) -> float:
    df = pd.read_parquet(micro_path)
    if "course_km" not in df.columns:
        raise ValueError(f"Micro parquet lacks course_km: {micro_path}")
    mx = float(pd.to_numeric(df["course_km"], errors="coerce").max())
    if not (mx > 0):
        raise ValueError(f"Invalid max course_km in {micro_path}")
    # Round up to nearest metre on course axis.
    return round(mx + 0.0005, 3)


def _patch_km_end(km_end: float) -> None:
    viewport = round(km_end + 0.1, 3)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["km_analysis_window"] = [0.0, km_end]
    manifest["km_viewport_window"] = [0.0, viewport]
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    tmap = json.loads(TERRAIN_MAP.read_text(encoding="utf-8"))
    tmap["generated_at"] = datetime.now(timezone.utc).isoformat()
    corridor = tmap.get("corridor") or {}
    corridor["km_end"] = km_end
    corridor["notes"] = (
        "Tier 0 map-first local hill loop (Tverrfjell). Not SUT_43. "
        f"Stream-distance axis km 0–{km_end:.3f} from Subject_A FIT {ACTIVITY_ID}. "
        "Operator adjudicates substrate from orthophoto."
    )
    tmap["corridor"] = corridor
    tmap["segments"] = [
        {
            "course_km_start": 0.0,
            "course_km_end": km_end,
            "surface_class": "S3",
            "friction_tier": "F2",
            "source": "seed",
            "label": "Trail tread (placeholder)",
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
    parser = argparse.ArgumentParser(description="Bootstrap Tverrfjell map-first HITL course")
    parser.add_argument("--fit", type=Path, default=None, help="Path to canonical or legacy FIT")
    parser.add_argument("--skip-wash", action="store_true", help="Reuse existing micro Parquet")
    parser.add_argument("--skip-panel", action="store_true", help="Only wash + patch km_end")
    args = parser.parse_args()

    fit_path = _resolve_fit_path(args.fit)
    micro_path = MICRO_DIR / DONOR_ID / f"activity_{ACTIVITY_ID}.parquet"

    if not args.skip_wash:
        fit_arg = fit_path
        try:
            fit_arg = fit_path.relative_to(_REPO)
        except ValueError:
            pass
        _run(
            [
                sys.executable,
                str(_SCRIPTS / "15_fit_micro_wash.py"),
                "--donor",
                DONOR_ID,
                "--activity",
                ACTIVITY_ID,
                "--fit",
                str(fit_arg),
                "--race",
                RACE_ID,
                "--project-course",
                "--enrich-ti",
                "--no-privacy-clip",
            ]
        )

    if not micro_path.exists():
        print(f"Micro parquet missing after wash: {micro_path}", file=sys.stderr)
        return 1

    km_end = _stream_km_end(micro_path)
    _patch_km_end(km_end)

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
        "\nOK Tverrfjell bootstrap complete.\n"
        "  Panel: 03_Processed_Data/spatial/tverrfjell_course/panel_1m.parquet\n"
        "  Label:  python3 04_Python_Scripts/spatial/gold_span_editor.py add "
        "--terrain-map config/spatial_terrain_map_tverrfjell.json ...\n"
        "  PNGs:   ./04_Python_Scripts/spatial/export_hitl_chunks_tverrfjell.sh"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
