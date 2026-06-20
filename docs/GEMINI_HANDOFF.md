# Handoff Brief: Anatomy of Pace

**From:** Cursor AI  
**To:** Gemini AI  
**Purpose:** Project context, current status, and planned work  
**Date:** 2026-06-20  
**Note:** Internal AI handoff — not public copy. Ghost Authority and English-only rules apply to all generated output.

---

## 1. Project Overview

**Anatomy of Pace** is a private data-science framework for analyzing running economy in technical mountain ultramarathons. The core thesis: replace "even pace" with **even effort**, calibrated against surface friction (Terrain Tax) and cumulative physiological degradation.

The repository hosts **two connected but separate plans:**

| Layer | Name | Role |
|-------|------|------|
| **Research** | Anatomy of Pace | Data pipeline, metrics, database, visualizations, publications (Substack / Instagram), donor reports |
| **Execution** | Endurance_Protocol | Internal training periodization, race tactics, strength programming |

Research output flows to execution via the **Sync Log** at `00_Core_Strategy/Sync_Logg_Analyse_til_Praksis.md`. Findings must be logged there before Endurance_Protocol documents are updated.

**Primary race targets:**

- Lysefjorden Inn (LFI): sub-10:50 finish (2027)
- Sandnes Ultra Trail 50 Miles (2028)

---

## 2. Mandatory Protocols

### Ghost Authority

- Faceless, clinical, scientific persona — no personal narrative.
- **Forbidden in external output:** personal names of any runner; the legacy training project title; local affiliations (geographic proper nouns are permitted).
- **Required identifiers:** `Subject_A`, `Subject_B`, `Reference_Elite_A`, etc.
- Real-name mapping lives **only** in gitignored `config/subject_registry.local.json` — never commit.
- No personal pronouns (I, we, my, our) in public copy.
- Example tone: *"The telemetry reveals…"*, *"Data indicates structural pacing decay…"*

### English-Only

- All new code comments, documentation, commits, and public copy must be in **English**.
- **Permitted Norwegian:** proper nouns only — place names (Rogaland, Lysefjorden), official race names (Lysefjorden Inn, Sandnes Ultra Trail), official Strava segment names as they appear in raw telemetry.

### Key Term Translations

| Legacy (NO) | Clinical English |
|-------------|------------------|
| Teknikk-Røntgen | **Kinematic_Scan** (default donor product) |
| Terrengindeks | Terrain Index (TI) |
| Terrengskatt | Terrain Tax |
| Vaskemaskinen | Data Pipeline / Telemetry Pipeline |
| Legacy training title | **Endurance_Protocol** |

Alternate donor product names: `Telemetry_Audit`, `Biomechanical_X_Ray`.

---

## 3. Folder Structure

Project root: `Anatomy_of_Pace/` on macOS. Numbered folders are unique (00–07).

```
00_Core_Strategy/     Sync Log (research → Endurance_Protocol)
01_Geo_Blueprints/    Kartverket N50 shapefiles (planned)
02_Raw_Data/          Raw .fit files, CSV scrapes (*.fit gitignored)
03_Processed_Data/    Cleaned CSV / Parquet
04_Python_Scripts/    All Python scripts
05_Macro_Database/    SQLite anatomy_macro.db (gitignored)
06_Visualizations/    Charts, Kinematic_Scan output (*.png gitignored)
07_ML_Models/         Future ML (currently empty)
docs/                 Research and strategy documentation
config/               Config + gitignored subject_registry.local.json
.venv/                Python virtual environment (gitignored)
```

**Distance naming convention:** Sandnes Ultra Trail "50 Miles" = `SUT_80` km in code; "100 Miles" = `SUT_160`.

---

## 4. Metrics Framework

| Metric | Status | Definition |
|--------|--------|------------|
| **APR** (Aerobic Pace Ratio) | Implemented | `pace_segment / pace_asphalt_anchor` @ iso-HR. Interim metric — includes grade and surface combined. **APR ≠ TI.** |
| **TI** (Terrain Index) | Target (not built) | `v_actual / v_GAP` — friction beyond grade. Requires GAP pipeline + 30s rolling window. |
| **TPR** | After TI | `Subject TI / Baseline TI` — efficiency vs course norm. Value < 1.0 = more efficient than course. |
| **EPR** | After TI | `Subject TI / Reference_Elite TI` — head-to-head on same segment when paired `.fit` data exists. |
| **EAR** | Implemented (interim) | APR-based elite comparison. Logic in benchmark scripts. |

**Pipeline order:** APR / EAR (now) → GAP module → TI → TPR + EPR.

**Baseline TI:** Objective terrain signature of a course, abstracted from reference elite telemetry — the course "tax rate," not one person's raw file.

**Donor value exchange:** `.fit` donation → **Kinematic_Scan** report. Reference elites receive the same product (often plus a pacing budget before their race). Recruitment is mutual, not one-way data extraction.

---

## 5. Data Architecture

| Layer | Source | Storage | Status |
|-------|--------|---------|--------|
| **Macro** | Race result scraping (e.g. runster.no) | SQLite `anatomy_macro.db` | Partial — 386 LFI 2026 results with checkpoint splits |
| **Meso** | Strava km-splits (planned) | TBD | Not built |
| **Micro** | Garmin `.fit` telemetry | `02_Raw_Data/` → cleaned CSV in `03_Processed_Data/` | Partial |

**Planned pipeline defenses (from master plan):**

1. **Seed Matrix** — calibrate on flat asphalt before introducing terrain
2. **Barometric Shift** — `shift(-3)` on altitude/GAP for barometric lag
3. **Snap-to-Route** — GeoPandas `sjoin_nearest` against trail network
4. **Privacy Zones** — clip first/last 500 m on imported third-party `.fit` files

---

## 6. Research Hypotheses

- **H1 — Effort Paradox:** In steep climbs, speed drops while physiological load remains stable.
- **H2 — Cumulative Debt:** Surface friction is a continuous biological drain; accelerates after ~50 km (CNS component per Millet).
- **H3 — Eccentric Downfall:** Late-race pace collapse on flat sections after eccentric quad damage — not central aerobic failure.

Scientific basis documented in `docs/theory.md` (Minetti, Pinnington & Dawson, Giandolini, Millet).

---

## 7. Key Scripts

All scripts live in `04_Python_Scripts/`.

| Script | Function |
|--------|----------|
| `01_vaskemaskinen.py` | FIT → cleaned CSV |
| `02_terrengindeks.py` | APR calculator (asphalt vs terrain @ iso-HR) |
| `03_batch_analyse.py` | Batch APR over all `.fit` files in raw data |
| `04_visualiser_ti.py` | APR bar chart per route → `06_Visualizations/APR_oversikt.png` |
| `06_macro_ingest.py` | Ingest LFI CSV results → SQLite |
| `07_plot_decay.py` | Macro checkpoint decay plot |
| `06_benchmark.py` | Paired APR comparison (EAR logic) |
| `07_batch_benchmark.py` | Multi-session benchmark trends |
| `05_radar_scrape.py` | Scrape runster.no race results |
| `init_db.py` | Initialize macro DB schema |
| `05_vam_kalkulator.py` | Vertical ascent rate analysis |

**Not built yet:**

- `01_strava_fetcher.py` (OAuth + `.fit` download from reference elites)
- GAP calculation module
- Kinematic_Scan report generator
- Streamlit dashboard (planned v4.0)

---

## 8. Documentation Index

| File | Content |
|------|---------|
| `docs/master_plan.md` | Architecture v3.5, terrain ontology (11 classes), infrastructure spec |
| `docs/theory.md` | Scientific foundation; metrics §5 (APR/TI/TPR/EPR) and §6 (Kinematic_Scan) |
| `docs/race_ecology.md` | Reference race catalog for macro database |
| `docs/outreach_referanselopere.md` | Strava OAuth pitches for reference elites (sanitize before public use) |
| `docs/launch_strategy.md` | Substack / Instagram ecosystem, Ghost Authority, donor exchange |
| `docs/README.md` | Doc index; two-plan split explained |
| Legacy Endurance_Protocol doc | Internal training manual (Norwegian — migrate to English) |
| `docs/lopsmanual_lfi_v2.2.md` | LFI race tactical matrix (partial English) |
| `.cursorrules` | AI enforcement rules for Cursor (Ghost Authority + English + metrics) |

---

## 9. Reference Elite Roles (clinical IDs)

| ID | Role | Primary terrain / race |
|----|------|------------------------|
| Reference_Elite_A | Technical flow baseline | SUT_80 |
| Reference_Elite_B | Extreme distance, Quad-Smash / CNS | SUT_160, OBT |
| Reference_Elite_C | Rogaland technical flow, API pilot | SUT_43, terrain classes 5–11 |
| Reference_Elite_D | Fell running + asphalt anchor (UK) | 5 Valleys, London Marathon |
| Reference_Elite_E | Thermal + alpine technical | Val d'Aran |

Intake method: Strava OAuth 2.0 (`activity:read_all`). Operational routine in outreach doc.

---

## 10. Current Status

### Complete

- Folder structure (00–07, unique numbering)
- Python venv + `requirements.txt`
- Documentation library in `docs/`
- Metrics framework defined and documented
- APR scripts operational on local `.fit` files
- Macro database: 386 LFI 2026 results with checkpoint splits
- `.gitignore` configured (blocks `.fit`, `.db`, `.venv`, secrets, subject registry)
- GitHub repository exists: [AnatomyOfPace/AnatomyOfPace](https://github.com/AnatomyOfPace/AnatomyOfPace)

### In Progress

- **Git merge incomplete.** Conflicts on `README.md` and `.gitignore` after `git pull origin main --allow-unrelated-histories`. Local commit exists (`Add project: docs, scripts, and folder structure`). Push not finished.

**Resolution commands:**

```bash
git checkout --theirs README.md      # keep GitHub public README
git checkout --ours .gitignore       # keep local .gitignore with .fit/.db rules
git add README.md .gitignore .cursorrules
git commit -m "Merge remote repository with local project"
git push -u origin main
```

Repository should remain **private** until Ghost Authority sanitization is complete.

### Not Started

- GAP module and real Terrain Index (TI)
- Strava OAuth fetcher script
- Kinematic_Scan v0 automation
- English migration of legacy Norwegian documentation
- Ghost Authority sanitization of scripts and docs for public visibility
- GeoPandas / Snap-to-Route
- Parquet + DuckDB micro processing layer
- ML models in `07_ML_Models/`

---

## 11. Recommended Next Steps (Priority Order)

1. **Complete GitHub sync** — resolve merge conflicts, push to private repo.
2. **Kinematic_Scan v0** — single script: input one `.fit` → APR profile chart + slowest segment identification → PNG output to `06_Visualizations/`.
3. **GAP module** — unlock TI, TPR, and EPR.
4. **Strava fetcher** — automated `.fit` intake from reference elites.
5. **Sanitization pass** — English translation + Subject_A identifiers before any public repo visibility.
6. **Endurance_Protocol** — continues on independent track; fed exclusively via Sync Log.

---

## 12. Instructions for Gemini

When assisting on this project:

1. Enforce **Ghost Authority** and **English-only** rules in all generated text.
2. Never conflate **APR** with **TI** — they measure different things.
3. Distinguish **Anatomy of Pace** (research) from **Endurance_Protocol** (training execution).
4. Use `docs/master_plan.md` and `docs/theory.md` as architecture source of truth.
5. Never commit personal names, `.fit` files, `anatomy_macro.db`, or `subject_registry.local.json`.
6. Default donor deliverable name: **Kinematic_Scan**.
7. Script directory: `04_Python_Scripts/`. Visual output: `06_Visualizations/`.
8. Legacy Norwegian filenames and content may exist locally — translate on contact; do not reproduce Norwegian conceptual terms in new output (except permitted proper nouns).

---

*End of handoff brief.*
