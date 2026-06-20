import fitparse
import pandas as pd
from pathlib import Path

# Definer stier
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = BASE_DIR / '02_Raw_Data'

def hent_og_vask_fit(filnavn):
    filsti = RAW_DATA_DIR / filnavn
    if not filsti.exists():
        return None
        
    try:
        fitfile = fitparse.FitFile(str(filsti))
        data = [record.get_values() for record in fitfile.get_messages('record')]
        df = pd.DataFrame(data)

        # Sikre fartskolonne
        if 'enhanced_speed' not in df.columns:
            df['enhanced_speed'] = df.get('speed', 0)
        
        # Filtrer stillstand (under 0.5 m/s)
        df = df[df['enhanced_speed'] > 0.5]
        
        # Standardiser
        cols = [c for c in ['timestamp', 'heart_rate', 'enhanced_speed'] if c in df.columns]
        df = df[cols].copy().ffill().dropna()
        
        # Pace (min/km)
        df['pace_min_km'] = (1000 / df['enhanced_speed']) / 60
        return df
    except Exception:
        return None

def get_pace_for_dynamic_zone(df):
    """Beregner snittfart basert på øktens egen gjennomsnittspuls +/- 5 bpm"""
    if df is None or df.empty or 'heart_rate' not in df.columns:
        return None
    
    avg_hr = df['heart_rate'].mean()
    sone_min = avg_hr - 5
    sone_max = avg_hr + 5
    
    subset = df[(df['heart_rate'] >= sone_min) & (df['heart_rate'] <= sone_max)]
    
    if subset.empty:
        return None
    return subset['pace_min_km'].mean()

# 1. Sett ankerpunkt
ANCHOR_FILE = "Stavanger_Halvmaraton.fit"
print(f"Laster inn aerobt anker: {ANCHOR_FILE}...")
df_asfalt = hent_og_vask_fit(ANCHOR_FILE)

if df_asfalt is None:
    print("Feil: Fant ikke ankerfilen.")
    exit()

snitt_asfalt = get_pace_for_dynamic_zone(df_asfalt)
print(f"Referanse-pace (asfalt ved avg puls): {snitt_asfalt:.2f} min/km\n")

# 2. Batch-prosessering
print(f"{'Filnavn':<30} | {'APR':<10} | {'Avg Puls'}")
print("-" * 55)

for fit_file in RAW_DATA_DIR.glob("*.fit"):
    if fit_file.name == ANCHOR_FILE:
        continue
    
    df_fjell = hent_og_vask_fit(fit_file.name)
    
    if df_fjell is not None:
        snitt_fjell = get_pace_for_dynamic_zone(df_fjell)
        avg_puls = df_fjell['heart_rate'].mean()
        
        if snitt_fjell is not None:
            apr = snitt_fjell / snitt_asfalt
            print(f"{fit_file.name[:30]:<30} | {apr:<10.2f} | {avg_puls:.0f} bpm")
        else:
            print(f"{fit_file.name[:30]:<30} | (Datafeil)   | {avg_puls:.0f} bpm")

print("\nBatch-analyse fullført.")