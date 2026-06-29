#!/usr/bin/env python3
"""
Phase B — end-to-end Garmin `.fit` corridor pipeline.

Chains Wave 2 micro wash → spatial 1 m panel → optional ML feature matrix.
Designed for SUT_43 gramstad_band (km 29–41) and reusable for other manifests.

Usage (from repo root):
    # Full SUT_43 panel rebuild from manifest (micro Parquet must exist or use --wash-all):
    python3 04_Python_Scripts/16_fit_corridor_pipeline.py \\
        --manifest config/spatial_align_manifest_sut43.example.json \\
        --wash-all --rebuild-panel --rebuild-ml-features

    # Wash one activity then align:
    python3 04_Python_Scripts/16_fit_corridor_pipeline.py \\
        --donor Subject_A --activity SUT43_20260418 \\
        --fit 02_Raw_Data/donors/Subject_A/SUT43_20260418.fit \\
        --race SUT_43 --project-course --enrich-ti \\
        --manifest config/spatial_align_manifest_sut43.example.json \\
        --rebuild-panel

Raw `.fit` files live under `02_Raw_Data/donors/{donor_id}/` (gitignored).
See `docs/fit_ingest_workflow.md` for canonical paths and Subject_* naming.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO_ROOT / "04_Python_Scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from fit_micro.activity_frame import micro_parquet_path  # noqa: E402
import importlib.util  # noqa: E402

_wash_spec = importlib.util.spec_from_file_location(
    "fit_micro_wash", _SCRIPTS / "15_fit_micro_wash.py"
)
_wash_mod = importlib.util.module_from_spec(_wash_spec)
_wash_spec.loader.exec_module(_wash_mod)
wash_fit = _wash_mod.wash_fit

from spatial.spatial_align import (  # noqa: E402
    align_panel,
    load_manifest,
    load_manifest_activities,
    panel_parquet_path,
)
from spatial.terrain_ml_features import (  # noqa: E402
    build_ml_feature_matrix,
    write_ml_features,
)

DEFAULT_SUT43_MANIFEST = _REPO_ROOT / "config" / "spatial_align_manifest_sut43.example.json"


def _resolve_manifest(path: Path | None) -> Path:
    p = path or DEFAULT_SUT43_MANIFEST
    return p if p.is_absolute() else _REPO_ROOT / p


def _fit_path_for_activity(spec: dict[str, Any]) -> Path | None:
    """Resolve local `.fit` path for a manifest activity row."""
    donor = spec["donor_id"]
    activity = str(spec["activity_id"])
    candidates = [
        _REPO_ROOT / "02_Raw_Data" / "donors" / donor / f"{activity}.fit",
        _REPO_ROOT / "02_Raw_Data" / "donors" / donor / f"activity_{activity}.fit",
        _REPO_ROOT / "02_Raw_Data" / "donors" / donor / f"SUT43_{activity}.fit",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def wash_manifest_activities(
    manifest_path: Path,
    *,
    race_id: str | None = None,
    project_course: bool = True,
    enrich_ti: bool = True,
    skip_existing: bool = False,
) -> list[dict[str, Any]]:
    """Wash all manifest activities that have a local `.fit` file."""
    manifest = load_manifest(manifest_path)
    rid = race_id or manifest.get("race_id", "SUT_43")
    results: list[dict[str, Any]] = []

    for spec in load_manifest_activities(manifest_path):
        donor = spec["donor_id"]
        activity = str(spec["activity_id"])
        micro_path = micro_parquet_path(donor, activity)
        if skip_existing and micro_path.exists():
            results.append({"donor_id": donor, "activity_id": activity, "skipped": True, "path": str(micro_path)})
            continue

        fit_path = _fit_path_for_activity(spec)
        if fit_path is None:
            results.append(
                {
                    "donor_id": donor,
                    "activity_id": activity,
                    "skipped": True,
                    "reason": "no_local_fit",
                }
            )
            continue

        out = wash_fit(
            fit_path,
            donor_id=donor,
            activity_id=activity,
            race_id=rid,
            project_course=project_course,
            enrich_ti_flag=enrich_ti,
            subject_id=spec.get("subject_id", donor),
        )
        results.append(
            {
                "donor_id": donor,
                "activity_id": activity,
                "fit_path": str(fit_path.relative_to(_REPO_ROOT)),
                "parquet_path": str(out.relative_to(_REPO_ROOT)),
            }
        )
    return results


def rebuild_panel(
    manifest_path: Path,
    *,
    project_course: bool = False,
    enrich_if_needed: bool = True,
    write_fit_panel_alias: bool = True,
) -> dict[str, Any]:
    """Align manifest activities onto 1 m grid and stack panel."""
    manifest = load_manifest(manifest_path)
    activities = load_manifest_activities(manifest_path)
    race_id = manifest.get("race_id", "SUT_43")
    corridor_id = manifest.get("corridor_id", "sut43_terrain_ontology")
    km_start = km_end = None
    if "km_analysis_window" in manifest:
        win = manifest["km_analysis_window"]
        km_start, km_end = float(win[0]), float(win[1])

    panel, meta = align_panel(
        activities,
        km_start=km_start,
        km_end=km_end,
        project_course=project_course,
        enrich_if_needed=enrich_if_needed,
        race_id=race_id,
        corridor_id=corridor_id,
    )

    if write_fit_panel_alias and not panel.empty:
        panel_path = panel_parquet_path(corridor_id=corridor_id)
        fit_panel_path = panel_path.with_name("fit_panel_1m.parquet")
        shutil.copy2(panel_path, fit_panel_path)
        meta["fit_panel_path"] = str(fit_panel_path.relative_to(_REPO_ROOT))

    return meta


def rebuild_ml_features(
    manifest_path: Path,
    *,
    output_path: Path | None = None,
) -> Path:
    """Build ml_features_1m.parquet from current panel + majority vote layer."""
    import pandas as pd

    manifest = load_manifest(manifest_path)
    corridor_id = manifest.get("corridor_id", "sut43_terrain_ontology")
    spatial_dir = _REPO_ROOT / "03_Processed_Data" / "spatial" / corridor_id
    panel_path = spatial_dir / "panel_1m.parquet"
    majority_path = spatial_dir / "hitl_v2_majority.parquet"
    out_path = output_path or spatial_dir / "ml_features_1m.parquet"

    km_lo, km_hi = 29.0, 41.0
    if "km_analysis_window" in manifest:
        win = manifest["km_analysis_window"]
        km_lo, km_hi = float(win[0]), float(win[1])

    panel = pd.read_parquet(panel_path)
    majority_df = pd.read_parquet(majority_path)
    features = build_ml_feature_matrix(panel, majority_df, km_lo=km_lo, km_hi=km_hi)
    meta = {
        "schema_version": "terrain_ml_features_v3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_panel": str(panel_path.relative_to(_REPO_ROOT)),
        "km_start": km_lo,
        "km_end": km_hi,
        "n_metres": len(features),
        "pipeline": "16_fit_corridor_pipeline",
    }
    write_ml_features(features, output_path=out_path, meta=meta)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase B — `.fit` wash → 1 m panel → ML features",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_SUT43_MANIFEST)
    parser.add_argument("--donor", help="Single-activity wash: donor id")
    parser.add_argument("--activity", help="Single-activity wash: activity id")
    parser.add_argument("--fit", type=Path, help="Single-activity wash: source `.fit` path")
    parser.add_argument("--race", default=None, help="Race registry id (e.g. SUT_43)")
    parser.add_argument("--project-course", action="store_true", help="GPX/stream course_km during wash")
    parser.add_argument("--enrich-ti", action="store_true", help="GAP/TI during wash")
    parser.add_argument("--wash-all", action="store_true", help="Wash all manifest activities with local `.fit`")
    parser.add_argument("--skip-existing-wash", action="store_true", help="Skip wash when micro Parquet exists")
    parser.add_argument("--rebuild-panel", action="store_true", help="Rebuild panel_1m from manifest")
    parser.add_argument("--rebuild-ml-features", action="store_true", help="Rebuild ml_features_1m.parquet")
    parser.add_argument(
        "--no-enrich-if-needed",
        action="store_true",
        help="Skip TI enrichment during panel align when ti column missing",
    )
    args = parser.parse_args()

    manifest_path = _resolve_manifest(args.manifest)

    if args.donor and args.activity and args.fit:
        fit_path = args.fit if args.fit.is_absolute() else _REPO_ROOT / args.fit
        manifest = load_manifest(manifest_path)
        race = args.race or manifest.get("race_id", "SUT_43")
        out = wash_fit(
            fit_path,
            donor_id=args.donor,
            activity_id=args.activity,
            race_id=race,
            project_course=args.project_course,
            enrich_ti_flag=args.enrich_ti,
            subject_id=args.donor,
        )
        print(f"OK wash → {out.relative_to(_REPO_ROOT)}")

    if args.wash_all:
        rows = wash_manifest_activities(
            manifest_path,
            race_id=args.race,
            project_course=True,
            enrich_ti=True,
            skip_existing=args.skip_existing_wash,
        )
        print(json.dumps(rows, indent=2))

    if args.rebuild_panel:
        meta = rebuild_panel(
            manifest_path,
            project_course=args.project_course,
            enrich_if_needed=not args.no_enrich_if_needed,
        )
        print(
            f"OK panel n={meta.get('n_activities')} → {meta.get('panel_path')} "
            f"fit_panel={meta.get('fit_panel_path', '(alias not written)')}"
        )

    if args.rebuild_ml_features:
        out = rebuild_ml_features(manifest_path)
        print(f"OK ml features → {out.relative_to(_REPO_ROOT)}")

    if not any(
        [
            args.wash_all,
            args.rebuild_panel,
            args.rebuild_ml_features,
            (args.donor and args.activity and args.fit),
        ]
    ):
        parser.error(
            "Provide --wash-all, --rebuild-panel, --rebuild-ml-features, "
            "or --donor + --activity + --fit"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
