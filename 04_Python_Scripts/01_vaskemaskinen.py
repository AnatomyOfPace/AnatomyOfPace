import fitparse
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from subject_resolve import find_fit, fit_filename_token

# Definer stier
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = BASE_DIR / '02_Raw_Data'
PROCESSED_DATA_DIR = BASE_DIR / '03_Processed_Data'

def vask_fit_fil(filnavn):
    print(f"Starter vask av: {filnavn}")
    file_path = RAW_DATA_DIR / filnavn
    
    # Vi leser filen direkte inn i fitparse uten å lukke den for tidlig
    fit = fitparse.FitFile(str(file_path))
    
    data = []
    for record in fit.get_messages('record'):
        d = record.get_values()
        data.append({
            'timestamp': d.get('timestamp'),
            'distance': d.get('distance'),
            'heart_rate': d.get('heart_rate'),
            'altitude': d.get('altitude'),
            'cadence': d.get('cadence'),
            'speed': d.get('speed')
        })
    
    df = pd.DataFrame(data)
    
    if df.empty:
        print("Advarsel: Ingen data funnet i filen.")
        return

    # Rensing
    df.dropna(subset=['timestamp'], inplace=True)
    df.ffill(inplace=True)
    
    output_navn = filnavn.replace('.fit', '_CLEAN.csv')
    df.to_csv(PROCESSED_DATA_DIR / output_navn, index=False)
    print(f"Vasking fullført. Lagret til: {output_navn}")

if __name__ == "__main__":
    token_a = fit_filename_token("Subject_A")
    try:
        vask_fit_fil(find_fit("LFI", token_a, "20260606"))
    except FileNotFoundError:
        pass
    try:
        vask_fit_fil('LFI_2026.fit')
    except Exception as e:
        print(f"En feil oppstod: {e}")