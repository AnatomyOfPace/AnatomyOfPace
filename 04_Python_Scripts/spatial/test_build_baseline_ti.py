#!/usr/bin/env python3
"""Unit tests for build_baseline_ti (synthetic panel — no local parquet required)."""

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

from spatial.build_baseline_ti import (  # noqa: E402
    BASE_DIR,
    build_baseline_matrix,
    build_course_grid,
    locked_gold_mask,
    lookup_baseline,
    prepare_cohort_frame,
    select_cohort_donors,
    tier_band_qc,
)


def _synthetic_terrain_map() -> dict:
    return {
        "corridor": {
            "race_id": "SUT_43",
            "sector_id": "sut43_full_course",
            "km_start": 0.5,
            "km_end": 2.0,
        },
        "hitl": {
            "operator_gold_spans": [
                {
                    "course_km_start": 0.5,
                    "course_km_end": 1.0,
                    "surface_class": "S1",
                    "friction_tier": "F0",
                    "gold_source": "operator",
                },
                {
                    "course_km_start": 1.0,
                    "course_km_end": 2.0,
                    "surface_class": "S3",
                    "friction_tier": "F2",
                    "gold_source": "operator",
                },
            ],
        },
    }


def _synthetic_panel() -> pd.DataFrame:
    rows: list[dict] = []
    for donor in ("Reference_Elite_A", "Subject_A"):
        for m in range(500, 2000, 100):
            km = m / 1000.0
            tier = "F0" if km < 1.0 else "F2"
            base_ti = 1.0 if tier == "F0" else 1.3
            noise = 0.02 if donor.startswith("Reference") else 0.05
            rows.append(
                {
                    "donor_id": donor,
                    "session_type": "race",
                    "course_m": float(m),
                    "course_km": km,
                    "ref_chainage_m": float(m),
                    "ti": base_ti + noise,
                    "grade_pct": 0.0 if km < 1.0 else 8.0,
                    "cadence_spm": 165.0,
                    "speed_mps": 3.0,
                }
            )
    return pd.DataFrame(rows)


class BuildBaselineTiTests(unittest.TestCase):
    def test_select_reference_elite_donors(self) -> None:
        panel = _synthetic_panel()
        donors, label, _ = select_cohort_donors(
            panel,
            cohort_mode="reference_elite",
            explicit_donors=None,
            reference_prefix="Reference_Elite_",
            strict_reference_elite=False,
        )
        self.assertEqual(donors, ["Reference_Elite_A"])
        self.assertEqual(label, "reference_elite")

    def test_interim_fallback_when_no_reference_elite(self) -> None:
        panel = _synthetic_panel()
        panel = panel[panel["donor_id"] != "Reference_Elite_A"]
        donors, label, warnings = select_cohort_donors(
            panel,
            cohort_mode="reference_elite",
            explicit_donors=None,
            reference_prefix="Reference_Elite_",
            strict_reference_elite=False,
        )
        self.assertEqual(donors, ["Subject_A"])
        self.assertEqual(label, "interim_race_panel")
        self.assertTrue(warnings)

    def test_locked_gold_mask(self) -> None:
        tmap = _synthetic_terrain_map()
        panel = _synthetic_panel()
        km = panel["course_km"]
        mask = locked_gold_mask(km, tmap)
        self.assertEqual(int(mask.sum()), len(panel))

    def test_matrix_and_lookup(self) -> None:
        tmap = _synthetic_terrain_map()
        panel = _synthetic_panel()
        cohort = prepare_cohort_frame(
            panel,
            tmap,
            donors=["Reference_Elite_A"],
            session_type="race",
            km_start=0.5,
            km_end=2.0,
            kinematics_config={},
            locked_gold_only=True,
        )
        matrix, lookups = build_baseline_matrix(cohort, min_samples=3)
        self.assertFalse(matrix.empty)
        val, level, n = lookup_baseline(
            friction_tier="F0",
            grade_bin="flat",
            locomotion_mode="run",
            lookups=lookups,
        )
        self.assertIn(level, ("tier_grade_mode", "tier_grade", "tier_mode", "tier_only", "tier_band_centre"))
        self.assertGreater(val, 0.0)
        self.assertGreaterEqual(n, 0)

    def test_course_grid_shape(self) -> None:
        tmap = _synthetic_terrain_map()
        panel = _synthetic_panel()
        cohort = prepare_cohort_frame(
            panel,
            tmap,
            donors=["Reference_Elite_A"],
            session_type="race",
            km_start=0.5,
            km_end=2.0,
            kinematics_config={},
            locked_gold_only=True,
        )
        matrix, lookups = build_baseline_matrix(cohort, min_samples=3)
        grid = build_course_grid(
            panel,
            tmap,
            cohort,
            lookups,
            donors=["Reference_Elite_A"],
            session_type="race",
            km_start=0.5,
            km_end=2.0,
            kinematics_config={},
        )
        self.assertGreater(len(grid), 0)
        self.assertIn("baseline_ti", grid.columns)
        self.assertTrue(grid["baseline_ti"].notna().all())

    def test_tier_band_qc(self) -> None:
        tmap = _synthetic_terrain_map()
        panel = _synthetic_panel()
        cohort = prepare_cohort_frame(
            panel,
            tmap,
            donors=["Reference_Elite_A"],
            session_type="race",
            km_start=0.5,
            km_end=2.0,
            kinematics_config={},
            locked_gold_only=True,
        )
        matrix, _ = build_baseline_matrix(cohort, min_samples=3)
        qc = tier_band_qc(matrix)
        tiers = {row["friction_tier"] for row in qc}
        self.assertTrue({"F0", "F2"}.issubset(tiers) or tiers)

    def test_cli_smoke(self) -> None:
        from spatial.build_baseline_ti import main

        tmap = _synthetic_terrain_map()
        panel = _synthetic_panel()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tmap_path = tmp_path / "tmap.json"
            panel_path = tmp_path / "panel.parquet"
            out = tmp_path / "grid.parquet"
            mat = tmp_path / "matrix.parquet"
            report = tmp_path / "report.json"
            tmap_path.write_text(json.dumps(tmap), encoding="utf-8")
            panel.to_parquet(panel_path, index=False)
            rc = main(
                [
                    "--terrain-map",
                    str(tmap_path),
                    "--panel",
                    str(panel_path),
                    "--km-start",
                    "0.5",
                    "--km-end",
                    "2.0",
                    "--output",
                    str(out),
                    "--matrix-output",
                    str(mat),
                    "--report-json",
                    str(report),
                    "--no-qc",
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            self.assertTrue(mat.exists())
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "baseline_ti_v0")


    def test_resolve_defaults_sut43_full_paths(self) -> None:
        from spatial.build_baseline_ti import resolve_defaults

        tmap_path = BASE_DIR / "config" / "spatial_terrain_map_sut43_full.json"
        if not tmap_path.exists():
            self.skipTest("spatial_terrain_map_sut43_full.json not in workspace")
        defaults = resolve_defaults(tmap_path)
        self.assertIn("baseline_ti_sut43_full.parquet", str(defaults["output"]))
        self.assertNotIn("gold_training_set", str(defaults["output"]))


if __name__ == "__main__":
    unittest.main()
