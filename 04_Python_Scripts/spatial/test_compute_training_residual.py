#!/usr/bin/env python3
"""Unit tests for compute_training_residual (synthetic panel)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from spatial.compute_training_residual import (  # noqa: E402
    aggregate_residual_cells,
    build_subject_residual,
)


def _minimal_terrain_map() -> dict:
    return {
        "hitl": {
            "operator_gold_spans": [
                {
                    "course_km_start": 29.0,
                    "course_km_end": 41.0,
                    "surface_class": "S3",
                    "friction_tier": "F2",
                }
            ],
            "trf_exclusions": [],
        }
    }


def _synthetic_race_panel(n_per_subject: int = 500) -> pd.DataFrame:
    km = np.linspace(29.0, 40.99, n_per_subject)
    rows = []
    for subject, scale in (("Subject_A", 1.15), ("Subject_B", 1.0)):
        for i, k in enumerate(km):
            rows.append(
                {
                    "donor_id": subject,
                    "subject_id": subject,
                    "session_type": "race",
                    "course_m": int(round(k * 1000)) + (0 if subject == "Subject_A" else 1),
                    "course_km": k,
                    "ref_chainage_m": int(round(k * 1000)),
                    "activity_course_km": k,
                    "ti": 1.2 * scale + 0.05 * np.sin(k),
                    "grade_pct": 5.0 if k < 35 else -8.0,
                    "cadence_spm": 140.0,
                    "speed_mps": 2.0,
                }
            )
    return pd.DataFrame(rows)


class ComputeTrainingResidualTests(unittest.TestCase):
    def test_build_subject_residual_delta_positive_for_hotter_athlete(self) -> None:
        panel = _synthetic_race_panel()
        terrain = _minimal_terrain_map()
        df = build_subject_residual(
            panel,
            terrain,
            subject_id="Subject_A",
            baseline_mode="cohort_median",
            km_start=29.0,
            km_end=41.0,
            session_type="race",
        )
        self.assertGreater(df["delta_ti"].mean(), 0.0)

    def test_aggregate_cells_returns_sorted_impact(self) -> None:
        panel = _synthetic_race_panel()
        terrain = _minimal_terrain_map()
        df = build_subject_residual(
            panel,
            terrain,
            subject_id="Subject_A",
            baseline_mode="cohort_median",
            km_start=29.0,
            km_end=41.0,
        )
        cells = aggregate_residual_cells(
            df,
            subject_id="Subject_A",
            sector_id="gramstad_band",
            delta_threshold=0.15,
            baseline_mode="cohort_median",
        )
        self.assertTrue(cells)
        impacts = [c["impact_score"] for c in cells]
        self.assertEqual(impacts, sorted(impacts, reverse=True))

    def test_sector_id_propagates_to_cells(self) -> None:
        panel = _synthetic_race_panel(200)
        terrain = _minimal_terrain_map()
        df = build_subject_residual(
            panel,
            terrain,
            subject_id="Subject_B",
            baseline_mode="cohort_median",
            km_start=29.0,
            km_end=41.0,
            sector_id="sut43_full_race",
        )
        cells = aggregate_residual_cells(
            df,
            subject_id="Subject_B",
            sector_id="sut43_full_race",
            delta_threshold=0.15,
            baseline_mode="cohort_median",
        )
        self.assertTrue(all(c["sector_id"] == "sut43_full_race" for c in cells))


    def test_dedupe_spine_metres_before_cell_count(self) -> None:
        panel = _synthetic_race_panel(100)
        # Duplicate every spine metre for Subject_B (simulates reprojection overlap).
        dup = panel[panel["donor_id"] == "Subject_B"].copy()
        dup["course_m"] = dup["course_m"] + 1
        panel = pd.concat([panel, dup], ignore_index=True)
        terrain = _minimal_terrain_map()
        df = build_subject_residual(
            panel,
            terrain,
            subject_id="Subject_B",
            baseline_mode="cohort_median",
            km_start=31.0,
            km_end=34.0,
            sector_id="bedrock_late_braking",
        )
        from spatial.compute_training_residual import trf_analysis_frame

        analysis = trf_analysis_frame(df)
        self.assertLessEqual(
            len(analysis),
            3000,
            "Corridor window should not exceed ~3k deduped spine metres",
        )
        cells = aggregate_residual_cells(
            analysis,
            subject_id="Subject_B",
            sector_id="bedrock_late_braking",
            delta_threshold=0.15,
            baseline_mode="cohort_median",
        )
        total_metres = sum(c["metre_count"] for c in cells)
        self.assertLessEqual(total_metres, len(analysis))


if __name__ == "__main__":
    unittest.main()
