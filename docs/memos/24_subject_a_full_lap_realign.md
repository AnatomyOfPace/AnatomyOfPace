# Subject_A Full-Lap Realign (Stream Stitch)

**Laboratory:** The Anatomy of Pace · **Authority:** Dr. Anatomy Pace  
**Date:** 2026-07-01 · **Phase:** F1 mid-course bridge  
**Status:** **INTERIM** — dual-athlete `panel_midcourse_1m.parquet` unlocked; gap telemetry interpolated

---

## Problem

Subject_A race alignment existed only as disjoint artifacts:

| Segment | km | Source |
|---------|-----|--------|
| Phase E start | 0.5–8.0 | `panel_start_race_1m.parquet` |
| **Gap** | **8.0–22.0** | *(missing)* |
| Spine | 22.0–41.0 | `aligned_Subject_A_SUT43_20260418_race_spine.parquet` |

`build_midcourse_panel.py` could not extract Subject_A rows in km 8–22, blocking dual-athlete HITL scaffold.

---

## Solution

`04_Python_Scripts/spatial/realign_subject_a_race.py` stitches:

1. **Start** — Phase E stream panel (km 0.5–8.0)
2. **Gap** — linear interpolation km 8.001–21.999 between nearest finite anchors (km 7.999 ↔ 22.001)
3. **Spine** — existing race spine (km 22.0–41.0)

Output: `aligned_Subject_A_SUT43_20260418_race.parquet` (40,501 rows, km 0.5–41.0)

Sidecar: `aligned_Subject_A_SUT43_20260418_race_realign_meta.json` flags interpolated window.

---

## Results (2026-07-01)

| Artifact | Rows | Donors | Coverage km 8–22 |
|----------|------|--------|------------------|
| `panel_midcourse_1m.parquet` | 28,000 | Subject_A + Subject_B | 100% |

Subject_A mid-course speed_mps: 13,999 / 14,000 finite (km 8.0 seam row NaN by design).

---

## Production replacement

When washed race micro is available locally:

```bash
python3 04_Python_Scripts/15_fit_micro_wash.py  # Subject_A SUT43_20260418
python3 04_Python_Scripts/spatial/corridor_multi_fit.py --km-start 0.5 --km-end 41 --project-course
python3 04_Python_Scripts/spatial/build_midcourse_panel.py
```

Overwrite interim stitch parquet; re-run spine extension + `reproject_to_spine.py`.

---

## Reference spine extension (2026-07-01)

`build_reference_spine.py` now exports km **8.0–41.0** (33,001 rows) from stitched Subject_A race alignment:

| Artifact | Window | Rows |
|----------|--------|------|
| `reference_spine_1m.parquet` | km 8–41 | 33,001 |
| `reference_spine_meta.json` | `km_window: [8.0, 41.0]` | — |

`ref_chainage_m` tracks Subject_A `course_km` 1:1 (8,000 m → 41,000 m). km 8–22 polyline inherits interpolated GPS from the stitch scaffold — replace when washed micro is available.

```bash
python3 04_Python_Scripts/spatial/build_reference_spine.py \\
    --manifest config/spatial_align_manifest_sut43.example.json
```

Next: `hitl_chunk_triage.py` on `chunk_priority_midcourse.csv`; merge `panel_start` + `panel_midcourse` + `panel_race` spine panels.

---

## Spine reproject (2026-07-01)

Race activities reprojected onto extended `reference_spine_1m` (km 8–41):

| Artifact | Rows | Notes |
|----------|------|-------|
| `panel_race_1m_spine.parquet` | 81,002 | Subject_A + Subject_B full lap |
| `panel_midcourse_1m_spine.parquet` | 33,379 | km 8–22 on `ref_chainage_m` |

**Anchor validation** (stream delta Subject_B vs Subject_A at pins): 228–389 m — within expected 282–390 m band on gramstad pins.

**Mid-course QC:** union spine coverage 100% on km 8–22. Subject_B `cross_track_m` median ~531 m in mid-course window reflects interpolated Subject_A spine polyline km 8–22 — replace after washed micro + production `corridor_multi_fit`.

`reproject_to_spine.py` falls back to prior `*_race_spine.parquet` when non-spine aligned parquet is absent (Subject_B cloud workspace).

---

## HMM draft extension (2026-07-01)

Extended `terrain_hmm_sut43_draft_predictions.parquet` to km **8.0–41.0** (33,186 rows):

| Window | Rows | Mean `hmm_confidence` | Low-conf (A) share |
|--------|------|----------------------|-------------------|
| km 8–22 | 14,186 | 0.732 | 43.6% |
| km 22–41 | 19,000 | 0.783 | — |

Mid-course triage after HMM extension: **5 RED / 5 YELLOW / 4 GREEN** (was 14 RED with A stub).

Top RED: `chunk_m11` km 19–20 (RPS 1.110), `chunk_m12` km 20–21 (RPS 1.097).

```bash
PYTHONPATH=04_Python_Scripts python3 04_Python_Scripts/spatial/terrain_ml_features.py \\
    --panel 03_Processed_Data/spatial/sut43_terrain_ontology/panel_midcourse_1m_spine.parquet \\
    --km-start 8 --km-end 22 \\
    --output 03_Processed_Data/spatial/sut43_terrain_ontology/midcourse_draft/ml_features_1m.parquet
python3 07_ML_Models/train_terrain_hmm.py --predict-km-start 8 --predict-km-end 41
```

---

*Internal memo — not public Anatomy of Pace copy.*
