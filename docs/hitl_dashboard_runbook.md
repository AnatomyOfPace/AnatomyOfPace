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

## Deferred — private web app (evaluate later)

**Status (2026-06-28):** Deferred. CLI dashboard + PNG export is the production HITL path for now.

**Re-evaluate when:** (a) chunk navigation via Preview feels too slow for daily labeling, (b) operator wants in-browser strip/map without re-export, or (c) two+ operators need shared QC view.

**If built:** prefer local **Streamlit read-only MVP** first (chunk picker, profile, F-tier strips, folium map) — reuse `panel_1m.parquet` + `spatial_terrain_map_sut43.json`; defer in-app gold writer until F-tier schema stable on km 29–41. Keep localhost-only; no public deploy.

**Not needed while:** `./04_Python_Scripts/spatial/export_hitl_chunks.sh` + runbook workflow meets labeling cadence.
