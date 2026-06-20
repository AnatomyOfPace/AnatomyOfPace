import fitparse
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

print("Gjør klar for visuell rendering av mekanisk friksjon...\n")

# Gjenbruk av den solide vaskefunksjonen vår
def hent_og_vask_fit(filnavn):
    filsti = os.path.join("../02_Raw_Data", filnavn)
    try:
        fitfile = fitparse.FitFile(filsti)
        data = []
        for record in fitfile.get_messages('record'):
            r_data = {}
            for field in record:
                r_data[field.name] = field.value
            data.append(r_data)
        df = pd.DataFrame(data)

        cols = [c for c in ['timestamp', 'heart_rate', 'enhanced_speed'] if c in df.columns]
        df = df[cols].copy().ffill().dropna()
        df = df[df['enhanced_speed'] > 0.5] 
        df['pace_min_km'] = (1000 / df['enhanced_speed']) / 60
        return df
    except Exception as e:
        print(f"Kritisk feil: {e}")
        return None

print("Henter asfalt-data...")
df_asfalt = hent_og_vask_fit("Stavanger_Halvmaraton.fit")
df_asfalt['Underlag'] = 'Asfalt (Halvmaraton)'

print("Henter fjell-data (Tygging av LFI tar litt tid)...")
df_fjell = hent_og_vask_fit("LFI_2026.fit")
df_fjell['Underlag'] = 'Fjell (LFI)'

# Slår sammen dataene, og isolerer en relevant aerob sone for et renere bilde
df_begge = pd.concat([df_asfalt, df_fjell])
df_fokus = df_begge[(df_begge['heart_rate'] >= 120) & (df_begge['heart_rate'] <= 160)]

print("Tegner grafen...")
# Setter opp lerretet (størrelse og design)
plt.figure(figsize=(12, 7))
sns.set_theme(style="whitegrid")

# Tegner selve spredningsdiagrammet
sns.scatterplot(data=df_fokus, x='heart_rate', y='pace_min_km', hue='Underlag', 
                palette=['#2ecc71', '#e74c3c'], alpha=0.15, s=20, edgecolor=None)

# Design og tekst på grafen
plt.title('Biomekanisk Friksjon: Asfalt vs Teknisk Fjell', fontsize=16, fontweight='bold', pad=20)
plt.xlabel('Puls (Slag per minutt)', fontsize=12)
plt.ylabel('Fart (Minutter per kilometer)', fontsize=12)
plt.ylim(3, 20) # Klipper y-aksen ved 20 min/km for å fjerne støy fra bratte gå-partier
plt.legend(title='Datasett', fontsize=11)

# Lagrer bildet i 06_Visualizations
ut_fil = os.path.join("../06_Visualizations", "01_Terrengindeks_Graf.png")
plt.savefig(ut_fil, dpi=300, bbox_inches='tight')

print("=" * 50)
print(f"SUKSESS! Grafen er ferdig tegnet.")
print(f"Du finner det ferdige bildet her: {ut_fil}")
print("=" * 50)