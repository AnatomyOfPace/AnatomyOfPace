import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# 1. Generer syntetisk telemetri som matcher formen på ditt opprinnelige SUT43-plott
np.random.seed(42)
# Technical Baseline — synthetic reference distribution (~10.5 min/km)
baseline = np.random.normal(loc=10.5, scale=2.5, size=5000)
baseline = baseline[(baseline > 5) & (baseline < 20)]

# Subject_01 — bimodal test subject (peaks ~6.5 and ~12.5 min/km)
subject_fast = np.random.normal(loc=6.5, scale=1.0, size=1500)
subject_slow = np.random.normal(loc=12.5, scale=3.0, size=3500)
subject = np.concatenate([subject_fast, subject_slow])
subject = subject[(subject > 5) & (subject < 20)]

# Samle i DataFrame for klinisk plotting
df_baseline = pd.DataFrame({'Pace': baseline, 'Entity': 'Technical_Baseline'})
df_subject = pd.DataFrame({'Pace': subject, 'Entity': 'Subject_01'})
df = pd.concat([df_baseline, df_subject])

# 2. Dark Mode Estetikk for "Ghost Authority"
plt.style.use('dark_background')
fig, ax = plt.subplots(figsize=(10, 10), facecolor='#0A0A0A')
ax.set_facecolor('#0A0A0A')
custom_palette = {'Subject_01': '#00E5FF', 'Technical_Baseline': '#FF0055'}

# 3. Rendring av plottet
sns.kdeplot(
    data=df, 
    x='Pace', 
    hue='Entity', 
    palette=custom_palette, 
    fill=True, 
    alpha=0.35, 
    linewidth=2.5, 
    ax=ax,
    common_norm=False
)

# 4. Typografi og grid
ax.set_title('SUT43 TELEMETRY: TECHNICAL FLOW', color='white', fontsize=22, fontweight='bold', pad=20)
ax.set_xlabel('Pace (min/km)', color='#A0A0A0', fontsize=16)
ax.set_ylabel('Time Density', color='#A0A0A0', fontsize=16)
ax.set_xlim(5, 20)

ax.grid(color='#2A2A2A', linestyle='--', linewidth=0.8)
for spine in ax.spines.values():
    spine.set_color('#2A2A2A')

plt.setp(ax.get_legend().get_texts(), color='#A0A0A0', fontsize=14)
plt.setp(ax.get_legend().get_title(), color='white', fontsize=16, fontweight='bold')

# 5. Eksporter det visuelle beviset
output_file = 'profile_telemetry.png'
plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='#0A0A0A')
print(f"Extraction complete. Target acquired: {output_file}")