import pandas as pd
from pathlib import Path

def scrape_race_results():
    url = "https://runster.no/results/race_results_lysefjorden_inn.sql?id_race=41&gender=all"
    save_dir = Path('02_Raw_Data/Results')
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / 'LFI_2026_Results.csv'
    
    print(f"Prøver å lese tabell fra: {url}")
    
    try:
        # read_html returnerer en liste over alle tabeller på siden
        tables = pd.read_html(url)
        
        if tables:
            # Vi antar at den første tabellen er den du vil ha
            df = tables[0]
            df.to_csv(save_path, index=False)
            print(f"Suksess! Tabellen er hentet og lagret til {save_path}")
            print(f"Antall rader hentet: {len(df)}")
        else:
            print("Fant ingen tabeller på siden.")
            
    except Exception as e:
        print(f"Feil under scraping: {e}")

if __name__ == "__main__":
    scrape_race_results()