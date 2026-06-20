import fitparse
import pandas as pd
import matplotlib.pyplot as plt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from subject_resolve import fit_filename_token

SUBJECT_A = "Subject_A"
SUBJECT_B = "Subject_B"
TOKEN_A = fit_filename_token(SUBJECT_A)
TOKEN_B = fit_filename_token(SUBJECT_B)

print(f"Starter Batch-analyse av alle økter ({SUBJECT_A} vs {SUBJECT_B})...\n")


def hent_fit_data(filsti):
    try:
        fitfile = fitparse.FitFile(filsti)
        data = []
        for record in fitfile.get_messages('record'):
            r_data = {}
            for field in record:
                if field.name in ['heart_rate', 'enhanced_speed']:
                    r_data[field.name] = field.value
            if 'enhanced_speed' in r_data and r_data['enhanced_speed'] is not None:
                data.append(r_data)
        df = pd.DataFrame(data)
        if 'enhanced_speed' in df.columns:
            df = df[df['enhanced_speed'] > 0.5].copy()
            df['pace_min_km'] = (1000 / df['enhanced_speed']) / 60
            return df
    except Exception:
        return None
    return None


data_folder = "../02_Raw_Data"
files = [f for f in os.listdir(data_folder) if f.endswith('.fit')]

dates = sorted(list(set([re.search(r'(\d{8})', f).group(1) for f in files if re.search(r'(\d{8})', f)])))

sessions = []
for date in dates:
    a_file = next((f for f in files if date in f and TOKEN_A in f), None)
    b_file = next((f for f in files if date in f and TOKEN_B in f), None)

    if a_file and b_file:
        print(f"Analyserer økt fra {date}...")
        df_a = hent_fit_data(os.path.join(data_folder, a_file))
        df_b = hent_fit_data(os.path.join(data_folder, b_file))

        if df_a is not None and df_b is not None:
            df_a = df_a[(df_a['heart_rate'] >= 130) & (df_a['heart_rate'] <= 160)]
            df_b = df_b[(df_b['heart_rate'] >= 130) & (df_b['heart_rate'] <= 160)]

            if not df_a.empty and not df_b.empty:
                sessions.append({
                    'Dato': date,
                    SUBJECT_A: df_a['pace_min_km'].median(),
                    SUBJECT_B: df_b['pace_min_km'].median()
                })

if sessions:
    df_result = pd.DataFrame(sessions)
    plt.figure(figsize=(12, 6))
    plt.plot(df_result['Dato'], df_result[SUBJECT_A], marker='o', label=SUBJECT_A, color='#3498db')
    plt.plot(df_result['Dato'], df_result[SUBJECT_B], marker='o', label=SUBJECT_B, color='#e74c3c')

    plt.title(f'Teknisk Flyt over tid ({SUBJECT_A} vs {SUBJECT_B})', fontsize=14)
    plt.ylabel('Median-fart (Min/km)')
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()

    ut_fil = os.path.join("../06_Visualizations", "05_Trend_Analyse.png")
    plt.savefig(ut_fil, dpi=300)
    print(f"\nSUKSESS! Trendanalysen er lagret i {ut_fil}")
else:
    print("Fant ingen parvise filer å sammenligne.")
