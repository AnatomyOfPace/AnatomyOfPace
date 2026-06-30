# Gold HITL — Low-Hanging Fruit & Annotation Tiers

**Laboratory:** The Anatomy of Pace · **Authority:** Dr. Anatomy Pace  
**Date:** 2026-06-30 · **Corridor:** SUT_43 gramstad_band (km 29–41)  
**Status:** Operator guidance — pairs with `17_sparse_gold_ml_suggestion_pipeline.md`

---

## Human annotation difficulty ladder

Operator terrain adjudication cost rises sharply off sealed road. Kartverket orthophoto resolves substrate class for engineered surfaces; trail tread requires field memory, kinematic context, or deferred ML assist.

| Tier | Difficulty | Typical adjudication | S/F examples |
|------|------------|----------------------|--------------|
| **0 — Practice (training loop)** | Trivial | Uniform engineered gravel loop; entire session one class | Gravel road **S2/F1** — Sunderunde training anchor (`sunderunde_training_gravel`) |
| **1 — Easy (map-first)** | Low | Visual on Kartverket orthophoto; no field visit required | Asphalt **S1**; gravel road **S2** |
| **2 — Moderate** | Medium | Trail vs non-trail boundary; wide forest road tread class | Forest road **S2** vs hard-pack trail **S3** |
| **3 — Hard** | High | Runnable trail grade within same visual corridor | Easy trail **S3** vs moderate technical **S4** |
| **4 — Very hard** | Highest | Subjective technical ceiling on identical surface appearance | Difficult rock **S5** vs very difficult **S6**; **F3** vs **F4** on same tread |

S1–S6 definitions and friction-tier mapping: `docs/friction_index_spec.md` §4.

---

## Workflow implication

1. **Tier 0 warm-up.** Use Sunderunde (`sunderunde_training_gravel`) as a full-session S2/F1 practice loop before SUT_43 gramstad_band work — zero trail ambiguity, low annotation cost.
2. **Lock Tier 1 first.** Seal road and obvious gravel spans (`S1`/`S2`, `F0`/`F1`) before trail work. Leave trail difficulty **gaps** intentionally — unlabeled metres are valid under the sparse gold contract.
3. **Road-first ML suggester.** Train `train_gold_suggester.py` on Tier 1–2 gold; run `suggest_gold_spans.py --mode gaps-only` to propose S/F on trail gaps. Operator reviews **hard calls only** (Tier 3–4), not metre-by-metre re-annotation.
4. **REVISE deferral on trail.** `--mode revise` on existing trail gold is **Tier 3 defer** — do not bulk-revise S3/S4 spans until road substrate is locked and the model has sufficient labeled trail metres. Revision flags on trail are adjudication queue, not auto-accept. Rationale: telemetry is non-identifiable across S-classes on trail (grade, locomotion, effort, fatigue mix the signal); see `docs/memos/17_sparse_gold_ml_suggestion_pipeline.md` §9.
5. **Gap preservation.** Tier 4 spans (`S5`/`S6`, `F3`/`F4` boundary) may remain `UNLABELED` until `nti_std` drops or reference-elite cross-check is available (`hitl.variance_gaps[]`).

**Calibration anchors** for telemetry clustering (O₂ vs O₁): sealed asphalt km 39.14–41.0 (S1/F0), hard gravel km 34.6–36.3 (S2/F1), Paradisskaret coarse gravel km 38.4–39.135 (S2/F3). See `docs/memos/19_dual_ontology_telemetry_clusters.md` §6.

---

## Related docs

- `docs/memos/17_sparse_gold_ml_suggestion_pipeline.md` — sparse gold contract, ML suggester CLI, telemetry non-identifiability (§9)
- `docs/memos/19_dual_ontology_telemetry_clusters.md` — O₁/O₂ bridge, Paradisskaret calibration windows
- `docs/memos/20_anchor_run_signature_library.md` — Sunderunde Tier 0 training gravel anchor (`sunderunde_training_gravel`)
- `docs/friction_index_spec.md` — F-tier authority; S1–S6 mapping table (§4)
- `docs/hitl_annotator.md` — operator workflow
