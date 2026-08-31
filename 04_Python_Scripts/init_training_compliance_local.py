#!/usr/bin/env python3
"""Initialize private meso compliance SQLite (gitignored).

Never touches 05_Macro_Database/anatomy_macro.db — race ecology stays separate.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = BASE_DIR / "training_compliance.local.db"
MACRO_DB = BASE_DIR / "05_Macro_Database" / "anatomy_macro.db"

SCHEMA = """
-- Private meso compliance only. Not race ecology.
CREATE TABLE IF NOT EXISTS daily_metrics (
    metric_date TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    body_mass_kg REAL,
    protein_g REAL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS session_fueling (
    activity_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    session_type TEXT,
    carbs_g_per_hr REAL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS session_summaries (
    activity_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    session_type TEXT,
    week_id TEXT,
    stream_distance_km REAL,
    fast_finish_km REAL,
    median_pace_min_per_km REAL,
    target_pace_min_per_km REAL,
    pace_delta_sec_per_km REAL,
    cardiac_drift_bpm REAL,
    compliance_score REAL,
    held_target INTEGER,
    details_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS compliance_flags (
    flag_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id TEXT,
    metric_date TEXT,
    flag_type TEXT NOT NULL,
    severity TEXT,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def init_compliance_db(db_path: Path) -> Path:
    resolved = db_path.resolve()
    if resolved == MACRO_DB.resolve():
        raise SystemExit(
            "Refusing to initialize training compliance on anatomy_macro.db "
            "(macro = race ecology only)."
        )
    if "anatomy_macro" in resolved.name:
        raise SystemExit(
            f"Refusing path that looks like the macro DB: {resolved}"
        )

    resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(resolved)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create gitignored training_compliance.local.db (meso only)."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="Path to local compliance DB (default: training_compliance.local.db)",
    )
    args = parser.parse_args(argv)
    path = init_compliance_db(args.db)
    print(f"Initialized private meso DB: {path}")
    print("Remember: this file is gitignored — never commit or publish.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
