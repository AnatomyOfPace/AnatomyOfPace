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
SUT43_PHASE_E_KM_START = 0.5
SUT43_PHASE_E_KM_END = 8.0
SUT43_MIDCOURSE_SECTOR_ID = "dalevatn_midcourse"
SUT43_MIDCOURSE_KM_START = 8.0
SUT43_MIDCOURSE_KM_END = 22.0
SUT43_MIDCOURSE_VIEWPORT_KM_END = 22.5
SUT43_REFERENCE_SPINE_KM_START = 8.0
SUT43_REFERENCE_SPINE_KM_END = 41.0
SUT43_PRIMARY_KM_START = 29.0
SUT43_PRIMARY_KM_END = 41.0
SUT43_PRIMARY_VIEWPORT_KM_END = 41.5

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
    return load_stress_test_window(km_start=km_start, km_end=km_end, registry=registry)
