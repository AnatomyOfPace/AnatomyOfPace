"""Registry and path helpers for Subject_A map-first orphan courses."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = BASE_DIR / "config" / "map_first_orphan_courses.json"
DONOR_ID = "Subject_A"
DONOR_DIR = BASE_DIR / "02_Raw_Data" / "donors" / DONOR_ID


def _norm_token(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", ascii_only.lower())


def load_registry() -> dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def list_orphan_courses() -> list[dict[str, Any]]:
    return list(load_registry().get("courses") or [])


def get_orphan_course(race_id: str) -> dict[str, Any]:
    for course in list_orphan_courses():
        if course.get("race_id") == race_id:
            return course
    known = ", ".join(c["race_id"] for c in list_orphan_courses())
    raise KeyError(f"Unknown orphan race_id {race_id!r} — expected one of: {known}")


def manifest_path(race_id: str) -> Path:
    return BASE_DIR / "config" / f"spatial_align_manifest_{race_id}.json"


def terrain_map_path(race_id: str) -> Path:
    return BASE_DIR / "config" / f"spatial_terrain_map_{race_id}.json"


def panel_path(race_id: str) -> Path:
    return BASE_DIR / "03_Processed_Data" / "spatial" / f"{race_id}_course" / "panel_1m.parquet"


def hitl_dir(race_id: str) -> Path:
    return BASE_DIR / "06_Visualizations" / f"{race_id}_hitl"


def gold_output_path(race_id: str) -> Path:
    return BASE_DIR / "03_Processed_Data" / "spatial" / f"gold_training_set_{race_id}.parquet"


def ml_predictions_path(race_id: str) -> Path:
    return (
        BASE_DIR
        / "03_Processed_Data"
        / "spatial"
        / f"{race_id}_course"
        / f"{race_id}_ml_predictions.parquet"
    )


def fits_match(course: dict[str, Any], path: Path) -> bool:
    name = _norm_token(path.stem)
    match = course.get("fit_match") or {}
    for token in match.get("all_tokens") or []:
        if _norm_token(str(token)) not in name:
            return False
    any_tokens = match.get("any_tokens") or []
    if any_tokens:
        if not any(_norm_token(str(token)) in name for token in any_tokens):
            return False
    return True


def discover_fit_candidates(course: dict[str, Any]) -> list[Path]:
    roots = (
        DONOR_DIR,
        BASE_DIR / "02_Raw_Data",
        Path.home() / "Downloads",
        Path.home() / "Desktop",
    )
    out: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.fit"):
            if not path.is_file():
                continue
            if not fits_match(course, path):
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            out.append(path.resolve())
    return sorted(out, key=lambda p: p.stat().st_mtime, reverse=True)


def corridor_id_for(race_id: str) -> str:
    return f"{race_id}_course"


def geography_label(course: dict[str, Any]) -> str:
    geo = course.get("geography") or {}
    parts = [geo.get("settlement"), geo.get("municipality"), geo.get("county")]
    return " · ".join(str(p) for p in parts if p)


def build_manifest(course: dict[str, Any], *, activity_id: str, km_end: float = 1.0) -> dict[str, Any]:
    race_id = str(course["race_id"])
    viewport = round(km_end + 0.1, 3)
    geo = course.get("geography") or {}
    return {
        "corridor_id": corridor_id_for(race_id),
        "race_id": race_id,
        "anchor_id": race_id,
        "terrain_map": f"config/spatial_terrain_map_{race_id}.json",
        "course_axis": "stream_distance",
        "km_analysis_window": [0.0, km_end],
        "km_viewport_window": [0.0, viewport],
        "default_align_mode": "stream",
        "default_direction": "auto",
        "stream_race_id": race_id,
        "multi_fit": True,
        "geography": geo,
        "panel_scope": (
            f"Subject_A anchor stream (stream-distance course axis). "
            f"{geo.get('municipality', '')}. Bootstrap via bootstrap_map_first_orphan.py."
        ),
        "activities": [
            {
                "donor_id": DONOR_ID,
                "activity_id": activity_id,
                "session_type": course.get("session_type") or "training",
                "subject_id": DONOR_ID,
                "align_mode": "stream",
                "note": f"{course.get('display_name')} — FIT {activity_id} defines stream-distance course axis.",
            }
        ],
        "build_commands": {
            "bootstrap": f"python3 04_Python_Scripts/spatial/bootstrap_map_first_orphan.py --course {race_id}",
            "hitl_export": f"./04_Python_Scripts/spatial/export_hitl_map_first_orphan.sh {race_id}",
        },
    }


def build_terrain_map(course: dict[str, Any], *, activity_id: str, km_end: float = 1.0) -> dict[str, Any]:
    from datetime import datetime, timezone

    race_id = str(course["race_id"])
    geo = dict(course.get("geography") or {})
    seed_surface = str(course.get("seed_surface") or "S2")
    seed_friction = str(course.get("seed_friction") or "F2")
    return {
        "schema_version": "spatial_terrain_map_v0",
        "ontology_version": "s6_v0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corridor": {
            "corridor_id": corridor_id_for(race_id),
            "race_id": race_id,
            "anchor_id": race_id,
            "km_start": 0.0,
            "km_end": km_end,
            "course_axis": "stream_distance",
            "geography": geo,
            "notes": (
                f"Tier 0 map-first orphan course ({course.get('display_name')}). "
                f"Stream-distance axis km 0–{km_end:.3f} from Subject_A FIT {activity_id}. "
                "Operator adjudicates substrate from orthophoto."
            ),
        },
        "clustering": {
            "method": None,
            "n_clusters": None,
            "fallback": "map_first_operator_gold",
            "note": "No GMM draft — operator_gold_spans[] is authoritative once breakpoints are locked.",
        },
        "segments": [
            {
                "course_km_start": 0.0,
                "course_km_end": km_end,
                "surface_class": seed_surface,
                "friction_tier": seed_friction,
                "source": "seed",
                "label": course.get("seed_label") or "Placeholder tread",
                "confidence": 0.3,
                "operator_note": "Map-first seed — superseded by operator_gold_spans when locked.",
            }
        ],
        "hitl": {
            "status": "review",
            "sector_id": corridor_id_for(race_id),
            "manual_overrides": [],
            "operator_gold_spans": [],
            "trf_exclusions": [],
            "behavioral_stops": [],
            "variance_gaps": [],
            "notes": (
                f"Append-only operator_gold_spans[] — map-first orphan {course.get('display_name')}. "
                f"Use gold_span_editor.py with --terrain-map config/spatial_terrain_map_{race_id}.json."
            ),
        },
    }


def write_course_configs(course: dict[str, Any], *, activity_id: str, km_end: float) -> None:
    manifest_path(course["race_id"]).write_text(
        json.dumps(build_manifest(course, activity_id=activity_id, km_end=km_end), indent=2) + "\n",
        encoding="utf-8",
    )
    terrain_map_path(course["race_id"]).write_text(
        json.dumps(build_terrain_map(course, activity_id=activity_id, km_end=km_end), indent=2) + "\n",
        encoding="utf-8",
    )
