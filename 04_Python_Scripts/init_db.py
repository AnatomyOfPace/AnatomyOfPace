import sqlite3
from pathlib import Path

# Definer stier
DB_DIR = Path('05_Macro_Database')
DB_PATH = DB_DIR / 'anatomy_macro.db'

# Opprett mappen hvis den ikke finnes
DB_DIR.mkdir(exist_ok=True)

# SQL-skjemaet pakket inn i en Python-streng
schema = """
-- 1. Katalog over løp (Race Ecology)
CREATE TABLE IF NOT EXISTS races (
    race_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT,
    primary_challenge TEXT,
    baseline_ti REAL
);

-- 2. Utøver-register
CREATE TABLE IF NOT EXISTS athletes (
    athlete_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL UNIQUE,
    team TEXT
);

-- 3. Hovedtabell for resultater (Makro-data)
CREATE TABLE IF NOT EXISTS race_results (
    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id INTEGER,
    athlete_id INTEGER,
    year INTEGER,
    finish_time_sec INTEGER,
    FOREIGN KEY (race_id) REFERENCES races(race_id),
    FOREIGN KEY (athlete_id) REFERENCES athletes(athlete_id)
);
"""

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.executescript(schema)
        conn.commit()
        conn.close()
        print(f"Suksess: Database initialisert på {DB_PATH}")
    except Exception as e:
        print(f"Feil ved initialisering: {e}")

if __name__ == "__main__":
    init_db()