#!/usr/bin/env python3
"""
Bootstrap machine draft for SUT_43 finish tail (km 42.5–43.0 → organiser Mål).

Writes config/spatial_terrain_map_sut43_finish_tail.json — does NOT touch locked
config/spatial_terrain_map_sut43_finish.json or spatial_terrain_map_sut43_full.json.

Usage:
    python3 04_Python_Scripts/spatial/build_finish_tail_terrain_draft.py --write

    python3 04_Python_Scripts/spatial/build_finish_tail_terrain_draft.py --write \\
        --export-chunk-index 0 \\
        --chunk-output 06_Visualizations/sut43_hitl_finish/chunk_f02_km42.5-43.0.png
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "04_Python_Scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "04_Python_Scripts"))

from spatial.corridor_multi_fit import align_activity_multi  # noqa: E402
from spatial.corridor_scope import SUT43_EXPERIMENT_RACE_ID, load_sut43_experiment_window  # noqa: E402
from spatial.majority_vote_draft import build_and_write_majority_vote  # noqa: E402
from spatial.spatial_align import load_manifest  # noqa: E402
from spatial.terrain_map_gen import build_terrain_map, write_terrain_map  # noqa: E402
from spatial.ti_draft_layer import (  # noqa: E402
    build_ti_draft_segments,
    ti_draft_metadata,
    write_ti_draft_to_terrain_map,
)

SUT43_FINISH_TAIL_KM_START = 42.5
SUT43_FINISH_TAIL_KM_END = 43.0
SUT43_FINISH_TAIL_SECTOR_ID = "finish_tail"
SUT43_CORRIDOR_ID = "sut43_terrain_ontology"

DEFAULT_PANEL_OUT = (
    _REPO_ROOT / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "panel_finish_tail_1m.parquet"
)
DEFAULT_MAP_OUT = _REPO_ROOT / "config" / "spatial_terrain_map_sut43_finish_tail.json"
DEFAULT_ONTOLOGY = (
    _REPO_ROOT / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "finish_tail_draft"
)
DEFAULT_MANIFEST = _REPO_ROOT / "config" / "spatial_align_manifest_sut43.local.json"

RACE_ACTIVITY_SPECS = (
    {"donor_id": "Subject_A", "activity_id": "SUT43_20260418", "session_type": "race", "align_mode": "stream"},
    {"donor_id": "Subject_B", "activity_id": "19000570862", "session_type": "race", "align_mode": "stream"},
)


def _race_panel_tail(panel: pd.DataFrame, *, km_lo: float, km_hi: float) -> pd.DataFrame:
    work = panel[(panel["course_km"] >= km_lo) & (panel["course_km"] < km_hi)].copy()
    if "session_type" in work.columns:
        race = work[work["session_type"] == "race"]
        if not race.empty:
            return race
    return work


def build_finish_tail_panel(
    manifest_path: Path,
    *,
    km_lo: float = SUT43_FINISH_TAIL_KM_START,
    km_hi: float = SUT43_FINISH_TAIL_KM_END,
    step_m: float = 1.0,
) -> tuple[pd.DataFrame, dict]:
    manifest = load_manifest(manifest_path)
    frames: list[pd.DataFrame] = []
    run_meta: list[dict] = []
    for spec in RACE_ACTIVITY_SPECS:
        grid, meta = align_activity_multi(
            spec,
            manifest,
            km_start=km_lo,
            km_end=km_hi,
            step_m=step_m,
            project_course=False,
            enrich_if_needed=False,
            race_id=manifest.get("race_id", SUT43_EXPERIMENT_RACE_ID),
            corridor_id=manifest.get("corridor_id", SUT43_CORRIDOR_ID),
            write=True,
        )
        if grid.empty:
            raise ValueError(f"No grid samples for {spec['donor_id']}/{spec['activity_id']} @ km {km_lo}–{km_hi}")
        frames.append(grid)
        run_meta.append(meta)

    panel = pd.concat(frames, ignore_index=True)
    panel_meta = {
        "phase": "finish_tail_panel",
        "km_window": [km_lo, km_hi],
        "row_count": int(len(panel)),
        "race_row_count": int(len(panel)),
        "unique_course_m": int(panel["course_m"].nunique()),
        "course_km_min": float(panel["course_km"].min()),
        "course_km_max": float(panel["course_km"].max()),
        "donors": run_meta,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "notes": (
            "Race streams only (Subject_A + Subject_B). "
            "Downstream of locked finish_band @ km 42.5 — draft bootstrap toward organiser Mål @ km 43.0."
        ),
    }
    return panel, panel_meta


def build_finish_tail_terrain_map(
    panel: pd.DataFrame,
    *,
    km_lo: float = SUT43_FINISH_TAIL_KM_START,
    km_hi: float = SUT43_FINISH_TAIL_KM_END,
    reference_donor: str = "Subject_A",
) -> dict:
    work = _race_panel_tail(panel, km_lo=km_lo, km_hi=km_hi)
    payload = build_terrain_map(work, reference_donor=reference_donor, n_clusters=6, method="gmm")

    _, _, corridor_meta = load_sut43_experiment_window(
        km_start=km_lo,
        km_end=km_hi,
        sector_id=SUT43_FINISH_TAIL_SECTOR_ID,
    )
    corridor_meta["sector_lock_version"] = None
    corridor_meta["sector_viewport_km_end"] = km_hi
    corridor_meta["upstream_sector_boundary_km"] = km_lo
    corridor_meta["downstream_sector_boundary_km"] = km_hi
    corridor_meta["gps_bridge_overlap_km"] = None
    corridor_meta["notes"] = (
        "Finish tail bootstrap (km 42.5–43.0): Loen-Alsvik asphalt into Alsvik / organiser Mål. "
        "Machine GMM draft — race streams only (Subject_A + Subject_B). "
        "Seam @ km 42.5 defers to locked finish_band S1/F0 in spatial_terrain_map_sut43_finish.json."
    )
    corridor_meta["geographic_anchors"] = [
        {
            "anchor_id": "finish_band_seam",
            "display_name": "finish_band downstream seam (Loen-Alsvik asphalt)",
            "course_km": km_lo,
            "role": "upstream_sector_boundary",
            "notes": "Locked S1/F0 @ km 42.0–42.5 in spatial_terrain_map_sut43_finish.json",
        },
        {
            "anchor_id": "official_finish",
            "display_name": "Official finish (Mål)",
            "course_km": 43.0,
            "role": "organiser_checkpoint",
            "registry_ref": "race_corridors.json → SUT_43.checkpoints.Mål",
            "notes": "Organiser distance 43 km on stream-distance axis",
        },
    ]
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
            "sector_id": SUT43_FINISH_TAIL_SECTOR_ID,
            "operator_gold_spans": [],
            "manual_overrides": [],
            "friction_spans": [],
            "authority": "gmm_draft",
            "notes": (
                "Finish-tail bootstrap draft — not operator gold. "
                "Seam @ km 42.5: expect S1/F0 continuous from locked finish_band. "
                "Operator lock required before panel_full / unified map merge."
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


def verify_seam_at_425(locked_finish_map: Path, panel: pd.DataFrame) -> dict:
    """Compare locked finish_band @ km 42.5 with draft tail telemetry."""
    locked = json.loads(locked_finish_map.read_text(encoding="utf-8"))
    spans = locked.get("hitl", {}).get("operator_gold_spans", [])
    last = spans[-1] if spans else {}
    seam_window = panel[(panel["course_km"] >= 42.45) & (panel["course_km"] <= 42.55)]
    race = seam_window[seam_window["session_type"] == "race"] if "session_type" in seam_window.columns else seam_window

    ti_med = float(race["ti"].median()) if "ti" in race.columns and not race.empty else None
    grade_med = float(race["grade_pct"].median()) if "grade_pct" in race.columns and not race.empty else None

    upstream_class = last.get("surface_class")
    upstream_tier = last.get("friction_tier")
    continuous = upstream_class == "S1" and upstream_tier == "F0"
    ti_in_f0 = ti_med is not None and 1.15 <= ti_med <= 1.45

    return {
        "seam_km": 42.5,
        "upstream_locked_span": {
            "course_km_start": last.get("course_km_start"),
            "course_km_end": last.get("course_km_end"),
            "surface_class": upstream_class,
            "friction_tier": upstream_tier,
        },
        "tail_telemetry_at_seam": {
            "n_samples": int(len(race)),
            "ti_median": ti_med,
            "grade_pct_median": grade_med,
        },
        "continuity_check": {
            "surface_tier_match_expected": continuous,
            "ti_in_f0_band": ti_in_f0,
            "verdict": "PASS" if continuous and ti_in_f0 else "REVIEW",
        },
        "notes": (
            "Seam expects S1/F0 asphalt continuous from locked finish_band span ending @ km 42.5. "
            "Draft tail GMM may propose micro-segments — operator adjudication required."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SUT_43 finish tail draft (km 42.5–43.0)")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--panel-out", type=Path, default=DEFAULT_PANEL_OUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_MAP_OUT)
    parser.add_argument("--ontology-dir", type=Path, default=DEFAULT_ONTOLOGY)
    parser.add_argument("--locked-finish-map", type=Path, default=_REPO_ROOT / "config/spatial_terrain_map_sut43_finish.json")
    parser.add_argument("--km-start", type=float, default=SUT43_FINISH_TAIL_KM_START)
    parser.add_argument("--km-end", type=float, default=SUT43_FINISH_TAIL_KM_END)
    parser.add_argument("--reference-donor", default="Subject_A")
    parser.add_argument("--write", action="store_true", help="Write panel, terrain map, and sidecars")
    parser.add_argument(
        "--export-chunk-index",
        type=int,
        default=None,
        help="Export validation_dashboard chunk (0 = km 42.5–43.0 when chunk-km=0.5)",
    )
    parser.add_argument("--chunk-km", type=float, default=0.5, help="Chunk width for HITL export")
    parser.add_argument("--chunk-output", type=Path, default=None)
    args = parser.parse_args()

    manifest_path = args.manifest if args.manifest.is_absolute() else _REPO_ROOT / args.manifest
    panel_out = args.panel_out if args.panel_out.is_absolute() else _REPO_ROOT / args.panel_out
    out_path = args.output if args.output.is_absolute() else _REPO_ROOT / args.output
    ontology_dir = args.ontology_dir if args.ontology_dir.is_absolute() else _REPO_ROOT / args.ontology_dir
    locked_map = args.locked_finish_map if args.locked_finish_map.is_absolute() else _REPO_ROOT / args.locked_finish_map

    panel, panel_meta = build_finish_tail_panel(
        manifest_path,
        km_lo=args.km_start,
        km_hi=args.km_end,
    )
    payload = build_finish_tail_terrain_map(
        panel,
        km_lo=args.km_start,
        km_hi=args.km_end,
        reference_donor=args.reference_donor,
    )
    seam_report = verify_seam_at_425(locked_map, panel)

    if not args.write and args.export_chunk_index is None:
        print(json.dumps({"panel_meta": panel_meta, "seam_report": seam_report, "n_segments": len(payload["segments"])}, indent=2))
        parser.error("Pass --write and/or --export-chunk-index")

    if args.write:
        panel_out.parent.mkdir(parents=True, exist_ok=True)
        panel.to_parquet(panel_out, index=False)
        meta_path = panel_out.with_name("panel_finish_tail_meta.json")
        meta_path.write_text(json.dumps({**panel_meta, "panel_path": str(panel_out.relative_to(_REPO_ROOT)), "seam_report": seam_report}, indent=2), encoding="utf-8")

        write_terrain_map(payload, out_path)
        work = _race_panel_tail(panel, km_lo=args.km_start, km_hi=args.km_end)
        build_and_write_majority_vote(
            work,
            km_lo=args.km_start,
            km_hi=args.km_end,
            output_dir=ontology_dir,
        )
        seam_out = ontology_dir / "seam_verification_42_5.json"
        seam_out.parent.mkdir(parents=True, exist_ok=True)
        seam_out.write_text(json.dumps(seam_report, indent=2), encoding="utf-8")

        print(
            f"OK finish tail panel → {panel_out.relative_to(_REPO_ROOT)} "
            f"(n={len(panel)}, coverage {panel_meta['course_km_min']:.3f}–{panel_meta['course_km_max']:.3f} km)"
        )
        print(
            f"OK finish tail terrain map → {out_path.relative_to(_REPO_ROOT)} "
            f"({len(payload['segments'])} segments, "
            f"credibility={payload['calibration_credibility_index']['index']:.3f})"
        )
        print(f"Seam @ km 42.5: {seam_report['continuity_check']['verdict']}")

    if args.export_chunk_index is not None:
        from spatial.validation_dashboard import main as dashboard_main

        chunk_out = args.chunk_output
        if chunk_out is None:
            lo = args.km_start + args.export_chunk_index * args.chunk_km
            hi = min(lo + args.chunk_km, args.km_end)
            chunk_out = (
                _REPO_ROOT
                / "06_Visualizations"
                / "sut43_hitl_finish"
                / f"chunk_f02_km{lo:.1f}-{hi:.1f}.png"
            )
        elif not chunk_out.is_absolute():
            chunk_out = _REPO_ROOT / chunk_out

        maj_parquet = ontology_dir / "hitl_v2_majority.parquet"
        dash_argv = [
            "validation_dashboard.py",
            "--terrain-map",
            str(out_path.relative_to(_REPO_ROOT)),
            "--panel",
            str(panel_out.relative_to(_REPO_ROOT)),
            "--km-start",
            str(args.km_start),
            "--km-end",
            str(args.km_end),
            "--chunk-km",
            str(args.chunk_km),
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
            "--with-map",
        ]
        sys.argv = dash_argv
        dashboard_main()


if __name__ == "__main__":
    main()
