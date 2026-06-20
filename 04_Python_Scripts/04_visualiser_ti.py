import fitparse
import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt

# Definer stier
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = BASE_DIR / '02_Raw_Data'
VIZ_DIR = BASE_DIR / '06_Visualizations'

# Opprett mappe for visualisering hvis den ikke finnes
VIZ_DIR.mkdir(exist_ok=True)

def hent_og_vask_fit(filnavn):
    filsti = RAW_DATA_DIR / filnavn
    try:
        fitfile = fitparse.FitFile(str(filsti))
        data = [record.get_values() for record in fitfile.get_messages('record')]
        df = pd.DataFrame(data)
        if 'enhanced_speed' not in df.columns:
            df['enhanced_speed'] = df.get('speed', 0)
        df = df[df['enhanced_speed'] > 0.5]
        cols = [c for c in ['timestamp', 'heart_rate', 'enhanced_speed'] if c in df.columns]
        df = df[cols].copy().ffill().dropna()
        df['pace_min_km'] = (1000 / df['enhanced_speed']) / 60
        return df
    except Exception:
        return None

def get_pace_for_dynamic_zone(df):
    if df is None or df.empty or 'heart_rate' not in df.columns:
        return None
    avg_hr = df['heart_rate'].mean()
    subset = df[(df['heart_rate'] >= avg_hr - 5) & (df['heart_rate'] <= avg_hr + 5)]
    return subset['pace_min_km'].mean() if not subset.empty else None

# 1. Hent data
print("Analyserer data for visualisering...")
df_asfalt = hent_og_vask_fit("Stavanger_Halvmaraton.fit")
snitt_asfalt = get_pace_for_dynamic_zone(df_asfalt)

results = []
for fit_file in RAW_DATA_DIR.glob("*.fit"):
    if fit_file.name == "Stavanger_Halvmaraton.fit": continue
    
    df_fjell = hent_og_vask_fit(fit_file.name)
    snitt_fjell = get_pace_for_dynamic_zone(df_fjell)
    
    if snitt_fjell:
        apr = snitt_fjell / snitt_asfalt
        # Forkorter navn for grafen
        label = fit_file.name.replace(".fit", "").replace("_2026", "")
        results.append({'label': label, 'apr': apr})

# 2. Generer graf
df_res = pd.DataFrame(results).sort_values('apr', ascending=True)

plt.figure(figsize=(10, 6))
bars = plt.barh(df_res['label'], df_res['apr'], color='skyblue')

# Legg til tallverdier på stolpene
for bar in bars:
    plt.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height()/2, 
             f'{bar.get_width():.2f}', va='center')

plt.title('Aerob Pace Ratio (APR) per rute')
plt.xlabel('APR (høyere verdi = tregere pace vs asfalt @ iso-HR)')
plt.grid(axis='x', linestyle='--', alpha=0.7)
plt.tight_layout()

# 3. Lagre
output_file = VIZ_DIR / 'APR_oversikt.png'
plt.savefig(output_file)
print(f"Visualisering lagret til: {output_file}")
plt.show()