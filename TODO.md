# Project Setup Checklist

## Python Virtual Environment & Dependencies — DONE

- [x] Create a virtual environment in the project root:
  ```bash
  python3 -m venv .venv
  ```
- [x] Activate the virtual environment:
  ```bash
  source .venv/bin/activate
  ```
- [x] Upgrade pip (recommended):
  ```bash
  pip install --upgrade pip
  ```
- [x] Install dependencies:
  ```bash
  pip install pandas fitparse requests beautifulsoup4 fuzzywuzzy python-Levenshtein stravalib python-dotenv pyarrow
  ```
- [x] Save dependencies to a requirements file:
  ```bash
  pip freeze > requirements.txt
  ```
