# Mid-Course Panel Ingest Scope (km 8.0–22.0)

**Laboratory:** The Anatomy of Pace · **Authority:** Dr. Anatomy Pace  
**Date:** 2026-07-01 · **Phase:** F1 mid-course bridge  
**Status:** **INTERIM DUAL-ATHLETE** — `panel_midcourse_1m.parquet` has Subject_A + Subject_B; Subject_A km 8–22 telemetry is stitch-interpolated pending washed micro

---

## Problem

SUT_43 panel coverage today is discontinuous on the race axis:

| Window | km | Panel artifact | Race rows |
|--------|-----|----------------|-----------|
| Phase E start | 0.5–8.0 | `panel_start_race_1m.parquet` | Subject_A + Subject_B |
| **Gap** | **8.0–22.0** | `panel_midcourse_1m.parquet` | Subject_A + Subject_B *(Subject_A interpolated)* |
| Dale upstream + gramstad | 22.0–41.0 | `panel_race_1m.parquet` / `panel_1m.parquet` | Subject_A + Subject_B |

Until km 8–22 is filled, full-lap TI/TPR analysis and continuous sparse-gold ML training are blocked.

---

## Sector definition

| Field | Value |
|-------|-------|
| **sector_id** | `dalevatn_midcourse` |
| **km window** | 8.0–22.0 (viewport 7.5–22.5) |
| **Terrain map** | `config/spatial_terrain_map_sut43_midcourse.json` |
| **Chunk plan** | `chunk_m00`–`chunk_m13` (14 × 1 km) |
| **Upstream seam** | km 8.0 — Phase E `leg_a_technical` Noredalen opening descent terminus |
| **Downstream seam** | km 22.0 — locked `dale_paradisskaret_upstream` chunk_u00 |

### Geographic anchors (do not confuse)

| Anchor | km | Role |
|--------|-----|------|
| Dale **timing index** | 8.1 | Organiser CP on shared start — **not** coastal Dale |
| Dalsnuten timing index | 10.37 | Organiser CP |
| Bjørndalsfjellet timing index | 14.39 | Organiser CP |
| Mattirudla timing index | 15.67 | Organiser CP |
| Lifjell **geographic summit** | ~18.0 | Garmin marker 18 — **not** Lifjell timing CP @ 5.87 |
| Coastal Dale (geographic) | ~23.5 | In upstream sector — **not** km 8.1 |

---

## Seed ontology (machine draft)

Six seed segments in `spatial_terrain_map_sut43_midcourse.json`:

1. km 8.0–10.4 — Noredalen valley floor (S3/F2)
2. km 10.4–14.0 — Kyllesvatnet / upland trail (S3/F2)
3. km 14.0–17.0 — Dalevatn descent Case Study #002 (S4/F3)
4. km 17.0–18.5 — Lifjell summit approach (S4/F3)
5. km 18.5–20.0 — Mid-race steep descent (S5/F4)
6. km 20.0–22.0 — Late-lap approach to upstream seam (S3/F2)

Operator gold: **not started**. Follow Tier 1–3 ladder in `docs/memos/18_gold_hitl_low_hanging_fruit.md`.

---

## Build pipeline

### Quick scaffold (stream axis, no spine extension)

```bash
python3 04_Python_Scripts/spatial/realign_subject_a_race.py   # Subject_A full-lap stitch
python3 04_Python_Scripts/spatial/build_midcourse_panel.py
```

Reads aligned race parquets, filters `activity_course_km` / `course_km` to km 8–22, writes:

- `03_Processed_Data/spatial/sut43_terrain_ontology/panel_midcourse_1m.parquet`
- `03_Processed_Data/spatial/sut43_terrain_ontology/panel_midcourse_meta.json`

### Production path (dual-athlete + spine)

1. Wash race micro: `15_fit_micro_wash.py` for Subject_A + Subject_B `SUT43_20260418`
2. `corridor_multi_fit.py --km-start 8.0 --km-end 22.0 --project-course`
3. `build_reference_spine.py --km-start 8 --km-end 41`
4. `reproject_to_spine.py --session-type race`
5. Merge `panel_start` + `panel_midcourse` + `panel_race` → unified `panel_1m.parquet`
6. `terrain_map_gen.py` on mid-course window
7. `hitl_chunk_triage.py` with `chunk_priority_midcourse.csv`

---

## Current blockers (2026-07-01)

| Blocker | Mitigation |
|---------|------------|
| Subject_A race spine clips km 22–41 only | **Mitigated (interim):** `realign_subject_a_race.py` stitches start + interpolated gap + spine |
| Subject_A race micro not in cloud workspace | Operator must wash from canonical `.fit` locally; replace interpolated km 8–22 telemetry |
| `reference_spine` window still km 22–41 | **Mitigated:** extended to km 8–41 via `build_reference_spine.py` (km 8–22 GPS interpolated) |

**Interim:** `realign_subject_a_race.py` + `build_midcourse_panel.py` populate **dual-athlete** race rows km 8–22 on stream axis. Subject_A gap telemetry is linearly interpolated — not operator gold.

---

## Success criteria

- [x] `panel_midcourse_1m.parquet` with Subject_A + Subject_B race rows km 8.0–21.999 *(Subject_A interpolated)*
- [ ] `check_spine_coverage.py` union ≥ 99% on km 8–22 after spine reproject *(spine extended km 8–41; reproject pending)*
- [ ] `hitl_chunk_triage.py` queue generated for `chunk_m00`–`chunk_m13`
- [ ] Seam QC: km 8.0 matches Phase E last metre; km 22.0 abuts upstream chunk_u00

---

## Related artifacts

| File | Purpose |
|------|---------|
| `config/spatial_align_manifest_sut43.example.json` → `phase_f_midcourse` | Manifest block + checklist |
| `config/spatial_terrain_sectors_sut43.json` | Sector registry entry |
| `04_Python_Scripts/spatial/realign_subject_a_race.py` | Subject_A full-lap stitch (start + gap + spine) |
| `04_Python_Scripts/spatial/build_midcourse_panel.py` | Mid-course panel builder |
| `ground_truth_review/chunk_priority_midcourse.csv` | HITL chunk ledger (pending gold) |

---

*Internal memo — not public Anatomy of Pace copy.*
