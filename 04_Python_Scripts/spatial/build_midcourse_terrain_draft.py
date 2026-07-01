#!/usr/bin/env python3
"""
Bootstrap machine draft for dalevatn_midcourse (SUT_43 km 8–22).

Writes config/spatial_terrain_map_sut43_midcourse.json — does NOT touch
start/upstream/gramstad terrain maps.

Usage:
    python3 04_Python_Scripts/spatial/build_midcourse_terrain_draft.py --write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "04_Python_Scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "04_Python_Scripts"))

from spatial.corridor_scope import (
    SUT43_MIDCOURSE_KM_END,
    SUT43_MIDCOURSE_KM_START,
    SUT43_MIDCOURSE_SECTOR_ID,
    SUT43_MIDCOURSE_VIEWPORT_KM_END,
    load_sut43_experiment_window,
)
from spatial.majority_vote_draft import build_and_write_majority_vote
from spatial.terrain_map_gen import build_terrain_map, write_terrain_map
from spatial.ti_draft_layer import (
    build_ti_draft_segments,
    ti_draft_metadata,
    write_ti_draft_to_terrain_map,
)

DEFAULT_PANEL = (
    _REPO_ROOT
    / "03_Processed_Data"
    / "spatial"
    / "sut43_terrain_ontology"
    / "panel_midcourse_1m_spine.parquet"
)
DEFAULT_OUT = _REPO_ROOT / "config" / "spatial_terrain_map_sut43_midcourse.json"
DEFAULT_ONTOLOGY = (
    _REPO_ROOT / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "midcourse_draft"
)


def _resolve_panel_km(panel: pd.DataFrame) -> pd.Series:
    if "course_km" in panel.columns and panel["course_km"].notna().any():
        return pd.to_numeric(panel["course_km"], errors="coerce")
    if "ref_chainage_m" in panel.columns:
        return pd.to_numeric(panel["ref_chainage_m"], errors="coerce") / 1000.0
    if "activity_course_km" in panel.columns:
        return pd.to_numeric(panel["activity_course_km"], errors="coerce")
    raise ValueError("Panel lacks course_km / ref_chainage_m / activity_course_km")


def _race_panel_midcourse(panel: pd.DataFrame, *, km_lo: float, km_hi: float) -> pd.DataFrame:
    work = panel.copy()
    work["course_km"] = _resolve_panel_km(work)
    if "course_m" not in work.columns:
        work["course_m"] = (work["course_km"] * 1000.0).round().astype(float)
    work = work[(work["course_km"] >= km_lo) & (work["course_km"] < km_hi)].copy()
    if "session_type" in work.columns:
        race = work[work["session_type"] == "race"]
        if not race.empty:
            work = race
    if "donor_id" in work.columns:
        work = work.drop_duplicates(subset=["course_m", "donor_id"], keep="first")
    return work


def _load_geographic_anchors(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    corridor = data.get("corridor") or {}
    anchors = corridor.get("geographic_anchors")
    return list(anchors) if anchors else []


def build_midcourse_terrain_map(
    panel: pd.DataFrame,
    *,
    km_lo: float = SUT43_MIDCOURSE_KM_START,
    km_hi: float = SUT43_MIDCOURSE_KM_END,
    reference_donor: str = "Subject_A",
    existing_map_path: Path | None = None,
) -> dict:
    work = _race_panel_midcourse(panel, km_lo=km_lo, km_hi=km_hi)
    payload = build_terrain_map(
        work, reference_donor=reference_donor, n_clusters=6, method="gmm", min_run_m=5
    )

    _, _, corridor_meta = load_sut43_experiment_window(
        km_start=km_lo,
        km_end=km_hi,
        sector_id=SUT43_MIDCOURSE_SECTOR_ID,
    )
    corridor_meta["sector_lock_version"] = None
    corridor_meta["sector_viewport_km_end"] = SUT43_MIDCOURSE_VIEWPORT_KM_END
    corridor_meta["upstream_sector_boundary_km"] = km_lo
    corridor_meta["downstream_sector_boundary_km"] = km_hi
    anchors_path = existing_map_path or DEFAULT_OUT
    corridor_meta["geographic_anchors"] = _load_geographic_anchors(anchors_path)
    corridor_meta["notes"] = (
        "GMM machine draft for dalevatn_midcourse (km 8–22). "
        "Subject_A km 8–22 telemetry interpolated on interim scaffold — operator gold required. "
        "Seam @ km 8.0 from Phase E start; seam @ km 22.0 into dale_paradisskaret_upstream."
    )
    payload["corridor"] = corridor_meta

    segs = [
        s
        for s in payload["segments"]
        if float(s["course_km_end"]) > km_lo and float(s["course_km_start"]) < km_hi
    ]
    for s in segs:
        s["course_km_start"] = max(float(s["course_km_start"]), km_lo)
        s["course_km_end"] = min(float(s["course_km_end"]), km_hi)
        s["course_m_start"] = s["course_km_start"] * 1000.0
        s["course_m_end"] = s["course_km_end"] * 1000.0
    payload["segments"] = segs

    hitl = dict(payload.get("hitl") or {})
    hitl.update(
        {
            "status": "draft",
            "sector_id": SUT43_MIDCOURSE_SECTOR_ID,
            "operator_gold_spans": [],
            "manual_overrides": [],
            "friction_spans": [],
            "authority": "gmm_draft",
            "notes": (
                "Mid-course GMM bootstrap — not operator gold. "
                "Promote locks via gold_span_editor.py against this file only."
            ),
        }
    )
    payload["hitl"] = hitl

    ti_segs = build_ti_draft_segments(work, km_lo, km_hi)
    ti_meta = ti_draft_metadata(
        variance_threshold=0.30,
        min_run_m=5,
        km_lo=km_lo,
        km_hi=km_hi,
        n_segments=len(ti_segs),
    )
    return write_ti_draft_to_terrain_map(payload, ti_segs, meta=ti_meta)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build dalevatn_midcourse terrain map GMM draft (km 8–22)")
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--ontology-dir", type=Path, default=DEFAULT_ONTOLOGY)
    parser.add_argument("--km-start", type=float, default=SUT43_MIDCOURSE_KM_START)
    parser.add_argument("--km-end", type=float, default=SUT43_MIDCOURSE_KM_END)
    parser.add_argument("--reference-donor", default="Subject_A")
    parser.add_argument("--write", action="store_true", help="Write terrain map + sidecars")
    parser.add_argument(
        "--export-chunk-index",
        type=int,
        default=None,
        help="Re-export validation_dashboard chunk (0=km 8–9, 1=km 9–10, …)",
    )
    parser.add_argument("--chunk-output", type=Path, default=None)
    args = parser.parse_args()

    panel_path = args.panel if args.panel.is_absolute() else _REPO_ROOT / args.panel
    out_path = args.output if args.output.is_absolute() else _REPO_ROOT / args.output
    ontology_dir = args.ontology_dir if args.ontology_dir.is_absolute() else _REPO_ROOT / args.ontology_dir

    panel = pd.read_parquet(panel_path)
    payload = build_midcourse_terrain_map(
        panel,
        km_lo=args.km_start,
        km_hi=args.km_end,
        reference_donor=args.reference_donor,
        existing_map_path=out_path,
    )

    if not args.write and args.export_chunk_index is None:
        parser.error("Pass --write and/or --export-chunk-index")

    if args.write:
        write_terrain_map(payload, out_path)
        work = _race_panel_midcourse(panel, km_lo=args.km_start, km_hi=args.km_end)
        build_and_write_majority_vote(
            work,
            km_lo=args.km_start,
            km_hi=args.km_end,
            output_dir=ontology_dir,
        )
        print(
            f"OK mid-course terrain map → {out_path.relative_to(_REPO_ROOT)} "
            f"({len(payload['segments'])} segments, "
            f"credibility={payload['calibration_credibility_index']['index']:.3f})"
        )

    if args.export_chunk_index is not None:
        from spatial.validation_dashboard import main as dashboard_main

        chunk_out = args.chunk_output
        if chunk_out is None:
            lo = args.km_start + args.export_chunk_index
            hi = lo + 1.0
            chunk_out = (
                _REPO_ROOT
                / "06_Visualizations"
                / "sut43_hitl_midcourse"
                / f"chunk_m{args.export_chunk_index:02d}_km{lo:.0f}-{hi:.0f}.png"
            )
        elif not chunk_out.is_absolute():
            chunk_out = _REPO_ROOT / chunk_out

        maj_parquet = ontology_dir / "hitl_v2_majority.parquet"
        dash_argv = [
            "validation_dashboard.py",
            "--terrain-map",
            str(out_path.relative_to(_REPO_ROOT)),
            "--panel",
            str(panel_path.relative_to(_REPO_ROOT)),
            "--km-start",
            str(args.km_start),
            "--km-end",
            str(args.km_end),
            "--chunk-km",
            "1",
            "--chunk-index",
            str(args.export_chunk_index),
            "--output-dir",
            str(chunk_out.parent.relative_to(_REPO_ROOT)),
            "--output",
            str(chunk_out.relative_to(_REPO_ROOT)),
            "--ti-draft",
            "--majority-draft",
            "--majority-parquet",
            str(maj_parquet.relative_to(_REPO_ROOT)),
        ]
        sys.argv = dash_argv
        dashboard_main()


if __name__ == "__main__":
    main()
