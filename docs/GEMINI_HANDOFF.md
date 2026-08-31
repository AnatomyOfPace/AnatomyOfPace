# Handoff Brief: The Anatomy of Pace

**From:** Cursor AI  
**To:** Gemini AI  
**Purpose:** Project context, current status, and active workstreams  
**Date:** 2026-08-31  
**Note:** Internal AI handoff — not public copy. Ghost Authority and English-only rules apply to all generated output destined for GitHub, Substack, Instagram, or donor deliverables.

---

## 1. Project Overview

**The Anatomy of Pace** is a data-science laboratory for analyzing running economy in technical mountain ultramarathons. The core thesis: replace "even pace" with **even effort**, calibrated against surface friction (Terrain Tax) and cumulative physiological degradation.

**Public owner:** **Dr. Anatomy Pace** — see `docs/brand_identity.md`.

The repository hosts **two connected but separate plans:**

| Layer | Name | Role |
|-------|------|------|
| **Research** | The Anatomy of Pace | Data pipeline, metrics, database, visualizations, publications (Substack / Instagram), donor reports |
| **Execution** | Private training manual *(local only — gitignored)* | Internal periodization, race tactics, strength programming for operators |

Research output may inform private training via the **Sync Log** at `00_Core_Strategy/Sync_Logg_Analyse_til_Praksis.md`. That bridge is **internal only** — never publish private training content under The Anatomy of Pace brand.

**Active research goal (internal):** Sub-10:50 at Lysefjorden Inn 2027. Sanitize race targets in any external-facing copy.

**Secondary horizon:** Sandnes Ultra Trail 50 Miles (2028).

---

## 2. Mandatory Protocols

### Ghost Authority

- Faceless, clinical, scientific persona — attribute public work to **Dr. Anatomy Pace** or *The Anatomy of Pace* laboratory.
- **Forbidden in external output:** personal names of any runner or collaborator; the private training project title or content; local affiliations (geographic proper nouns are permitted for parsing only — never in public narrative).
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
| Innsatsparadokset | Effort Paradox |
| Kumulativ gjeld | Cumulative Debt |

Alternate donor product names: `Telemetry_Audit`, `Biomechanical_X_Ray`.

**Scope firewall:** The private training project is **not** part of The Anatomy of Pace brand. Never mention it in external-facing output.

---

## 3. Folder Structure

Project root: `Anatomy_of_Pace/` on macOS. Numbered folders are unique (00–07).

```
00_Core_Strategy/     Sync Log (research → private training)
01_Geo_Blueprints/    Kartverket N50 shapefiles (planned)
02_Raw_Data/          Raw .fit files, CSV scrapes, organiser GPX (*.fit gitignored)
03_Processed_Data/    Cleaned CSV / Parquet; spatial panels under spatial/
04_Python_Scripts/    All Python scripts; spatial/ subpackage for HITL + align
05_Macro_Database/    SQLite anatomy_macro.db (gitignored)
06_Visualizations/    Charts, Kinematic_Scan output, sut43_hitl/ chunk PNGs (*.png gitignored)
07_ML_Models/         Terrain HMM/GB drafts, joblib models
docs/                 Research and strategy documentation
config/               Config + gitignored subject_registry.local.json
.venv/                Python virtual environment (gitignored)
```

**Distance naming convention:** Sandnes Ultra Trail "50 Miles" = `SUT_80` km in code; "100 Miles" = `SUT_160`; 43 km variant = `SUT_43`.

---

## 4. Metrics Framework

| Metric | Status | Definition |
|--------|--------|------------|
| **APR** (Aerobic Pace Ratio) | Implemented | `pace_segment / pace_asphalt_anchor` @ iso-HR. Interim metric — includes grade and surface combined. **APR ≠ TI.** |
| **TI** (Terrain Index) | In progress (spatial pilot) | `v_actual / v_GAP` — friction beyond grade. Requires GAP pipeline + 30s rolling window. Spatial HITL builds S1–S6 / F0–F4 ground truth for TI calibration. |
| **TPR** | After TI | `Subject TI / Baseline TI` — efficiency vs course norm. Value < 1.0 = more efficient than course. |
| **EPR** | After TI | `Subject TI / Reference_Elite TI` — head-to-head on same segment when paired `.fit` data exists. |
| **EAR** | Implemented (interim) | APR-based elite comparison. Logic in benchmark scripts. |

**Pipeline order:** APR / EAR (now) → GAP module → TI → TPR + EPR.

**Baseline TI:** Objective terrain signature of a course, abstracted from reference elite telemetry — the course "tax rate," not one person's raw file.

**Donor value exchange:** `.fit` donation → **Kinematic_Scan** report. Reference elites receive the same product (often plus a pacing budget before their race).

**Source of truth:** `docs/master_plan.md`, `docs/theory.md`, `docs/brand_identity.md`.

---

## 5. Data Architecture

| Layer | Source | Storage | Status |
|-------|--------|---------|--------|
| **Macro** | Race result scraping (e.g. runster.no) | SQLite `anatomy_macro.db` | Partial — LFI 2026 results with checkpoint splits |
| **Meso** | Strava km-splits (planned) | TBD | Not built |
| **Micro** | Garmin `.fit` telemetry | `02_Raw_Data/` → washed Parquet in `03_Processed_Data/micro/` via `15_fit_micro_wash.py` | **Partial** — Wave 2 ActivityFrame (`wave2_v1`) |
| **Spatial panel** | Multi-FIT align to course spine | `03_Processed_Data/spatial/{corridor_id}/panel_1m.parquet` | **Built** for SUT_43 operator scope, O₁ anchors (Stavanger HM, 3_sjoerslopet, Sunderunde), orphan bootstraps |
| **Meso / compliance** | Planned session tags + weekly rollups | **TBD** — see §5.1 | **Not built** |

### 5.1 Meso layer & private training blueprint (do not conflate with macro DB)

**TRF is diagnostic, not prescriptive** (`docs/training_residual_framework.md`). A periodized **Sub-1:40 / 3-Sjøersløpet-style training blueprint** (4-day matrix, fast-finish Sunday sims, nutrition anchors, lifting) belongs in the **private training manual** and **gitignored local config** — not in public SQLite schema or GitHub commits.

| Need | Correct layer | Wrong approach |
|------|---------------|----------------|
| Race results ecology (LFI splits, finish times) | `05_Macro_Database/anatomy_macro.db` — `races`, `race_results` | — |
| Weekly plan (Tue micro / Wed recovery / Fri aerobic+lifting / Sun sim) | Gitignored `config/training_blueprint.local.json` + private manual | `ALTER TABLE` on `anatomy_macro.db` |
| Session type per FIT (`activity_id` → `tuesday_micro`, `sunday_simulator`) | Gitignored `config/session_metadata.local.json` | Hard-coded personal targets in public Python |
| Daily weight / protein / carbs | Gitignored local DB or JSON (`training_compliance.local.db`) | Public repo fields with operator targets |
| Sunday fast-finish pace check (e.g. 4:44 min/km on final 1.5–5 km) | **Pandas on washed micro Parquet** — future `evaluate_fast_finish.py` reading **local** blueprint | SQL on empty tables before FIT ingest |
| 3_sjoerslopet course axis / TI calibration | Spatial pipeline — `config/spatial_align_manifest_3_sjoerslopet.json` | Projecting every training run onto race course |

**3_sjoerslopet in this repo** = **O₂ mixed gravel/asphalt race anchor** (~21.25 km stream) for TI/gold-suggester calibration — **not** a weekly training planner. Training venues (e.g. gravel intervals at local lakes, easy recovery loops) use **stream distance** on each FIT unless the session is an explicit race-course simulation.

**Recommended architecture (when building compliance tooling):**

```
Private (gitignored)
├── config/training_blueprint.local.json    ← 4-day matrix, pace bands, monthly progression, recovery weeks
├── config/session_metadata.local.json      ← activity_id → session_type, week_id, phase
└── training_compliance.local.db            ← optional: daily_metrics, session_summaries, compliance flags

Public (Anatomy of Pace)
├── 15_fit_micro_wash.py                    ← existing micro ingest
├── evaluate_fast_finish.py                 ← future: local blueprint + Parquet → pace/drift flags (no personal targets in repo)
└── docs/                                   ← meso spec only; no operator body-comp numbers
```

**Sunday fast-finish evaluation (conceptual):**

1. Tag washed activities via local metadata (`session_type = sunday_simulator`).
2. Resolve fast-finish window from local blueprint (`km_end - [1.5..5.0]` by month; recovery week → no fast finish).
3. On stream `distance_m` / `course_km`, compute median pace + cardiac drift (HR rise at stable speed) in that window.
4. Flag deviations vs blueprint tolerance; write summaries to **local** DB only.

**Monthly progression / recovery-week rules** belong in **blueprint JSON**, not SQL migrations:

- Base phase: shorter fast finish (e.g. 1.5–2 km @ target pace).
- Build phase: extend fast finish (e.g. 3–5 km @ target pace).
- Recovery week (every 4th): halve Tuesday volume, cap Sunday distance, drop fast finish, reduce lifting intensity — all blueprint flags.

**Bridge:** Compliance findings → Sync Log → private manual. Never reverse-publish blueprint content under The Anatomy of Pace brand.

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

## 7. HITL Annotator Sprint (v0.3.x)

**Primary workflow:** `04_Python_Scripts/spatial/suggest_gold_spans.py` (CSV lock proposals → manual JSON append).  
**Streamlit annotator:** `04_Python_Scripts/spatial/hitl_annotator_app.py` — **PARKED** (v0.3.1 retained for regression).  
**Operator guide:** `docs/hitl_annotator.md`  
**Companion runbook:** `docs/hitl_dashboard_runbook.md`

### Launch

```bash
cd /path/to/Anatomy_of_Pace
export MPLCONFIGDIR="${MPLCONFIGDIR:-$(pwd)/.mplconfig}"
mkdir -p "$MPLCONFIGDIR" .tile_cache

streamlit run 04_Python_Scripts/spatial/hitl_annotator_app.py
```

Safety checks (no Streamlit UI):

```bash
python3 04_Python_Scripts/spatial/hitl_annotator_app.py --import-test
python3 04_Python_Scripts/spatial/hitl_annotator_app.py --dry-run-test
```

### Features (verified in current codebase)

| Feature | Detail |
|---------|--------|
| **Kartverket basemap** | Standard / Greyscale / Satellite orthophoto (Flyfoto); maritime layers blocked |
| **Metric scalebar** | Bottom-left on topo PNG; 1:1 lon/lat aspect lock via square matplotlib canvas |
| **Dual-layer TI + HMM viz** | Continuous mode: plasma TI trace + semi-transparent HMM background shapes |
| **Operator gold on map toggle** | Sidebar **Map track: Operator gold** — gold spans vs GMM draft `segments[]` |
| **Crosshair + click-to-set locks** | Hover readout (course_km, TI, S#/F#); **Set Start** / **Set End** + profile click |
| **Dry-run Save Lock** | Default ON; confirmation modal before production JSON append |
| **Chunk triage queue** | RPS-ranked RED / YELLOW / GREEN from `hitl_chunk_triage.py` |
| **Profile modes** | Continuous TI gradient vs Categorical F-tier / S-class validation |
| **Six-row Plotly stack** | TI (+ HMM), cross-athlete NTI σ heatmap, speed (m/s), grade (%), pace expected (min/km), categorical strip |
| **Speed traces (row 3)** | Consensus median + optional Subject_A / Subject_B overlay; zero/halt masking; explicit padded y-axis (`fixedrange=True`) |
| **Overlap guard** | Blocks intersecting `operator_gold_spans[]` writes |

### Panel scope

| Window | Status |
|--------|--------|
| **km 22.0–41.0** | Built — Dale upstream (22–29) + gramstad_band (29–41) operator panel |
| **km 0.5–8.0** | Phase E scoped — ingest not executed; see `docs/memos/16_phase_e_start_ingest_scope.md` |
| **km 0.5–21.9** | Panel gap — no race rows until full-lap spine rebuild |

Constants: `corridor_scope.py` → `SUT43_UPSTREAM_KM_START = 22.0`, `SUT43_PRIMARY_KM_START = 29.0`, `SUT43_PRIMARY_KM_END = 41.0`.

### Terrain map config files

| File | Sector | `course_km` window |
|------|--------|-------------------|
| `config/spatial_terrain_map_sut43.json` | gramstad_band | 29–41 (primary RED queue) |
| `config/spatial_terrain_map_sut43_upstream.json` | dale_paradisskaret_upstream | 22–29 |
| `config/spatial_terrain_map_sut43_start.json` | leg_a_technical (stub) | 0.5–8.0 — seed segments only |

Operator gold appends to `hitl.operator_gold_spans[]` in the active terrain map JSON. Upstream locks must **not** be written into the gramstad map file.

### Known fixes applied (v0.3.0 → v0.3.1)

| Issue | Resolution |
|-------|------------|
| Hover rerun storm | `@st.fragment` on profile interaction; crosshair-only updates use `st.rerun(scope="fragment")` |
| Axis zoom 0–600 squash | Removed erroneous y-axis `scaleanchor`; x-axes locked to `[km_lo, km_hi]` on `course_km` |
| Row 6 S-class y-range | Categorical strip: `range=[-0.55, 5.45]`, `fixedrange=True`, S1–S6 tick labels |
| Speed row invisible / bad y-axis | `_speed_display_values()` masks halt zeros; `_speed_y_range()` sets explicit padded m/s range |
| Fragment rerun | `_render_profile_interaction` wrapped in `@st.fragment` |
| IndentationError | Resolved — app imports and `--import-test` pass |

Headless regression probes in `--figure-test` cover chunk_00 (upstream speed traces), chunk_08 (Vassfjellet RED), and basemap layer matrix.

### Related spatial scripts

| Script | Function |
|--------|----------|
| `spatial/build_gold_training_set.py` | Per-metre feature export + sparse gold labels |
| `spatial/train_gold_suggester.py` | Train ML suggester → `07_ML_Models/spatial/gold_suggester_v0.joblib` |
| `spatial/suggest_gold_spans.py` | ML (`--engine ml`) or HMM heuristic lock proposals CSV |
| `spatial/gold_span_editor.py` | CLI list/add/delete operator gold spans (backup on write) |
| `spatial/hitl_chunk_triage.py` | RPS triage queue CSV generation |
| `spatial/validation_dashboard.py` | Chunk PNG export + topo QC |
| `spatial/hitl_nti_consistency.py` | NTI gap fill after locks |
| `spatial/corridor_multi_fit.py` | Multi-FIT panel build |
| `spatial/terrain_map_gen.py` | NTI aggregation, terrain map generation |
| `07_ML_Models/train_terrain_hmm.py` | HMM draft parquet for row 4 underlay |

**Design memo:** `docs/memos/17_sparse_gold_ml_suggestion_pipeline.md` — sparse gold contract, feature matrix, human loop.

---

## 8. Legacy Key Scripts

All scripts live in `04_Python_Scripts/`.

| Script | Function |
|--------|----------|
| `01_vaskemaskinen.py` | FIT → cleaned CSV |
| `02_terrengindeks.py` | APR calculator (asphalt vs terrain @ iso-HR) |
| `03_batch_analyse.py` | Batch APR over all `.fit` files in raw data |
| `04_visualiser_ti.py` | APR bar chart per route → `06_Visualizations/` |
| `06_macro_ingest.py` | Ingest LFI CSV results → SQLite |
| `07_plot_decay.py` | Macro checkpoint decay plot |
| `06_benchmark.py` | Paired APR comparison (EAR logic) |
| `07_batch_benchmark.py` | Multi-session benchmark trends |
| `05_radar_scrape.py` | Scrape runster.no race results |
| `15_fit_micro_wash.py` | Wave 2 FIT wash → micro Parquet + optional `--project-course` + `--enrich-ti` |
| `16_fit_corridor_pipeline.py` | End-to-end wash → align → panel orchestrator |
| `spatial/compare_stavanger_halvmarathon_races.py` | YoY race stream compare (2025 vs 2026); panel-first; GPS route-change detection; manifest-locked reroute windows |
| `spatial/compute_training_residual.py` | TRF post-session diagnostics (gramstad_band scope) |
| `init_db.py` | Initialize **macro** DB only (`races`, `athletes`, `race_results`) — not training sessions |
| `05_vam_kalkulator.py` | Vertical ascent rate analysis |

**Still not built:**

- `01_strava_fetcher.py` (OAuth + `.fit` download from reference elites)
- Full GAP calculation module (unlocks production TI)
- Kinematic_Scan v0 automation (donor PDF pipeline)
- **Meso layer / training compliance** (`evaluate_fast_finish.py`, local blueprint sync — see §5.1)
- English migration of legacy Norwegian documentation in untouched local files

---

## 9. Documentation Index

| File | Content |
|------|---------|
| `docs/master_plan.md` | Architecture v3.5, terrain ontology (11 classes), infrastructure spec |
| `docs/theory.md` | Scientific foundation; metrics §5 (APR/TI/TPR/EPR) and §6 (Kinematic_Scan) |
| `docs/brand_identity.md` | Dr. Anatomy Pace public boundary, Ghost Authority, channel map |
| `docs/hitl_annotator.md` | HITL operator guide (launch, workflow, class reference) |
| `docs/hitl_dashboard_runbook.md` | PNG export, topo QC, triage generation |
| `docs/friction_index_spec.md` | F0–F4 friction tier authority spec |
| `docs/race_ecology.md` | Reference race catalog for macro database |
| `docs/launch_strategy.md` | Substack / Instagram ecosystem, donor exchange |
| `docs/memos/16_phase_e_start_ingest_scope.md` | Phase E km 0–8 ingest scope (not yet built) |
| `.cursorrules` | AI enforcement rules for Cursor (Ghost Authority + English + metrics) |

---

## 10. Reference Elite Roles (clinical IDs)

| ID | Role | Primary terrain / race |
|----|------|------------------------|
| Reference_Elite_A | Technical flow baseline | SUT_80 |
| Reference_Elite_B | Extreme distance, Quad-Smash / CNS | SUT_160, OBT |
| Reference_Elite_C | Rogaland technical flow, API pilot | SUT_43, terrain classes 5–11 |
| Reference_Elite_D | Fell running + asphalt anchor (UK) | 5 Valleys, London Marathon |
| Reference_Elite_E | Thermal + alpine technical | Val d'Aran |

Intake method: Strava OAuth 2.0 (`activity:read_all`). Operational routine in outreach doc.

---

## 11. Current Status (August 2026)

### Complete

- Folder structure (00–07, unique numbering)
- Python venv + `requirements.txt` (includes `streamlit`, spatial stack, `fitparse`, Parquet)
- Wave 2 micro wash (`15_fit_micro_wash.py`, `fit_micro/` ActivityFrame Parquet)
- Spatial multi-FIT panels + HITL for SUT_43 (upstream + gramstad), O₁ anchors (Stavanger Halvmarathon, 3_sjoerslopet, Sunderunde)
- Stavanger Halvmarathon YoY compare — panel grid align, GPS route-change detection, two manifest-locked reroute windows (`compare_stavanger_halvmarathon_races.py`)
- TRF scaffold on gramstad_band (`compute_training_residual.py`)
- Macro database scaffold + LFI ingest scripts
- Spatial HITL: suggest_gold_spans, validation_dashboard, chunk exports, Streamlit annotator v0.3.1
- Upstream sector (km 22–29): operator gold locked
- `.gitignore` configured (blocks `.fit`, `.db`, `.venv`, secrets, subject registry)

### In Progress

- Full-course SUT_43 operator gold review (full-lap HITL)
- SUT_43 gramstad paired TRF Substack publication (on hold pending gold sign-off)
- Gramstad_band remaining YELLOW/GREEN queue
- GAP module and production TI
- Ghost Authority sanitization for public visibility

### Not Started

- **Meso / training compliance layer** (§5.1) — blueprint evaluator on micro Parquet + local config only
- Full-lap SUT_43 merged panel after gold gate
- Strava OAuth fetcher script
- Kinematic_Scan v0 automation (donor PDF)
- GeoPandas / Snap-to-Route at scale

---

## 12. Recommended Next Steps (Priority Order)

1. **Complete SUT_43 full-course operator gold** — full-lap HITL chunks; re-export composite/TRF after sign-off.
2. **GAP module** — unlock production TI, TPR, and EPR.
3. **Kinematic_Scan v0** — single script: input one `.fit` → profile chart + slowest segment → PNG to `06_Visualizations/`.
4. **Meso compliance (local only)** — if operator requests Sub-1:40 / 4-day blueprint tracking: build `evaluate_fast_finish.py` + gitignored `training_blueprint.local.json`; do **not** extend `anatomy_macro.db` (see §5.1).
5. **Sanitization pass** — English + Subject_A identifiers before public deliverables.
6. **Strava fetcher** — automated `.fit` intake from reference elites.

---

## 13. Instructions for Gemini

When assisting on this project:

1. Enforce **Ghost Authority** and **English-only** rules in all generated text destined for external channels.
2. Never conflate **APR** with **TI** — they measure different things.
3. Distinguish **The Anatomy of Pace** (research) from **private training** (local, gitignored — never publish).
4. Use `docs/master_plan.md`, `docs/theory.md`, and `docs/brand_identity.md` as architecture source of truth.
5. **Do not commit unless explicitly asked** — operators control git history.
6. Never commit personal names, `.fit` files, `anatomy_macro.db`, `panel_1m.parquet`, or `subject_registry.local.json`.
7. Default donor deliverable name: **Kinematic_Scan** — not legacy Norwegian product terms.
8. Script directory: `04_Python_Scripts/`. Spatial HITL: `04_Python_Scripts/spatial/`. Visual output: `06_Visualizations/`.
9. For HITL work, read `docs/hitl_annotator.md` before modifying `hitl_annotator_app.py`.
10. Legacy Norwegian filenames and content may exist locally — translate on contact; do not reproduce Norwegian conceptual terms in new output (except permitted proper nouns).
11. Attribute public-facing work to **Dr. Anatomy Pace** — never to real individuals.

### 13.1 Reject or redirect: “Sub-1:40 blueprint → SQLite macro DB” proposals

Operators may ask to align FIT telemetry with a **private 4-day training matrix** (Tuesday micro-intervals, Wednesday recovery, Friday aerobic + lifting, Sunday simulator with fast-finish blocks targeting ~4:44 min/km for a ~21 km Sub-1:40 goal). **Do not implement this by altering `anatomy_macro.db` or adding operator body-weight / macro-nutrition targets to public schema.**

| Gemini-style request | Verdict | What to do instead |
|---------------------|---------|-------------------|
| `ALTER TABLE` on `anatomy_macro.db` for workouts | **Reject** | Macro DB = race ecology only (`init_db.py`) |
| SQL on “final 1.5–5 km Sunday runs” before ingest | **Redirect** | Compute from washed micro Parquet; optional sync to **local** SQLite summaries |
| Categorize runs in SQLite by day-of-week matrix | **Local only** | `session_metadata.local.json` + `training_blueprint.local.json` |
| Log daily weight / protein / carbs in public repo | **Reject** | Gitignored `training_compliance.local.db` or private manual |
| Project all training FITs on `3_sjoerslopet` course axis | **Reject** | Use 3_sjoerslopet spatial pipeline **only** for race-anchor / sim sessions on that course |
| Pandas weekly deviation + cardiac drift flags | **Approve (public script)** | Generic `evaluate_fast_finish.py` reading **local** blueprint config |

**Session-type pace bands (private blueprint — do not commit numeric targets to GitHub):**

| Day | Session type | Role |
|-----|--------------|------|
| Tuesday | Micro-intervals | Gravel intervals (e.g. 3×10 min work / 45s–15s); target pace band in local blueprint |
| Wednesday | Active recovery | Fixed-distance easy run; high pace floor |
| Friday | Aerobic + strength | Short easy jog then lifting block (details in private manual) |
| Sunday | Simulator | Long run with optional fast-finish; distance and finish length progress by month; recovery week removes fast finish |

**Progression rules** (September → October fast-finish length, every-4th-week recovery) live in **`training_blueprint.local.json`**, not SQL migrations.

**Git on Mac:** Operators on `main` must merge feature branches explicitly — `git pull` alone does not apply remote branch commits. Use `git merge origin/<branch>` or `git checkout <branch>`.

---

*End of handoff brief.*
