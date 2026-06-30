# HITL Operator Guide — Terrain Gold Input

**Primary workflow (2026-06-30):** sparse-gold ML pipeline (build → train → suggest) + `gold_span_editor.py` CLI  
**Legacy heuristic:** `suggest_gold_spans.py --engine hmm` (HMM + TI, no trained model)  
**Streamlit annotator:** `04_Python_Scripts/spatial/hitl_annotator_app.py` — **PARKED** (v0.3.1 retained for regression; not the default operator path)  
**Design memo:** [`docs/memos/17_sparse_gold_ml_suggestion_pipeline.md`](memos/17_sparse_gold_ml_suggestion_pipeline.md)  
**Authority:** Dr. Anatomy Pace laboratory · Subject_A / Subject_B race panel only  
**Companion:** [`docs/hitl_dashboard_runbook.md`](hitl_dashboard_runbook.md) (PNG export, topo QC, RPS triage generation)

Operator input is stored as append-only entries in `hitl.operator_gold_spans[]` inside the terrain map JSON.

---

## Quick start (ML pipeline + CLI editor)

1. **Install** — `pip install -r requirements.txt` from repo root.
2. **Confirm data** — `panel_1m.parquet`, HMM draft parquet, and `config/spatial_terrain_map_sut43.json` exist locally.
3. **Build training export** — per-metre features + sparse gold labels (`build_gold_training_set.py`).
4. **Train suggester** — `HistGradientBoosting` on labeled metres only (`train_gold_suggester.py`).
5. **Generate suggestions** — ML engine: gaps, revisions, or both (`suggest_gold_spans.py --engine ml`).
6. **Review CSV** — agree/disagree with each `NEW` / `REVISE` row; ignore `KEEP` unless auditing.
7. **Promote locks** — `gold_span_editor.py add` (overlap-safe, backup on write) or manual JSON append.
8. **Verify** — `python3 -m json.tool config/spatial_terrain_map_sut43.json > /dev/null` and re-export chunk PNG.

```bash
# Full ML loop (gramstad_band km 29–41)
python3 04_Python_Scripts/spatial/build_gold_training_set.py \
  --km-start 29 --km-end 41 \
  --output 03_Processed_Data/spatial/gold_training_set_sut43.parquet

python3 04_Python_Scripts/spatial/train_gold_suggester.py \
  --training-set 03_Processed_Data/spatial/gold_training_set_sut43.parquet

python3 04_Python_Scripts/spatial/suggest_gold_spans.py \
  --engine ml --mode all \
  --km-start 37 --km-end 38 --chunk chunk_08 \
  --output 03_Processed_Data/spatial/suggested_locks_chunk08_ml.csv

# Promote accepted span (example)
python3 04_Python_Scripts/spatial/gold_span_editor.py add \
  --km-start 38.1 --km-end 38.2 --surface S3 --friction F2 \
  --reason "operator accepted ML NEW suggestion"
```

### Gold span editor CLI

| Command | Purpose |
|---------|---------|
| `gold_span_editor.py list` | Index all `operator_gold_spans[]` |
| `gold_span_editor.py add --km-start … --km-end … --surface S# --friction F# --reason "…"` | Append non-overlapping span (timestamped JSON backup) |
| `gold_span_editor.py delete --index N` | Remove span by list index |

Gaps between spans are allowed; overlap on add is rejected.

---

## Quick start (legacy HMM heuristic)

### Streamlit annotator (parked)

The Plotly + Streamlit UI remains in-repo for `--import-test` regression and optional visual review. Do **not** rely on it for production lock promotion until re-activated.

```bash
streamlit run 04_Python_Scripts/spatial/hitl_annotator_app.py
```

---

## Suggestion workflow

**Script:** `04_Python_Scripts/spatial/suggest_gold_spans.py`

### ML engine (primary)

Trained on operator-labeled metres only. Modes:

| `--mode` | Behaviour |
|----------|-----------|
| `gaps-only` | **NEW** spans on unlabeled metres (≥ 50 m contiguous runs) |
| `revise` | **REVISE** where model disagrees with existing gold above probability threshold |
| `all` | Gaps + revisions + **KEEP** summary rows where model agrees |

Course-wide windows: `--km-start` / `--km-end` (no triage queue required).

```bash
python3 04_Python_Scripts/spatial/suggest_gold_spans.py \
  --engine ml --mode gaps-only \
  --km-start 37 --km-end 38 \
  --model 07_ML_Models/spatial/gold_suggester_v0.joblib \
  --output 03_Processed_Data/spatial/suggested_locks_sut43.csv
```

| ML output column | Meaning |
|------------------|---------|
| `action` | `NEW` \| `REVISE` \| `KEEP` |
| `surface_class` / `friction_tier` | Model suggestion |
| `gold_surface` / `gold_friction` | Existing operator gold (revise/keep rows) |
| `surface_proba` / `friction_proba` | Holdout-style class probabilities |
| `confidence` | LOW / MED / HIGH from min(proba) |
| `rationale` | One-line summary |

### HMM engine (legacy heuristic)

Proposes lock spans on **ungolded metres** within triage chunks: HMM draft S-class runs (≥ 50 m), friction tier from consensus TI (`docs/friction_index_spec.md` §3 bands), confidence from HMM *p* + NTI σ. Skips ranges overlapping existing `operator_gold_spans[]`.

```bash
# RED queue (default)
python3 04_Python_Scripts/spatial/suggest_gold_spans.py \
  --queue RED \
  --output 03_Processed_Data/spatial/suggested_locks_sut43.csv

# Single chunk probe — HMM engine (prints sample rows)
python3 04_Python_Scripts/spatial/suggest_gold_spans.py \
  --engine hmm --chunk chunk_08 \
  --output 03_Processed_Data/spatial/suggested_locks_sut43.csv
```

| Output column | Meaning |
|---------------|---------|
| `chunk_id` | Triage chunk label |
| `km_start` / `km_end` | Suggested lock window |
| `surface_class` | Modal HMM S-class on contiguous run |
| `friction_tier` | F0–F4 from consensus TI median |
| `confidence` | LOW / MED / HIGH (HMM *p* + NTI σ) |
| `ti_median` | Consensus TI in window |
| `hmm_p_median` | Median HMM max-state probability |
| `rationale` | One-line auto summary |

After review, append accepted rows using the [manual append schema](#manual-append-schema). The suggestion CSV is **not** written to the terrain map automatically.

---

## Prerequisites

| Item | Path / note |
|------|-------------|
| **Repo root** | All commands run from `/Users/eiriklarsen/Desktop/Anatomy_of_Pace` (or your local clone). |
| **Python env** | Python 3.11+ recommended; `pip install -r requirements.txt` installs `streamlit`, `plotly`, `contextily`, `pandas`, `pyarrow`. |
| **Panel parquet** | `03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet` — race rows for Subject_A / Subject_B on `course_km` / `ref_chainage_m`. **Not committed**; rebuild via spatial align pipeline if missing. |
| **Terrain map JSON** | `config/spatial_terrain_map_sut43.json` (gramstad_band km 29–41). Upstream km 22–29 → `config/spatial_terrain_map_sut43_upstream.json`. |
| **Triage queue CSV** | `03_Processed_Data/spatial/sut43_terrain_ontology/ground_truth_review/triage_queue_sut43.csv` — optional but recommended; regenerate with `hitl_chunk_triage.py` (see runbook). |
| **HMM draft parquet** | `07_ML_Models/terrain_hmm_sut43_draft_predictions.parquet` — optional; powers row 4 draft strip. Missing file → empty draft strip, annotator still runs. |
| **Subject registry** | `config/subject_registry.local.json` (gitignored) — **not required by the annotator** (panel already uses `Subject_A` / `Subject_B` as `donor_id`). Required for FIT ingest / panel build. Template: `config/subject_registry.example.json`. |
| **Matplotlib cache** | `export MPLCONFIGDIR="$(pwd)/.mplconfig"` before launch if topo basemap warns about cache dirs. |
| **Tile cache** | `.tile_cache/` at repo root — Kartverket / OSM tiles for topo panel. |

---

## Launch commands

### Default (gramstad_band)

```bash
cd /path/to/Anatomy_of_Pace
export MPLCONFIGDIR="${MPLCONFIGDIR:-$(pwd)/.mplconfig}"
mkdir -p "$MPLCONFIGDIR" .tile_cache

streamlit run 04_Python_Scripts/spatial/hitl_annotator_app.py
```

Browser opens at `http://localhost:8501`.

### Headless / remote

```bash
streamlit run 04_Python_Scripts/spatial/hitl_annotator_app.py --server.headless true
```

### Custom data paths (CLI after `--`)

```bash
streamlit run 04_Python_Scripts/spatial/hitl_annotator_app.py -- \
  --panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet \
  --terrain-map config/spatial_terrain_map_sut43.json \
  --triage-queue 03_Processed_Data/spatial/sut43_terrain_ontology/ground_truth_review/triage_queue_sut43.csv \
  --hmm-draft 07_ML_Models/terrain_hmm_sut43_draft_predictions.parquet \
  --lat-offset 0.00012 --lon-offset -0.00008
```

| Flag | Purpose |
|------|---------|
| `--lat-offset` | Shift panel GPS latitude (degrees) for topo basemap alignment |
| `--lon-offset` | Shift panel GPS longitude (degrees) for topo basemap alignment |

Paths are also editable in the sidebar without restarting.

### Safety verification (non-production)

```bash
python3 04_Python_Scripts/spatial/hitl_annotator_app.py --import-test
python3 04_Python_Scripts/spatial/hitl_annotator_app.py --dry-run-test
```

`--dry-run-test` writes `temp_test.json` only — never touches `config/spatial_terrain_map_sut43.json`.

### Disable Streamlit usage stats

Either create `.streamlit/config.toml`:

```toml
[browser]
gatherUsageStats = false
```

Or pass at launch:

```bash
streamlit run 04_Python_Scripts/spatial/hitl_annotator_app.py --browser.gatherUsageStats false
```

### Upstream sector (km 22–29)

Set **Terrain map JSON** in the sidebar to `config/spatial_terrain_map_sut43_upstream.json` before saving locks. Do **not** write upstream spans into `spatial_terrain_map_sut43.json`.

### Upstream calibration (Hogstad approach)

Strategic Command pivot: validate HITL tooling on the **start-of-course corridor** before resuming gramstad_band RED review. Use a **separate terrain map file** and **separate triage output** so gramstad locks stay isolated.

| Item | Path / value |
|------|----------------|
| Terrain map | `config/spatial_terrain_map_sut43_upstream.json` — sector `dale_paradisskaret_upstream`, km 22–29; 27 operator gold spans locked 2026-06-29 |
| Panel | `03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet` (race rows km **22.0–41.0** only) |
| Triage queue | `ground_truth_review/triage_queue_upstream.csv` — generate with `--km-start 22 --km-end 29 --output …/triage_queue_upstream.csv` |
| Calibration target | `chunk_00` km 22–23 (RED, RPS ~0.88) or manual window ~km 23.5 Dale CP band |

**Panel coverage gap (2026-06-29):** No local race panel rows exist for km 0.5–21.9. Memo window km 0.5–15 (Hogstad timing index ~0.66, Dalevatn ~14.5) requires a full-lap panel rebuild via the spatial align pipeline before triage or locks are meaningful there. Until then, upstream calibration runs on the **km 22–29 panel window** that matches the upstream map segments.

**Launch (upstream calibration):**

```bash
cd /path/to/Anatomy_of_Pace
export MPLCONFIGDIR="${MPLCONFIGDIR:-$(pwd)/.mplconfig}"
mkdir -p "$MPLCONFIGDIR" .tile_cache

# Regenerate upstream-only triage (does not overwrite gramstad queue)
python3 04_Python_Scripts/spatial/hitl_chunk_triage.py \
  --km-start 22 --km-end 29 \
  --output 03_Processed_Data/spatial/sut43_terrain_ontology/ground_truth_review/triage_queue_upstream.csv

streamlit run 04_Python_Scripts/spatial/hitl_annotator_app.py -- \
  --terrain-map config/spatial_terrain_map_sut43_upstream.json \
  --triage-queue 03_Processed_Data/spatial/sut43_terrain_ontology/ground_truth_review/triage_queue_upstream.csv
```

Sidebar: confirm **Terrain map JSON** ends in `spatial_terrain_map_sut43_upstream.json` before **Save Lock**. Footer must show upstream filename — not `spatial_terrain_map_sut43.json`.

**Gramstad isolation checklist after upstream session:**

1. `spatial_terrain_map_sut43.json` — no new entries in `hitl.operator_gold_spans[]` with `course_km_start` < 29.
2. `triage_queue_sut43.csv` — still gramstad window (km 29–41); regenerate with `--km-start 29 --km-end 41` if overwritten.
3. Re-launch annotator with `--terrain-map config/spatial_terrain_map_sut43.json` before gramstad RED work.

---

## Step-by-step workflow

### 1 — Select review window

**With triage queue (recommended):**

1. Sidebar → **Triage queue** → filter `RED` / `YELLOW` / `GREEN` / `ALL`.
2. Pick a chunk from the dropdown (sorted by RPS descending within the filter).
3. View window auto-sets to that chunk's `km_start`–`km_end`.

**Without triage queue:**

- Sidebar shows **course_km_start** / **course_km_end** sliders (defaults: corridor km 29–41 bounds).

### 2 — Review telemetry

Main panel (Plotly, four stacked rows):

| Row | Signal | Use |
|-----|--------|-----|
| 1 | TI trace (+ HMM dual-layer in Continuous mode) | Grade-adjusted performance index; HMM draft as semi-transparent background |
| 2 | Cross-athlete NTI σ heatmap | High σ → disagreement or behavioral event; defer or TRF-tag |
| 3 | Consensus speed + optional athlete overlay | Subject_A / Subject_B speed (dotted); halt alignment at CPs |
| 4 | Categorical strip | **Continuous mode:** operator gold (if present) + faint HMM draft. **Categorical mode:** operator gold + F-tier edges + faint HMM underlay |

### Decision workflow — layer reference (v0.3.1)

Use these layers together when reviewing RED chunks (e.g. `chunk_08` km 37–38):

| Layer | Location | Authority | Purpose |
|-------|----------|-----------|---------|
| **Topo map track** | Main panel PNG | Toggle **Map track: Operator gold** (default ON when gold spans exist) | Geographic S-class colour on course trace — gold spans when ON, GMM `segments[]` draft when OFF |
| **TI row 1** | Plotly · Continuous mode | Mechanical truth | Plasma TI gradient; optional HMM background strip for algorithmic hint |
| **NTI σ row 2** | Plotly | Cross-athlete divergence | High σ → pause lock; investigate behavioral or alignment |
| **Speed row 3** | Plotly | Context | Consensus + athlete traces; CP halts are TRF exclusions, not S-class downgrades |
| **Row 4 strip** | Plotly · Categorical mode (preferred for lock validation) | Operator gold + F-tier edges; faint HMM underlay | Side-by-side gold vs draft before **Save Lock** |
| **Crosshair** | Sidebar + chart metrics | Gold first (`S#/F#`), else HMM draft | Metre-precise class at cursor; drives click-to-set lock bounds |
| **Draft vs gold caption** | Above profile chart | Diagnostic only | % of gold-covered metres where HMM draft S-class ≠ operator gold — highlights unresolved disagreement |

**Recommended RED review sequence:** Enable topo → confirm **Map track: Operator gold** → switch profile to **Categorical F-tier / S-class** → hover transitions → read **Draft vs gold** caption → narrow lock window with **Set Start** / **Set End** → dry-run **Save Lock** first.

**Profile mode toggle (sidebar):**

| Mode | Purpose |
|------|---------|
| **Continuous TI gradient** | Deep dive — TI line with HMM draft strip overlaid; hover shows raw TI + HMM class + confidence per metre |
| **Categorical F-tier / S-class** | Lock validation — operator gold spans with F-tier edge colours + faint HMM draft underlay |

**Zoom (v0.3.0):** Profile rows use `dragmode=zoom` with `shared_xaxes=True` — box-zoom or scroll-zoom on any row syncs all four `course_km` windows. Reset via Plotly **home** icon in the chart toolbar.

**Crosshair readout (v0.3.0):** Hover the profile (requires `streamlit-plotly-events`). Sidebar and the metric strip above the chart show **course_km**, **TI**, and **Class** (`S#/F#` from operator gold, else HMM draft). A faint vertical line marks the crosshair km.

**Click-to-set lock bounds (v0.3.0):** Sidebar → **Set Start** or **Set End**, then click the profile. The nearest metre row populates `course_km_start` / `course_km_end`. Shift-click is not available in Streamlit; use the two-step button mode.

**Topo vs profile zoom:** The Kartverket PNG is rendered for the **chunk window** only and does **not** follow Plotly zoom. Use the synced profile axis for metre-precision review; use topo as geographic reference for the chunk.

**Optional panels:**

- **Show topo basemap** — Kartverket layer (Standard / Greyscale / Satellite) via `contextily`, synced to the same `course_km` window. **1:1 lon/lat aspect lock** (`map_display_aspect=1.0`) on a square matplotlib canvas (`TOPO_MAP_SIZE_IN=7.2` in) and **metric scalebar** (bottom-left). Display uses `display_aspect_locked_image` (base64 `<img>` with `aspect-ratio:1/1`, `object-fit:contain`, centred column, max 720 px wide) — not `use_container_width`. Profile chart fixed **800 px** wide. GPS drift correction via CLI `--lat-offset` / `--lon-offset`. Standard and greyscale layers work without a token; **Satellite orthophoto (Flyfoto)** requires `NIB_WMTS_TOKEN`.
- **Map track: Operator gold** — When ON (default if `operator_gold_spans[]` overlap the view window), topo track colours follow locked operator gold via `decision_mode` overlay. When OFF, track shows GMM draft `segments[]`. Caption shows active mode (`track: operator gold` vs `track: GMM draft`).
- **Athlete overlay** — per-subject speed on row 3.

**Basemap — orthophoto token (Satellite / Flyfoto only):**

1. Generate a token at [services.norgeibilder.no/token](https://services.norgeibilder.no/token).
2. **Shell export** (one session): `export NIB_WMTS_TOKEN='your-token'` before `streamlit run …`.
3. **Or `.env` file** (persistent): copy `.env.example` → `.env`, set `NIB_WMTS_TOKEN=…` (gitignored); the annotator loads it via `python-dotenv` on startup.

**Cross-athlete km caveat:** Subject_A and Subject_B stream `course_km` can differ by ~280–350 m at the same geographic landmark. Compare halts by geography / Subject_A axis, not raw Subject_B km alone. See runbook § Cross-athlete alignment.

### Circle Test (geometry QC)

Verify **1:1 lon/lat aspect lock** on the topo basemap panel after chunk or slider changes. The Plotly telemetry stack uses `course_km` (not geographic axes) and is intentionally **not** 1:1.

1. Launch annotator with topo enabled (`contextily` installed, lat/lon in panel window).
2. Enable **Show topo basemap** for a 1 km chunk with visible switchbacks (e.g. gramstad `chunk_05` km 34–35).
3. **Visual check:** Trail bends and contour spacing should look geographically natural — not horizontally stretched or vertically squashed. A **metric scalebar** (bottom-left) should show a round length (e.g. 50 m, 100 m, 500 m) appropriate to the chunk width.
4. **Resize test:** Widen the browser to full screen — topo PNG stays square (centred `st.columns([1,2,1])`, CSS `aspect-ratio:1/1`, `object-fit:contain`, max 720 px). Profile chart stays fixed **800 px** wide (`use_container_width=False`); drag-zoom on `course_km` should persist across Streamlit reruns (`uirevision='constant'`). Plotly profile rows are **not** 1:1 (TI vs km units differ by design).
5. **Chunk hop:** Select a different triage chunk (or move km sliders). Basemap re-renders with new square bounds — repeat visual check.
6. **Optional CLI calibration:** `--lat-offset` / `--lon-offset` (degrees) shift panel GPS before render without breaking aspect lock:

```bash
streamlit run 04_Python_Scripts/spatial/hitl_annotator_app.py -- \
  --lat-offset 0.0 --lon-offset 0.0
```

7. **Headless smoke test** (import + safety gates, no Streamlit UI):

```bash
python3 04_Python_Scripts/spatial/hitl_annotator_app.py --import-test
python3 04_Python_Scripts/spatial/hitl_annotator_app.py --dry-run-test
```

Pass criteria: import test OK; dry-run overlap gate blocks intersecting span; non-overlapping append writes to `temp_test.json` only.

### 3 — Assign surface + friction span

Sidebar → **Lock span**:

| Field | Guidance |
|-------|----------|
| `course_km_start` / `course_km_end` | Metre-precise window on Subject_A `course_km`. Defaults to current view bounds — **narrow** to the transition you are locking. |
| `surface_class` | S1–S6 descriptive label (see [Class reference](#class-reference)). |
| `friction_tier` | F0–F4 **authority** label (see [Class reference](#class-reference)). Always set — required for TRF and dashboard F-tier edges. |
| `reason` | Short clinical rationale (field anchor, transition, seam from prior chunk). Stored in JSON. |

**Friction is authority; S-class is descriptive.** A gravel road can be S2/F1; chunky tractor gravel may be S2/F3. See `docs/friction_index_spec.md`.

### 4 — Save Lock

**Dry-run is default (v0.3.0).** Sidebar → **Dry-run Save Lock** stays checked for calibration and UI trust passes. Click **Save Lock** to preview the span without writing JSON. Uncheck dry-run only when ready to promote; a confirmation dialog still gates production writes.

Click **Save Lock** (primary sidebar button).

1. **Overlap guard** — if the span intersects any existing `operator_gold_spans[]` entry, an error banner appears and the write is blocked.
2. **Confirmation modal** — otherwise a dialog shows `course_km` window, `surface_class`, `friction_tier`, and target JSON filename. Click **Confirm write** to append or **Cancel** to abort.

The app calls `append_operator_gold_span()`:

- Reads the full terrain map JSON.
- **Appends** one object to `hitl.operator_gold_spans[]`.
- Writes pretty-printed JSON with trailing newline.

Success banner shows `S#/F# km start–end`. Footer info bar shows total `operator_gold_spans` count and `hitl.status`.

### 5 — Verify JSON and export PNG

See [Post-lock verification](#post-lock-verification).

---

## Class reference

### Surface classes (S1–S6)

Descriptive ontology for clustering and dashboard overlays. **Not** friction authority.

| Code | Label | TI band | Typical tread |
|------|-------|---------|---------------|
| **S1** | Asphalt | 0.85–1.15 | Sealed road, finish-band pavement |
| **S2** | Gravel | 0.90–1.20 | Hard-pack gravel, compacted forest road |
| **S3** | Grass or hard dirt | 1.05–1.45 | Dry slab, grass, compacted dirt tread |
| **S4** | Technical rock (medium) | 1.40–1.80 | Rooty / coarse stone trail, exposed bedrock steps |
| **S5** | Technical rock (difficult) | 1.80–2.60 | Loose mass, coarse ur, runnability collapse |
| **S6** | Bog (wet mud) | 2.00–4.50 | Deep bog, vacuum mud |

Source: `04_Python_Scripts/spatial/surface_ontology.py` · theory: `docs/theory.md` § terrain scale · `docs/master_plan.md` §4.

### Friction tiers (F0–F4)

**Operator gold authority** for ground truth, TRF, and Baseline TI calibration.

| Tier | Name | Expected TI | Runnable? | Examples |
|------|------|-------------|-----------|----------|
| **F0** | Neutral | 0.85–1.15 | Full run | Sealed asphalt |
| **F1** | Low | 0.90–1.20 | Full run | Hard-pack gravel road |
| **F2** | Moderate | 1.05–1.45 | Full run | Compacted dirt, grass/lyng |
| **F3** | High | 1.40–1.80 | Run with care | Chunky gravel, rooty trail, bedrock steps |
| **F4** | Severe | 1.80–4.50 | Walk / scramble | Loose scree, deep bog |

Full spec: [`docs/friction_index_spec.md`](friction_index_spec.md) §3.

**Common gramstad_band pairings:** S3/F2 (low-friction trail), S4/F3 (bedrock / technical), S2/F1 (hard-pack gravel), S6/F4 (bog).

---

## Calibration vs RED queue workflow

Strategic Command sequencing — validate tooling on a known chunk before high-stakes RED review.

| Phase | Target | Queue | Rationale |
|-------|--------|-------|-----------|
| **1 — Calibration** | `chunk_05` km 34–35 | GREEN (RPS ~0.36) | Partial prior gold + known narrative; validate UI trust |
| **2 — RED pivot** | Top RED chunk (`chunk_08` km 37–38, RPS ~0.82) | RED | Highest algorithmic + kinematic disagreement |

**Calibration checklist (`chunk_05`, km 34–35):**

| km | Feature | Expected class |
|----|---------|----------------|
| 34.0 | Seam from chunk_04 | S3/F2 continues |
| ~34.2 | Field anchor — compact runnable dirt | S3/F2 |
| ~34.60 | Trail → F4504 gravel (Gramstad farm) | S3/F2 ends; S2/F1 gravel downstream |
| ~34.64 | Drink CP halt | TRF exclusion 34.55–35.05 (`cp_halt`) — **not** an S-class downgrade |

**Micro-seam operator test (v0.3.0):** Launch annotator → triage **GREEN** → `chunk_05`. Hover km **34.64** — crosshair should read ~`34.641` km, TI ~3.x, class near **S2/F1** (Gramstad gravel band). Use **Set Start** / **Set End** + click to bracket the halt without writing JSON (dry-run on). CLI calibration probe:

```bash
python3 04_Python_Scripts/spatial/hitl_annotator_app.py --import-test
```

Reference PNG: `06_Visualizations/sut43_hitl/chunk_05_km34-35.png`.

**How to open calibration chunk in the annotator:** Triage filter → `GREEN` → select `chunk_05 km 34.0–35.0`. (No `--calibrate` CLI flag in the current app.)

**Do not auto-lock during calibration.** Review telemetry first; promote spans manually with **Save Lock**.

**After calibration sign-off:** Switch triage filter to `RED`, work top-ranked chunks, then re-run `hitl_chunk_triage.py` after major lock waves.

### Triage queue columns

`triage_queue_sut43.csv`:

| Column | Meaning |
|--------|---------|
| `chunk_id` | 1 km chunk label (`chunk_05`, etc.) |
| `km_start` / `km_end` | Review window |
| `A` | Algorithmic blindness (% metres HMM *p* < 0.70) |
| `B` | Kinematic divergence (% metres \|NTI_A − NTI_B\| ≥ 0.30) |
| `C` | Severity multiplier from TI p90 |
| `RPS` | `((0.6×A) + (0.4×B)) × (1 + C)` |
| `queue` | RED > 0.75 · YELLOW 0.40–0.75 · GREEN < 0.40 |

Regenerate: `python3 04_Python_Scripts/spatial/hitl_chunk_triage.py --km-start 29 --km-end 41`

Chunk coverage ledger: `ground_truth_review/chunk_priority.csv`.

---

## Annotator vs manual JSON editing

| Method | When to use |
|--------|-------------|
| **Streamlit annotator** (preferred) | Normal operator sessions; enforces append-only writes and required fields. |
| **Manual JSON append** | Batch scripts, recovery, or when Streamlit unavailable. Same schema as the app. |
| **validation_dashboard PNG only** | QC / export — does **not** write gold. |

### Manual append schema

Add **only** to the end of `hitl.operator_gold_spans[]`:

```json
{
  "course_km_start": 34.0,
  "course_km_end": 34.6,
  "surface_class": "S3",
  "friction_tier": "F2",
  "gold_source": "operator",
  "mode": "operator_gold",
  "locked_at": "2026-06-29",
  "reason": "Low-friction trail; field anchor ~34.2; seam from chunk_04"
}
```

Validate after edit:

```bash
python3 -m json.tool config/spatial_terrain_map_sut43.json > /dev/null
```

**TRF exclusions** (`hitl.trf_exclusions[]`) and **behavioral stops** (`hitl.behavioral_stops[]`) are **not** editable in the annotator — add via controlled JSON edit or scripts. CP halts are exclusions, not surface downgrades.

---

## Post-lock verification

After each lock session:

1. **JSON validity** — `python3 -m json.tool config/spatial_terrain_map_sut43.json > /dev/null`
2. **Append check** — New entry at end of `hitl.operator_gold_spans[]` with `mode: operator_gold`, `gold_source: operator`, `locked_at`, `friction_tier`.
3. **NTI gaps** (optional) — `python3 04_Python_Scripts/spatial/hitl_nti_consistency.py --apply-gaps` for the locked km window.
4. **PNG re-export** — Commit-ready QC artifact:

```bash
export MPLCONFIGDIR="${MPLCONFIGDIR:-$(pwd)/.mplconfig}"

python3 04_Python_Scripts/spatial/validation_dashboard.py \
  --terrain-map config/spatial_terrain_map_sut43.json \
  --panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet \
  --chunk-km 1 --chunk-index 5 \
  --output-dir 06_Visualizations/sut43_hitl \
  --verify-export
```

5. **Chunk notes** — Update `ground_truth_review/chunk_priority.csv` notes only after deliberate operator sign-off (not during calibration-only UI passes).

---

## What NOT to do

| Rule | Why |
|------|-----|
| **Do not edit or delete existing `operator_gold_spans[]` entries** | Append-only audit trail; downstream ML and TRF assume monotonic promotion. |
| **Do not splice spans into the middle of the JSON array** | Breaks review diffs and can orphan overlapping windows. |
| **Do not lock without `friction_tier`** | Dashboard shows amber edge; TRF cannot tier-baseline. |
| **Do not downgrade S-class for CP halts** | Use `hitl.trf_exclusions[]` with `exclusion_type: cp_halt`. |
| **Do not merge upstream draft into gramstad map** | km 22–29 → `spatial_terrain_map_sut43_upstream.json` only. |
| **Do not treat HMM row 4 or GMM draft as authority** | Operator gold overrides all ML hints. |
| **Do not commit `panel_1m.parquet` or `subject_registry.local.json`** | Local runtime / PII — gitignored by design. |

---

## Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| `Panel not found` on launch | Missing `panel_1m.parquet` | Rebuild spatial panel (`corridor_multi_fit.py` + align manifest). |
| `Terrain map not found` | Wrong sidebar path | Point to `config/spatial_terrain_map_sut43.json`. |
| Triage queue warning | CSV missing or stale | Run `hitl_chunk_triage.py`; or use km sliders. |
| Empty row 4 (HMM draft) | Draft parquet missing | Run `07_ML_Models/train_terrain_hmm.py` or ignore — not blocking for locks. |
| Topo basemap disabled | No `contextily` or no lat/lon in window | `pip install contextily`; confirm panel geography for selected km. |
| Satellite basemap blank | Missing `NIB_WMTS_TOKEN` | Generate token at [services.norgeibilder.no/token](https://services.norgeibilder.no/token); `export NIB_WMTS_TOKEN=…` or add to `.env` (see Basemap token steps above). Standard/greyscale work without token. |
| `Basemap tiles unavailable` | Network / tile server | Check `.tile_cache/` writable; retry; offline → disable topo, use PNG export. |
| Matplotlib cache errors | Headless env | `export MPLCONFIGDIR="$(pwd)/.mplconfig"`. |
| Save Lock error `course_km_end must exceed course_km_start` | Inverted or equal bounds | Set end > start. |
| Overlap blocked banner | New span intersects existing gold | Narrow window or pick adjacent unclaimed km |
| Duplicate overlapping spans | Re-locked same window | Overlap guard blocks write; inspect JSON if legacy duplicates exist |
| Streamlit usage-stats prompt | Default Streamlit telemetry | `--browser.gatherUsageStats false` or `.streamlit/config.toml`. |
| Crosshair frozen / click-to-set inactive | `streamlit-plotly-events` missing | `pip install streamlit-plotly-events` or `pip install -r requirements.txt` |
| Topo does not zoom with profile | Static matplotlib PNG by design | Zoom profile rows; use PNG export for full-chunk QC |

---

## Controls reference

| Control | Location | Purpose |
|---------|----------|---------|
| Data source paths | Sidebar | Panel, terrain map, triage CSV, HMM draft |
| Queue filter | Sidebar | RED / YELLOW / GREEN / ALL |
| Chunk selector | Sidebar | Sets view window from triage queue |
| Profile mode | Sidebar | Continuous TI gradient (dual-layer TI + HMM) vs Categorical F-tier / S-class validation |
| km sliders | Sidebar | Manual window when queue absent |
| Athlete overlay | Sidebar | Subject_A / Subject_B speed traces |
| Show topo basemap | Sidebar | Chunk-window reference map · **Basemap Layer** radio · **1:1 lon/lat aspect** · metric scalebar (bottom-left) · static (no Plotly zoom follow) |
| Map track: Operator gold | Sidebar | Topo track colours from `operator_gold_spans[]` (ON) vs GMM draft `segments[]` (OFF) |
| Basemap Layer | Sidebar | Standard topo (default) · Greyscale · Satellite orthophoto — Sjøkart/maritime blocked |
| Crosshair / Set Start / Set End | Sidebar + above chart | Hover readout · click-to-set lock bounds |
| Dry-run Save Lock | Sidebar | Preview append without JSON write (default on) |
| Lock span inputs | Sidebar | `course_km_start`, `course_km_end`, S-class, F-tier, reason |
| Save Lock | Sidebar | Dry-run preview or confirmation modal → append |
| Plotly chart | Main | TI (+ HMM dual-layer), NTI σ, speed, categorical strip · drag-zoom on `course_km` |
| Footer info | Main | Map filename, gold span count, `hitl.status`, panel row count |

---

## Known annotator gaps (2026-06-29)

| Gap | Workaround |
|-----|------------|
| Topo PNG does not follow Plotly zoom | Profile rows sync on `course_km`; re-open chunk or use PNG export for static QC |
| ~~Topo track showed GMM draft only~~ | **Resolved v0.3.1:** **Map track: Operator gold** toggle (default ON when gold spans in window) |
| No Plotly-native geo subplot with 1:1 lat/lon zoom sync | Matplotlib topo uses equal aspect; metre work on profile axis |
| No shift-click for lock bounds | **Set Start** / **Set End** + click |
| No `--calibrate chunk_05` CLI / URL presets | Triage queue → GREEN → `chunk_05`; or km sliders |
| No in-app gold span list / expander | Inspect JSON or export PNG |
| No TRF exclusion UI | Manual JSON edit to `hitl.trf_exclusions[]` |
| No lock-hint prefill from prior gold | Set lock fields manually from chunk notes / reference PNG |
| No chunk_priority.csv writer | Update CSV manually after sign-off |
| CLI lat/lon offset not editable in sidebar | Restart with `--lat-offset` / `--lon-offset` |

**Resolved in v0.2.0:** dual-layer TI + HMM visualization toggle · operator gold categorical overlay · pre-save confirmation modal · overlap guard · windowed panel load.

Folium basemap + richer chunk picker remain deferred per runbook. PNG export + Streamlit annotator meet current labeling cadence.

---

## Related artifacts

| Artifact | Path |
|----------|------|
| Terrain map (gramstad) | `config/spatial_terrain_map_sut43.json` |
| Terrain map (upstream) | `config/spatial_terrain_map_sut43_upstream.json` |
| Triage queue | `03_Processed_Data/spatial/sut43_terrain_ontology/ground_truth_review/triage_queue_sut43.csv` |
| Chunk priority ledger | `03_Processed_Data/spatial/sut43_terrain_ontology/ground_truth_review/chunk_priority.csv` |
| HITL status memo | `docs/memos/15_hitl_status_20260629.md` |
| Friction spec | `docs/friction_index_spec.md` |
| Dashboard runbook | `docs/hitl_dashboard_runbook.md` |

---

*Ghost Authority: Subject_A / Subject_B only in examples. No personal identifiers in committed artifacts.*
