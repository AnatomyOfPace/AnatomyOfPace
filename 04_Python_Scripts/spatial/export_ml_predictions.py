#!/usr/bin/env python3
"""
Export per-metre ML predictions parquet for HITL decision-mode strips.

Writes ``course_km``, ``pred_class`` (surface S-class), and friction/confidence
columns beside the panel for map-first courses (Tverrfjell, etc.).

Usage (from repo root):
    python3 04_Python_Scripts/spatial/export_ml_predictions.py \\
        --terrain-map config/spatial_terrain_map_tverrfjell.json \\
        --model 07_ML_Models/spatial/gold_suggester_tverrfjell_v0.joblib
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.gold_training_common import build_training_frame, resolve_gold_training_defaults
from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.suggest_gold_spans import _predict_bundle

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_TERRAIN_MAP = BASE_DIR / "config" / "spatial_terrain_map_tverrfjell.json"
DEFAULT_MODEL = BASE_DIR / "07_ML_Models" / "spatial" / "gold_suggester_tverrfjell_v0.joblib"


def default_output_path(terrain_map_path: Path, panel_path: Path) -> Path:
    tmap = load_terrain_map(terrain_map_path)
    race_id = str((tmap.get("corridor") or {}).get("race_id") or "course")
    return panel_path.parent / f"{race_id}_ml_predictions.parquet"


def export_ml_predictions(
    *,
    panel_path: Path,
    terrain_map_path: Path,
    model_path: Path,
    output_path: Path,
    hmm_draft: Path | None = None,
) -> Path:
    if not model_path.exists():
        raise FileNotFoundError(f"ML model not found: {model_path}")
    if not panel_path.exists():
        raise FileNotFoundError(f"Panel not found: {panel_path}")

    tmap = load_terrain_map(terrain_map_path)
    corridor = tmap.get("corridor") or {}
    km_lo = float(corridor.get("km_start") or 0.0)
    km_hi = float(corridor.get("km_end") or 0.0)
    if km_hi <= km_lo:
        panel = pd.read_parquet(panel_path)
        km_hi = float(panel["course_km"].max()) + 0.001

    frame = build_training_frame(
        panel_path=panel_path,
        terrain_map_path=terrain_map_path,
        hmm_path=hmm_draft,
        km_lo=km_lo,
        km_hi=km_hi,
    )
    bundle = joblib.load(model_path)
    predicted = _predict_bundle(frame, bundle)

    out = predicted[["course_m", "course_km"]].copy()
    out["pred_class"] = predicted["pred_surface"].astype(str)
    out["pred_friction"] = predicted["pred_friction"].astype(str)
    out["surface_proba"] = predicted["surface_proba"]
    out["friction_proba"] = predicted["friction_proba"]
    out["pred_confidence"] = predicted["pred_confidence"]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(output_path, index=False)

    meta = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "panel": str(panel_path.relative_to(BASE_DIR)),
        "terrain_map": str(terrain_map_path.relative_to(BASE_DIR)),
        "model": str(model_path.relative_to(BASE_DIR)),
        "rows": int(len(out)),
        "km_range": [km_lo, km_hi],
        "class_counts": out["pred_class"].value_counts().to_dict(),
    }
    meta_path = output_path.with_suffix(".summary.json")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Export per-metre ML predictions for HITL dashboards")
    parser.add_argument("--terrain-map", type=Path, default=DEFAULT_TERRAIN_MAP)
    parser.add_argument("--panel", type=Path, default=None)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--hmm-draft", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    terrain_map_path = args.terrain_map if args.terrain_map.is_absolute() else BASE_DIR / args.terrain_map
    model_path = args.model if args.model.is_absolute() else BASE_DIR / args.model
    resolved = resolve_gold_training_defaults(terrain_map_path)
    panel_path = args.panel
    if panel_path is None:
        panel_path = resolved["panel"] if resolved else None
    if panel_path is None:
        print("ERROR --panel required (or use a terrain map with resolve_gold_training_defaults)", file=sys.stderr)
        return 1
    if not panel_path.is_absolute():
        panel_path = BASE_DIR / panel_path

    hmm_path = args.hmm_draft
    if hmm_path is not None and not hmm_path.is_absolute():
        hmm_path = BASE_DIR / hmm_path
    if hmm_path is None and resolved:
        hmm_path = resolved.get("hmm_draft")

    output_path = args.output
    if output_path is None:
        output_path = default_output_path(terrain_map_path, panel_path)
    elif not output_path.is_absolute():
        output_path = BASE_DIR / output_path

    try:
        written = export_ml_predictions(
            panel_path=panel_path,
            terrain_map_path=terrain_map_path,
            model_path=model_path,
            output_path=output_path,
            hmm_draft=hmm_path,
        )
    except FileNotFoundError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    rel = written.relative_to(BASE_DIR)
    print(f"Wrote {rel} ({len(pd.read_parquet(written))} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
