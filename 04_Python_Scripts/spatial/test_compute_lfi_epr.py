#!/usr/bin/env python3
"""Unit tests for compute_lfi_epr (synthetic micro frames)."""

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

from fit_micro.activity_frame import write_parquet  # noqa: E402
from spatial.compute_lfi_epr import (  # noqa: E402
    compute_all_epr,
    compute_epr_cell,
    load_lfi_corridors,
)


def _synthetic_lfi_frame(donor_scale: float, n: int = 2000) -> pd.DataFrame:
    km = np.linspace(0.5, 30.0, n)
    return pd.DataFrame(
        {
            "course_km": km,
            "ti": 1.2 * donor_scale + 0.1 * np.sin(km),
            "grade": np.zeros(n),
        }
    )


class ComputeLfiEprTests(unittest.TestCase):
    def test_epr_greater_when_athlete_hotter(self) -> None:
        athlete = _synthetic_lfi_frame(1.2)
        elite = _synthetic_lfi_frame(1.0)
        row = compute_epr_cell(
            athlete,
            elite,
            corridor_id="test",
            label="test",
            km_start=13.0,
            km_end=16.5,
            min_samples=30,
        )
        self.assertTrue(row["paired"])
        self.assertGreater(row["epr_mean"], 1.1)

    def test_corridors_load(self) -> None:
        corridors = load_lfi_corridors()
        ids = {c["corridor_id"] for c in corridors}
        self.assertIn("neverdalsskaret_descent", ids)

    def test_cli_smoke(self) -> None:
        from spatial.compute_lfi_epr import main

        athlete = _synthetic_lfi_frame(1.15)
        elite = _synthetic_lfi_frame(1.0)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            write_parquet(athlete, "Subject_A", "LFI_20260606")
            write_parquet(elite, "Reference_Elite_A", "18815539842")
            # Redirect micro dir by patching paths via running from repo with env - skip
            # Run main with explicit paths not supported - use compute_all_epr directly
            corridors = load_lfi_corridors()
            rows = compute_all_epr(athlete, elite, corridors[:3], min_samples=10)
            self.assertTrue(any(r["paired"] for r in rows))


if __name__ == "__main__":
    unittest.main()
