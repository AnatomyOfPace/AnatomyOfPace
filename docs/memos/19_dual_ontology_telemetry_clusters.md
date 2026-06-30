# Dual Ontology — Operator Gold vs Telemetry Clusters

**Laboratory:** The Anatomy of Pace · **Authority:** Dr. Anatomy Pace  
**Date:** 2026-06-30 · **Corridor:** SUT_43 gramstad_band + upstream Dale sector  
**Status:** v0 — `build_telemetry_clusters.py` proof on road + Paradisskaret anchors

---

## 1. Problem

A single flat S-class (S1–S6) is **not** the natural unit for telemetry. Observed kinematics reflect **substrate × locomotion × grade × effort**; operator gold encodes **surface × friction** only. Collapsing both into one ontology produces REVISE noise on trail, false merges on road, and non-identifiable class boundaries (see `docs/memos/17_sparse_gold_ml_suggestion_pipeline.md` §9).

The laboratory therefore operates **two ontologies** with an explicit probabilistic bridge.

---

## 2. O₁ — Operator / course ontology

| Element | Detail |
|---------|--------|
| **Classes** | Surface S1–S6; friction F0–F4 per `docs/friction_index_spec.md` |
| **Authority** | Sparse operator gold in `hitl.operator_gold_spans[]` |
| **Contract** | Append-only spans; gaps valid; no forced full-course coverage |
| **Scope** | What the course metre **is** (map, field, adjudication) |

Reference: `docs/memos/17_sparse_gold_ml_suggestion_pipeline.md` §2.

---

## 3. O₂ — Telemetry / behavioral clusters

Unsupervised clusters on **windowed kinematic features** approximate behavioral substrate families, not operator S-labels.

### 3.1 Per-metre base features

| Column | Source |
|--------|--------|
| `ti` | Consensus TI (cross-athlete median) |
| `grade_pct` | Grade percent |
| `speed` | Speed (m/s) |
| `pace_expected` | GAP-expected pace |
| `nti_std` | Cross-athlete NTI σ (when panel has multiple donors) |

### 3.2 Windowed features (e.g. 60 m rolling)

| Column | Meaning |
|--------|---------|
| `ti_mean`, `ti_std` | Local friction tax stability |
| `speed_mean` | Locomotion intensity |
| `pace_residual_mean` | Observed vs expected pace tax |
| `walk_fraction` | Fraction of metres with speed below walk threshold (~1.2 m/s) |

### 3.3 Grade conditioning

Cluster **within** grade bins (uphill / flat / downhill per TRF §3.2) so uphill walk does not masquerade as a surface class. Optional `grade_bin` column exported with cluster assignments.

### 3.4 O₂ semantic vocabulary (informal)

Clusters approximate families such as:

```
{ sealed_road, hard_gravel, loose_gravel, tractor_road,
  runnable_trail, technical_trail, bog_rock, stairs_rock }
× { run, shuffle_walk, hike_walk }
```

**Expected collapses:** `sealed_road × run` ≈ `hard_gravel × run` (shared cluster family). `loose_gravel` / `tractor_road` remain distinct — Paradisskaret coarse gravel is the calibration anchor.

---

## 4. Bridge — many-to-many O₂ → O₁

| Rule | Detail |
|------|--------|
| **Mapping** | Empirical **P(S, F \| cluster_id)** from labeled metres only |
| **Output** | `cluster_to_gold_mapping.csv`: `cluster_id`, dominant S, dominant F, `n_metres`, per-class **P(surface)** |
| **Abstain** | Low cluster margin or high `nti_std` → no gold suggestion (sparse gap policy) |
| **Not 1:1** | One cluster may map to multiple S/F pairs; one S/F may emit multiple clusters across grade/locomotion |

The gold suggester (`train_gold_suggester.py`) remains a **direct** feature→S/F classifier on O₁ labels. The bridge table is a **parallel** interpretability layer for cluster transitions in gaps.

---

## 5. Non-identifiability (cross-ref memo 17 §9)

Telemetry does **not** uniquely identify S-class or F-tier. Grade, locomotion mode, tactical effort, and cumulative debt mix the signal. Therefore:

- O₂ clusters are **weak corroboration**, not ontological truth.
- REVISE flags on trail are **review queue**, not proof of mis-labeling.
- Road substrate (S1/S2, F0/F1) is more separable in feature space than technical trail (S3–S6, F2–F4).

Full factor table: `docs/memos/17_sparse_gold_ml_suggestion_pipeline.md` §9.

---

## 6. Paradisskaret calibration anchors

Known km windows validate that O₂ separates friction tiers within the same S-class:

| Window (km) | O₁ gold | Expected O₂ signature |
|-------------|---------|----------------------|
| 39.140–41.0 | S1 / F0 | `sealed_road × run`, low TI variance |
| 34.6–36.3 | S2 / F1 | `hard_gravel × run`, near-sealed kinematics |
| 38.4–39.135 | S2 / F3 | `loose_gravel` / coarse road, elevated TI σ and pace tax |

If clustering cannot split F1 vs F3 gravel in the 38.4–39.14 band, the **feature set or grade conditioning** is insufficient — not operator adjudication.

Road proof windows (upstream Dale sector): km 22–29 per `config/spatial_terrain_map_sut43_upstream.json`; spot-check km 23–24 for asphalt/gravel mix.

---

## 7. Hierarchy L0–L3

| Level | Content | Gold? | Cluster role |
|-------|---------|-------|--------------|
| **L0** | Corridor class: road \| trail \| built | Partial (map) | Primary split |
| **L1** | Substrate: S1 asphalt … S6 very difficult | **Yes** | Inferred via bridge |
| **L2** | Friction: F0–F4 | **Yes** | Inferred via bridge + TI bands |
| **L3** | Locomotion: run \| walk \| scramble | **No** (telemetry-only) | Native O₂ axis |
| **L3b** | Pole policy: off \| on \| mixed | **No** (session/section metadata) | Confounds speed/TI on same substrate |

**Gold spans encode L1+L2 only.** Clusters primarily capture L0+L3 (+ pole policy where known) and grade, then **infer** L1+L2 where labeled metres exist.

Pole use is not logged in FIT; anchor runs carry `pole_policy` in the manifest (`off` for road races, `on_mixed` for scramble sessions). SUT_43 race metres may need section-level pole priors from race manual — not O₁ gold fields.

### Road-first strategy

Aligns with `docs/memos/18_gold_hitl_low_hanging_fruit.md`:

1. Lock Tier 1–2 road gold (S1/S2, F0/F1) before trail gap-fill.
2. Cluster upstream road windows first; expect 1–2 dominant fast-road families.
3. Use Paradisskaret F3 anchor to validate loose-gravel separation before trail clustering.
4. Defer REVISE on trail gold until road bridge table is stable.

---

## 8. v0 CLI

```bash
# Upstream road proof (km 23–24)
python3 04_Python_Scripts/spatial/build_telemetry_clusters.py \
  --km-start 23 --km-end 24 \
  --terrain-map config/spatial_terrain_map_sut43_upstream.json

# Paradisskaret coarse gravel anchor
python3 04_Python_Scripts/spatial/build_telemetry_clusters.py \
  --km-start 38.4 --km-end 39.14 \
  --terrain-map config/spatial_terrain_map_sut43.json
```

**Outputs:**

- `03_Processed_Data/spatial/telemetry_clusters_sut43.parquet` — per-metre `cluster_id`, `grade_bin`, features
- `03_Processed_Data/spatial/cluster_to_gold_mapping.csv` — when operator gold covers the window

---

## 9. Next steps (ML pipeline)

| Step | Script / artifact | Purpose |
|------|-------------------|---------|
| 1 | `build_telemetry_clusters.py` (v0) | Grade-stratified GMM/HDBSCAN; bridge table |
| 2 | Extend `suggest_gold_spans.py` | Gap proposals from **cluster transitions**, not HMM alone |
| 3 | Mixture / HMM on O₂ | States = telemetry clusters; emit S/F via learned emission map |
| 4 | Multi-task head | Shared encoder → S, F, locomotion; do not backprop locomotion into S |
| 5 | Residual tax model | Predict pace residual after grade + mode; F-tier from magnitude |
| 6 | Abstain policy | Wire cluster margin + `nti_std` into suggestion CSV rationale |

---

## 10. Related docs

- `docs/memos/17_sparse_gold_ml_suggestion_pipeline.md` — sparse gold, suggester CLI, non-identifiability (§9)
- `docs/memos/18_gold_hitl_low_hanging_fruit.md` — annotation tiers, road-first HITL
- `docs/friction_index_spec.md` — F-tier authority
- `docs/training_residual_framework.md` — grade bins, locomotion gates

---

## 11. O₂ anchor run library (cross-ref)

Extra high-effort sessions with known substrate × locomotion calibrate O₂ centroids **without** polluting SUT_43 `course_km` ontology. Event-agnostic feature export: `build_anchor_features.py` + `config/anchor_runs_manifest.json`. Locomotion extension: `run | walk | scramble`. Full spec: [`20_anchor_run_signature_library.md`](20_anchor_run_signature_library.md).

---

## 12. v0 limitations

- Single corridor (SUT_43); no cross-race transfer.
- GMM default; BIC-based component count not yet automated.
- Bridge table is empirical counts, not calibrated probabilities.
- No cluster-transition span merger in `suggest_gold_spans.py` yet (step 2 deferred).
