"""Sector routing for gold suggester models on SUT_43."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_ROUTING_MANIFEST = BASE_DIR / "config" / "gold_suggester_routing.json"
DEFAULT_MODEL_DIR = BASE_DIR / "07_ML_Models" / "spatial"

# Course km bounds (inclusive start, exclusive end) on SUT_43 stream-distance axis.
SECTOR_START_KM_LO = 0.5
SECTOR_START_KM_HI = 8.0
SECTOR_BRIDGE_KM_LO = 8.0
SECTOR_BRIDGE_KM_HI = 22.0
SECTOR_DOWNSTREAM_KM_LO = 22.0
SECTOR_DOWNSTREAM_KM_HI = 41.0


@dataclass(frozen=True)
class SectorRoute:
    sector_id: str
    km_lo: float
    km_hi: float
    model_path: Path


def default_sector_routes(model_dir: Path | None = None) -> list[SectorRoute]:
    root = model_dir or DEFAULT_MODEL_DIR
    return [
        SectorRoute("start", SECTOR_START_KM_LO, SECTOR_START_KM_HI, root / "gold_suggester_sector_start.joblib"),
        SectorRoute("bridge", SECTOR_BRIDGE_KM_LO, SECTOR_BRIDGE_KM_HI, root / "gold_suggester_sector_bridge.joblib"),
        SectorRoute(
            "downstream",
            SECTOR_DOWNSTREAM_KM_LO,
            SECTOR_DOWNSTREAM_KM_HI,
            root / "gold_suggester_sector_downstream.joblib",
        ),
    ]


def load_routing_manifest(path: Path | None = None) -> list[SectorRoute]:
    manifest_path = path or DEFAULT_ROUTING_MANIFEST
    if not manifest_path.exists():
        return default_sector_routes()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    routes: list[SectorRoute] = []
    for row in payload.get("sectors", []):
        model_path = Path(row["model_path"])
        if not model_path.is_absolute():
            model_path = BASE_DIR / model_path
        routes.append(
            SectorRoute(
                sector_id=str(row["sector_id"]),
                km_lo=float(row["km_lo"]),
                km_hi=float(row["km_hi"]),
                model_path=model_path,
            )
        )
    routes.sort(key=lambda r: r.km_lo)
    return routes


def sector_for_km(km: float, routes: list[SectorRoute]) -> SectorRoute | None:
    for route in routes:
        if route.km_lo <= km < route.km_hi:
            return route
    return None


def resolve_sector_for_window(km_lo: float, km_hi: float, routes: list[SectorRoute]) -> SectorRoute:
    """Pick sector model when the window lies fully inside one sector."""
    mid = (km_lo + km_hi) / 2.0
    hit = sector_for_km(mid, routes)
    if hit is not None:
        return hit
    for route in routes:
        if km_lo >= route.km_lo and km_hi <= route.km_hi:
            return route
    raise ValueError(f"No sector route covers window km {km_lo}–{km_hi}")


def window_sector_slices(km_lo: float, km_hi: float, routes: list[SectorRoute]) -> list[tuple[SectorRoute, float, float]]:
    """Split [km_lo, km_hi) at sector boundaries for per-metre routing."""
    slices: list[tuple[SectorRoute, float, float]] = []
    cursor = km_lo
    while cursor < km_hi - 1e-9:
        route = sector_for_km(cursor + 1e-6, routes)
        if route is None:
            raise ValueError(f"No sector route at km {cursor}")
        seg_hi = min(km_hi, route.km_hi)
        if seg_hi <= cursor:
            break
        slices.append((route, cursor, seg_hi))
        cursor = seg_hi
    return slices


class SectorModelCache:
    """Lazy-load sector joblib bundles."""

    def __init__(self, routes: list[SectorRoute]) -> None:
        self._routes = routes
        self._bundles: dict[str, dict[str, Any]] = {}

    def bundle_for(self, route: SectorRoute) -> dict[str, Any]:
        key = str(route.model_path)
        if key not in self._bundles:
            if not route.model_path.exists():
                raise FileNotFoundError(f"Sector model not found: {route.model_path}")
            self._bundles[key] = joblib.load(route.model_path)
        return self._bundles[key]


def predict_frame_routed(
    frame: pd.DataFrame,
    routes: list[SectorRoute],
    *,
    cache: SectorModelCache | None = None,
) -> pd.DataFrame:
    """Apply sector-specific models to a training frame (requires course_km)."""
    from spatial.suggest_gold_spans import _predict_bundle

    if frame.empty:
        return frame
    if "course_km" not in frame.columns:
        raise ValueError("Routed prediction requires course_km column")
    cache = cache or SectorModelCache(routes)
    km_lo = float(frame["course_km"].min())
    km_hi = float(frame["course_km"].max()) + 0.001
    parts: list[pd.DataFrame] = []
    for route, seg_lo, seg_hi in window_sector_slices(km_lo, km_hi, routes):
        seg = frame[(frame["course_km"] >= seg_lo) & (frame["course_km"] < seg_hi)]
        if seg.empty:
            continue
        bundle = cache.bundle_for(route)
        parts.append(_predict_bundle(seg, bundle))
    if not parts:
        return frame
    return pd.concat(parts, ignore_index=True).sort_values("course_km").reset_index(drop=True)


def manifest_payload(model_dir: Path | None = None) -> dict[str, Any]:
    routes = default_sector_routes(model_dir)
    return {
        "schema_version": "gold_suggester_routing_v0",
        "course_id": "SUT_43",
        "routing_mode": "pure_sector",
        "sectors": [
            {
                "sector_id": r.sector_id,
                "km_lo": r.km_lo,
                "km_hi": r.km_hi,
                "model_path": str(r.model_path),
            }
            for r in routes
        ],
    }


def hybrid_manifest_payload(model_dir: Path | None = None) -> dict[str, Any]:
    root = model_dir or DEFAULT_MODEL_DIR
    v0 = root / "gold_suggester_v0.joblib"
    bridge = root / "gold_suggester_sector_bridge.joblib"
    return {
        "schema_version": "gold_suggester_routing_v0",
        "course_id": "SUT_43",
        "routing_mode": "hybrid",
        "notes": "start and downstream retain gold_suggester_v0; bridge uses corridor-only sector model.",
        "sectors": [
            {"sector_id": "start", "km_lo": SECTOR_START_KM_LO, "km_hi": SECTOR_START_KM_HI, "model_path": str(v0)},
            {"sector_id": "bridge", "km_lo": SECTOR_BRIDGE_KM_LO, "km_hi": SECTOR_BRIDGE_KM_HI, "model_path": str(bridge)},
            {
                "sector_id": "downstream",
                "km_lo": SECTOR_DOWNSTREAM_KM_LO,
                "km_hi": SECTOR_DOWNSTREAM_KM_HI,
                "model_path": str(v0),
            },
        ],
    }
