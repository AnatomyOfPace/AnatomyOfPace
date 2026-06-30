# Multi-Task Gold Suggester — Neural Network Design Memo

**Laboratory:** The Anatomy of Pace · **Authority:** Dr. Anatomy Pace  
**Date:** 2026-06-30 · **Extends:** [`17_sparse_gold_ml_suggestion_pipeline.md`](17_sparse_gold_ml_suggestion_pipeline.md), [`20_anchor_run_signature_library.md`](20_anchor_run_signature_library.md)  
**Status:** v1 sketch — design only; **no implementation scheduled**

---

## 1. Motivation

The v0 gold suggester (`train_gold_suggester.py`) trains **independent** `HistGradientBoostingClassifier` models for surface (S1–S6) and friction (F0–F4) on labeled SUT_43 metres. Telemetry on the same tread class shifts materially when **grade**, **locomotion mode**, or **pole deployment** change — confounders that co-vary on ultra courses.

A **multi-headed neural network** with a shared encoder can learn a joint representation for correlated confounders (grade × mode × poles × substrate) before task-specific heads. Weak supervision from the O₂ anchor library — especially LFI 2026 pole-on-road windows (memo 20) — supplies labels that do **not** exist in O₁ gold.

---

## 2. Architecture proposal (v1 sketch)

### 2.1 Shared encoder

**Input:** rolling window features per metre (or per 60 m window centre), aligned with anchor and cluster pipelines:

| Feature | Source |
|---------|--------|
| `ti_mean`, `ti_std` | Minetti TI on 60 m window |
| `grade_pct` | Course or session grade |
| `speed_mean` | Rolling speed |
| `pace_residual_mean` | Observed vs expected pace |
| `walk_fraction`, `scramble_fraction` | Locomotion heuristics (`build_anchor_features.py`) |
| `nti_std` (optional) | Cross-athlete dispersion when panel available |

For SUT_43 supervised path, merge with `gold_training_common.FEATURE_COLUMNS` where overlap exists (`consensus_nti`, `nti_std`, `grade_pct_median`, `speed_mps_median`, `pace_gap_flat_median`, `hmm_confidence`, …). Encoder: 2–3 layer MLP (128 → 64 → 32) or 1D temporal conv over ±30 m context (deferred v2).

### 2.2 Task heads

| Head | Target | Label source | Loss |
|------|--------|--------------|------|
| **Head S** | Multiclass S1–S6 | Operator gold (`operator_gold_spans[]`) | Weighted CE; **mask unlabeled** |
| **Head F** | Ordinal F0–F4 (5-class categorical v0; CORAL ordinal v1) | Operator gold | Weighted CE; **mask unlabeled** |
| **Head locomotion** | `run` \| `walk` \| `scramble` | Anchor manifest `locomotion_mix` + heuristics; optional self-supervised consistency | CE on weak labels |
| **Head pole** | `off` \| `on` \| `mixed` | Anchor `pole_policy` + LFI `pole_section_windows_km[]`; Halvmarathon / 3-sjøersløpet = off | CE on section labels |

**Critical:** pole and locomotion heads are **not** in O₁ gold. They train only where anchor metadata or section windows provide weak labels.

### 2.3 Loss

```
L = w_S · CE(S | labeled) + w_F · CE(F | labeled) + w_L · CE(locomotion | weak) + w_P · CE(pole | weak)
```

- Mask S/F loss where `is_labeled == False`.
- Default weights: `w_S = w_F = 1.0`, `w_L = 0.3`, `w_P = 0.3` (tune on holdout).
- Class weights for rare S/F tiers (S6, F4) as in v0 stratified training.

### 2.4 Inference behaviour

- Emit S/F only when `max(softmax) ≥ τ` (default τ = 0.55, match `suggest_gold_spans.py`).
- **Abstain** on low margin for any head — do not force gap-fill when pole head disagrees with road-substrate prior.
- Pole/locomotion heads used as **confounder features** for revision flags, not written to O₁ JSON.

---

## 3. Why NN over HistGradientBoosting

| Factor | HistGradientBoosting (v0) | Multi-head NN |
|--------|---------------------------|---------------|
| Correlated confounders | Separate trees per task; no shared latent space | Shared encoder disentangles grade/mode/pole |
| Weak auxiliary labels | Not supported | Locomotion/pole heads from anchors |
| Data volume | Strong on tabular, small N | Needs more samples or pretrain |
| Interpretability | Feature importances per model | Blacker; cluster-bridge tables help |
| Deployment | `joblib`, fast CPU | PyTorch or sklearn `MLPClassifier` multi-output |

**When NN wins:** pole-on vs pole-off on same asphalt (LFI finish vs Halvmarathon) at similar grade and speed — tree models treat TI/pace identically without pole bit.

**When trees win:** current 12k labeled SUT_43 metres with strong per-class holdout metrics (memo 17 §5).

---

## 4. Risks

| Risk | Mitigation |
|------|------------|
| Small labeled set (~12k m) | Pretrain encoder on anchor parquets + full SUT_43 unlabeled metres (self-supervised TI reconstruction optional) |
| Overfit on S6/F4 tails | Dropout 0.2; early stopping; abstain on low margin |
| Weak pole labels wrong on SUT_43 | LFI windows only for pole head v0; SUT_43 pole head frozen or low weight until section tags exist |
| Train/serve skew | Same `build_gold_training_set.py` feature pipeline; version encoder input schema |
| Scope creep | Pole/locomotion heads **do not** extend `operator_gold_spans[]` without operator review |

---

## 5. Practical path

| Step | Action | Owner / artifact |
|------|--------|------------------|
| 1 | `build_gold_training_set.py` + `build_anchor_features.py --all` → merged pretrain parquet | `03_Processed_Data/spatial/gold_pretrain_merged.parquet` (TBD) |
| 2 | Attach weak labels: locomotion from heuristics; pole from `anchor_runs_manifest.json` section windows | Label join script (TBD) |
| 3 | **v0 NN:** sklearn `MLPClassifier` multi-output or small PyTorch module — 2 heads (S, F) only, shared trunk | `07_ML_Models/spatial/gold_suggester_nn_v0.pt` |
| 4 | Add locomotion + pole heads; pretrain on anchors, finetune on SUT_43 labeled | `gold_suggester_nn_v1` |
| 5 | Holdout compare to `gold_suggester_v0.joblib` on same labelled metre split | Metrics JSON alongside metadata |
| 6 | Wire `suggest_gold_spans.py --engine nn` only if NN beats v0 on gap-fill precision | CLI flag |

**Fallback:** retain `HistGradientBoosting` v0 until **labeled SUT_43 metres ≥ 25 000** *or* anchor pretrain + pole-head validation on LFI section windows shows ≥5 pp F1 gain on S/F holdout.

---

## 6. Go / no-go (2026-06-30)

| Criterion | Current state | Gate |
|-----------|---------------|------|
| Labeled SUT_43 metres | 12 000 | Need ≥ 25 000 for finetune-first NN |
| Anchor feature parquets | Manifest ready; LFI + Halvmarathon `.fit` present | Need `build_anchor_features.py --all` run + pooled export |
| Pole weak labels | LFI `pole_section_windows_km` in manifest | Need label join + QC on km 24–28 vs Halvmarathon |
| v0 sklearn baseline | Strong holdout on S/F (memo 17) | NN must beat v0 on gap-only precision |
| Engineering cost | No PyTorch dep in spatial ML path today | sklearn MLP v0 is lower cost entry |

**Recommendation: NO-GO for NN v0 now.** Continue `gold_suggester_v0.joblib` for HITL gap-fill. **Proceed with anchor feature export** (including LFI pole windows) as pretrain prep. Revisit multi-head NN when labeled metres cross 25 000 **or** anchor-merged pretrain dataset exceeds 50 000 weak-labeled window rows with pole-head sanity check on LFI Daladalen vs Halvmarathon asphalt.

---

## 7. Related docs

- [`17_sparse_gold_ml_suggestion_pipeline.md`](17_sparse_gold_ml_suggestion_pipeline.md) — v0 sklearn pipeline
- [`20_anchor_run_signature_library.md`](20_anchor_run_signature_library.md) — LFI pole-mixed road anchor
- `config/anchor_runs_manifest.json` — `lfi_2026.pole_section_windows_km[]`
- `04_Python_Scripts/spatial/gold_training_common.py` — SUT_43 feature contract
- `04_Python_Scripts/spatial/train_gold_suggester.py` — v0 trainer
