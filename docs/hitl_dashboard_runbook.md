# HITL Dashboard Runbook

**Purpose:** Operator friction-first QC for `gramstad_band` (km 29–41 on SUT_43). The validation dashboard surfaces assigned gold, friction tiers (F0–F4), cluster TI rank, variance gaps, and topo context — not an ML labeling guide.

**Script:** `04_Python_Scripts/spatial/validation_dashboard.py`

---

## Prerequisites

| Item | Path / note |
|------|-------------|
| Panel parquet | `03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet` |
| Terrain map | `config/spatial_terrain_map_sut43.json` |
| Organiser GPX | `02_Raw_Data/organiser_gpx/COURSE_SUT43_official_2027.gpx` (auto when panel is SUT_43) |
| HITL sidecars (decision mode) | `hitl_v1_effective.parquet`, `hitl_agreement.parquet`, `fit_ti_clusters_Subject_*.parquet` beside panel |
| Network | Kartverket / OpenTopoMap / OSM tile fetch (cached under `.tile_cache/`) |
| Matplotlib cache | Set `MPLCONFIGDIR` to a writable dir (e.g. repo `.mplconfig/`) on headless runs |

---

## Commands

### Single chunk (decision mode, km window)

```bash
export MPLCONFIGDIR="${MPLCONFIGDIR:-$(pwd)/.mplconfig}"
mkdir -p "$MPLCONFIGDIR"

python3 04_Python_Scripts/spatial/validation_dashboard.py \
  --terrain-map config/spatial_terrain_map_sut43.json \
  --panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet \
  --chunk-km 1 \
  --chunk-index 4 \
  --output-dir 06_Visualizations/sut43_hitl \
  --verify-export
```

Writes `06_Visualizations/sut43_hitl/chunk_04_km33-34.png`.

### Bulk export (12 × 1 km chunks, km 29–41)

```bash
./04_Python_Scripts/spatial/export_hitl_chunks.sh
```

### Spine-panel cross-athlete export (race panel on ref_chainage_m)

Use when verifying per-subject NTI/speed overlays on the Subject_A race spine (Subject_A + Subject_B race streams):

```bash
./04_Python_Scripts/spatial/export_hitl_chunks.sh --spine-panel \
  --chunk-index 5 \
  --output 06_Visualizations/sut43_hitl/chunk_05_km34-35_spine.png
```

Or `SPINE_PANEL=1 ./04_Python_Scripts/spatial/export_hitl_chunks.sh --chunk-index 5 --output ...`.

Writes to `06_Visualizations/sut43_hitl_spine/` on bulk `--export-chunks`; single-chunk `--output` gets `_spine` suffix when `--spine-panel` is set.

Or manually:

```bash
python3 04_Python_Scripts/spatial/validation_dashboard.py \
  --terrain-map config/spatial_terrain_map_sut43.json \
  --panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet \
  --chunk-km 1 \
  --export-chunks \
  --output-dir 06_Visualizations/sut43_hitl \
  --verify-export
```

### Full-corridor debug (non-decision overlays)

```bash
python3 04_Python_Scripts/spatial/validation_dashboard.py \
  --terrain-map config/spatial_terrain_map_sut43.json \
  --panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet \
  --full-overlays \
  --with-map \
  --ti-draft
```

---

## Reading the dashboard (decision mode)

| Layer | Meaning |
|-------|---------|
| **Topo map** | Kartverket topo (OSM fallbacks). Track polylines use **GPX centerline** (`track_geo`), not panel GPS. Faint gray = athlete GPS spread. Decision mode draws **two parallel class-coloured tracks** on that centerline — wide assigned (−12 m perpendicular offset) and narrow ML (+12 m); on switchbacks they can look like misaligned doubles, not a basemap bug. |
| **Assigned strip** | S-class fill; **F-tier coloured edge** (F0–F4) on operator gold with `friction_tier`; label `S#/F#` on wide spans. Amber edge = operator gold without tier. |
| **ML strip** | Full-corridor GBM draft guide (diagnostic, not friction authority). |
| **Cluster TI rank** | Per-athlete `cluster_ti_rank` (0=low … 5=high); yellow edge = rank ≥ 4 review priority. |
| **Elevation / NTI** | Consensus NTI median ± σ; red spans = high cross-athlete variance (variance gap candidates). |
| **Variance gap** | Grey deferred spans in terrain map — do not assign friction until σ revisit. |

Gold edits: append to `hitl.operator_gold_spans[]` with `surface_class`, `friction_tier` (F0–F4), and `reason`. Re-export affected chunks after JSON save.

---

## Cross-athlete alignment caveat

Per-athlete FIT stream `course_km` can diverge by **~280–350 m** at the same geographic landmark (food CP, drink CP, stile) between Subject_A and Subject_B. UTM co-location confirms the same physical events (typically 1–12 m apart); only the stream km labels differ. Cross-athlete comparison on raw `course_km` does **not** achieve 1 m precision.

### Spine reprojection (step 1 — available)

Build canonical axis, then reproject aligned activities:

```bash
python3 04_Python_Scripts/spatial/build_reference_spine.py \\
  --manifest config/spatial_align_manifest_sut43.example.json

python3 04_Python_Scripts/spatial/reproject_to_spine.py \\
  --manifest config/spatial_align_manifest_sut43.example.json
```

Outputs: `reference_spine_1m.parquet`, `panel_race_1m_spine.parquet` (keyed on `ref_chainage_m`), per-activity `aligned_*_spine.parquet`, `reproject_spine_meta.json` with anchor validation.

| Context | Rule |
|---------|------|
| **Canonical axis** | `ref_chainage_m` on Subject_A race spine — operator gold stays on Subject_A `activity_course_km` |
| **Operator gold / HITL** | Lock on Subject_A panel km; **1:1 mapping** `ref_chainage_km == course_km` on spine (no span re-key required) |
| **Single-subject TRF** | OK on legacy `panel_1m.parquet` or `panel_race_1m_spine.parquet` |
| **Cross-athlete same-metre TRF** | `--cross-athlete` + `panel_race_1m_spine.parquet`; join on `ref_chainage_m` + `subject_id` |
| **Validation dashboard** | `--panel panel_race_1m_spine.parquet` — per-subject NTI overlays on ref_chainage axis |
| **Behavioral stop tags** | Anchor to geography (UTM / pin / Subject_A panel window) — not Subject_B stream km alone |
| **TRF exclusions** | `hitl.trf_exclusions[]` on Subject_A `course_km` — `exclusion_type`, `subject_scope`, optional `anchor_id`; masked in `compute_training_residual.py` (cells + cross-athlete paired stats) |

Each `trf_exclusions` entry: `course_km_start`, `course_km_end`, `exclusion_type` (`cp_halt` | `co_wait` | `single_athlete_asymmetry` | `behavioral_stop`), `subject_scope` (`both` | `Subject_A_only`), clinical `reason`. Companion tags live in `hitl.behavioral_stops[]`.

### Step 2 — spine-keyed consumers (available)

```bash
# Cross-athlete TRF sanity check (gramstad_band km 29–41):
python3 04_Python_Scripts/spatial/compute_training_residual.py \\
  --cross-athlete \\
  --panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_race_1m_spine.parquet \\
  --terrain-map config/spatial_terrain_map_sut43.json

# HITL dashboard with cross-athlete profile overlays:
python3 04_Python_Scripts/spatial/validation_dashboard.py \\
  --terrain-map config/spatial_terrain_map_sut43.json \\
  --panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_race_1m_spine.parquet \\
  --chunk-km 2 --chunk-index 1 --with-map --decision-mode

# Training tiles onto spine:
python3 04_Python_Scripts/spatial/reproject_to_spine.py \\
  --manifest config/spatial_align_manifest_sut43.example.json \\
  --session-type all
```

Outputs include `cross_athlete_trf_summary.json`, `panel_training_1m_spine.parquet`, per-activity `aligned_*_spine.parquet`.

**Training spine coverage QC:** `python3 04_Python_Scripts/spatial/check_spine_coverage.py` — reports per-activity and union `ref_chainage_m` coverage on km 29–41. Full-band field protocol: `docs/fit_ingest_workflow.md` § Full-band training traverse protocol.

### Deferred (step 3+)

**Related:** `docs/training_residual_framework.md` §6 (comparison modes, cross-athlete paired)

---

## Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| Grey map, no tiles | Network block or contextily miss | Check stderr `WARN map basemap missing`; confirm `.tile_cache/` writable; retry (3× backoff + OSM fallback built in). |
| Track offset from basemap | Panel GPS used instead of GPX | Should not occur when GPX exists — all map polylines use `track_geo`. Check stderr geo mismatch stats (`WARN geo mismatch` if median > 15 m). |
| Corrupt / zero-byte PNG | Interrupted save | Atomic write (`*.tmp` → rename) + `--verify-export` (PIL verify, non-zero exit). Delete partial file and re-run chunk. |
| Stale preview in IDE | Cached PNG mtime | Re-export chunk; hard-refresh preview. |
| Missing F-tier edge | Span lacks `friction_tier` in JSON | Add `friction_tier` to `operator_gold_spans[]` entry; re-export. |

---

## Ghost Authority

Committed artifacts use **Subject_*** identifiers and **Dr. Anatomy Pace** laboratory framing only. No personal names or private training references in dashboard titles, stderr, or exported PNG metadata.

**Related:** `docs/friction_index_spec.md` · `docs/training_residual_framework.md`

---

## Sector 2 bootstrap checklist — `dale_paradisskaret_upstream` (km 22–29)

**Status (2026-06-29):** Machine draft generated. Sector 1 (`gramstad_band` km 29–41) remains the locked operator-gold reference.

**Sector bounds:** Subject_A / Subject_B SUT43_20260418 stream axis **km 22.0–29.0** (upstream of gramstad_band seam @ km 29.0). Registry: `config/spatial_terrain_sectors_sut43.json`.

### Upstream draft vs operator gold (gramstad_band)

| Aspect | `dale_paradisskaret_upstream` (km 22–29) | `gramstad_band` (km 29–41) |
|--------|------------------------------------------|----------------------------|
| Terrain map file | `config/spatial_terrain_map_sut43_upstream.json` | `config/spatial_terrain_map_sut43.json` |
| Authority | **GMM cluster draft** (`segments[]`, `source: cluster`) | **Operator gold** (`hitl.operator_gold_spans[]` + friction locks) |
| Friction tiers (F0–F4) | **None** — S-class only until HITL | Locked on promoted spans per `docs/friction_index_spec.md` |
| HITL status | `hitl.status: draft` | `hitl.status: review` with 31+ operator gold spans |
| Seam @ km 29.0 | Draft ends; no write into gramstad_band file | Operator gold from `chunk_00` applies downstream |
| Dashboard overlay | `gmm_draft` + TI-band `ti_draft_segments[]` + v2 majority vote | Operator gold + accept-draft policies + ML guide |

**Do not merge** upstream draft into `spatial_terrain_map_sut43.json` without operator sign-off — that file holds gramstad_band locks.

| Step | Action | Artifact / command |
|------|--------|-------------------|
| 1 | Confirm sector bounds + anchor crosswalk | `config/spatial_terrain_sectors_sut43.json` · memo 13 bridge table |
| 2 | Expand align window + rebuild panel | `corridor_multi_fit.py --manifest config/spatial_align_manifest_sut43.example.json` with `km_analysis_window: [22.0, 41.0]` |
| 3 | Extend reference spine | `python3 04_Python_Scripts/spatial/build_reference_spine.py --manifest config/spatial_align_manifest_sut43.example.json --km-start 22 --km-end 41` |
| 4 | Reproject race + training to spine | `reproject_to_spine.py --manifest … --session-type all` |
| 5 | Generate terrain map draft (ML clusters) | `python3 04_Python_Scripts/spatial/build_upstream_terrain_draft.py --write` → `config/spatial_terrain_map_sut43_upstream.json` |
| 5b | ML feature matrix (upstream window) | `python3 04_Python_Scripts/spatial/terrain_ml_features.py --km-start 22 --km-end 29 --majority 03_Processed_Data/spatial/sut43_terrain_ontology/upstream_draft/hitl_v2_majority.parquet --output 03_Processed_Data/spatial/sut43_terrain_ontology/upstream_draft/ml_features_1m.parquet` |
| 6 | Export first HITL chunk | `build_upstream_terrain_draft.py --write --export-chunk-index 1` or `validation_dashboard.py --terrain-map config/spatial_terrain_map_sut43_upstream.json --km-start 22 --km-end 29 --chunk-km 1 --chunk-index 1 --output 06_Visualizations/sut43_hitl_upstream/chunk_u01_km23-24.png --ti-draft --majority-draft` |
| 7 | Operator gold + friction tiers | Append to `hitl.operator_gold_spans[]` in **`spatial_terrain_map_sut43_upstream.json`** (not gramstad_band file) |
| 8 | TRF exclusions | Tag CP halts / co-wait on Subject_A `course_km` before cross-athlete TRF |
| 9 | Cross-athlete TRF | `compute_training_residual.py --cross-athlete` on extended `panel_race_1m_spine.parquet` |
| 10 | Update chunk priority | `ground_truth_review/chunk_priority_dale_upstream.csv` |

**HITL chunk plan (1 km):** `chunk_u00` km 22–23 … `chunk_u06` km 28–29. Priority queue in `chunk_priority_dale_upstream.csv`.

**Recommended first operator session:** **`chunk_u01` (km 23–24)** — geographic Dale coastal anchor @ km 23.5; bridge crosswalk to SUT_160 km ~141.5; race telemetry present on both athletes. Alternative entry: **`chunk_u00` (km 22–23)** for sector boundary at bridge window start (SUT_160 Dale aid @ SUT_43 km 22.43).

**Training TRF caveat:** No continuous training tile covers km 22–24. `Gramstad_runden_reverse_20250430` begins @ km 24.33. Race-only panel OK for HITL; training TRF deferred until upstream training traverse recorded.

**Not in scope for Sector 2 bootstrap:** SUT_160 bridge panel (`dale_to_paradisskaret_stress_test`) — separate axis; early-lap `dalevatn_band` km 13–25 (superseded ontology, different geography).

---

## Interactive HITL annotator (Streamlit)

**Script:** `04_Python_Scripts/spatial/hitl_annotator_app.py`

Local Plotly profile + operator gold writer. Promotes spans to `hitl.operator_gold_spans[]` with `mode: operator_gold`, `gold_source: operator`, `locked_at`, and friction tier. Does **not** replace PNG export workflow — use both for in-browser zoom/pan and committed lock promotion.

```bash
pip install streamlit plotly   # or: pip install -r requirements.txt

streamlit run 04_Python_Scripts/spatial/hitl_annotator_app.py
```

| Control | Purpose |
|---------|---------|
| View sliders | Plotly zoom window (`course_km_start` / `course_km_end`) |
| Lock span inputs | Metre-precise gold span to append |
| surface_class / friction_tier | S1–S6 · F0–F4 |
| Save Lock | Appends to terrain map JSON (sidebar path configurable for upstream `spatial_terrain_map_sut43_upstream.json`) |
| Athlete overlay | Subject_A / Subject_B speed + NTI traces |

**Upstream sector:** set terrain map path to `config/spatial_terrain_map_sut43_upstream.json` in the sidebar before locking km 22–29 spans. Keep gramstad_band locks in `spatial_terrain_map_sut43.json` only.

---

## HMM draft triage (management-by-exception)

Train draft class predictions on **12 km operator gold** (km 22–34), then rank unreviewed chunks via **Review Priority Score (RPS)**:

```bash
# HMM draft (does not replace operator gold)
python3 07_ML_Models/train_terrain_hmm.py

# RPS triage queue — gramstad_band default km 29–41
python3 04_Python_Scripts/spatial/hitl_chunk_triage.py --km-start 29 --km-end 41
```

**RPS formula (per 1 km chunk):**

| Index | Meaning | Computation |
|-------|---------|-------------|
| **A** | Algorithmic blindness | % metres where HMM max-state probability *p* < 0.70 |
| **B** | Kinematic divergence | % metres where \|NTI_Subject_A − NTI_Subject_B\| ≥ 0.30 |
| **C** | Severity multiplier | `min(1, max(0, (TI_p90 − 1.0) / 2.5))` — TI ≥ 3.5 → 1.0 |

`RPS = ((0.6 × A) + (0.4 × B)) × (1 + C)`

**Queue bands:** RED RPS > 0.75 · YELLOW 0.40–0.75 · GREEN < 0.40

Chunk boundaries are read from `ground_truth_review/chunk_priority.csv` when present.

**HMM over-smoothing gates** (printed when draft parquet exists): MVL ≥ 15 m on S5/S6 runs · S5/S6 volume within ±10% of TI ≥ 2.5 spike metres · 2–8 class switches/km.

Outputs: `07_ML_Models/terrain_hmm_sut43_draft_predictions.parquet`, `ground_truth_review/triage_queue_sut43.csv` (columns: `chunk_id`, `km_start`, `km_end`, `A`, `B`, `C`, `RPS`, `queue`).

---

## Deferred — full private web app

**Status (2026-06-29):** Streamlit annotator MVP shipped (profile + gold writer). Folium basemap + chunk picker remain deferred — PNG export via `export_hitl_chunks.sh` still recommended for topo QC.

**Not needed while:** Streamlit annotator + PNG export meet labeling cadence.
