#!/usr/bin/env python3
"""Smoke tests for render_sut43_bedrock_corridor_basemap.py."""

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

from spatial.render_sut43_bedrock_corridor_basemap import (  # noqa: E402
    BEDROCK_CORRIDOR_KM,
    plot_corridor_slice_highlight,
    render_bedrock_corridor_basemap,
)
from spatial.spatial_hitl_overlay import load_terrain_map  # noqa: E402

BASE = Path(__file__).resolve().parent.parent.parent
TERRAIN = BASE / "config" / "spatial_terrain_map_sut43.json"


def _synthetic_panel(km_lo: float = 30.0, km_hi: float = 35.0, step_m: int = 100) -> pd.DataFrame:
    """Minimal race FIT panel along a short lat/lon segment (Gramstad-scale)."""
    kms = np.arange(km_lo, km_hi + 0.001, step_m / 1000.0)
    lat0, lon0 = 58.8860, 5.8090
    lat1, lon1 = 58.8835, 5.7985
    t = (kms - km_lo) / max(km_hi - km_lo, 1e-6)
    return pd.DataFrame(
        {
            "course_m": (kms * 1000).astype(int),
            "course_km": kms,
            "latitude": lat0 + t * (lat1 - lat0),
            "longitude": lon0 + t * (lon1 - lon0),
            "altitude_m": 220.0 - 40.0 * t,
            "activity_id": "SUT43_20260418",
            "donor_id": "Subject_A",
            "session_type": "race",
        }
    )


class BedrockCorridorBasemapTests(unittest.TestCase):
    def test_corridor_highlight_no_crash_on_synthetic_geo(self) -> None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        geo = _synthetic_panel()
        fig, ax = plt.subplots()
        drawn = plot_corridor_slice_highlight(ax, geo, BEDROCK_CORRIDOR_KM)
        plt.close(fig)
        self.assertTrue(drawn)

    def test_render_writes_png_without_basemap(self) -> None:
        if not TERRAIN.exists():
            self.skipTest("terrain map not in workspace")
        terrain_map = load_terrain_map(TERRAIN)
        panel = _synthetic_panel()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "corridor_basemap.png"
            path = render_bedrock_corridor_basemap(
                terrain_map,
                panel,
                output_path=out,
                gpx_path=None,
                require_basemap=False,
            )
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 500)


if __name__ == "__main__":
    unittest.main()
