"""
Corridor window helpers for spatial stress-test scope.

Course-direction km windows are read from config/race_corridors.json.
Finish anchor: SUT_160 km 161 (Alsvik).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RACE_CORRIDORS_PATH = BASE_DIR / "config" / "race_corridors.json"

STRESS_TEST_RACE_ID = "SUT_160"
STRESS_TEST_CORRIDOR_ID = "dale_to_paradisskaret_stress_test"
STRESS_TEST_SECTOR_ID = "dale_to_paradisskaret"
STRESS_TEST_SECTOR_LOCK_VERSION = "2026-06-26-dale-to-paradisskaret"

# SUT_43 terrain ontology experiment (Subject_A + Subject_B panel).
SUT43_EXPERIMENT_RACE_ID = "SUT_43"
SUT43_CORRIDOR_ID = "sut43_terrain_ontology"
SUT43_SECTOR_ID = "gramstad_band"
SUT43_SECTOR_LOCK_VERSION = "2026-06-26-sut43-gramstad-band"
SUT43_UPSTREAM_SECTOR_ID = "dale_paradisskaret_upstream"
SUT43_UPSTREAM_KM_START = 22.0
SUT43_UPSTREAM_KM_END = 29.0
SUT43_UPSTREAM_VIEWPORT_KM_END = 29.5
SUT43_GPS_BRIDGE_KM_START = 22.0
SUT43_GPS_BRIDGE_KM_END = 34.2
SUT43_FULL_KM_START = 0.5
SUT43_FULL_KM_END = 42.5
SUT43_PRIMARY_KM_START = 29.0
SUT43_PRIMARY_KM_END = 41.0
SUT43_PRIMARY_VIEWPORT_KM_END = 41.5
# Geographic Dalsnuten summit (Garmin marker 25) — race_corridors.json dalsnuten_summit.
SUT43_DALSNUTEN_SUMMIT_KM = 25.0
# Blog composite viewport: Dalsnuten summit through Gramstad band end.
SUT43_DALSNUTEN_GRAMSTAD_VIEWPORT_KM: tuple[float, float] = (SUT43_DALSNUTEN_SUMMIT_KM, SUT43_PRIMARY_KM_END)
SUT43_FULL_RACE_KM_START = 0.5
SUT43_FULL_RACE_KM_END = 43.0
SUT43_FULL_RACE_SECTOR_ID = "sut43_full_race"

# Sunderunde Tier 0 training loop (stream-distance axis).
SUNDERUNDE_RACE_ID = "Sunderunde"
SUNDERUNDE_CORRIDOR_ID = "sunderunde_training_loop"
SUNDERUNDE_KM_START = 0.0
SUNDERUNDE_KM_END = 19.5

# Stavanger Halvmarathon O₁ asphalt anchor (stream-distance axis).
STAVANGER_HALVMARATHON_RACE_ID = "stavanger_halvmarathon"
STAVANGER_HALVMARATHON_CORRIDOR_ID = "stavanger_halvmarathon_course"
STAVANGER_HALVMARATHON_KM_START = 0.0
STAVANGER_HALVMARATHON_KM_END = 21.38

# 3-sjøersløpet O₁ gravel-road race anchor (stream-distance axis).
SJOERSLOPET_RACE_ID = "3_sjoerslopet"
SJOERSLOPET_CORRIDOR_ID = "3_sjoerslopet_course"
SJOERSLOPET_KM_START = 0.0
SJOERSLOPET_KM_END = 21.25

# Tverrfjell local hill loop — Uskedalen, Kvinnherad, Vestland (not Rogaland; not SUT_43).
TVERFJELL_RACE_ID = "tverrfjell"
TVERFJELL_CORRIDOR_ID = "tverrfjell_course"
TVERFJELL_KM_START = 0.0
TVERFJELL_KM_END = 23.549
TVERFJELL_GEOGRAPHY = {
    "settlement": "Uskedalen",
    "municipality": "Kvinnherad",
    "county": "Vestland",
    "region": "Hardanger / Sunnhordland",
    "not_in": ["Rogaland"],
}

# Klepp Runde local training loop — Klepp (locality in Uskedalen), Kvinnherad, Vestland.
# Not Klepp municipality (Rogaland/Jæren) — homonym.
KLEPP_RUNDE_RACE_ID = "klepp_runde"
KLEPP_RUNDE_CORRIDOR_ID = "klepp_runde_course"
KLEPP_RUNDE_KM_START = 0.0
KLEPP_RUNDE_KM_END = 1.0  # patched by bootstrap from FIT stream length
KLEPP_RUNDE_GEOGRAPHY = {
    "settlement": "Klepp",
    "locality": "Uskedalen",
    "municipality": "Kvinnherad",
    "county": "Vestland",
    "region": "Hardanger / Sunnhordland",
    "homonym_warning": "Not Klepp municipality (Rogaland/Jæren)",
    "not_in": ["Rogaland", "Klepp municipality"],
}

# Gramstad Runde local training loop — Sandnes, Rogaland (map-first stream axis).
# Not SUT_43 gramstad_band sector (km 29–41 organiser GPX).
GRAMSTAD_RUNDE_RACE_ID = "gramstad_runde"
GRAMSTAD_RUNDE_CORRIDOR_ID = "gramstad_runde_course"
GRAMSTAD_RUNDE_KM_START = 0.0
GRAMSTAD_RUNDE_KM_END = 1.0  # patched by bootstrap from FIT stream length
GRAMSTAD_RUNDE_GEOGRAPHY = {
    "settlement": "Gramstad",
    "municipality": "Sandnes",
    "county": "Rogaland",
    "region": "Jæren",
    "not_sut43_sector": "gramstad_band",
}

# Vinje Terrengløp trail event — Vinje, Telemark (map-first stream axis).
VINJE_TERRENGLOP_RACE_ID = "vinje_terrenglop"
VINJE_TERRENGLOP_CORRIDOR_ID = "vinje_terrenglop_course"
VINJE_TERRENGLOP_KM_START = 0.0
VINJE_TERRENGLOP_KM_END = 1.0  # patched by bootstrap from FIT stream length
VINJE_TERRENGLOP_GEOGRAPHY = {
    "settlement": "Vinje",
    "municipality": "Vinje",
    "county": "Telemark",
    "region": "Hardangervidda / Vestfold og Telemark",
    "event": "Vinje Terrengløp",
}

# Operator scope: Dale aid CP band through Paradisskaret Downhill end (course km).
DEFAULT_KM_START = 140.0
DEFAULT_KM_END = 155.58
# Locked sector map viewport (config/sut160_sector_zoom.local.json → dale_to_paradisskaret).
SECTOR_VIEWPORT_KM_END = 156.0

# Registry anchors (2026-06-25 corridor lock).
DALE_AID_CHECKPOINT_KM = 140.4
PARADISSKARET_DOWNHILL_END_KM = 155.58


def load_race_corridors() -> dict[str, Any]:
    if not RACE_CORRIDORS_PATH.exists():
        raise FileNotFoundError(f"Corridor registry not found: {RACE_CORRIDORS_PATH}")
    return json.loads(RACE_CORRIDORS_PATH.read_text(encoding="utf-8"))


def load_sub_corridor_window(
    race_id: str,
    corridor_key: str,
    *,
    registry: dict[str, Any] | None = None,
) -> tuple[float, float, dict[str, Any]]:
    """Return (km_start, km_end, corridor record) for a named sub_corridor."""
    reg = registry if registry is not None else load_race_corridors()
    race = reg.get(race_id)
    if race is None:
        raise KeyError(f"Race {race_id!r} not in {RACE_CORRIDORS_PATH.name}")
    subs = race.get("sub_corridors") or {}
    rec = subs.get(corridor_key)
    if rec is None:
        raise KeyError(f"sub_corridor {corridor_key!r} not found under {race_id}")
    if rec.get("retired"):
        raise ValueError(f"sub_corridor {corridor_key!r} is retired")
    return float(rec["km_start"]), float(rec["km_end"]), rec


def load_stress_test_window(
    *,
    km_start: float | None = None,
    km_end: float | None = None,
    registry: dict[str, Any] | None = None,
) -> tuple[float, float, dict[str, Any]]:
    """
    Dale CP (~km 140) through Paradisskaret Downhill end (~km 155.58).

    Defaults align with paradisskaret_downhill_finish end and Dale aid checkpoint
    in race_corridors.json (SUT_160).
    """
    reg = registry if registry is not None else load_race_corridors()
    race = reg[STRESS_TEST_RACE_ID]
    _, downhill_end, downhill_rec = load_sub_corridor_window(
        STRESS_TEST_RACE_ID,
        "paradisskaret_downhill_finish",
        registry=reg,
    )
    start = DEFAULT_KM_START if km_start is None else float(km_start)
    end = DEFAULT_KM_END if km_end is None else float(km_end)
    meta = {
        "corridor_id": STRESS_TEST_CORRIDOR_ID,
        "sector_id": STRESS_TEST_SECTOR_ID,
        "sector_lock_version": STRESS_TEST_SECTOR_LOCK_VERSION,
        "race_id": STRESS_TEST_RACE_ID,
        "km_start": start,
        "km_end": end,
        "sector_viewport_km_end": SECTOR_VIEWPORT_KM_END,
        "dale_aid_checkpoint_km": race.get("checkpoints", {}).get("Dale_aid_late", DALE_AID_CHECKPOINT_KM),
        "paradisskaret_downhill_end_km": downhill_end,
        "paradisskaret_downhill_label": downhill_rec.get("label"),
        "finish_km": race.get("finish_km", 161.0),
    }
    return start, end, meta


def load_sut43_experiment_window(
    *,
    km_start: float | None = None,
    km_end: float | None = None,
    sector_id: str = SUT43_SECTOR_ID,
    registry: dict[str, Any] | None = None,
) -> tuple[float, float, dict[str, Any]]:
    """
    Primary SUT_43 ontology window: Gramstad band km 29–41 (operator lock).

    Covers late-loop Revhol traverse (~29), Bjørndalsfjellet climb/descent (~30–32),
    Gramstad flat (~32), late_braking (33–34), and post-bridge late-lap terrain
  through km 41 — shared geography with SUT_160 Dale→Gramstad (memo 13) for km
  29–34.2; km 34.2–41 is stream-axis only (outside GPS bridge LUT).
    """
    reg = registry if registry is not None else load_race_corridors()
    race = reg[SUT43_EXPERIMENT_RACE_ID]
    start = SUT43_PRIMARY_KM_START if km_start is None else float(km_start)
    end = SUT43_PRIMARY_KM_END if km_end is None else float(km_end)
    _, brake_end, brake_rec = load_sub_corridor_window(
        SUT43_EXPERIMENT_RACE_ID,
        "late_braking",
        registry=reg,
    )
    meta = {
        "corridor_id": SUT43_CORRIDOR_ID,
        "sector_id": sector_id,
        "sector_lock_version": SUT43_SECTOR_LOCK_VERSION,
        "race_id": SUT43_EXPERIMENT_RACE_ID,
        "km_start": start,
        "km_end": end,
        "sector_viewport_km_end": SUT43_PRIMARY_VIEWPORT_KM_END,
        "late_braking_km": [brake_rec.get("km_start"), brake_end],
        "late_braking_label": brake_rec.get("label"),
        "gps_bridge_overlap_km": [29.0, 34.2],
        "finish_km": race.get("finish_km", 43.0),
        "full_course_window": [SUT43_FULL_KM_START, SUT43_FULL_KM_END],
        "course_axis": "stream_distance",
        "gpx_reference": "COURSE_SUT43_official_2027.gpx",
    }
    return start, end, meta


def load_sunderunde_window(
    *,
    km_start: float | None = None,
    km_end: float | None = None,
) -> tuple[float, float, dict[str, Any]]:
    """Sunderunde training loop — FIT stream-distance axis km 0–19.5."""
    start = SUNDERUNDE_KM_START if km_start is None else float(km_start)
    end = SUNDERUNDE_KM_END if km_end is None else float(km_end)
    meta = {
        "corridor_id": SUNDERUNDE_CORRIDOR_ID,
        "race_id": SUNDERUNDE_RACE_ID,
        "anchor_id": "sunderunde_training_gravel",
        "km_start": start,
        "km_end": end,
        "course_axis": "stream_distance",
        "terrain_map": "config/spatial_terrain_map_sunderunde.json",
    }
    return start, end, meta


def load_stavanger_halvmarathon_window(
    *,
    km_start: float | None = None,
    km_end: float | None = None,
) -> tuple[float, float, dict[str, Any]]:
    """Stavanger Halvmarathon — FIT stream-distance axis km 0–21.38 (O₁ asphalt anchor)."""
    start = STAVANGER_HALVMARATHON_KM_START if km_start is None else float(km_start)
    end = STAVANGER_HALVMARATHON_KM_END if km_end is None else float(km_end)
    meta = {
        "corridor_id": STAVANGER_HALVMARATHON_CORRIDOR_ID,
        "race_id": STAVANGER_HALVMARATHON_RACE_ID,
        "anchor_id": "stavanger_halvmarathon",
        "km_start": start,
        "km_end": end,
        "course_axis": "stream_distance",
        "terrain_map": "config/spatial_terrain_map_stavanger_halvmarathon.json",
    }
    return start, end, meta


def load_3_sjoerslopet_window(
    *,
    km_start: float | None = None,
    km_end: float | None = None,
) -> tuple[float, float, dict[str, Any]]:
    """3-sjøersløpet race — FIT stream-distance axis km 0–21.25 (O₁ gravel-road anchor)."""
    start = SJOERSLOPET_KM_START if km_start is None else float(km_start)
    end = SJOERSLOPET_KM_END if km_end is None else float(km_end)
    meta = {
        "corridor_id": SJOERSLOPET_CORRIDOR_ID,
        "race_id": SJOERSLOPET_RACE_ID,
        "anchor_id": "3_sjoerslopet",
        "km_start": start,
        "km_end": end,
        "course_axis": "stream_distance",
        "terrain_map": "config/spatial_terrain_map_3_sjoerslopet.json",
    }
    return start, end, meta


def load_tverrfjell_window(
    *,
    km_start: float | None = None,
    km_end: float | None = None,
) -> tuple[float, float, dict[str, Any]]:
    """Tverrfjell hill loop (Uskedalen, Kvinnherad, Vestland) — FIT stream-distance axis."""
    start = TVERFJELL_KM_START if km_start is None else float(km_start)
    end = TVERFJELL_KM_END if km_end is None else float(km_end)
    meta = {
        "corridor_id": TVERFJELL_CORRIDOR_ID,
        "race_id": TVERFJELL_RACE_ID,
        "anchor_id": "tverrfjell",
        "km_start": start,
        "km_end": end,
        "course_axis": "stream_distance",
        "terrain_map": "config/spatial_terrain_map_tverrfjell.json",
        "geography": dict(TVERFJELL_GEOGRAPHY),
    }
    return start, end, meta


def load_klepp_runde_window(
    *,
    km_start: float | None = None,
    km_end: float | None = None,
) -> tuple[float, float, dict[str, Any]]:
    """Klepp Runde loop (Klepp locality, Uskedalen) — FIT stream-distance axis."""
    start = KLEPP_RUNDE_KM_START if km_start is None else float(km_start)
    end = KLEPP_RUNDE_KM_END if km_end is None else float(km_end)
    meta = {
        "corridor_id": KLEPP_RUNDE_CORRIDOR_ID,
        "race_id": KLEPP_RUNDE_RACE_ID,
        "anchor_id": "klepp_runde",
        "km_start": start,
        "km_end": end,
        "course_axis": "stream_distance",
        "terrain_map": "config/spatial_terrain_map_klepp_runde.json",
        "geography": dict(KLEPP_RUNDE_GEOGRAPHY),
    }
    return start, end, meta


def load_gramstad_runde_window(
    *,
    km_start: float | None = None,
    km_end: float | None = None,
) -> tuple[float, float, dict[str, Any]]:
    """Gramstad Runde loop (Sandnes, Rogaland) — FIT stream-distance axis."""
    start = GRAMSTAD_RUNDE_KM_START if km_start is None else float(km_start)
    end = GRAMSTAD_RUNDE_KM_END if km_end is None else float(km_end)
    meta = {
        "corridor_id": GRAMSTAD_RUNDE_CORRIDOR_ID,
        "race_id": GRAMSTAD_RUNDE_RACE_ID,
        "anchor_id": "gramstad_runde",
        "km_start": start,
        "km_end": end,
        "course_axis": "stream_distance",
        "terrain_map": "config/spatial_terrain_map_gramstad_runde.json",
        "geography": dict(GRAMSTAD_RUNDE_GEOGRAPHY),
    }
    return start, end, meta


def load_vinje_terrenglop_window(
    *,
    km_start: float | None = None,
    km_end: float | None = None,
) -> tuple[float, float, dict[str, Any]]:
    """Vinje Terrengløp trail event (Telemark) — FIT stream-distance axis."""
    start = VINJE_TERRENGLOP_KM_START if km_start is None else float(km_start)
    end = VINJE_TERRENGLOP_KM_END if km_end is None else float(km_end)
    meta = {
        "corridor_id": VINJE_TERRENGLOP_CORRIDOR_ID,
        "race_id": VINJE_TERRENGLOP_RACE_ID,
        "anchor_id": "vinje_terrenglop",
        "km_start": start,
        "km_end": end,
        "course_axis": "stream_distance",
        "terrain_map": "config/spatial_terrain_map_vinje_terrenglop.json",
        "geography": dict(VINJE_TERRENGLOP_GEOGRAPHY),
    }
    return start, end, meta


def load_map_first_orphan_window(
    race_id: str,
    *,
    km_start: float | None = None,
    km_end: float | None = None,
) -> tuple[float, float, dict[str, Any]]:
    """Map-first orphan course — FIT stream-distance axis (registry-driven)."""
    reg_path = BASE_DIR / "config" / "map_first_orphan_courses.json"
    if not reg_path.exists():
        raise KeyError(f"Orphan registry not found: {reg_path}")
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    course = next((c for c in (reg.get("courses") or []) if c.get("race_id") == race_id), None)
    if course is None:
        raise KeyError(f"race_id {race_id!r} not in map_first_orphan_courses.json")
    start = 0.0 if km_start is None else float(km_start)
    end = 1.0 if km_end is None else float(km_end)
    meta = {
        "corridor_id": f"{race_id}_course",
        "race_id": race_id,
        "anchor_id": race_id,
        "km_start": start,
        "km_end": end,
        "course_axis": "stream_distance",
        "terrain_map": f"config/spatial_terrain_map_{race_id}.json",
        "geography": dict(course.get("geography") or {}),
    }
    return start, end, meta


def load_experiment_window(
    race_id: str = STRESS_TEST_RACE_ID,
    *,
    km_start: float | None = None,
    km_end: float | None = None,
    registry: dict[str, Any] | None = None,
) -> tuple[float, float, dict[str, Any]]:
    """Dispatch corridor window loader by race_id."""
    if race_id == SUT43_EXPERIMENT_RACE_ID:
        return load_sut43_experiment_window(km_start=km_start, km_end=km_end, registry=registry)
    if race_id == SUNDERUNDE_RACE_ID:
        return load_sunderunde_window(km_start=km_start, km_end=km_end)
    if race_id == STAVANGER_HALVMARATHON_RACE_ID:
        return load_stavanger_halvmarathon_window(km_start=km_start, km_end=km_end)
    if race_id == SJOERSLOPET_RACE_ID:
        return load_3_sjoerslopet_window(km_start=km_start, km_end=km_end)
    if race_id == TVERFJELL_RACE_ID:
        return load_tverrfjell_window(km_start=km_start, km_end=km_end)
    if race_id == KLEPP_RUNDE_RACE_ID:
        return load_klepp_runde_window(km_start=km_start, km_end=km_end)
    if race_id == GRAMSTAD_RUNDE_RACE_ID:
        return load_gramstad_runde_window(km_start=km_start, km_end=km_end)
    if race_id == VINJE_TERRENGLOP_RACE_ID:
        return load_vinje_terrenglop_window(km_start=km_start, km_end=km_end)
    orphan_reg = BASE_DIR / "config" / "map_first_orphan_courses.json"
    if orphan_reg.exists():
        orphan_ids = {
            str(c["race_id"]) for c in json.loads(orphan_reg.read_text(encoding="utf-8")).get("courses") or []
        }
        if race_id in orphan_ids:
            return load_map_first_orphan_window(race_id, km_start=km_start, km_end=km_end)
    return load_stress_test_window(km_start=km_start, km_end=km_end, registry=registry)
