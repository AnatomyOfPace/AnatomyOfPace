#!/usr/bin/env python3
"""
QC corridor-slice TRF cells for SUT_43 gramstad blog publish.

Flags metre_count values that exceed the geographic analysis envelope
(km_end - km_start) — a common artifact when spine rows are not deduped
or when a gramstad-band cell is pasted into a corridor table.

Usage (repo root):
    python3 04_Python_Scripts/spatial/verify_trf_corridor_blog_cells.py

    python3 04_Python_Scripts/spatial/verify_trf_corridor_blog_cells.py \\
        --corridor-dir 03_Processed_Data/spatial/sut43_terrain_ontology/race_trf_bedrock_late_braking \\
        --km-start 31.0 --km-end 34.0
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CORRIDOR_DIR = (
    BASE_DIR / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "race_trf_bedrock_late_braking"
)


def _load_cells(path: Path) -> list[dict[str, Any]]:
    report = json.loads(path.read_text(encoding="utf-8"))
    return list(report.get("cells") or [])


def _find_cell(cells: list[dict[str, Any]], *, tier: str, grade: str, mode: str) -> dict[str, Any] | None:
    for cell in cells:
        if (
            cell.get("friction_tier") == tier
            and cell.get("grade_band") == grade
            and cell.get("locomotion_mode") == mode
        ):
            return cell
    return None


def verify_corridor_cells(
    corridor_dir: Path,
    *,
    km_start: float,
    km_end: float,
    subjects: tuple[str, ...] = ("Subject_A", "Subject_B"),
) -> int:
    corridor_dir = corridor_dir if corridor_dir.is_absolute() else BASE_DIR / corridor_dir
    max_metres = int(round((km_end - km_start) * 1000 * 1.05))  # 5% slack for partial-km bounds
    errors: list[str] = []
    rows: list[str] = []

    for subject in subjects:
        report_path = corridor_dir / f"training_residual_report_{subject}.json"
        if not report_path.exists():
            errors.append(f"Missing report: {report_path.relative_to(BASE_DIR)}")
            continue
        cells = _load_cells(report_path)
        cell = _find_cell(cells, tier="F3", grade="downhill", mode="hike")
        if not cell:
            errors.append(f"{subject}: no F3 · downhill · hike cell in corridor report")
            continue
        n = int(cell.get("metre_count") or 0)
        delta = cell.get("delta_ti_mean")
        km_lo = cell.get("course_km_start")
        km_hi = cell.get("course_km_end")
        rows.append(
            f"  {subject}: ΔTI={delta:+.3f}  km {km_lo}–{km_hi}  metre_count={n}"
            if delta is not None
            else f"  {subject}: km {km_lo}–{km_hi}  metre_count={n}"
        )
        if n > max_metres:
            errors.append(
                f"{subject}: metre_count={n} exceeds corridor envelope "
                f"km {km_start}–{km_end} (max ~{max_metres} m) — re-run TRF after spine dedup"
            )

    print(f"Corridor TRF blog QC — {corridor_dir.relative_to(BASE_DIR)}")
    print(f"  Analysis envelope: km {km_start}–{km_end} (max metre_count ~{max_metres})")
    for row in rows:
        print(row)

    if errors:
        print("\nFAIL:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("\nOK corridor F3 · downhill · hike cells within geographic envelope.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify corridor TRF cells for blog publish.")
    parser.add_argument("--corridor-dir", type=Path, default=DEFAULT_CORRIDOR_DIR)
    parser.add_argument("--km-start", type=float, default=31.0)
    parser.add_argument("--km-end", type=float, default=34.0)
    args = parser.parse_args(argv)
    return verify_corridor_cells(
        args.corridor_dir,
        km_start=args.km_start,
        km_end=args.km_end,
    )


if __name__ == "__main__":
    raise SystemExit(main())
