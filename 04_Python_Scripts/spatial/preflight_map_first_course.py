#!/usr/bin/env python3
"""
Preflight checks for map-first HITL courses (Tverrfjell, Klepp Runde, …).

Catches common operator pitfalls before bulk PNG export:
  - wrong race_id / SUT_43 axis label
  - GPS centroid outside expected geography
  - empty operator_gold_spans (ML strip will be blank until trained)
  - missing TI / zero speed telemetry (weak ML + locomotion)
  - stale ML predictions vs model mtime

Usage:
    python3 04_Python_Scripts/spatial/preflight_map_first_course.py \\
        --terrain-map config/spatial_terrain_map_klepp_runde.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.gold_training_common import resolve_gold_training_defaults
from spatial.spatial_hitl_overlay import load_terrain_map
from spatial.validation_dashboard import resolve_axis_label

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Expected GPS bands — warn when centroid is outside.
# Klepp Runde: local place name "Klepp" in Uskedalen (not Klepp municipality, Rogaland).
USKEDALEN_BAND = {"lat_min": 59.86, "lat_max": 59.95, "lon_min": 5.88, "lon_max": 6.02}
SANDNES_GRAMSTAD_BAND = {"lat_min": 58.75, "lat_max": 58.95, "lon_min": 5.55, "lon_max": 5.85}
VINJE_TELEMARK_BAND = {"lat_min": 59.40, "lat_max": 59.80, "lon_min": 7.25, "lon_max": 8.55}

# Map-first Vinje: FIT stream GPS is the geography source of truth after bootstrap.
# Static bands are advisory warnings only — never block export on centroid alone.
TRUST_FIT_GPS_RACES = frozenset({"vinje_terrenglop"})

GEO_BANDS: dict[str, dict[str, float]] = {
    "tverrfjell": dict(USKEDALEN_BAND),
    "klepp_runde": dict(USKEDALEN_BAND),
    "gramstad_runde": dict(SANDNES_GRAMSTAD_BAND),
    "vinje_terrenglop": dict(VINJE_TELEMARK_BAND),
}

WRONG_REGION: dict[str, dict[str, float | str]] = {
    "tverrfjell": {"lat_min": 59.75, "label": "south of Uskedalen (Sandnes/SUT_43 band)"},
    "klepp_runde": {
        "lat_min": 59.0,
        "label": "Rogaland Jæren (Klepp municipality homonym — not Uskedalen Klepp)",
    },
    "gramstad_runde": {
        "lat_max": 59.0,
        "label": "Uskedalen (wrong course — not Sandnes/Gramstad)",
    },
}


def _resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else BASE_DIR / path


def _repo_rel(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(BASE_DIR.resolve()))
    except ValueError:
        return str(resolved)


def _panel_path(terrain_map_path: Path, panel: Path | None) -> Path:
    if panel is not None:
        return panel if panel.is_absolute() else BASE_DIR / panel
    resolved = resolve_gold_training_defaults(terrain_map_path)
    if resolved:
        return resolved["panel"]
    race_id = str((load_terrain_map(terrain_map_path).get("corridor") or {}).get("race_id") or "")
    return BASE_DIR / "03_Processed_Data" / "spatial" / f"{race_id}_course" / "panel_1m.parquet"


def _telemetry_report(panel: pd.DataFrame) -> dict[str, float | int]:
    n = len(panel)
    out: dict[str, float | int] = {"rows": n}
    for col, min_valid in (
        ("ti", 0.05),
        ("speed_mps", 0.05),
        ("cadence_spm", 0.05),
        ("grade_pct", 0.05),
        ("grade", 0.05),
    ):
        if col not in panel.columns:
            continue
        s = pd.to_numeric(panel[col], errors="coerce")
        nonzero = (s.notna() & (s != 0)).sum()
        out[f"{col}_nonzero_pct"] = round(100.0 * nonzero / max(n, 1), 1)
    return out


def run_preflight(
    terrain_map_path: Path,
    *,
    panel_path: Path | None = None,
    ml_model: Path | None = None,
    ml_predictions: Path | None = None,
    strict: bool = False,
) -> int:
    terrain_map_path = terrain_map_path if terrain_map_path.is_absolute() else BASE_DIR / terrain_map_path
    tmap = load_terrain_map(terrain_map_path)
    corridor = tmap.get("corridor") or {}
    race_id = str(corridor.get("race_id") or "")
    panel_file = _panel_path(terrain_map_path, panel_path)

    errors: list[str] = []
    warnings: list[str] = []

    if not panel_file.exists():
        errors.append(f"Panel missing: {panel_file} — run bootstrap first")
        for e in errors:
            print(f"FAIL {e}", file=sys.stderr)
        return 1

    panel = pd.read_parquet(panel_file)
    axis = resolve_axis_label(tmap, panel)
    print(f"OK race_id={race_id!r} axis={axis!r}")

    if axis.startswith("SUT_43"):
        errors.append("axis label is SUT_43 — wrong course or stale terrain map")

    lat = pd.to_numeric(panel["latitude"], errors="coerce")
    lon = pd.to_numeric(panel["longitude"], errors="coerce")
    c_lat, c_lon = float(lat.mean()), float(lon.mean())
    print(f"OK GPS centroid {c_lat:.5f}°N {c_lon:.5f}°E (FIT stream — source of truth)")
    trust_gps = race_id in TRUST_FIT_GPS_RACES or str(corridor.get("course_axis")) == "stream_distance"

    band = GEO_BANDS.get(race_id)
    if band:
        if not (band["lat_min"] <= c_lat <= band["lat_max"]):
            msg = f"centroid lat {c_lat:.4f} outside advisory {race_id} band"
            (warnings if trust_gps else errors).append(msg)
        if not (band["lon_min"] <= c_lon <= band["lon_max"]):
            msg = f"centroid lon {c_lon:.4f} outside advisory {race_id} band"
            (warnings if trust_gps else errors).append(msg)

    wrong = WRONG_REGION.get(race_id)
    if wrong and not trust_gps:
        lat_min = wrong.get("lat_min")
        lat_max = wrong.get("lat_max")
        lon_min = wrong.get("lon_min")
        lon_max = wrong.get("lon_max")
        if lat_min is not None and c_lat < float(lat_min):
            errors.append(f"centroid {c_lat:.4f}°N is {wrong['label']}")
        if lat_max is not None and c_lat > float(lat_max):
            errors.append(f"centroid {c_lat:.4f}°N is {wrong['label']}")
        if lon_min is not None and c_lon < float(lon_min):
            errors.append(f"centroid {c_lon:.4f}°E is {wrong['label']}")
        if lon_max is not None and c_lon > float(lon_max):
            errors.append(f"centroid {c_lon:.4f}°E is {wrong['label']}")
    elif wrong and trust_gps:
        warnings.append("advisory homonym/region checks skipped — trusting FIT GPS for map-first course")

    gold = tmap.get("hitl", {}).get("operator_gold_spans") or []
    print(f"OK operator_gold_spans: {len(gold)}")
    if not gold:
        warnings.append(
            "no operator_gold_spans — label before training ML; export ML strip empty until model exists"
        )

    telem = _telemetry_report(panel)
    print(f"OK telemetry: {json.dumps({k: v for k, v in telem.items() if k != 'rows'})}")
    ti_pct = telem.get("ti_nonzero_pct", 0)
    speed_pct = telem.get("speed_mps_nonzero_pct", 0)
    if ti_pct < 50:
        warnings.append(
            f"TI coverage low ({ti_pct}%) — run bootstrap with --enrich-ti; ML quality may suffer"
        )
    if speed_pct < 50:
        warnings.append(
            f"speed_mps mostly zero ({speed_pct}% nonzero) — locomotion strip leans on grade/F-tier only"
        )

    course_dir = panel_file.parent
    if ml_model is None:
        ml_model = BASE_DIR / "07_ML_Models" / "spatial" / f"gold_suggester_{race_id}_v0.joblib"
    if ml_predictions is None:
        ml_predictions = course_dir / f"{race_id}_ml_predictions.parquet"

    if ml_model.exists():
        print(f"OK ML model {ml_model.relative_to(BASE_DIR)}")
        if not ml_predictions.exists():
            warnings.append("ML model exists but predictions parquet missing — export will generate it")
        elif ml_model.stat().st_mtime > ml_predictions.stat().st_mtime:
            warnings.append("ML model newer than predictions — export will regenerate parquet")
    else:
        warnings.append(f"no ML model at {ml_model.relative_to(BASE_DIR)} — ML predicted strip will be empty")

    for w in warnings:
        print(f"WARN {w}")
    for e in errors:
        print(f"FAIL {e}", file=sys.stderr)

    if errors:
        return 1
    if strict and warnings:
        # strict = fail on warnings only when --fail-on-warn
        pass
    print("OK preflight passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight map-first HITL course before PNG export")
    parser.add_argument("--terrain-map", type=Path, required=True)
    parser.add_argument("--panel", type=Path, default=None)
    parser.add_argument("--ml-model", type=Path, default=None)
    parser.add_argument("--ml-predictions", type=Path, default=None)
    parser.add_argument("--strict", action="store_true", help="Reserved for future fail-on-warn")
    args = parser.parse_args()
    return run_preflight(
        args.terrain_map,
        panel_path=args.panel,
        ml_model=args.ml_model,
        ml_predictions=args.ml_predictions,
        strict=args.strict,
    )


if __name__ == "__main__":
    raise SystemExit(main())
