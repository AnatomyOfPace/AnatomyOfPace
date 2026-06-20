import fitparse
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

print("Starter Klatre- og VAM-modulen (Vertikal Fart)...\n")

def hent_hoydedata(filnavn):
    filsti = os.path.join("../02_Raw_Data", filnavn)
    try:
        fitfile = fitparse.FitFile(filsti)
        data = []
        for record in fitfile.get_messages('record'):
            r_data = {}
            for field in record:
                # Vi ber den hente både vanlig altitude og Garmin sin enhanced_altitude
                if field.name in ['timestamp', 'heart_rate', 'altitude', 'enhanced_altitude']:
                    r_data[field.name] = field.value
            data.append(r_data)
        
        df = pd.DataFrame(data)
        
        # Hvis Garmin brukte 'enhanced_altitude', døper vi den bare om til 'altitude'
        if 'enhanced_altitude' in df.columns:
            df['altitude'] = df['enhanced_altitude']
            
        cols = [c for c in ['timestamp', 'heart_rate', 'altitude'] if c in df.columns]
        
        if 'altitude' not in cols:
            print("Feil: Fant ingen høydedata i filen.")
            return None
            
        df = df[cols].copy().ffill().dropna()
        return df
    except Exception as e:
        print(f"Fant ikke filen: {e}")
        return None

print("Henter høydedata fra fjellet (Dette kan ta litt tid)...")
df = hent_hoydedata("LFI_2026.fit")

if df is not None and not df.empty:
    print("Kalkulerer VAM (Vertical Ascent Meters per hour)...")
    
    # 1. Regn ut endring i høyde og tid over vinduer på 60 sekunder
    df['alt_diff'] = df['altitude'].diff(periods=60)
    df['time_diff'] = df['timestamp'].diff(periods=60).dt.total_seconds()
    
    # 2. Behold bare rader hvor vi faktisk klatrer oppover (minst 5 meter stigning)
    df_klatre = df[(df['alt_diff'] > 5) & (df['time_diff'] > 0)].copy()
    
    # 3. Beregn VAM
    df_klatre['VAM'] = (df_klatre['alt_diff'] / df_klatre['time_diff']) * 3600
    
    # Fjerner urealistiske GPS-utslag over 3000 høydemeter i timen
    df_klatre = df_klatre[df_klatre['VAM'] < 3000]

    print("Tegner visuell høydeprofil...")
    
    # 4. Setter opp lerretet
    plt.figure(figsize=(12, 7))
    sns.set_theme(style="whitegrid")
    
    sns.scatterplot(data=df_klatre, x='heart_rate', y='VAM', alpha=0.3, color='#e67e22', s=30, edgecolor=None)
    sns.regplot(data=df_klatre, x='heart_rate', y='VAM', scatter=False, color='#d35400', line_kws={"linewidth":2})

    plt.title('Klatrekapasitet (VAM) vs Puls under Lysefjorden Inn', fontsize=16, fontweight='bold', pad=15)
    plt.xlabel('Puls (Slag per minutt)', fontsize=12)
    plt.ylabel('VAM (Høydemeter per time)', fontsize=12)
    
    # 5. Lagrer bildet
    ut_fil = os.path.join("../06_Visualizations", "03_VAM_Graf.png")
    plt.savefig(ut_fil, dpi=300, bbox_inches='tight')
    
    print("\n" + "=" * 50)
    print("SUKSESS! Klatrekapasiteten er ferdig kartlagt.")
    print(f"Den vertikale fasiten ligger her: {ut_fil}")
    print("=" * 50)