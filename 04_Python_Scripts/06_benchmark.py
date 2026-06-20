import fitparse
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from subject_resolve import find_fit, fit_filename_token

SUBJECT_A = "Subject_A"
SUBJECT_B = "Subject_B"

print(f"Starter Benchmark-analyse: SUT43 ({SUBJECT_A} vs {SUBJECT_B})...\n")


def hent_og_vask_benchmark(filnavn, utover_navn):
    filsti = os.path.join("../02_Raw_Data", filnavn)
    try:
        fitfile = fitparse.FitFile(filsti)
        data = []
        for record in fitfile.get_messages('record'):
            r_data = {}
            for field in record:
                if field.name in ['timestamp', 'heart_rate', 'enhanced_speed']:
                    r_data[field.name] = field.value
            if 'enhanced_speed' in r_data and r_data['enhanced_speed'] is not None:
                data.append(r_data)

        df = pd.DataFrame(data)
        cols = [c for c in ['timestamp', 'heart_rate', 'enhanced_speed'] if c in df.columns]
        df = df[cols].copy().ffill().dropna()
        df = df[df['enhanced_speed'] > 0.5]
        df['pace_min_km'] = (1000 / df['enhanced_speed']) / 60
        df['Løper'] = utover_navn
        return df
    except Exception as e:
        print(f"Klarte ikke lese {filnavn}: {e}")
        return None


print("Henter data...")
fit_a = find_fit("SUT43", fit_filename_token(SUBJECT_A), "20260418")
fit_b = find_fit("SUT43", fit_filename_token(SUBJECT_B), "20260418")
df_a = hent_og_vask_benchmark(fit_a, SUBJECT_A)
df_b = hent_og_vask_benchmark(fit_b, SUBJECT_B)

if df_a is not None and df_b is not None:
    print("Kalkulerer teknisk differanse...")

    df_samlet = pd.concat([df_a, df_b])
    df_fokus = df_samlet[(df_samlet['heart_rate'] >= 130) & (df_samlet['heart_rate'] <= 160)]

    plt.figure(figsize=(12, 7))
    sns.set_theme(style="whitegrid")

    sns.kdeplot(data=df_fokus, x='pace_min_km', hue='Løper', fill=True, common_norm=False,
                palette=['#3498db', '#e74c3c'], alpha=0.4, linewidth=2)

    plt.title(f'Teknisk Flyt SUT43: {SUBJECT_A} vs {SUBJECT_B}', fontsize=16, fontweight='bold', pad=15)
    plt.xlabel('Fart (Minutter per kilometer)', fontsize=12)
    plt.ylabel('Tidsandel (Tetthet)', fontsize=12)
    plt.xlim(5, 20)

    ut_fil = os.path.join("../06_Visualizations", "04_Benchmark_Graf.png")
    plt.savefig(ut_fil, dpi=300, bbox_inches='tight')

    print("\n" + "=" * 50)
    print("SUKSESS! Benchmark-grafen er klar.")
    print(f"Resultatet ligger i: {ut_fil}")
    print("=" * 50)
else:
    print("\n" + "-" * 50)
    print(f"Feil: Kunne ikke hente begge filene for {SUBJECT_A} og {SUBJECT_B}.")
    print("Sjekk 02_Raw_Data/ og config/subject_registry.local.json (fit_tokens).")
    print("-" * 50)
