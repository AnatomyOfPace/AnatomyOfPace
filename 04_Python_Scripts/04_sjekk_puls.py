import fitparse
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from subject_resolve import find_fit, fit_filename_token

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = BASE_DIR / '02_Raw_Data'

def sjekk_puls_profil(filnavn):
    filsti = RAW_DATA_DIR / filnavn
    if not filsti.exists():
        print(f"Fant ikke filen: {filnavn}")
        return

    fitfile = fitparse.FitFile(str(filsti))
    data = [r.get_values() for r in fitfile.get_messages('record')]
    df = pd.DataFrame(data)

    if 'heart_rate' not in df.columns:
        print("Ingen pulsdata funnet i filen.")
        return

    # Vi ser på hele datasettet, ikke bare over 0.5 m/s
    hr_data = df['heart_rate'].dropna()

    print(f"\n--- Pulsprofil for {filnavn} ---")
    print(f"Gjennomsnittspuls: {hr_data.mean():.1f} bpm")
    print(f"Min puls:          {hr_data.min():.0f} bpm")
    print(f"Max puls:          {hr_data.max():.0f} bpm")
    
    # Hvor mye av tiden var over 140?
    over_140 = (hr_data > 140).mean() * 100
    print(f"Tid over 140 bpm:  {over_140:.1f}%")

if __name__ == "__main__":
    token_a = fit_filename_token("Subject_A")
    sjekk_puls_profil(find_fit("Sunderunde", token_a, "20260530"))