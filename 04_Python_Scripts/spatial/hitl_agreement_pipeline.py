#!/usr/bin/env python3
"""
Dual-HITL agreement pipeline — v1 effective, v2 majority vote, agreement layer.

Phase 1 only (no ML training). Does not mutate terrain map HITL entries unless
``--write-sidecar`` is passed for v2 majority segments.
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

from spatial.hitl_agreement import build_agreement_layer, write_agreement_outputs
from spatial.hitl_v1_layer import build_and_write_hitl_v1, build_hitl_v1_effective
from spatial.ti_draft_layer import resolve_km_window
from spatial.validation_dashboard import load_terrain_map

DEFAULT_PANEL = (
    _REPO_ROOT / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology" / "panel_1m.parquet"
)
DEFAULT_TERRAIN_MAP = _REPO_ROOT / "config" / "spatial_terrain_map_sut43.json"
DEFAULT_ONTOLOGY_DIR = (
    _REPO_ROOT / "03_Processed_Data" / "spatial" / "sut43_terrain_ontology"
)


def run_pipeline(
    *,
    terrain_map_path: Path,
    panel_path: Path,
    km_lo: float | None,
    km_hi: float | None,
    output_dir: Path,
    write: bool,
    write_sidecar: bool,
    sigma_gate: bool,
    min_run_m: int,
    regenerate_chunk: int | None,
    chunk_km: float,
) -> dict:
    terrain_map = load_terrain_map(terrain_map_path)
    panel = pd.read_parquet(panel_path)
    resolved_lo, resolved_hi = resolve_km_window(
        terrain_map, panel, km_lo=km_lo, km_hi=km_hi
    )

    from spatial.hitl_v1_layer import build_hitl_v1_effective
    from spatial.majority_vote_draft import (
        build_majority_vote_frame,
        majority_draft_segments,
        majority_vote_metadata,
        write_majority_vote_outputs,
    )

    v1_df = build_hitl_v1_effective(terrain_map, panel, resolved_lo, resolved_hi)
    majority_df = build_majority_vote_frame(
        panel, resolved_lo, resolved_hi, sigma_gate=sigma_gate
    )
    segments = majority_draft_segments(majority_df, min_run_m=min_run_m)

    merged, report = build_agreement_layer(
        v1_df,
        majority_df,
        km_lo=resolved_lo,
        km_hi=resolved_hi,
        min_run_m=min_run_m,
        terrain_map=terrain_map,
    )

    agr_parquet = output_dir / "hitl_agreement.parquet"
    agr_json = output_dir / "hitl_agreement.json"
    if write:
        build_and_write_hitl_v1(
            terrain_map, panel, km_lo=resolved_lo, km_hi=resolved_hi, output_dir=output_dir
        )
        donors = sorted(panel["donor_id"].unique().tolist())
        meta = majority_vote_metadata(
            km_lo=resolved_lo,
            km_hi=resolved_hi,
            donors=donors,
            n_metres=len(majority_df),
            n_segments=len(segments),
            sigma_gate=sigma_gate,
        )
        write_majority_vote_outputs(
            majority_df,
            segments,
            meta,
            output_dir=output_dir,
            write_sidecar_to_map=terrain_map if write_sidecar else None,
            terrain_map_path=terrain_map_path if write_sidecar else None,
        )
        write_agreement_outputs(merged, report, output_dir=output_dir)

    chunk_path: Path | None = None
    if regenerate_chunk is not None:
        chunk_path = _regenerate_dashboard_chunk(
            terrain_map_path=terrain_map_path,
            panel_path=panel_path,
            output_dir=_REPO_ROOT / "06_Visualizations" / "sut43_hitl",
            chunk_index=regenerate_chunk,
            chunk_km=chunk_km,
            agreement_parquet=agr_parquet if write else None,
            ontology_dir=output_dir,
        )

    metrics = report["metrics"]
    disagreements = report.get("disagreement_spans") or []

    summary = {
        "km_window": (resolved_lo, resolved_hi),
        "outputs": {
            "hitl_v1_effective": str(output_dir / "hitl_v1_effective.parquet"),
            "hitl_v2_majority_parquet": str(output_dir / "hitl_v2_majority.parquet"),
            "hitl_v2_majority_json": str(output_dir / "hitl_v2_majority.json"),
            "hitl_agreement_parquet": str(agr_parquet),
            "hitl_agreement_json": str(agr_json),
        },
        "gold_metres": metrics["gold_metres"],
        "silver_metres": metrics["silver_metres"],
        "cohens_kappa": metrics["cohens_kappa"],
        "agreement_pct": metrics["agreement_pct"],
        "tier_counts": metrics["tier_counts"],
        "example_disagreements": [
            {
                "km": f"{d['course_km_start']:.3f}–{d['course_km_end']:.3f}",
                "label": d.get("surface_class"),
            }
            for d in disagreements[:5]
        ],
        "chunk_path": str(chunk_path) if chunk_path else None,
    }
    return summary


def _regenerate_dashboard_chunk(
    *,
    terrain_map_path: Path,
    panel_path: Path,
    output_dir: Path,
    chunk_index: int,
    chunk_km: float,
    agreement_parquet: Path | None,
    ontology_dir: Path,
) -> Path:
    from spatial.corridor_scope import SUT43_PRIMARY_KM_END, SUT43_PRIMARY_KM_START
    from spatial.validation_dashboard import (
        iter_review_chunks,
        load_terrain_map,
        render_validation_dashboard,
        resolve_ti_draft_segments,
        resolve_viewport_km,
        ti_draft_segments_from_map,
    )

    terrain_map = load_terrain_map(terrain_map_path)
    panel = pd.read_parquet(panel_path)
    work = panel.sort_values("course_m")
    p_lo, p_hi = float(work["course_km"].min()), float(work["course_km"].max())
    km_start = max(SUT43_PRIMARY_KM_START, p_lo)
    km_end = min(SUT43_PRIMARY_KM_END, p_hi)
    chunks = iter_review_chunks(km_start, km_end, chunk_km=chunk_km)
    by_idx = {i: (lo, hi) for i, lo, hi in chunks}
    if chunk_index not in by_idx:
        raise ValueError(
            f"chunk-index {chunk_index} out of range (0..{len(chunks) - 1})"
        )
    lo, hi = by_idx[chunk_index]

    agr_path = agreement_parquet or (ontology_dir / "hitl_agreement.parquet")
    agreement_df = pd.read_parquet(agr_path) if agr_path.exists() else None
    maj_path = ontology_dir / "hitl_v2_majority.parquet"
    majority_df = pd.read_parquet(maj_path) if maj_path.exists() else None

    full_lo, full_hi = resolve_viewport_km(terrain_map, work)
    stored_ti = ti_draft_segments_from_map(terrain_map)
    ti_draft = resolve_ti_draft_segments(
        terrain_map,
        panel,
        km_lo=full_lo,
        km_hi=full_hi,
        variance_threshold=0.30,
        enable=bool(stored_ti),
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"chunk_{chunk_index:02d}_km{lo:.0f}-{hi:.0f}.png"
    render_validation_dashboard(
        terrain_map,
        panel,
        output_path=out_path,
        chunk_window=(lo, hi),
        with_map=True,
        ti_draft_segments=ti_draft,
        show_ti_draft=bool(stored_ti),
        agreement_df=agreement_df,
        majority_df=majority_df,
        show_agreement=agreement_df is not None,
        show_majority_draft=majority_df is not None,
        gap_class_row_only=True,
        decision_mode=True,
    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dual-HITL agreement pipeline (v1 effective vs v2 majority vote)"
    )
    parser.add_argument(
        "--terrain-map",
        type=Path,
        default=DEFAULT_TERRAIN_MAP,
    )
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--km-start", type=float, default=None)
    parser.add_argument("--km-end", type=float, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_ONTOLOGY_DIR,
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write parquet/JSON outputs to --output-dir",
    )
    parser.add_argument(
        "--write-sidecar",
        action="store_true",
        help="Also merge hitl_v2 sidecar into terrain map JSON",
    )
    parser.add_argument(
        "--sigma-gate",
        action="store_true",
        help="Exclude high-σ metres from v2 voter eligibility",
    )
    parser.add_argument("--min-run-m", type=int, default=5)
    parser.add_argument(
        "--regenerate-chunk",
        type=int,
        default=None,
        help="Regenerate validation_dashboard chunk PNG with agreement overlay",
    )
    parser.add_argument(
        "--chunk-km",
        type=float,
        default=1.0,
        help="Chunk width for --regenerate-chunk (default 1 km)",
    )
    args = parser.parse_args()

    tmap = args.terrain_map if args.terrain_map.is_absolute() else _REPO_ROOT / args.terrain_map
    panel = args.panel if args.panel.is_absolute() else _REPO_ROOT / args.panel
    out_dir = args.output_dir if args.output_dir.is_absolute() else _REPO_ROOT / args.output_dir

    if not args.write and not args.regenerate_chunk:
        parser.error("Pass --write and/or --regenerate-chunk to produce outputs")

    summary = run_pipeline(
        terrain_map_path=tmap,
        panel_path=panel,
        km_lo=args.km_start,
        km_hi=args.km_end,
        output_dir=out_dir,
        write=args.write,
        write_sidecar=args.write_sidecar,
        sigma_gate=args.sigma_gate,
        min_run_m=args.min_run_m,
        regenerate_chunk=args.regenerate_chunk,
        chunk_km=args.chunk_km,
    )

    print(
        f"OK dual-HITL pipeline km {summary['km_window'][0]:.1f}–{summary['km_window'][1]:.1f}"
    )
    print(
        f"   gold: {summary['gold_metres']} m | silver: {summary['silver_metres']} m | "
        f"κ={summary['cohens_kappa']} | agreement={summary['agreement_pct']}%"
    )
    print(f"   tiers: {json.dumps(summary['tier_counts'])}")
    if summary["example_disagreements"]:
        print("   example disagreements:")
        for ex in summary["example_disagreements"]:
            print(f"     {ex['km']} ({ex['label']})")
    if summary["chunk_path"]:
        rel = Path(summary["chunk_path"]).relative_to(_REPO_ROOT)
        print(f"   chunk → {rel}")
    if args.write:
        for key, path in summary["outputs"].items():
            print(f"   {key} → {Path(path).relative_to(_REPO_ROOT)}")


if __name__ == "__main__":
    main()
