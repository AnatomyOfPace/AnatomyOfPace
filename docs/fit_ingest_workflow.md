# Garmin `.fit` Ingest Workflow (Phase B)

Clinical English · Ghost Authority safe · local paths only.

The laboratory ingests Garmin `.fit` telemetry through a three-tier pipeline aligned with `docs/master_plan.md` §5 (Mikro tier) and the Phase B roadmap in `docs/memos/terrain_ml_roadmap.local.md`.

## Data layout (gitignored)

| Path | Purpose |
|------|---------|
| `02_Raw_Data/donors/{donor_id}/` | Canonical washed-source `.fit` copies (Subject_A, Subject_B, Reference_Elite_*) |
| `02_Raw_Data/inbox/strava/{donor_id}/` | Pre-clip Strava export inbox |
| `03_Processed_Data/micro/{donor_id}/activity_{id}.parquet` | Normalized ActivityFrame (native Hz) |
| `03_Processed_Data/spatial/{corridor_id}/panel_1m.parquet` | Multi-athlete 1 m course grid |
| `03_Processed_Data/spatial/{corridor_id}/fit_panel_1m.parquet` | Alias of `panel_1m` when built from FIT wash |
| `03_Processed_Data/spatial/{corridor_id}/ml_features_1m.parquet` | Per-metre ML feature matrix (join key: `course_m`) |

**Never commit** raw `.fit` files or paths containing personal identifiers. Use `Subject_A`, `Subject_B`, `Reference_Elite_D` in manifests and docs.

### Canonical donor naming (SUT_43)

| Rule | Example |
|------|---------|
| One canonical `.fit` per donor under `donors/{Subject_*}/` | `02_Raw_Data/donors/Subject_A/SUT43_20260418.fit` |
| Filename pattern | `SUT43_{race_date_or_strava_id}.fit` — **no real names**, no `_Garmin_` suffix |
| Strava activity alias (optional) | `ln -sf SUT43_20260418.fit activity_19000570862.fit` |
| Root `02_Raw_Data/*.fit` inbox | Legacy exports; **`donors/` is canonical** for wash/panel. Byte-identical root copies may be moved to `02_Raw_Data/_archive/`. |

Subject_A race-day: `SUT43_20260418.fit` + `activity_22575150868.fit` → same file.  
Subject_B race-day: `SUT43_20260418.fit` + `activity_19000570862.fit` → same file (full HR+cadence; do **not** use archived `activity_18162306249.fit`).

## ActivityFrame schema (`wave2_v1`)

Core telemetry plus optional running dynamics when the device exports them:

| Column | Unit | Notes |
|--------|------|-------|
| `timestamp`, `elapsed_s` | UTC / s | Record time |
| `distance_m`, `course_km` | m / km | Stream distance; `course_km` from stream (SUT_43) or GPX snap (SUT_160) |
| `latitude`, `longitude` | deg | WGS84 |
| `altitude_m` | m | Enhanced barometric preferred |
| `heart_rate` | bpm | NaN when absent |
| `cadence_spm`, `speed_mps` | spm / m/s | Enhanced speed preferred |
| `grade`, `grade_pct`, `pace_gap_flat`, `ti` | — | Added by `--enrich-ti` (Minetti GAP engine) |
| `vertical_oscillation_mm` | mm | Running dynamics |
| `step_length_m` | m | From FIT step_length (mm → m) |
| `stance_time_ms` | ms | Ground contact time |
| `power_w` | W | When power meter present |

Privacy: external donor files are clipped ±500 m at wash time (`donor_io.apply_privacy_clip`).

**Partial corridor runs (Subject_* training tiles):** If the activity ends inside the study window (e.g. gramstad_band km 29–33), the default tail clip removes all corridor data. Pass **`--no-privacy-clip`** on wash for operator-owned partial tiles; full race files keep the clip unless debugging.

**Reverse training tiles:** Set manifest `"direction": "reverse"` when the lap traverses upstream on the race course axis (e.g. bedrock F3 km 31.0–32.0); GPX snap keeps course metres fixed — grade bins flip vs race-forward on the same span.

```bash
python3 04_Python_Scripts/15_fit_micro_wash.py \
  --donor Subject_A \
  --activity SUT43_20260418 \
  --fit 02_Raw_Data/donors/Subject_A/SUT43_20260418.fit \
  --race SUT_43 \
  --project-course \
  --enrich-ti
```

SUT_43 uses **stream-distance** course axis (`course_project.py` → `distance_m / 1000`), not organiser GPX snap.

## Step 2 — Align to 1 m panel

```bash
python3 04_Python_Scripts/spatial/spatial_align.py \
  --manifest config/spatial_align_manifest_sut43.example.json \
  --enrich-if-needed
```

Output: `03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet` — long format with `donor_id`, `activity_id`, `course_m`, telemetry columns.

## Step 3 — ML features (optional)

```bash
python3 04_Python_Scripts/spatial/terrain_ml_features.py
```

Join key for downstream models: **`course_m`** (integer metres along course axis).

## End-to-end (recommended)

```bash
python3 04_Python_Scripts/16_fit_corridor_pipeline.py \
  --manifest config/spatial_align_manifest_sut43.example.json \
  --wash-all \
  --rebuild-panel \
  --rebuild-ml-features
```

This re-washes local `.fit` files, rebuilds the gramstad_band panel (km 29–41), writes `fit_panel_1m.parquet`, and refreshes `ml_features_1m.parquet` with HR and running-dynamics medians when present.

## SUT_43 manifest activities

| Donor | Activity ID | Canonical FIT | Notes |
|-------|-------------|---------------|-------|
| Subject_A | `SUT43_20260418` | `donors/Subject_A/SUT43_20260418.fit` | SUT_43 race 2026-04-18 |
| Subject_B | `19000570862` | `donors/Subject_B/SUT43_20260418.fit` | SUT_43 race-day — full HR+cadence (Strava 19000570862) |

Reference_Elite_D SUT_160 wash is deferred to Phase D (`config/spatial_align_manifest.example.json`).

## Full-band training traverse protocol (`gramstad_band` km 29–41)

**Goal:** One continuous Subject_A training activity on SUT_43 race tread covering the full `gramstad_band` analysis window (km 29.0–41.0 on `ref_chainage_m`). Partial reverse tiles currently union to ~43% spine coverage — insufficient for meter-by-meter TRF on the downstream tail and Vassfjellet band.

**Manifest slot:** `pending_activities[]` → `gramstad_band_full_traverse_20260628` in `config/spatial_align_manifest_sut43.example.json`.

### Field recording spec

| Item | Requirement |
|------|-------------|
| **Course** | SUT_43 organiser tread only — same physical corridor as race-day Subject_A spine |
| **Direction** | **Reverse** (upstream on course axis: start downstream near km 41, finish upstream near km 29) — matches existing partial tiles and preserves grade semantics vs race-forward on identical course metres |
| **Span** | Continuous traverse km 29.0–41.0 — no off-corridor detours (Lifjell loop geometry fails spine QC) |
| **Device** | Garmin with barometric altimeter + HR; 1 s recording; GLONASS/Galileo enabled |
| **Pace** | Steady training effort — avoid long halts; tag intentional CP stops in HITL `trf_exclusions[]` after ingest |
| **Privacy** | Operator-owned tile — wash with **`--no-privacy-clip`** |

**Anchors to verbalise at start/finish (course-direction):**

- **Downstream start** (~km 41): Alsvik asphalt tail / Paradisskaret sector
- **Upstream finish** (~km 29): Gramstad approach from Revhol sector
- **Mid-band knots:** food CP ~km 30.52, drink CP ~km 34.64, Paradisskaret stile ~km 39.14

### Post-record ingest (operator checklist)

1. Copy FIT → `02_Raw_Data/donors/Subject_A/gramstad_band_full_traverse_20260628.fit`
2. Wash micro Parquet:

```bash
python3 04_Python_Scripts/15_fit_micro_wash.py \
  --donor Subject_A \
  --activity gramstad_band_full_traverse_20260628 \
  --fit 02_Raw_Data/donors/Subject_A/gramstad_band_full_traverse_20260628.fit \
  --race SUT_43 \
  --project-course \
  --enrich-ti \
  --no-privacy-clip
```

3. Promote manifest row: move `gramstad_band_full_traverse_20260628` from `pending_activities[]` to `activities[]` in `config/spatial_align_manifest_sut43.example.json` (or local copy).
4. Rebuild panel + spine:

```bash
python3 04_Python_Scripts/16_fit_corridor_pipeline.py \
  --manifest config/spatial_align_manifest_sut43.example.json \
  --rebuild-panel --rebuild-ml-features

python3 04_Python_Scripts/spatial/build_reference_spine.py \
  --manifest config/spatial_align_manifest_sut43.example.json

python3 04_Python_Scripts/spatial/reproject_to_spine.py \
  --manifest config/spatial_align_manifest_sut43.example.json \
  --session-type all
```

5. **QC gates** (must pass before TRF / HITL promotion):

```bash
python3 04_Python_Scripts/spatial/check_spine_coverage.py \
  --manifest config/spatial_align_manifest_sut43.example.json
```

| Gate | Pass criterion |
|------|----------------|
| Union coverage | ≥ 95% unique `ref_chainage_m` on km 29–41 |
| Cross-track | Per-activity `cross_track_m` median ≤ 30 m |
| Continuity | No major gap ≥ 200 m except tagged TRF exclusions |

6. Optional: refresh TRF and HITL exports per `docs/hitl_dashboard_runbook.md`.

### Activities that do **not** close the gap

| Activity | Why excluded |
|----------|--------------|
| `hommersak_storaberget_20250628` | Early-lap tile km 1.85–8.0 — zero `gramstad_band` overlap |
| `gramstad_lifjell_20250625` | Off-corridor GPS (median cross_track 172 m) — spine QC fail |
| `LFI_20260606` | Lysefjorden Inn course axis — not SUT_43 stream/GPX snap |
| `SUT43_20260418` (race) | Full km 29–41 on spine — **race** session; TRF training panel requires dedicated training traverse |

Partial tiles (`SUT43_sector_31-32_reverse_20260627`, `Gramstad_runden_reverse_20250430`, `gramstad_bedrock_rain_20260327`) remain valid for bedrock co-wait QC and segment overlap but cannot be stitched into continuous full-band coverage.

## Next steps (Phase B remainder)

- Feature ablation: vote-only vs FIT telemetry vs full matrix on LOOCV
- Per-athlete HR iso-effort TI (`fit_micro/effort_paradox.py`)
- Full-course SUT_43 stretch (km 0.5–42.5) after gramstad_band sector lock
- Reference_Elite_D `.fit` → SUT_160 Dale–Alsvik corridor (Phase D)

## Tverrfjell local loop (map-first HITL, not SUT_43)

**Geography:** Uskedalen, Kvinnherad, Vestland (Hardanger / Sunnhordland). **Not Rogaland.** SUT_43 (Sandnes) is a separate county ~120 km south — the Tverrfjell pipeline uses FIT stream distance only; never snap to SUT GPX or write into SUT terrain maps.

| Step | Command |
|------|---------|
| Place FIT | `02_Raw_Data/donors/Subject_A/Tverrfjell_20260704.fit` (rename from legacy `Tverrfjell_*_20260704.fit`) |
| Bootstrap | `python3 04_Python_Scripts/spatial/bootstrap_tverrfjell_course.py` |
| Label | `gold_span_editor.py add --terrain-map config/spatial_terrain_map_tverrfjell.json ...` |
| Dashboard PNGs | `./04_Python_Scripts/spatial/export_hitl_chunks_tverrfjell.sh` → `06_Visualizations/tverrfjell_hitl/chunk_t*.png` (24 × 1 km, km 0–23.549) |

Configs: `config/spatial_align_manifest_tverrfjell.json`, `config/spatial_terrain_map_tverrfjell.json`.

## Klepp Runde local loop (map-first HITL)

**Geography:** Klepp — a very local place name in **Uskedalen** (Kvinnherad, Vestland), near Tverrfjell. Not Klepp municipality (Rogaland/Jæren). Map-first FIT stream axis — not SUT_43 organiser GPX.

Expected GPS centroid ~59.9°N, ~5.9°E (Uskedalen band). A centroid near 58.8°N indicates the Rogaland homonym, not this course.

### Avoiding Tverrfjell pitfalls

| Tverrfjell issue | Klepp safeguard |
|------------------|-----------------|
| Wrong axis / SUT_43 geography | `verify_klepp_runde_hitl_exports.py` + `preflight_map_first_course.py` |
| Lost `operator_gold_spans` on `git restore` | Backup after each session: `cp config/spatial_terrain_map_klepp_runde.json config/spatial_terrain_map_klepp_runde.gold_local.json` (gitignored copy — never rely on committed JSON for gold). **Recover:** `gold_span_editor.py restore --terrain-map config/spatial_terrain_map_klepp_runde.json` if `.gold_local.json` exists; pipelines also auto-read `.gold_local.json` when the tracked map has fewer spans. |
| ML strip empty | Export script auto-loads `klepp_runde_ml_predictions.parquet` when model exists — **train before final PNG export** |
| Locomotion strip missing | Export auto-generates `locomotion_mode_1m.parquet` |
| Wrong training panel (SUT_43) | Always pass `--terrain-map config/spatial_terrain_map_klepp_runde.json` to `build_gold_training_set.py` |
| Stale PNGs after code pull | Re-run `export_hitl_chunks_klepp_runde.sh` after `git pull` |
| Weak TI / zero speed in panel | Bootstrap runs `--enrich-ti`; preflight warns if telemetry coverage is low |

### Ordered workflow

| Step | Command |
|------|---------|
| Pull branch | `git pull origin cursor/klepp-runde-bootstrap-0c6a` |
| Place FIT | `02_Raw_Data/donors/Subject_A/Klepp_Runde_*.fit` |
| Bootstrap | `python3 04_Python_Scripts/spatial/bootstrap_klepp_runde_course.py --fit <path>` |
| Preflight | `python3 04_Python_Scripts/spatial/preflight_map_first_course.py --terrain-map config/spatial_terrain_map_klepp_runde.json` |
| Label + backup | `gold_span_editor.py add ...` then `cp ...gold_local.json` |
| Train ML | `build_gold_training_set.py` → `train_gold_suggester.py` with `--metadata-out ...klepp_runde_v0_metadata.json` |
| Export PNGs | `./04_Python_Scripts/spatial/export_hitl_chunks_klepp_runde.sh` |

**Quick start (bootstrap + PNGs + labeling hints):**

```bash
./04_Python_Scripts/spatial/start_klepp_annotation.sh --fit 02_Raw_Data/donors/Subject_A/YOUR_Klepp_Runde.fit
```

Configs: `config/spatial_align_manifest_klepp_runde.json`, `config/spatial_terrain_map_klepp_runde.json`.
