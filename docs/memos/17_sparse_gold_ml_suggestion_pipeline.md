# Sparse Gold ML Suggestion Pipeline — Design Memo

**Laboratory:** The Anatomy of Pace · **Authority:** Dr. Anatomy Pace  
**Date:** 2026-06-30 · **Corridor:** SUT_43 gramstad_band (km 29–41)  
**Status:** v0 scaffold — CLI workflow (Streamlit HITL **parked**)

---

## 1. Problem

Operator terrain gold must be **sparse by design**: the laboratory annotates only km ranges where tread is confident, leaving **gaps** where uncertainty remains. Full-course forced coverage is rejected. ML must learn from labeled metres only and **propose** fills in gaps plus **revision flags** on existing gold where the model disagrees at low operator confidence.

---

## 2. Sparse gold contract

| Rule | Detail |
|------|--------|
| **Append-only spans** | `hitl.operator_gold_spans[]` in `config/spatial_terrain_map_sut43.json` |
| **Gaps allowed** | No requirement for contiguous km coverage; unlabeled metres are `UNLABELED` |
| **No overlap on add** | New spans must not intersect existing gold (`gold_span_editor.py` enforces) |
| **Fields per span** | `course_km_start`, `course_km_end`, `surface_class` (S1–S6), `friction_tier` (F0–F4), `reason`, `gold_source`, `locked_at` |
| **Authority** | Operator gold overrides GMM/HMM draft; ML suggestions are **non-authoritative** until accepted |

Reference structure: `config/spatial_terrain_map_sut43.json` → `hitl.operator_gold_spans[]`.

---

## 3. Feature matrix (per metre)

Built from race panel + HMM draft (`build_gold_training_set.py` / `gold_training_common.py`):

| Feature group | Columns |
|---------------|---------|
| **NTI / TI** | `consensus_nti`, `nti_std`, `nti_median`, `ti_median`, `ti_raw_median` |
| **Grade / kinematics** | `grade_pct_median`, `speed_mps_median`, `mechanical_kappa_median`, `cadence_spm_median`, `pace_gap_flat_median` |
| **Geography** | `altitude_m` |
| **HMM draft** | `hmm_confidence`, `hmm_draft_class_ord` (ordinal encoding of `draft_class`) |

Source parquets:

- `03_Processed_Data/spatial/sut43_terrain_ontology/panel_1m.parquet`
- `07_ML_Models/terrain_hmm_sut43_draft_predictions.parquet`

---

## 4. Labels

| Column | Meaning |
|--------|---------|
| `label_surface` | Operator S-class where gold span covers metre; else `null` |
| `label_friction` | Operator F-tier where gold span covers metre; else `null` |
| `is_labeled` | `True` iff metre falls inside any `operator_gold_spans[]` entry |

Training uses **labeled metres only** (`is_labeled == True`). Gaps remain unlabeled at export time.

---

## 5. Training (`train_gold_suggester.py`)

| Target | Model | Notes |
|--------|-------|-------|
| `label_surface` | `HistGradientBoostingClassifier` | Multiclass S1–S6 |
| `label_friction` | `HistGradientBoostingClassifier` | Multiclass F0–F4 (ordinal treated as categorical v0) |

- Holdout: stratified 80/20 on labeled metres (seed 42).
- Artifacts: `07_ML_Models/spatial/gold_suggester_v0.joblib` + `gold_suggester_v0_metadata.json` (feature list, class lists, per-class metrics).
- Minimum labeled metres guard (default 200) — fails fast if gold too sparse.

---

## 6. Inference (`suggest_gold_spans.py --engine ml`)

| Mode | Behaviour |
|------|-----------|
| `--mode gaps-only` | Propose **NEW** spans on unlabeled metres (contiguous runs ≥ 50 m, modal predicted S/F) |
| `--mode revise` | Flag **REVISE** where existing gold S or F disagrees with model and `max(proba) < threshold` |
| `--mode all` | Gaps + revision flags; labeled agreement → **KEEP** summary rows optional |

Output CSV columns: `action`, `km_start`, `km_end`, `surface_class`, `friction_tier`, `confidence`, `gold_surface`, `gold_friction`, `rationale`, `chunk_id` (when triage-bound).

Course-wide scope: `--km-start` / `--km-end` without triage queue dependency.

Legacy HMM+TI engine retained: `--engine hmm` (pre-ML heuristic path).

---

## 7. Human loop

```
build_gold_training_set → train_gold_suggester → suggest_gold_spans (review CSV)
        ↑                                                      |
        └──────── gold_span_editor (agree → add / disagree → skip) ┘
```

1. Operator edits gold via `gold_span_editor.py` or manual JSON append.
2. Rebuild training export and retrain after material gold changes.
3. Review suggestion CSV; accept **NEW** / **REVISE** rows through editor or append.
4. Re-export chunk PNG (`validation_dashboard.py`) for QC.

---

## 8. Annotation difficulty & road-first strategy

Trail tread adjudication is materially harder than sealed-road map work. Operator effort should follow a **difficulty ladder** (map-first asphalt/gravel → trail boundary → S3/S4 → S5/S6 and F3/F4). Lock Tier 1 road gold first; leave trail difficulty gaps; train the suggester on road spans before gap-fill on trail; defer `--mode revise` on existing trail gold until Tier 3 queue.

Full tier definitions and workflow rules: `docs/memos/18_gold_hitl_low_hanging_fruit.md`.

---

## 9. Telemetry non-identifiability

There is **no unique telemetry signature per S-class or F-tier**. The same locked substrate (e.g. S3, F3) can present different observed TI, speed, and pace depending on grade, locomotion mode (run vs walk), tactical effort, and fatigue state — the Effort Paradox and terrain tax from `docs/theory.md` §5 and `docs/friction_index_spec.md` §2.

| Factor | Effect on signal |
|--------|------------------|
| **Grade** | GAP-normalized TI still shifts with braking κ and line choice on steep tread |
| **Locomotion** | Walk/scramble on F4 metres collapses speed without a distinct S-class channel |
| **Tactical effort** | Iso-HR pacing holds load while pace varies — APR and TI diverge from tier expectation |
| **Fatigue** | Late-loop cumulative debt inflates observed TI on otherwise unchanged tread |
| **Pole use** | Poles on vs stowed alters cadence, arm work, and apparent pace tax on the same tread |

The gold suggester treats NTI, grade, speed, κ, and HMM draft as **weak corroborating evidence**, not a bijective class→signal map. Operator gold is **ontological truth** (what the course metre *is*); telemetry **corroborates** on sealed road (S1/S2, F0/F1) but is **not definitive** for trail adjudication (S3–S6, F2–F4).

**Pipeline implications:**

- **REVISE disagreement is expected** on trail spans — model flags are review queue, not proof of mis-labeling.
- **Gaps remain valid** where telemetry cannot disambiguate Tier 3–4 tread (sparse gold contract).
- **Road classes are more separable** than trail in feature space; train and lock Tier 1–2 before trusting gap-fill or revision on technical metres.
- **Dual ontology:** operator gold (O₁) and telemetry clusters (O₂) are separate layers bridged by empirical P(S,F | cluster); see `docs/memos/19_dual_ontology_telemetry_clusters.md`.

---

## 10. Related docs

- `docs/memos/18_gold_hitl_low_hanging_fruit.md` — annotation difficulty ladder, road-first HITL
- `docs/memos/19_dual_ontology_telemetry_clusters.md` — O₁/O₂ dual ontology, grade-stratified clusters
- `docs/friction_index_spec.md` — F-tier authority; S1–S6 mapping (§4)
- `docs/hitl_annotator.md` — operator workflow (Streamlit parked)
- `docs/GEMINI_HANDOFF.md` — spatial script index
- `07_ML_Models/train_terrain_gb.py` — prior LOOCV GBM on agreement labels (separate track)

---

## 11. v0 limitations

- No active learning or span-level probability calibration.
- Friction model is flat multiclass, not ordinal regression.
- Revision mode uses per-metre disagreement; span merge is contiguous-run heuristic only.
- Single corridor (gramstad_band); upstream map merge deferred.
