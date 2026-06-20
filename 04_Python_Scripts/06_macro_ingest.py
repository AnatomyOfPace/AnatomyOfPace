import sqlite3
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / '05_Macro_Database' / 'anatomy_macro.db'

def time_to_seconds(time_str):
    try:
        parts = list(map(int, str(time_str).split(':')))
        if len(parts) == 3: return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2: return parts[0] * 60 + parts[1]
    except: return 0
    return 0

def ingest_runster_data(csv_file):
    df = pd.read_csv(csv_file)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    YEAR = 2026

    for _, row in df.iterrows():
        athlete_name = row['Navn']
        split_p = time_to_seconds(row['Preikestolhytta'])
        split_s = time_to_seconds(row['Sognesand'])

        cursor.execute("SELECT athlete_id FROM athletes WHERE full_name = ?", (athlete_name,))
        result = cursor.fetchone()

        if result:
            athlete_id = result[0]
            cursor.execute('''
                UPDATE race_results 
                SET split_preikestol_sec = ?, split_sognesand_sec = ?
                WHERE athlete_id = ? AND year = ?
            ''', (split_p, split_s, athlete_id, YEAR))

    conn.commit()
    conn.close()
    print("Segment-data injisert.")

if __name__ == "__main__":
    csv_path = BASE_DIR / '02_Raw_Data' / 'Results' / 'LFI_2026_Results.csv'
    ingest_runster_data(csv_path)
