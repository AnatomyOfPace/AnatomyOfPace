#!/usr/bin/env python3
"""
Bootstrap machine draft for dale_paradisskaret_upstream (SUT_43 km 22–29).

Writes config/spatial_terrain_map_sut43_upstream.json — does NOT touch
config/spatial_terrain_map_sut43.json (gramstad_band operator gold km 29–41).

Usage:
    python3 04_Python_Scripts/spatial/build_upstream_terrain_draft.py --write

    python3 04_Python_Scripts/spatial/build_upstream_terrain_draft.py --write \\
        --export-chunk-index 1 \\
        --chunk-output 06_Visualizations/sut43_hitl_upstream/chunk_u01_km23-24.png
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
    SUT43_UPSTREAM_KM_END,
    SUT43_UPSTREAM_KM_START,
    SUT43_UPSTREAM_SECTOR_ID,
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
    _REPO_ROOT / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "panel_1m.parquet"
)
DEFAULT_OUT = _REPO_ROOT / "config" / "spatial_terrain_map_sut43_upstream.json"
DEFAULT_ONTOLOGY = (
    _REPO_ROOT / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "upstream_draft"
)


def _race_panel_upstream(panel: pd.DataFrame, *, km_lo: float, km_hi: float) -> pd.DataFrame:
    work = panel[(panel["course_km"] >= km_lo) & (panel["course_km"] < km_hi)].copy()
    if "session_type" in work.columns:
        race = work[work["session_type"] == "race"]
        if not race.empty:
            return race
    return work


def build_upstream_terrain_map(
    panel: pd.DataFrame,
    *,
    km_lo: float = SUT43_UPSTREAM_KM_START,
    km_hi: float = SUT43_UPSTREAM_KM_END,
    reference_donor: str = "Subject_A",
) -> dict:
    work = _race_panel_upstream(panel, km_lo=km_lo, km_hi=km_hi)
    payload = build_terrain_map(work, reference_donor=reference_donor, n_clusters=6, method="gmm")

    _, _, corridor_meta = load_sut43_experiment_window(
        km_start=km_lo,
        km_end=km_hi,
        sector_id=SUT43_UPSTREAM_SECTOR_ID,
    )
    corridor_meta["sector_lock_version"] = None
    corridor_meta["sector_viewport_km_end"] = km_hi + 0.5
    corridor_meta["gps_bridge_overlap_km"] = [km_lo, km_hi]
    corridor_meta["downstream_sector_boundary_km"] = km_hi
    corridor_meta["notes"] = (
        "Machine draft for dale_paradisskaret_upstream (km 22–29). "
        "Operator gold for gramstad_band km 29–41 remains in spatial_terrain_map_sut43.json."
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
            "sector_id": SUT43_UPSTREAM_SECTOR_ID,
            "operator_gold_spans": [],
            "manual_overrides": [],
            "friction_spans": [],
            "authority": "gmm_draft",
            "notes": (
                "Upstream bootstrap draft — not operator gold. "
                "Seam @ km 29.0 defers to gramstad_band lock in spatial_terrain_map_sut43.json."
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
    parser = argparse.ArgumentParser(
        description="Build dale_paradisskaret_upstream terrain map draft (km 22–29)"
    )
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--ontology-dir", type=Path, default=DEFAULT_ONTOLOGY)
    parser.add_argument("--km-start", type=float, default=SUT43_UPSTREAM_KM_START)
    parser.add_argument("--km-end", type=float, default=SUT43_UPSTREAM_KM_END)
    parser.add_argument("--reference-donor", default="Subject_A")
    parser.add_argument("--write", action="store_true", help="Write terrain map + sidecars")
    parser.add_argument(
        "--export-chunk-index",
        type=int,
        default=None,
        help="Re-export validation_dashboard chunk (0=km 22–23, 1=km 23–24, …)",
    )
    parser.add_argument("--chunk-output", type=Path, default=None)
    args = parser.parse_args()

    panel_path = args.panel if args.panel.is_absolute() else _REPO_ROOT / args.panel
    out_path = args.output if args.output.is_absolute() else _REPO_ROOT / args.output
    ontology_dir = args.ontology_dir if args.ontology_dir.is_absolute() else _REPO_ROOT / args.ontology_dir

    panel = pd.read_parquet(panel_path)
    payload = build_upstream_terrain_map(
        panel,
        km_lo=args.km_start,
        km_hi=args.km_end,
        reference_donor=args.reference_donor,
    )

    if not args.write and args.export_chunk_index is None:
        parser.error("Pass --write and/or --export-chunk-index")

    if args.write:
        write_terrain_map(payload, out_path)
        work = _race_panel_upstream(panel, km_lo=args.km_start, km_hi=args.km_end)
        build_and_write_majority_vote(
            work,
            km_lo=args.km_start,
            km_hi=args.km_end,
            output_dir=ontology_dir,
        )
        print(
            f"OK upstream terrain map → {out_path.relative_to(_REPO_ROOT)} "
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
                / "sut43_hitl_upstream"
                / f"chunk_u{args.export_chunk_index:02d}_km{lo:.0f}-{hi:.0f}.png"
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
