"""
Project activity GPS onto organiser GPX → course_km column.

Reuses nearest-point-on-polyline logic aligned with generate_sut_race_hook_plots.py.
LFI races without organiser GPX fall back to stream distance (distance_m / 1000).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ORGANISER_GPX_DIR = BASE_DIR / "02_Raw_Data" / "organiser_gpx"
GPX_NS = {"gpx": "http://www.topografix.com/GPX/1/1"}

RACE_GPX: dict[str, str] = {
    "SUT_160": "COURSE_SUT160_official_2027.gpx",
    "SUT_43": "COURSE_SUT43_official_2027.gpx",
    "SUT_80": "COURSE_SUT80_official_2027.gpx",
    "SUT_10": "COURSE_SUT10_official_2027.gpx",
}

# Races where corridor km windows are calibrated on FIT stream distance (not GPX axis).
STREAM_DISTANCE_RACES = frozenset(
    {
        "LFI",
        "LFI_62",
        "LFI_2026",
        "SUT_43",
        "SUT_23",
        "SUT_10",
        "tverrfjell",
        "klepp_runde",
        "gramstad_runde",
        "vinje_terrenglop",
    }
)


def resolve_gpx_path(race_id: str | None, gpx_path: Path | None = None) -> Path | None:
    """Return organiser GPX path for race_id, explicit override, or None (stream fallback)."""
    if gpx_path is not None:
        p = Path(gpx_path)
        return p if p.is_absolute() else BASE_DIR / p
    if not race_id:
        return None
    rid = race_id.strip()
    if rid in STREAM_DISTANCE_RACES or rid.startswith("LFI") or rid.startswith("SUT_43"):
        return None
    fname = RACE_GPX.get(rid)
    if fname is None:
        return None
    path = ORGANISER_GPX_DIR / fname
    if not path.exists():
        raise FileNotFoundError(f"Organiser GPX not found for {rid}: {path}")
    return path


def load_gpx_latlon(path: Path) -> tuple[np.ndarray, np.ndarray]:
    root = ET.parse(path).getroot()
    lats: list[float] = []
    lons: list[float] = []
    for trkpt in root.findall(".//gpx:trkpt", GPX_NS):
        lat = trkpt.get("lat")
        lon = trkpt.get("lon")
        if lat is None or lon is None:
            continue
        lats.append(float(lat))
        lons.append(float(lon))
    if not lats:
        raise ValueError(f"No track points in {path.name}")
    return np.asarray(lats), np.asarray(lons)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
    return float(2 * r * np.arcsin(np.sqrt(np.clip(a, 0, 1))))


def load_gpx_course_km(path: Path) -> pd.DataFrame:
    """Organiser GPX track with cumulative haversine distance_km (course axis)."""
    lats, lons = load_gpx_latlon(path)
    keep = [0]
    for i in range(1, len(lats)):
        if lats[i] != lats[i - 1] or lons[i] != lons[i - 1]:
            keep.append(i)
    lats, lons = lats[keep], lons[keep]
    seg_m = np.zeros(len(lats))
    for i in range(1, len(lats)):
        seg_m[i] = _haversine_m(lats[i - 1], lons[i - 1], lats[i], lons[i])
    return pd.DataFrame(
        {"latitude": lats, "longitude": lons, "distance_km": np.cumsum(seg_m) / 1000.0}
    ).sort_values("distance_km")


def _nearest_track_km_batch(
    course: pd.DataFrame,
    lats: np.ndarray,
    lons: np.ndarray,
) -> np.ndarray:
    """Nearest GPX vertex course_km for each (lat, lon) — matches hook-plot snap."""
    work = course.sort_values("distance_km")
    clat = work["latitude"].to_numpy(dtype=float)
    clon = work["longitude"].to_numpy(dtype=float)
    ckm = work["distance_km"].to_numpy(dtype=float)
    out = np.full(len(lats), np.nan, dtype=float)
    valid = np.isfinite(lats) & np.isfinite(lons)
    if not valid.any():
        return out

    for idx in np.where(valid)[0]:
        lat, lon = float(lats[idx]), float(lons[idx])
        cos_lat = np.cos(np.radians(lat))
        dlat = (clat - lat) * 111_320.0
        dlon = (clon - lon) * cos_lat * 111_320.0
        i = int(np.argmin(dlat * dlat + dlon * dlon))
        out[idx] = ckm[i]
    return out


def project_course_km(
    frame: pd.DataFrame,
    *,
    race_id: str | None = None,
    gpx_path: Path | None = None,
) -> pd.DataFrame:
    """
    Assign course_km along organiser GPX (SUT races) or stream distance (LFI).

    Requires latitude/longitude for GPX snap; stream fallback uses distance_m.
    """
    out = frame.copy()
    gpx = resolve_gpx_path(race_id, gpx_path)

    if gpx is None:
        if "distance_m" in out.columns:
            out["course_km"] = pd.to_numeric(out["distance_m"], errors="coerce") / 1000.0
        else:
            out["course_km"] = float("nan")
        return out

    if not {"latitude", "longitude"}.issubset(out.columns):
        raise ValueError("GPX projection requires latitude and longitude columns")

    course = load_gpx_course_km(gpx)
    lats = pd.to_numeric(out["latitude"], errors="coerce").to_numpy(dtype=float)
    lons = pd.to_numeric(out["longitude"], errors="coerce").to_numpy(dtype=float)
    out["course_km"] = _nearest_track_km_batch(course, lats, lons)
    return out
