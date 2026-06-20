import requests
from pathlib import Path

def download_sql_results(url, filename):
    save_dir = Path(__file__).resolve().parent.parent / '02_Raw_Data' / 'Results'
    save_dir.mkdir(exist_ok=True)
    save_path = save_dir / filename
    
    print(f"Laster ned datasett fra: {url}")
    response = requests.get(url)
    
    if response.status_code == 200:
        with open(save_path, 'wb') as f:
            f.write(response.content)
        print(f"Data lagret til {save_path}")
    else:
        print(f"Feil: Kunne ikke laste ned (Statuskode: {response.status_code})")

if __name__ == "__main__":
    target_url = "https://runster.no/results/race_results_lysefjorden_inn.sql?id_race=41&gender=all"
    download_sql_results(target_url, "LFI_Raw_Data.sql")