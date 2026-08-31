#!/usr/bin/env python3
"""Log a recovery-week override into training_compliance.local.db (meso only).

Inserts one row into existing compliance_flags — no schema changes.
Never touches anatomy_macro.db.

Tuesday rest session_type convention: ``tuesday_rest`` (not generic rest_override).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = BASE_DIR / "training_compliance.local.db"
DEFAULT_SESSION_META = BASE_DIR / "config" / "session_metadata.local.json"
MACRO_DB = BASE_DIR / "05_Macro_Database" / "anatomy_macro.db"

# Canonical recovery-week protocol (private meso). Edit via --protocol-json if needed.
DEFAULT_PROTOCOL: dict[str, Any] = {
    "tuesday": {"session_type": "tuesday_rest", "status": "rest"},
    "wednesday": {"session_type": "wednesday_recovery", "distance_km": 8.2},
    "friday": {
        "session_type": "friday_aerobic",
        "easy_jog_km_min": 5.0,
        "easy_jog_km_max": 7.0,
        "lift_intensity_factor": 0.8,
    },
    "sunday": {
        "session_type": "sunday_simulator",
        "distance_cap_km": 12.0,
        "fast_finish": False,
    },
}

FLAG_TYPE = "recovery_week_override"


def _refuse_macro(db_path: Path) -> Path:
    resolved = db_path.resolve()
    if resolved == MACRO_DB.resolve() or "anatomy_macro" in resolved.name:
        raise SystemExit("Refusing to write recovery override into anatomy_macro.db")
    return resolved


def load_session_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Copy config/session_metadata.local.example.json first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def build_override_payload(
    *,
    subject_id: str,
    week_id: str,
    month_key: str | None,
    protocol: dict[str, Any],
    notes: str | None,
) -> dict[str, Any]:
    return {
        "flag_type": FLAG_TYPE,
        "subject_id": subject_id,
        "week_id": week_id,
        "month_key": month_key,
        "is_recovery_week": True,
        "sunday_distance_cap_km": float(
            (protocol.get("sunday") or {}).get("distance_cap_km", 12.0)
        ),
        "fast_finish_required": False,
        "protocol": protocol,
        "notes": notes
        or (
            "Recovery override: Tue rest (tuesday_rest); Wed 8.2 km; "
            "Fri 5–7 km + 80% lift; Sun 12 km cap; fast finish removed"
        ),
    }


def insert_recovery_flag(
    db_path: Path,
    *,
    payload: dict[str, Any],
    metric_date: str | None = None,
    activity_id: str | None = None,
) -> int:
    resolved = _refuse_macro(db_path)
    if not resolved.exists():
        raise FileNotFoundError(
            f"Compliance DB missing: {resolved}. Run init_training_compliance_local.py first."
        )

    day = metric_date or date.today().isoformat()
    message = json.dumps(payload, ensure_ascii=True)
    conn = sqlite3.connect(resolved)
    try:
        cur = conn.execute(
            """
            INSERT INTO compliance_flags (
                activity_id, metric_date, flag_type, severity, message
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (activity_id, day, FLAG_TYPE, "info", message),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def sync_current_week_metadata(
    meta_path: Path,
    *,
    week_id: str,
    month_key: str | None,
    protocol: dict[str, Any],
    notes: str | None,
) -> None:
    """Update gitignored session_metadata.local.json current_week + stamp activities."""
    data = load_session_meta(meta_path)
    notes_text = notes or (
        "Recovery override: Tue rest; Wed 8.2 km; Fri 5–7 km + 80% lift; "
        "Sun 12 km cap; fast finish removed"
    )
    data["current_week"] = {
        "week_id": week_id,
        "month_key": month_key,
        "is_recovery_week": True,
        "sunday_distance_cap_km": float(
            (protocol.get("sunday") or {}).get("distance_cap_km", 12.0)
        ),
        "fast_finish_required": False,
        "protocol": protocol,
        "notes": notes_text,
    }
    # Stamp existing activity tags in this week as recovery
    activities = data.get("activities") or {}
    for _aid, meta in activities.items():
        if not isinstance(meta, dict):
            continue
        if meta.get("week_id") == week_id or meta.get("inherit_current_week"):
            meta["is_recovery_week"] = True
            meta["sunday_distance_cap_km"] = data["current_week"]["sunday_distance_cap_km"]
            meta["fast_finish_required"] = False
            if meta.get("session_type") == "sunday_simulator" and "notes" not in meta:
                meta["notes"] = (
                    "Recovery week: Sunday distance cap 12 km; fast-finish removed"
                )
    data["activities"] = activities
    meta_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Insert recovery-week override into training_compliance.local.db"
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--session-meta", type=Path, default=DEFAULT_SESSION_META)
    parser.add_argument("--week-id", default=None, help="e.g. 2026-W36")
    parser.add_argument("--month-key", default=None, help="e.g. 2026-09")
    parser.add_argument("--metric-date", default=None, help="ISO date for the flag row")
    parser.add_argument(
        "--activity-id",
        default=None,
        help="Optional Sunday activity_id to attach to the flag row",
    )
    parser.add_argument(
        "--protocol-json",
        type=Path,
        default=None,
        help="Optional JSON file overriding DEFAULT_PROTOCOL",
    )
    parser.add_argument(
        "--sync-metadata",
        action="store_true",
        help="Also set current_week + is_recovery_week on matching activities in local JSON",
    )
    parser.add_argument("--notes", default=None)
    args = parser.parse_args(argv)

    protocol = DEFAULT_PROTOCOL
    if args.protocol_json is not None:
        protocol = json.loads(args.protocol_json.read_text(encoding="utf-8"))

    subject_id = "Subject_A"
    week_id = args.week_id
    month_key = args.month_key
    notes = args.notes

    if args.session_meta.exists():
        meta = load_session_meta(args.session_meta)
        subject_id = str(meta.get("subject_id") or subject_id)
        current = meta.get("current_week") or {}
        week_id = week_id or current.get("week_id") or "2026-W36"
        month_key = month_key or current.get("month_key") or "2026-09"
        if current.get("protocol"):
            protocol = current["protocol"]
        notes = notes or current.get("notes")
    else:
        week_id = week_id or "2026-W36"
        month_key = month_key or "2026-09"

    payload = build_override_payload(
        subject_id=subject_id,
        week_id=str(week_id),
        month_key=month_key,
        protocol=protocol,
        notes=notes,
    )
    flag_id = insert_recovery_flag(
        args.db,
        payload=payload,
        metric_date=args.metric_date,
        activity_id=args.activity_id,
    )
    print(f"logged recovery_week_override flag_id={flag_id}")
    print(f"  db:      {args.db}")
    print(f"  week_id: {payload['week_id']}")
    print(f"  sunday_cap_km: {payload['sunday_distance_cap_km']}")
    print(f"  tuesday: {protocol.get('tuesday')}")
    print(f"  wednesday: {protocol.get('wednesday')}")
    print(f"  friday: {protocol.get('friday')}")
    print(f"  sunday: {protocol.get('sunday')}")

    if args.sync_metadata:
        sync_current_week_metadata(
            args.session_meta,
            week_id=str(week_id),
            month_key=month_key,
            protocol=protocol,
            notes=notes,
        )
        print(f"  synced:  {args.session_meta}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
