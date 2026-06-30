# O₂ Anchor Run Signature Library

**Laboratory:** The Anatomy of Pace · **Authority:** Dr. Anatomy Pace  
**Date:** 2026-06-30 · **Extends:** [`19_dual_ontology_telemetry_clusters.md`](19_dual_ontology_telemetry_clusters.md)  
**Status:** v0 — manifest + `build_anchor_features.py` scaffold

---

## 1. Problem

O₂ telemetry clusters on SUT_43 course metres inherit **course_km ontology** (operator gold, corridor locks, spine alignment). That coupling is correct for in-race gap-fill but **pollutes calibration** when the laboratory needs pure substrate × locomotion signatures:

- Asphalt high-effort run (TI ≈ 1.0 family)
- Gravel-road high-effort run (hard-gravel family, near-sealed kinematics)
- Scramble / hands-on-rock (irregular pace, reduced cadence regularity)

Extra **anchor runs** supply reference kinematics **without** writing spans into `spatial_terrain_map_sut43.json`.

---

## 2. O₂ anchor library concept

| Element | Detail |
|---------|--------|
| **Purpose** | Named reference sessions with **known dominant substrate + locomotion** |
| **Authority** | Operator manifest `config/anchor_runs_manifest.json` — not operator gold |
| **Index** | **Event-agnostic** `elapsed_m` (or segment index) — no `course_km` |
| **Features** | Same windowed pipeline as `build_telemetry_clusters.py` (TI, grade, speed, pace residual, walk/scramble fractions) |
| **Isolation** | Anchor parquets live under `03_Processed_Data/spatial/anchor_features/` — never merged into SUT_43 panel without explicit bridge step |

Anchors **calibrate** cluster centroids and emission priors; they do **not** create O₁ spans on the race map.

---

## 3. Locomotion taxonomy extension (L3)

Memo 19 defined L3 as `run | walk`. Anchor library extends O₂ locomotion to three classes:

| Class | Telemetry signature | Notes |
|-------|-------------------|--------|
| **run** | Cadence ≥ run gate; speed above walk threshold | Default on road/gravel |
| **walk** | Speed below ~1.2 m/s; regular hike cadence | Uphill power-hike, flat shuffle |
| **scramble** | Hands-on-rock; speed irregular; cadence unstable or absent; high local grade variance | **New** — Selvikstakken class |

`scramble_fraction` is computed in `build_anchor_features.py` as a rolling fraction where speed is below scramble speed cap **and** absolute grade exceeds scramble grade floor. Full four-gate TRF integration (`locomotion_mode.py`) remains deferred — scramble is O₂-only until TRF §3.3 is updated.

### 3.5 Pole policy (behavioral confounder)

| Policy | Typical context | Telemetry effect |
|--------|-----------------|------------------|
| **off** | Road races (Halvmarathon, 3-sjøersløpet) | Higher arm swing; faster apparent run signature |
| **on** | Technical climb / scramble | Reduced vertical oscillation; different cadence vs same grade walk |
| **mixed** | LFI 2026 (section-tagged), SUT_43 race by section | Same S-class can flip kinematic family when poles deploy; road sections with poles on differ from pole-off road anchors |

Pole state is **not** an O₁ field. Manifest `pole_policy` tags anchor runs; LFI adds `pole_section_windows_km[]` for weak pole-head labels; future SUT_43 work may attach section priors without extending `operator_gold_spans[]`.

---

## 4. Calibration set (v0)

| Source | Role | Dominant O₂ signature |
|--------|------|------------------------|
| **Stavanger Halvmarathon** | Extra run 1 | `sealed_road × run` — asphalt TI ≈ 1.0; **poles off** |
| **3-sjøersløpet** | Extra run 2 | `hard_gravel × run` — gravel-road, **race high effort**; **poles off** |
| **Sunderunde** | Extra run 2b | `hard_gravel × run` — gravel-road, **training low effort**; **poles off**; S2/F1 map-first annotate |
| **Lysefjorden Inn 2026** | Extra run 3 | `mixed_road_trail × run_walk` — **poles mixed**; pole-on asphalt + gravel roads (Daladalen km 24–28, finish km 55–62) |
| **Selvikstakken** | Extra run 4 | `technical_rock × scramble` — scramble locomotion class |
| **Paradisskaret** (in-course) | SUT_43 windows km 34.6–36.3, 38.4–39.14, 39.14–41.0 | F1 vs F3 gravel split validation per memo 19 §6 |

**Pole calibration triad (v0):** Halvmarathon and 3-sjøersløpet supply pole-**off** road kinematics on sealed asphalt and hard gravel respectively (race effort on gravel). **Sunderunde** adds pole-off gravel at **low training effort** — same S2/F1 substrate class, lower HR/pace stress than 3-sjøersløpet. LFI 2026 closes the gap: same substrates with **poles on** (or mixed deploy at km 7), isolating pole as a confounder independent of S-class. Section windows live in `config/anchor_runs_manifest.json` → `lfi_2026.pole_section_windows_km[]`.

**Workflow:**

1. Build anchor feature parquets from manifest (`build_anchor_features.py`).
2. Fit O₂ clusters on anchor library **pooled** (grade-stratified) → reference centroids.
3. Project SUT_43 race metres onto anchor centroids (cosine / Mahalanobis in feature space) **without** relabeling course gold.
4. Use Paradisskaret in-course windows to confirm loose-gravel separation matches anchor gravel family.

---

## 5. Separation from O₁ / course_km

| Concern | Anchor library | SUT_43 panel clustering |
|---------|----------------|-------------------------|
| Distance index | `elapsed_m` | `course_m` / `course_km` |
| Gold spans | None (manifest metadata only) | `hitl.operator_gold_spans[]` |
| TI denominator | Shared asphalt anchor (`Stavanger Halvmaraton` or Seed Matrix) | Same — comparable TI scale |
| Output | `anchor_features_<id>.parquet` | `telemetry_clusters_sut43.parquet` |
| Bridge to O₁ | Optional learned map from anchor cluster → S/F **priors** | Empirical P(S,F \| cluster) on labeled metres |

Injecting anchor metres into the SUT_43 panel would falsely imply those sessions share the race spine — **forbidden** for v0.

---

## 6. Feature extraction pipeline

Reuses `build_telemetry_clusters.py` constants and rolling logic:

| Stage | Implementation |
|-------|----------------|
| Ingest | `11_gap_engine.load_fit` + `apply_gap` @ asphalt anchor |
| Resample | 1 m grid on cumulative session distance → `elapsed_m` |
| Base features | `ti`, `grade_pct`, `speed`, `pace_expected`, `pace_residual` |
| Window (60 m) | `ti_mean`, `ti_std`, `speed_mean`, `pace_residual_mean`, `walk_fraction`, `scramble_fraction` |
| Grade conditioning | `assign_grade_bin` — same TRF §3.2 bins |

CLI:

```bash
python3 04_Python_Scripts/spatial/build_anchor_features.py
python3 04_Python_Scripts/spatial/build_anchor_features.py --anchor-id stavanger_halvmarathon
```

---

## 7. Data inventory (2026-06-30)

| Anchor | `.fit` in repo | Macro DB / race_vintages | Notes |
|--------|----------------|--------------------------|--------|
| Stavanger Halvmarathon | ✅ `02_Raw_Data/Stavanger_Halvmaraton.fit` | Not in `race_registry.csv` | Subject_A Seed Matrix lock; ~21.4 km; poles off |
| 3-sjøersløpet | ✅ `02_Raw_Data/3_sjøers_Eirik_20251108.fit` | Not registered | Subject_A race stream (2025-11-08); poles off; high effort |
| Sunderunde (training gravel) | ✅ `02_Raw_Data/Sunderunde_Eirik_20260530.fit` | Not registered | Subject_A training loop (2026-05-30); poles off; low effort; S2/F1 map-first annotate. Subject_B candidate: `Sunderunde_Solvi_20260530.fit` |
| Lysefjorden Inn 2026 | ✅ `02_Raw_Data/LFI_Eirik_20260606.fit` (alias `LFI_2026.fit`) | `anatomy_macro.db` LFI 2026 checkpoint splits | Subject_A only; activity `LFI_20260606`; ~62 km course-projected; poles mixed (off km 0–7, on from km 7); pole-on-road windows km 24–28 (Daladalen asphalt/gravel), km 55–62 (finish asphalt). Processed micro parquet present. Subject_B LFI stream not in repo. |
| Selvikstakken | ❌ Missing | SUT_160 corridor only (`selvikstakken_climb` km 73–73.7) | Dedicated scramble session TBD — export from watch |
| Paradisskaret | ✅ In SUT_43 panel | SUT_43 operator gold | In-course only; use `build_telemetry_clusters.py` |

---

## 8. Operator ingest checklist

1. **Stavanger Halvmarathon** — run `build_anchor_features.py` (path already in manifest).
2. **3-sjøersløpet** — `fit_path` = `3_sjøers_Eirik_20251108.fit`; run `build_anchor_features.py --anchor-id 3_sjoerslopet` (race gravel, high effort).
2b. **Sunderunde (training gravel)** — `fit_path` = `Sunderunde_Eirik_20260530.fit`; run `build_anchor_features.py --anchor-id sunderunde_training_gravel` (low effort; S2/F1 Tier 0 annotation practice).
3. **Lysefjorden Inn 2026** — run `build_anchor_features.py --anchor-id lfi_2026`; slice `pole_section_windows_km` for pole-on-road feature export (Daladalen + finish asphalt). Full 62 km race is heterogeneous — do not pool as single-substrate centroid without grade/substrate stratification.
4. **Selvikstakken** — export high-effort scramble session (full climb + descent) to `02_Raw_Data/anchors/selvikstakken_<subject>_<date>.fit`; update manifest `fit_path`.
5. Re-run `build_anchor_features.py --all`; QC mean TI on asphalt anchor window ≈ 1.0.
6. Pool anchor parquets for centroid fit (step 2 in §4 — script TBD).

---

## 9. Related docs

- [`19_dual_ontology_telemetry_clusters.md`](19_dual_ontology_telemetry_clusters.md) — O₁/O₂ bridge, Paradisskaret windows
- [`21_multitask_gold_suggester_nn.md`](21_multitask_gold_suggester_nn.md) — multi-head pole/locomotion extension (design)
- `config/anchor_runs_manifest.json` — run registry
- `04_Python_Scripts/spatial/build_anchor_features.py` — event-agnostic feature export
- `docs/master_plan.md` — Seed Matrix (asphalt + gravel calibration intent)
