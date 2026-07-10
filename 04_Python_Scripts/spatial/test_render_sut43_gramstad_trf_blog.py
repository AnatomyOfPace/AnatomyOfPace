#!/usr/bin/env python3
"""Smoke tests for render_sut43_gramstad_trf_blog.py."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.render_sut43_gramstad_trf_blog import (  # noqa: E402
    render_delta_ti_gap_spine,
    render_dilution_figure,
    render_friction_strip,
    render_paired_figure,
)

BASE = Path(__file__).resolve().parent.parent.parent
TERRAIN = BASE / "config" / "spatial_terrain_map_sut43.json"


def _minimal_report(subject: str, delta: float) -> dict:
    cell = {
        "friction_tier": "F3",
        "grade_band": "downhill",
        "locomotion_mode": "hike",
        "delta_ti_mean": delta,
        "course_km_start": 29.8,
        "course_km_end": 39.1,
        "impact_score": abs(delta) * 1000,
    }
    return {
        "subject_id": subject,
        "cells": [cell],
        "top_cells_by_impact": [cell],
    }


class RenderTrfBlogTests(unittest.TestCase):
    def test_friction_strip_writes_png(self) -> None:
        if not TERRAIN.exists():
            self.skipTest("terrain map not in workspace")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "strip.png"
            render_friction_strip(TERRAIN, output_path=out)
            self.assertGreater(out.stat().st_size, 1000)

    def test_paired_and_dilution_png(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ra = _minimal_report("Subject_A", 0.68)
            rb = _minimal_report("Subject_B", -0.18)
            rf = _minimal_report("Subject_A", 0.08)
            render_paired_figure(ra, rb, tmp_path / "paired.png")
            render_dilution_figure(rf, ra, tmp_path / "dilution.png")
            self.assertTrue((tmp_path / "paired.png").exists())
            self.assertTrue((tmp_path / "dilution.png").exists())

    def test_delta_ti_gap_spine_png(self) -> None:
        km = np.linspace(29.0, 40.99, 2400)
        gap = 0.05 * np.sin((km - 29.0) * 0.8)
        gap += np.where((km >= 31.08) & (km <= 33.80), 0.85 + 0.1 * np.sin(km * 12), 0.0)
        paired = pd.DataFrame(
            {
                "course_km": km,
                "ref_chainage_m": (km * 1000).astype(int),
                "delta_ti_gap": gap,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "gap.png"
            render_delta_ti_gap_spine(paired, output_path=out)
            self.assertGreater(out.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
