#!/usr/bin/env python3
"""Apply October peak local overrides to gitignored meso blueprint files.

Updates only:
  - config/training_blueprint.local.json
  - config/session_metadata.local.json (summary block)

Never touches anatomy_macro.db. Base-pace companion context stays clinical
(no personal names). Fast-finish target remains 4:44 for evaluate_fast_finish.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
BLUEPRINT_EXAMPLE = BASE_DIR / "config" / "training_blueprint.local.example.json"
BLUEPRINT_LOCAL = BASE_DIR / "config" / "training_blueprint.local.json"
SESSION_EXAMPLE = BASE_DIR / "config" / "session_metadata.local.example.json"
SESSION_LOCAL = BASE_DIR / "config" / "session_metadata.local.json"
MACRO_DB = BASE_DIR / "05_Macro_Database" / "anatomy_macro.db"

# October local override: slower base for easy companion cruise; finish unchanged.
OCTOBER_BASE_PACE = "6:45"
OCTOBER_FAST_FINISH = "4:44"


def _refuse_if_macro(path: Path) -> None:
    if path.resolve() == MACRO_DB.resolve() or "anatomy_macro" in path.name:
        raise SystemExit("Refusing to write October overrides into anatomy_macro.db")


def ensure_local_from_example(example: Path, local: Path) -> None:
    if not local.exists():
        if not example.exists():
            raise FileNotFoundError(f"Missing example template: {example}")
        shutil.copy(example, local)
        print(f"created {local} from example")


def patch_october_protocol(blueprint: dict[str, Any]) -> dict[str, Any]:
    sunday = blueprint.setdefault("week_matrix", {}).setdefault("sunday", {})
    protocols = sunday.setdefault("execution_protocols", {})
    peak = protocols.setdefault("2026-10-peak", {})
    peak["label"] = "october_peak_stokkavatnet_halandsvatnet"
    peak["phase"] = "peak_race_simulator"
    peak["is_recovery_week"] = False
    peak["total_volume"] = {"distance_km_min": 16.0, "distance_km_max": 18.0}
    peak["venue"] = {
        "loop": "Store_Stokkavatnet_Halandsvatnet",
        "planned_combo_km_min": 16.0,
        "planned_combo_km_max": 17.0,
        "notes": (
            "Store Stokkavatnet + Hålandsvatnet combo; stream distance "
            "(not 3_sjoerslopet course projection)"
        ),
    }
    peak["base_execution"] = {
        "distance_km_min": 11.0,
        "distance_km_max": 15.0,
        "pace_min_per_km_lo": OCTOBER_BASE_PACE,
        "pace_min_per_km_hi": OCTOBER_BASE_PACE,
        "pace_mode": "easy_companion_cruise",
        "notes": (
            f"Cruise first 11–15 km at {OCTOBER_BASE_PACE} min/km "
            "(easy companion cruise). Longer time-on-feet before threshold."
        ),
    }
    peak["trigger"] = {
        "stream_km_window_start_min": 11.0,
        "stream_km_window_start_max": 15.0,
        "action": "shift_to_target_pace",
        "target_pace_min_per_km": OCTOBER_FAST_FINISH,
        "notes": "Begin fast finish so final 3–5 km land at target",
    }
    peak["finish"] = {
        "fast_finish_km_min": 3.0,
        "fast_finish_km_max": 5.0,
        "target_pace_min_per_km": OCTOBER_FAST_FINISH,
        "condition": "depleted_legs",
        "notes": "Unchanged: full race-simulation finish @ 4:44 despite slower base",
    }
    peak["fueling"] = {
        "mandatory": True,
        "carbs_g_per_hr_min": 45,
        "carbs_g_per_hr_max": 60,
        "start_early": True,
        "required_log": True,
        "product_hint": "threshold_gel_support",
        "intent": (
            "Mandatory 45–60 g/hr — slower 6:45 base increases total time on feet "
            "before the 3–5 km @ 4:44 threshold block"
        ),
    }
    peak["evaluator"] = {
        "session_type": "sunday_simulator",
        "month_key": "2026-10",
        "is_recovery_week": False,
        "fast_finish_required": True,
        "fast_finish_km_band": [3.0, 5.0],
        "target_pace_min_per_km": OCTOBER_FAST_FINISH,
        "notes": (
            "evaluate_fast_finish scores only the final 3–5 km vs 4:44; "
            "base cruise pace is ignored by the evaluator"
        ),
    }
    # Keep monthly progression band aligned with finish window
    ff = sunday.setdefault("fast_finish", {})
    ff["target_pace_min_per_km"] = OCTOBER_FAST_FINISH
    prog = ff.setdefault("progression_by_month", {})
    prog["2026-10"] = {"fast_finish_km_min": 3.0, "fast_finish_km_max": 5.0}
    return blueprint


def patch_session_summary(meta: dict[str, Any]) -> dict[str, Any]:
    meta["october_peak_protocol_summary"] = {
        "phase": "peak_race_simulator",
        "total_volume_km": [16.0, 18.0],
        "venue_combo_km": [16.0, 17.0],
        "venue": "Store_Stokkavatnet_Halandsvatnet",
        "base_km": [11.0, 15.0],
        "base_pace_min_per_km": [OCTOBER_BASE_PACE, OCTOBER_BASE_PACE],
        "base_pace_mode": "easy_companion_cruise",
        "fast_finish_km": [3.0, 5.0],
        "target_pace_min_per_km": OCTOBER_FAST_FINISH,
        "carbs_g_per_hr": [45, 60],
        "fueling_mandatory_early": True,
        "detail": (
            "Local override: base 6:45; finish still 3–5 km @ 4:44. "
            "See training_blueprint.local.json execution_protocols.2026-10-peak"
        ),
    }
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Patch gitignored October peak blueprint (meso only)."
    )
    parser.add_argument("--blueprint", type=Path, default=BLUEPRINT_LOCAL)
    parser.add_argument("--session-meta", type=Path, default=SESSION_LOCAL)
    args = parser.parse_args(argv)

    _refuse_if_macro(args.blueprint)
    _refuse_if_macro(args.session_meta)
    ensure_local_from_example(BLUEPRINT_EXAMPLE, args.blueprint)
    ensure_local_from_example(SESSION_EXAMPLE, args.session_meta)

    blueprint = json.loads(args.blueprint.read_text(encoding="utf-8"))
    blueprint = patch_october_protocol(blueprint)
    args.blueprint.write_text(json.dumps(blueprint, indent=2) + "\n", encoding="utf-8")

    meta = json.loads(args.session_meta.read_text(encoding="utf-8"))
    meta = patch_session_summary(meta)
    args.session_meta.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    peak = blueprint["week_matrix"]["sunday"]["execution_protocols"]["2026-10-peak"]
    print("october_local_override_applied")
    print(f"  blueprint:     {args.blueprint}")
    print(f"  base_pace:     {peak['base_execution']['pace_min_per_km_lo']} min/km")
    print(f"  total_km:      {peak['total_volume']}")
    print(f"  fast_finish:   {peak['finish']['fast_finish_km_min']}–"
          f"{peak['finish']['fast_finish_km_max']} km @ "
          f"{peak['finish']['target_pace_min_per_km']}")
    print(f"  fueling:       {peak['fueling']['carbs_g_per_hr_min']}–"
          f"{peak['fueling']['carbs_g_per_hr_max']} g/hr (mandatory)")
    print("  macro_db:      untouched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
