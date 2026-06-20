import fitparse
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from subject_resolve import find_fit, fit_filename_token

# Definer stier basert på hvor skriptet ligger (04_Python_Scripts/)
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = BASE_DIR / '02_Raw_Data'

print("Starter Aerob Pace Ratio-kalkulatoren (APR)...\n")

def hent_og_vask_fit(filnavn):
    filsti = RAW_DATA_DIR / filnavn
    
    if not filsti.exists():
        print(f"FEIL: Fant ikke filen {filnavn} i {RAW_DATA_DIR}")
        return None
        
    try:
        print(f"Prosesserer: {filnavn}...")
        fitfile = fitparse.FitFile(str(filsti))
        data = []
        for record in fitfile.get_messages('record'):
            data.append(record.get_values())
        
        df = pd.DataFrame(data)

        # 1. Sikre at fart-kolonne finnes (prioriterer enhanced_speed)
        if 'enhanced_speed' not in df.columns:
            df['enhanced_speed'] = df.get('speed', 0)
        
        # 2. Filtrer bort stillstand (alt under 0.5 m/s fjernes umiddelbart)
        df = df[df['enhanced_speed'] > 0.5]
        
        # 3. Standardiser kolonner (ffill fyller hull etter start)
        cols = [c for c in ['timestamp', 'heart_rate', 'enhanced_speed'] if c in df.columns]
        df = df[cols].copy().ffill().dropna()

        # 4. Beregn pace (min/km)
        # Formel: (1000m / speed(m/s)) / 60 = min/km
        df['pace_min_km'] = (1000 / df['enhanced_speed']) / 60
        return df
        
    except Exception as e:
        print(f"Feil ved prosessering av {filnavn}: {e}")
        return None

# --- HOVEDPROSESS ---

# 1. Laster inn datafabrikkens råvarer
print("Laster inn aerobt anker (Asfalt)...")
df_asfalt = hent_og_vask_fit("Stavanger_Halvmaraton.fit")

print("Laster inn teknisk terreng...")
token_b = fit_filename_token("Subject_B")
df_fjell = hent_og_vask_fit(find_fit("Sunderunde", token_b, "20260530"))

# 2. Utfør analysen
if df_asfalt is not None and df_fjell is not None:
    # Vi isolerer en moderat aerob sone for sammenligning (140-150 bpm)
    sone_min, sone_max = 140, 150

    snitt_asfalt = df_asfalt[(df_asfalt['heart_rate'] >= sone_min) & (df_asfalt['heart_rate'] <= sone_max)]['pace_min_km'].mean()
    snitt_fjell = df_fjell[(df_fjell['heart_rate'] >= sone_min) & (df_fjell['heart_rate'] <= sone_max)]['pace_min_km'].mean()

    # APR = pace_terreng / pace_asfalt @ iso-HR (ikke TI — se docs/theory.md §5)
    apr = snitt_fjell / snitt_asfalt

    print("\n" + "=" * 50)
    print(f"  AEROB PACE RATIO (Puls: {sone_min}-{sone_max})")
    print("=" * 50)
    print(f"Fart på flat asfalt:    {snitt_asfalt:.2f} min/km")
    print(f"Fart i teknisk fjell:   {snitt_fjell:.2f} min/km")
    print("-" * 50)
    print(f"APR:                    {apr:.2f}")
    print("=" * 50)
    print(f"Konklusjon: Ved samme puls krevde terrenget")
    print(f"{apr:.2f}x mer tid per kilometer enn asfaltankeret.")
    print("(APR ≠ TI — inkluderer stigning + underlag; TI krever GAP.)")
else:
    print("\nKunne ikke fullføre analysen. Sjekk at begge filene ligger i 02_Raw_Data.")