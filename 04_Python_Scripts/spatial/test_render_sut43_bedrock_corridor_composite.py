#!/usr/bin/env python3
"""Smoke tests for render_sut43_bedrock_corridor_composite.py."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.render_sut43_bedrock_corridor_composite import (  # noqa: E402
    BEDROCK_CORRIDOR_KM,
    DEFAULT_VIEWPORT_KM,
    build_delta_ti_gap_profile,
    build_elevation_profile,
    render_bedrock_corridor_composite,
)
from spatial.reproject_to_spine import normalize_panel_axes  # noqa: E402
from spatial.spatial_hitl_overlay import load_terrain_map  # noqa: E402

BASE = Path(__file__).resolve().parent.parent.parent
TERRAIN = BASE / "config" / "spatial_terrain_map_sut43.json"


def _synthetic_panel(km_lo: float = 30.0, km_hi: float = 35.0) -> pd.DataFrame:
    kms = np.arange(km_lo, km_hi + 0.001, 0.1)
    lat0, lon0 = 58.8860, 5.8090
    lat1, lon1 = 58.8835, 5.7985
    t = (kms - km_lo) / max(km_hi - km_lo, 1e-6)
    return pd.DataFrame(
        {
            "course_m": (kms * 1000).astype(int),
            "course_km": kms,
            "latitude": lat0 + t * (lat1 - lat0),
            "longitude": lon0 + t * (lon1 - lon0),
            "altitude_m": 280.0 - 60.0 * t + 15.0 * np.sin(kms * 3),
            "activity_id": "SUT43_20260418",
            "donor_id": "Subject_A",
            "session_type": "race",
        }
    )


def _synthetic_paired(km_lo: float = 30.0, km_hi: float = 35.0) -> pd.DataFrame:
    kms = np.arange(km_lo, km_hi + 0.001, 0.001)
    gap = 0.05 * np.sin(kms * 4)
    gap += np.where((kms >= 31.08) & (kms <= 33.80), 0.7, 0.0)
    return pd.DataFrame({"course_km": kms, "delta_ti_gap": gap})


class BedrockCorridorCompositeTests(unittest.TestCase):
    def test_profile_builders(self) -> None:
        panel = _synthetic_panel()
        paired = _synthetic_paired()
        v_lo, v_hi = DEFAULT_VIEWPORT_KM
        elev = build_elevation_profile(panel, v_lo, v_hi)
        gap = build_delta_ti_gap_profile(paired, v_lo, v_hi, rolling_m=25)
        self.assertGreater(len(elev), 10)
        self.assertGreater(len(gap), 10)

    def test_render_composite_without_basemap(self) -> None:
        if not TERRAIN.exists():
            self.skipTest("terrain map not in workspace")
        terrain_map = load_terrain_map(TERRAIN)
        panel = normalize_panel_axes(_synthetic_panel())
        paired = _synthetic_paired()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "composite.png"
            path = render_bedrock_corridor_composite(
                terrain_map,
                panel,
                paired,
                output_path=out,
                gpx_path=None,
                require_basemap=False,
                corridor_km=BEDROCK_CORRIDOR_KM,
            )
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
