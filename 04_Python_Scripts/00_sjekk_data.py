import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CLEAN_FILE = BASE_DIR / '03_Processed_Data' / 'LFI_2026_CLEAN.csv'

def verifiser_data():
    if not CLEAN_FILE.exists():
        print("Feil: Filen finnes ikke.")
        return
    
    df = pd.read_csv(CLEAN_FILE)
    print("--- DATA SJEKK ---")
    print(f"Antall rader: {len(df)}")
    print("\nDe 5 første radene:")
    print(df.head())
    print("\nKolonner funnet:")
    print(df.columns.tolist())
    
    # Sjekk for manglende verdier
    print("\nMangler i data:")
    print(df.isnull().sum())

if __name__ == "__main__":
    verifiser_data()