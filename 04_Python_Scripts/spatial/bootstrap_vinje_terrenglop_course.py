#!/usr/bin/env python3
"""
Bootstrap Vinje Terrengløp Tier-0 course for map-first HITL (Vinje, Telemark).

Trail event / training FIT on stream-distance axis — not SUT_43 organiser GPX.

1. Resolve canonical FIT (filename must contain Vinje + Terrengl).
2. Wash micro Parquet (stream-distance course axis).
3. Patch manifest + terrain map km_end from FIT stream length.
4. Rebuild 1 m panel.

Usage (from repo root, after placing FIT locally):
    python3 04_Python_Scripts/spatial/bootstrap_vinje_terrenglop_course.py \\
        --fit 02_Raw_Data/donors/Subject_A/Vinje_Terrenglop_20251005.fit
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

import seed_matrix  # noqa: E402

MANIFEST = _REPO / "config" / "spatial_align_manifest_vinje_terrenglop.json"
TERRAIN_MAP = _REPO / "config" / "spatial_terrain_map_vinje_terrenglop.json"
DONOR_ID = "Subject_A"
RACE_ID = "vinje_terrenglop"
DONOR_DIR = _REPO / "02_Raw_Data" / "donors" / DONOR_ID


def _normalize_fit_name(name: str) -> str:
    """Fold unicode (e.g. ø→o) so Terrengløp matches Terrenglop."""
    import unicodedata

    folded = unicodedata.normalize("NFKD", name)
    return "".join(ch for ch in folded if not unicodedata.combining(ch)).lower()


def _is_vinje_terrenglop_fit(path: Path) -> bool:
    name = _normalize_fit_name(path.name)
    return "vinje" in name and "terrengl" in name


def _discover_roots() -> list[Path]:
    home = Path.home()
    roots = [
        _REPO / "02_Raw_Data",
        home / "Downloads",
        home / "Desktop",
        home / "Documents",
        home / "Garmin",
        home / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "Downloads",
    ]
    out: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve()) if root.exists() else str(root)
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


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
    for root in _discover_roots():
        if not root.exists():
            continue
        for path in _iter_fit_files(root):
            if not _is_vinje_terrenglop_fit(path):
                continue
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(path)
    return candidates


def _fit_not_found_message(explicit: Path | None = None) -> str:
    discovered = _discover_fit_candidates()
    lines = [
        "No Vinje Terrengløp FIT at the expected path.",
        "Filename must contain 'Vinje' and 'Terrengl' (ø is OK — e.g. Terrengløp).",
    ]
    if explicit is not None:
        lines.insert(0, f"FIT not found: {explicit}")
    if discovered:
        lines.append("\nAuto-discovered candidates (pass one with --fit):")
        lines.extend(f"  - {p}" for p in discovered)
    else:
        lines.append("\nNo candidates under 02_Raw_Data, Downloads, Desktop, Documents, or ~/Garmin.")
        lines.append("Find the export on your Mac, then:")
        lines.append("  mdfind -name vinje | grep -i '\\.fit$'")
        lines.append("  find ~/Downloads ~/Desktop -iname '*vinje*.fit' 2>/dev/null")
        lines.append("\nThen copy or pass the real path:")
        lines.append(
            f"  --fit {_REPO / '02_Raw_Data' / 'donors' / DONOR_ID / 'YOUR_Vinje_Terrenglop.fit'}"
        )
    return "\n".join(lines)


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
            raise FileNotFoundError(_fit_not_found_message(p))
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
            "Multiple Vinje Terrengløp FIT files found — pass exactly one with --fit:\n" + lines
        )

    raise FileNotFoundError(_fit_not_found_message())


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
            "note": f"Vinje Terrengløp loop — FIT {activity_id} defines stream-distance course axis.",
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
        "Tier 0 map-first (Vinje Terrengløp, Telemark). "
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


def _resolve_o2_anchor() -> Path | None:
    try:
        return seed_matrix.anchor_path(DONOR_ID)
    except FileNotFoundError:
        return seed_matrix.discover_anchor_fit("Stavanger_Halvmaraton.fit")


def _run(cmd: list[str]) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=_REPO, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Vinje Terrengløp map-first HITL course")
    parser.add_argument("--fit", type=Path, default=None, help="Path to Vinje*Terrengl*.fit")
    parser.add_argument("--skip-wash", action="store_true", help="Reuse existing micro Parquet")
    parser.add_argument("--skip-panel", action="store_true", help="Only wash + patch km_end")
    parser.add_argument("--no-enrich-ti", action="store_true")
    parser.add_argument("--enrich-ti", action="store_true")
    parser.add_argument("--discover", action="store_true", help="List Vinje Terrengløp FIT candidates")
    args = parser.parse_args()

    if args.discover:
        found = _discover_fit_candidates()
        if found:
            print("Vinje Terrengløp FIT matches:")
            for p in found:
                try:
                    print(f"  {p.relative_to(_REPO)}")
                except ValueError:
                    print(f"  {p}")
            print("\nUse one path with --fit, or omit --fit if exactly one match exists.")
        else:
            print("No filename containing both 'Vinje' and 'Terrengl' found.")
            print(_fit_not_found_message())
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
        anchor = _resolve_o2_anchor()
        if args.enrich_ti:
            if anchor is None:
                raise FileNotFoundError(
                    "O₂ anchor Stavanger_Halvmaraton.fit not found under 02_Raw_Data"
                )
            cmd.append("--enrich-ti")
        elif not args.no_enrich_ti and anchor is not None:
            rel = anchor.relative_to(_REPO) if anchor.is_relative_to(_REPO) else anchor
            print(f"OK O₂ anchor → {rel}")
            cmd.append("--enrich-ti")
        elif not args.no_enrich_ti:
            print(
                "WARN Stavanger_Halvmaraton.fit not found — skipping --enrich-ti "
                "(orthophoto HITL still works)"
            )
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
        "\nOK Vinje Terrengløp bootstrap complete.\n"
        f"  Activity: {activity_id}\n"
        "  Panel: 03_Processed_Data/spatial/vinje_terrenglop_course/panel_1m.parquet\n"
        "  Preflight: python3 04_Python_Scripts/spatial/preflight_map_first_course.py "
        "--terrain-map config/spatial_terrain_map_vinje_terrenglop.json\n"
        "  Label:  python3 04_Python_Scripts/spatial/gold_span_editor.py "
        "--terrain-map config/spatial_terrain_map_vinje_terrenglop.json add ...\n"
        "  PNGs:   ./04_Python_Scripts/spatial/export_hitl_chunks_vinje_terrenglop.sh"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
