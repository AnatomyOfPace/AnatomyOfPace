# Handoff Brief: The Anatomy of Pace

**From:** Cursor AI  
**To:** Gemini AI  
**Purpose:** Project context, current status, and active workstreams  
**Date:** 2026-07-01  
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
| **Micro** | Garmin `.fit` telemetry | `02_Raw_Data/` → cleaned Parquet in `03_Processed_Data/micro/` | Partial |
| **Spatial panel** | Multi-FIT align to course spine | `03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet` | **km 0.5–8.0** (Phase E start) + **km 22.0–41.0** (upstream + gramstad_band) |

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
| **km 0.5–8.0** | **Phase E start sector** — panel built (`5689aeb`); **operator gold labels complete** through Noredalen opening descent @ km 8.0 (`46a0ff2`, 2026-07-01) |
| **km 8.0–21.9** | **Panel gap** — no race telemetry rows until mid-course spine rebuild |
| **km 22.0–29.0** | **Dale upstream** — panel built; **100% operator gold** (chunks u00–u06, locked 2026-06-29) |
| **km 29.0–41.0** | **gramstad_band** — panel built; **partial operator gold** (see §11 coverage table) |

Constants: `corridor_scope.py` → `SUT43_UPSTREAM_KM_START = 22.0`, `SUT43_PRIMARY_KM_START = 29.0`, `SUT43_PRIMARY_KM_END = 41.0`.

### Terrain map config files

| File | Sector | `course_km` window |
|------|--------|-------------------|
| `config/spatial_terrain_map_sut43_start.json` | leg_a_technical | 0.5–8.0 — **operator gold locked** (13 spans) |
| `config/spatial_terrain_map_sut43_upstream.json` | dale_paradisskaret_upstream | 22–29 — **fully locked** |
| `config/spatial_terrain_map_sut43.json` | gramstad_band | 29–41 — **partial locks** |

Operator gold appends to `hitl.operator_gold_spans[]` in the active terrain map JSON. Locks must **not** cross sector file boundaries (start / upstream / gramstad).

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

**Design memos:** `docs/memos/17_sparse_gold_ml_suggestion_pipeline.md`, `docs/memos/18_gold_hitl_low_hanging_fruit.md`, `docs/memos/21_multitask_gold_suggester_nn.md`.

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
| `init_db.py` | Initialize macro DB schema |
| `05_vam_kalkulator.py` | Vertical ascent rate analysis |
| `08_kinematic_scan.py` | Kinematic_Scan scaffold (donor deliverable) |
| `11_gap_engine.py` | GAP calculation scaffold |
| `12_strava_fetcher.py` | Strava OAuth scaffold |
| `15_fit_micro_wash.py` | FIT micro-wash pipeline entry |
| `16_fit_corridor_pipeline.py` | Corridor FIT ingest orchestration |

**Still not production-ready:**

- Full GAP module (unlocks production TI / TPR / EPR)
- Kinematic_Scan v0 automation (donor PDF pipeline)
- Strava OAuth fetcher (scaffold only — not operational)
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
| `docs/training_residual_framework.md` | TRF specification (locomotion gates, ΔTI residualization) |
| `docs/race_ecology.md` | Reference race catalog for macro database |
| `docs/launch_strategy.md` | Substack / Instagram ecosystem, donor exchange |
| `docs/memos/15_hitl_status_20260629.md` | HITL sprint snapshot — km 22–34 lock wave |
| `docs/memos/17_sparse_gold_ml_suggestion_pipeline.md` | Sparse gold ML contract |
| `docs/memos/18_gold_hitl_low_hanging_fruit.md` | Annotation tier ladder + REVISE deferral policy |
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

## 11. Current Status (July 2026)

**Git:** `main` @ `46a0ff2` (2026-07-01) — synced with `origin/main`, clean working tree.

### SUT_43 operator gold coverage

| Sector | km window | Operator gold | Notes |
|--------|-----------|---------------|-------|
| **Phase E start** | 0.5–8.0 | **Complete** | 13 spans locked 2026-06-30 → 2026-07-01; viewport terminus @ Noredalen opening descent km 8.0 |
| **Mid-course gap** | 8.0–21.9 | **None** | Panel + labels pending spine rebuild |
| **Dale upstream** | 22.0–29.0 | **100%** | chunks u00–u06 locked 2026-06-29 |
| **gramstad_band early** | 29.0–34.0 | **100%** | chunks 00–04 locked 2026-06-29 |
| **gramstad_band mid** | 34.0–37.0 | **Partial** | chunk_05 ~87%, chunk_06 ~76%, chunk_07 ~0% operator gold (draft preservation ~80%) |
| **gramstad_band late** | 37.0–41.0 | **Partial** | chunk_08 ~92% operator gold; chunks 09–10 ~41–42%; chunk_11 100% |

**gramstad_band triage queue (RPS-ranked):** top RED = `chunk_08` (km 37–38); YELLOW on chunks 00–04 (post-lock QC drift), 07, 09–10; GREEN on 05–06, 11.

**Phase E open operator questions (recorded in lock notes):**

- ~km 5.15 tread step character (post-descent technical tread)
- ~km 5.45–5.87 Skrussfjell rim tread vs trail
- ~km 6.29 Skrussfjell DH onset tread character
- Hommersåk training TI cross-check deferred on all start-sector locks (effort mixing)

### Complete

- Folder structure (00–07, unique numbering)
- Python venv + `requirements.txt` (includes `streamlit`, `streamlit-plotly-events`, `contextily`, `plotly`, `scikit-learn`)
- Documentation library in `docs/`
- Metrics framework defined and documented
- APR scripts operational on local `.fit` files
- Macro database: LFI 2026 results with checkpoint splits (local `.db`, gitignored)
- Spatial HITL pipeline: panel build, terrain maps, RPS triage, Streamlit annotator v0.3.1
- Sparse gold ML suggestion pipeline v0 (CLI build/train/suggest)
- Dale upstream (km 22–29): full operator gold
- Phase E start sector (km 0.5–8.0): operator gold labels + start panel
- gramstad_band (km 29–34): full operator gold
- Four-gate locomotion classifier + TRF kinematics integration (`locomotion_mode.py`)
- `.gitignore` configured (blocks `.fit`, `.db`, `.venv`, secrets, subject registry)
- GitHub repository: [AnatomyOfPace/AnatomyOfPace](https://github.com/AnatomyOfPace/AnatomyOfPace)

### In Progress

- **gramstad_band km 34–40** — operator gold on chunks 05–10; `chunk_08` (Vassfjellet, km 37–38) is highest-RPS RED
- Terrain HMM / GB draft refinement against operator gold
- Sparse gold ML suggester training on expanding label set (road-first, Tier 3 REVISE deferral on trail)
- Ghost Authority sanitization of scripts and docs for public visibility
- GAP module and production Terrain Index (TI)

### Not Started

- Full-lap SUT_43 panel (km 0.5–42.5 end-to-end)
- Mid-course panel bridge (km 8.0–21.9)
- Kinematic_Scan v0 automation (donor PDF)
- English migration of all legacy Norwegian documentation
- GeoPandas / Snap-to-Route at scale
- Parquet + DuckDB micro processing layer
- v4.0 cloud migration (PostgreSQL, S3, Dynamic Resistance Score)

### Recent lock waves (reference)

| Date | Commit | Content |
|------|--------|---------|
| 2026-06-29 | `b29991a` | gramstad chunk_04 + locomotion classifier |
| 2026-06-30 | `5689aeb` | Phase E start panel km 0.5–8 + GPX re-projection fix |
| 2026-06-30 | `7df9fa2` | Phase E chunk_00 — Hommersåk chute S1/F0 @ Hogstad anchor |
| 2026-07-01 | `e81b9d3` | Phase E topo correction — Frøylandsvatnet lakeshore S2/F1 |
| 2026-07-01 | `46a0ff2` | Phase E complete through km 8.0 — Noredalen rim + opening descent |

---

## 12. Recommended Next Steps (Priority Order)

1. **gramstad_band RED queue** — lock `chunk_08` (km 37–38, Vassfjellet); advance chunks 07 / 09 / 10; re-run triage after each lock wave.
2. **Phase E QC pass** — resolve open topo questions (~5.15, 5.45–5.87, ~6.29); optional hommersak training TI corroboration when effort mixing is controlled.
3. **Mid-course panel bridge** — extend spine + panel km 8.0–21.9 to close the telemetry gap between start sector and Dale upstream.
4. **GAP module** — unlock production TI, TPR, and EPR.
5. **Kinematic_Scan v0** — single script: input one `.fit` → APR profile chart + slowest segment → PNG to `06_Visualizations/`.
6. **Sanitization pass** — English translation + Subject_A identifiers before any expanded public repo visibility.
7. **Strava fetcher** — operationalize OAuth `.fit` intake from reference elites.

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
12. **Labels ≠ panel rows:** operator gold in terrain map JSON can exist before washed race telemetry covers the same km window — verify panel scope before triage or ML training.

---

*End of handoff brief.*
