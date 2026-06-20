import fitparse
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

print("Starter Pulssone-arkitekten...\n")

def hent_pulsdata(filnavn):
    filsti = os.path.join("../02_Raw_Data", filnavn)
    try:
        fitfile = fitparse.FitFile(filsti)
        data = []
        for record in fitfile.get_messages('record'):
            r_data = {}
            for field in record:
                if field.name == 'heart_rate':
                    r_data['heart_rate'] = field.value
            if 'heart_rate' in r_data:
                data.append(r_data)
        return pd.DataFrame(data).dropna()
    except Exception as e:
        print(f"Fant ikke filen: {e}")
        return None

# 1. Velger filen vi skal analysere
fil_for_analyse = "Stavanger_Halvmaraton.fit"
print(f"Henter hvert eneste hjerteslag fra {fil_for_analyse}...")
df = hent_pulsdata(fil_for_analyse)

if df is not None and not df.empty:
    # 2. Definerer pulssonene 
    # (Justert generisk for ultra: Z1 < 135, Z2 135-150, Z3 151-165, Z4 166-175, Z5 > 175)
    bins = [0, 134, 150, 165, 175, 250]
    labels = ['Sone 1\n(<135)', 'Sone 2\n(135-150)', 'Sone 3\n(151-165)', 'Sone 4\n(166-175)', 'Sone 5\n(>175)']
    
    # Sorterer dataene inn i sonene
    df['Sone'] = pd.cut(df['heart_rate'], bins=bins, labels=labels)

    # Regner om fra sekunder til antall minutter per sone
    sone_tider = df['Sone'].value_counts().sort_index() / 60

    print("Kalkulerer tid og tegner stolpediagram...")
    
    # 3. Setter opp lerretet og tegner grafen
    plt.figure(figsize=(10, 6))
    sns.set_theme(style="whitegrid")
    
    # Bruker en fargepalett som går fra kjølig (Z1) til varm (Z5)
    ax = sns.barplot(x=sone_tider.index, y=sone_tider.values, palette="coolwarm")
    
    plt.title(f'Tid i Pulssoner - {fil_for_analyse}', fontsize=16, fontweight='bold', pad=15)
    plt.xlabel('Intensitetssone', fontsize=12)
    plt.ylabel('Tid (Minutter)', fontsize=12)
    
    # Skriver nøyaktig antall minutter på toppen av hver stolpe
    for i, v in enumerate(sone_tider.values):
        ax.text(i, v + 0.5, f"{v:.1f} min", ha='center', fontweight='bold', color='black')

    # 4. Lagrer mesterverket
    ut_fil = os.path.join("../06_Visualizations", "02_Pulssoner_Graf.png")
    plt.savefig(ut_fil, dpi=300, bbox_inches='tight')
    
    print("\n" + "=" * 50)
    print("SUKSESS! Pulssonene er ferdig kartlagt.")
    print(f"Grafen ligger nå klar her: {ut_fil}")
    print("=" * 50)