import matplotlib.pyplot as plt
import sqlite3
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from subject_resolve import db_full_name

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / '05_Macro_Database' / 'anatomy_macro.db'
SUBJECT_A = "Subject_A"


def plot_decay():
    conn = sqlite3.connect(DB_PATH)
    subject_name = db_full_name(SUBJECT_A)
    query = """
    SELECT
        (SELECT AVG(split_preikestol_sec) FROM race_results) as avg_p,
        (SELECT AVG(split_sognesand_sec) FROM race_results) as avg_s,
        split_preikestol_sec,
        split_sognesand_sec
    FROM race_results r
    JOIN athletes a ON r.athlete_id = a.athlete_id
    WHERE a.full_name = ? AND r.year = 2026;
    """
    df = pd.read_sql_query(query, conn, params=(subject_name,))
    conn.close()

    segments = ['Preikestolhytta', 'Sognesand']
    field_avg = [df['avg_p'][0], df['avg_s'][0]]
    subject_data = [df['split_preikestol_sec'][0], df['split_sognesand_sec'][0]]

    plt.figure(figsize=(10, 6))
    plt.plot(segments, field_avg, marker='o', label='Feltets Gjennomsnitt', linestyle='--')
    plt.plot(segments, subject_data, marker='o', label=SUBJECT_A, linewidth=2)
    plt.title(f'Performance Decay: {SUBJECT_A} vs Feltet (LFI 2026)')
    plt.ylabel('Tid i sekunder')
    plt.legend()
    plt.grid(True)

    plt.savefig(BASE_DIR / '06_Visualizations' / 'Performance_Decay.png')
    print("Visualisering lagret til 06_Visualizations/Performance_Decay.png")


if __name__ == "__main__":
    plot_decay()
