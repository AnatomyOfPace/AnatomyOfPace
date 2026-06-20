import matplotlib.pyplot as plt
import seaborn as sns

# 1. Klinisk Dark Mode oppsett for Ghost Authority
plt.style.use('dark_background')
fig, ax = plt.subplots(figsize=(10, 10), facecolor='#0A0A0A')
ax.set_facecolor('#0A0A0A')

# 2. Farger: Neon Blå/Cyan (Subject_01) og Neon Rød (Technical_Baseline)
custom_palette = ['#00E5FF', '#FF0055']

# (Her setter du inn ditt faktiske KDE-plott fra Pandas DataFrame)
# Eksempel: 
# sns.kdeplot(data=df, x='Fart', hue='Løper', palette=custom_palette, fill=True, alpha=0.3, linewidth=2.5, ax=ax)

# 3. Engelsk, maskinell tekst
ax.set_title('SUT43 TELEMETRY: TECHNICAL FLOW DISTRIBUTION', color='white', fontsize=18, fontweight='bold', pad=20)
ax.set_xlabel('Pace (min/km)', color='#A0A0A0', fontsize=14)
ax.set_ylabel('Time Density', color='#A0A0A0', fontsize=14)

# 4. Klinisk rutenett og ramme
ax.grid(color='#2A2A2A', linestyle='--', linewidth=0.5)
for spine in ax.spines.values():
    spine.set_color('#2A2A2A')

# 5. Legend-anonymisering
# Sørg for at labels i DataFrame-et er 'Subject_01' og 'Technical_Baseline' før plotting
plt.setp(ax.get_legend().get_texts(), color='#A0A0A0')

# Lagre i riktig format
plt.savefig('06_Visualizations/profile_telemetry.png', dpi=300, bbox_inches='tight', facecolor='#0A0A0A')
