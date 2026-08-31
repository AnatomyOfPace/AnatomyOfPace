#!/usr/bin/env python3
"""Unit tests for evaluate_fast_finish (synthetic ActivityFrame)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from evaluate_fast_finish import (  # noqa: E402
    evaluate_activity,
    pace_str_to_min_per_km,
    resolve_fast_finish_km,
    resolve_is_recovery_week,
    score_fast_finish,
)
from init_training_compliance_local import init_compliance_db  # noqa: E402
from log_recovery_compliance import (  # noqa: E402
    DEFAULT_PROTOCOL,
    build_override_payload,
    insert_recovery_flag,
)


def _blueprint() -> dict:
    return {
        "subject_id": "Subject_A",
        "week_matrix": {
            "sunday": {
                "session_type": "sunday_simulator",
                "fast_finish": {
                    "enabled": True,
                    "target_pace_min_per_km": "4:44",
                    "tolerance_sec_per_km": 5.0,
                    "default_fast_finish_km": 2.0,
                    "progression_by_month": {
                        "2026-09": {
                            "fast_finish_km_min": 1.5,
                            "fast_finish_km_max": 2.0,
                        },
                        "2026-10": {
                            "fast_finish_km_min": 3.0,
                            "fast_finish_km_max": 5.0,
                        },
                    },
                    "recovery_week": {"drop_fast_finish": True},
                },
            }
        },
    }


def _synthetic_frame(
    *,
    total_km: float = 21.0,
    finish_pace_min_km: float = 4.7333,
    early_hr: float = 145.0,
    late_hr: float = 152.0,
) -> pd.DataFrame:
    # 1 Hz samples along stream distance
    n = int(total_km * 1000)
    distance_m = np.arange(n, dtype=float)
    finish_m = 2000.0
    speed = np.full(n, 1000.0 / (5.2 * 60.0))  # easy early
    finish_speed = 1000.0 / (finish_pace_min_km * 60.0)
    speed[-int(finish_m) :] = finish_speed
    hr = np.linspace(early_hr, late_hr, n)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-09-01", periods=n, freq="s"),
            "elapsed_s": np.arange(n, dtype=float),
            "distance_m": distance_m,
            "course_km": distance_m / 1000.0,
            "heart_rate": hr,
            "speed_mps": speed,
        }
    )


class EvaluateFastFinishTests(unittest.TestCase):
    def test_pace_parse_444(self) -> None:
        self.assertAlmostEqual(pace_str_to_min_per_km("4:44"), 4 + 44 / 60, places=5)

    def test_september_progression_midpoint(self) -> None:
        km = resolve_fast_finish_km(
            _blueprint(), month_key="2026-09", is_recovery_week=False
        )
        self.assertAlmostEqual(km, 1.75, places=5)

    def test_october_progression_midpoint(self) -> None:
        km = resolve_fast_finish_km(
            _blueprint(), month_key="2026-10", is_recovery_week=False
        )
        self.assertAlmostEqual(km, 4.0, places=5)

    def test_recovery_week_drops_fast_finish(self) -> None:
        km = resolve_fast_finish_km(
            _blueprint(), month_key="2026-09", is_recovery_week=True
        )
        self.assertIsNone(km)

    def test_recovery_week_evaluate_is_exempt_not_zero_miss(self) -> None:
        frame = _synthetic_frame(total_km=12.0, finish_pace_min_km=5.5)
        result = evaluate_activity(
            frame,
            activity_id="synth_recovery",
            blueprint=_blueprint(),
            session_meta={
                "subject_id": "Subject_A",
                "session_type": "sunday_simulator",
                "week_id": "2026-W36",
                "month_key": "2026-09",
                "is_recovery_week": True,
                "sunday_distance_cap_km": 12.0,
                "fast_finish_required": False,
            },
        )
        self.assertEqual(result.status, "recovery_exempt")
        self.assertEqual(result.skipped_reason, "recovery_exempt")
        self.assertIsNone(result.compliance_score)
        self.assertIsNone(result.held_target)
        self.assertIsNone(result.pace_delta_sec_per_km)
        self.assertIsNone(result.target_pace_min_per_km)

    def test_top_level_recovery_flag_inherits(self) -> None:
        self.assertTrue(
            resolve_is_recovery_week(
                {"session_type": "sunday_simulator", "week_id": "2026-W36"},
                meta_root={"is_recovery_week": True},
            )
        )
        self.assertFalse(
            resolve_is_recovery_week(
                {
                    "session_type": "sunday_simulator",
                    "week_id": "2026-W38",
                    "is_recovery_week": False,
                },
                meta_root={"is_recovery_week": True},
            )
        )

    def test_held_target_on_444_finish(self) -> None:
        frame = _synthetic_frame(finish_pace_min_km=4.7333)
        result = evaluate_activity(
            frame,
            activity_id="synth_001",
            blueprint=_blueprint(),
            session_meta={
                "subject_id": "Subject_A",
                "session_type": "sunday_simulator",
                "week_id": "2026-W36",
                "month_key": "2026-09",
                "is_recovery_week": False,
            },
        )
        self.assertIsNone(result.skipped_reason)
        self.assertTrue(result.held_target)
        self.assertGreaterEqual(result.compliance_score, 85.0)

    def test_slow_finish_fails(self) -> None:
        frame = _synthetic_frame(finish_pace_min_km=5.2)
        result = evaluate_activity(
            frame,
            activity_id="synth_002",
            blueprint=_blueprint(),
            session_meta={
                "subject_id": "Subject_A",
                "session_type": "sunday_simulator",
                "month_key": "2026-09",
                "is_recovery_week": False,
            },
        )
        self.assertFalse(result.held_target)
        self.assertLess(result.compliance_score, 70.0)

    def test_score_helper_tolerance(self) -> None:
        score, held, delta = score_fast_finish(
            median_pace=pace_str_to_min_per_km("4:49"),
            target_pace=pace_str_to_min_per_km("4:44"),
            tolerance_sec_per_km=5.0,
            cardiac_drift_bpm=3.0,
        )
        self.assertTrue(held)
        self.assertGreater(score, 50.0)
        self.assertAlmostEqual(delta, 5.0, places=1)

    def test_init_refuses_macro_db_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "anatomy_macro.db"
            with self.assertRaises(SystemExit):
                init_compliance_db(bad)

    def test_init_creates_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "training_compliance.local.db"
            init_compliance_db(db)
            self.assertTrue(db.exists())

    def test_log_recovery_inserts_compliance_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "training_compliance.local.db"
            init_compliance_db(db)
            payload = build_override_payload(
                subject_id="Subject_A",
                week_id="2026-W36",
                month_key="2026-09",
                protocol=DEFAULT_PROTOCOL,
                notes=None,
            )
            self.assertEqual(
                payload["protocol"]["tuesday"]["session_type"], "tuesday_rest"
            )
            flag_id = insert_recovery_flag(db, payload=payload, metric_date="2026-09-01")
            self.assertGreaterEqual(flag_id, 1)


if __name__ == "__main__":
    unittest.main()
