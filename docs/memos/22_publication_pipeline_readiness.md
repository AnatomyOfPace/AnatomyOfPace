# Publication Pipeline Readiness — Gemini Handoff Memo

**Laboratory:** The Anatomy of Pace · **Authority:** Dr. Anatomy Pace
**Date:** 2026-07-01 · **Corridor:** SUT_43 gramstad_band (km 29–41)
**Status:** Reconciliation — 17-article taxonomy committed; gold readiness assessed against artifacts
**Extends:** `docs/publication_pipeline.md`, `docs/memos/17_sparse_gold_ml_suggestion_pipeline.md`, `docs/memos/18_gold_hitl_low_hanging_fruit.md`

---

## 1. What shipped

The expanded publication taxonomy (17 candidates, sections I–VII) is now a committed, public-safe artifact: `docs/publication_pipeline.md` (PR #5, branch `cursor/publication-pipeline-candidates-1cda`). It consolidates the core pipeline (Articles 1–4) with methodology (5–7), terrain deep-dives (8–10), pipeline transparency (11–13), macro/predictive (14–16), and a discovery-layer hook (17), plus Ghost Authority ground rules and an editorial sequence.

Nomenclature, visual-defensibility, and firewall constraints validated: clinical English only, `Kinematic_Scan` / TI / Terrain Tax, `Subject_*` / `Reference_Elite_*` IDs, no private-training crossover.

---

## 2. Bottleneck reconciliation (correction to prior framing)

Prior handoff framed the empirical foundation as broadly "pending." Artifact inspection shows the `gramstad_band` foundation is **substantially in hand**; the outstanding work is narrower than stated.

### Already supplied

| Dependency | Evidence | State |
|------------|----------|-------|
| Corridor lock + alignment | `align_meta.json` — sector lock `2026-06-26-sut43-gramstad-band`, 9 aligned activities (Subject_A race + Subject_B race + 7 training), coverage ≈ 1.0 | Locked |
| Micro panel | `panel_1m.parquet` (+ race/training splits) | Built |
| Gold export | `gold_training_set_sut43.summary.json` — km 22–41, 19,000 m, 100% labeled; full S1–S6 + F0–F4 distributions | Exported |
| Asphalt anchors (Article 5 contrast) | `gold_training_set_stavanger_halvmarathon.summary.json`, `gold_training_set_3_sjoerslopet.summary.json` | Present |
| Start sector | `gold_training_set_start.summary.json` — km 0.5–8.0, 100% labeled (2026-07-01) | Complete |

### Genuinely outstanding

1. **Mid-band operator gold (km 34–40).** Per `ground_truth_review/chunk_priority.csv`: chunk_00–04 (km 29–34) and chunk_11 (km 40–41) are 100% operator-gold locked, but chunk_05–10 are partial — **chunk_07 and chunk_09 carry ≈ 0 operator gold** (draft-preservation fill) with heavy `abstain` / `review`. The export's 100% is operator gold **plus** agreement/draft-preservation fills. Remaining calls are the Tier 3–4 technical-trail hard cases (S4/S5/S6, F3/F4 boundaries) deferred in memo 18.
2. **Article 1 visualization render.** `06_Visualizations/` is empty — the categorical HMM draft sequence vs continuous TI trace figure is not yet rendered. Building blocks exist (`spatial/ti_draft_layer.py`, `spatial/spatial_hitl_overlay.py`, `04_visualiser_ti.py`, HMM draft in `07_ML_Models/`).
3. **Production TI (GAP-gated).** `04_Python_Scripts/11_gap_engine.py` is present, but per `theory.md` §5 production-grade TI depends on validated GAP + Barometric Shift. Interim path (APR + Minetti draft-TI) remains authoritative until then.

---

## 3. Per-article readiness (priority sequence)

| Article | Gold dependency | Verdict |
|---------|-----------------|---------|
| **1 — DNA of the Trail** | gramstad gold + panel | Data ready km 29–34 & 40–41; **needs HITL sign-off on km 34–40 + one `06_Visualizations/` render** |
| **5 — The Two Rulers** | matched technical vs asphalt anchor | **Ready now** on APR + Minetti draft-TI (anchors + gramstad gold both present) |
| **12 — Friction First** | friction-tier gold | **Ready** — F0–F4 tiers populated across the band |
| 4 / 6 / 7 (Kinematic_Scan, TPR, EPR) | production TI | Correctly blocked on GAP validation |

---

## 4. Requested Gemini alignment

1. **Confirm editorial launch order.** Articles 5 and 12 are unblocked today; propose leading with **Article 5** (metric literacy) then **Article 12**, holding **Article 1** for the km 34–40 adjudication + figure.
2. **Adjudication scope.** Approve treating km 34–40 Tier 3–4 metres as an operator HITL queue (not model auto-accept), consistent with memo 18 §4.
3. **Visualization spec sign-off.** Confirm the Article 1 figure contract: dark-mode, zero/halt-masked speed trace, categorical HMM draft band over continuous TI, routed to `06_Visualizations/`.
4. **Interim-TI disclosure.** Confirm public copy labels draft-era TI as Minetti-interim until the GAP module is validated, to preserve visual defensibility.

---

## 5. References

- `docs/publication_pipeline.md` — 17-article taxonomy (PR #5)
- `03_Processed_Data/spatial/sut43_terrain_ontology/align_meta.json` — sector lock + alignment
- `03_Processed_Data/spatial/gold_training_set_sut43.summary.json` — gold export coverage
- `03_Processed_Data/spatial/sut43_terrain_ontology/ground_truth_review/chunk_priority.csv` — per-chunk operator-gold triage
- `docs/memos/18_gold_hitl_low_hanging_fruit.md` — Tier ladder / deferral policy
- `docs/theory.md` §5 — TI/APR/TPR/EPR and GAP gating
