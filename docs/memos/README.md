# AI Handoff & Collaboration Memos

Standalone Markdown files for attaching to Gemini, ChatGPT, or other sessions.  
**Internal use only** — not public Anatomy of Pace copy.

## Index

| Date | Subject | File | Wave / status |
|------|---------|------|---------------|
| 2026-06-25 | Project-wide AI handoff | [`01_gemini_handoff.md`](01_gemini_handoff.md) | Ongoing — update on material state change |
| 2026-06-25 | Cursor session recap | [`02_cursor_session_summary.md`](02_cursor_session_summary.md) | Session snapshot |
| 2026-06-25 | Gemini opening prompt | [`03_gemini_opening_prompt.md`](03_gemini_opening_prompt.md) | Paste-first + attach handoff |
| 2026-06-25 | Gemini context update card | [`04_gemini_context_update.md`](04_gemini_context_update.md) | Mid-thread refresh |
| 2026-06-20 | Legacy context card | [`00_gemini_context_card.md`](00_gemini_context_card.md) | Superseded by `01` / `04` |
| **2026-06-26** | **Wave 1 — Lars Ole collaboration context** | [`03_wave1_collaboration_context_20260626.local.md`](03_wave1_collaboration_context_20260626.local.md) | **Wave 1 shipped** — deliverables built; field validation pending |
| **2026-06-26** | **Triad alignment & Wave 2 horizon** | [`04_triad_alignment_wave2_20260626.local.md`](04_triad_alignment_wave2_20260626.local.md) | **Wave 2 kickoff** — operational roles locked |
| **2026-06-26** | **Wave 2 `.fit` parser architecture** | [`05_wave2_fit_parser_architecture.local.md`](05_wave2_fit_parser_architecture.local.md) | **Proposal** — scaffold pending `.fit` donor files |
| **2026-06-26** | **Cursor → Gemini post-Wave 1 handoff** | [`06_cursor_to_gemini_handoff_20260626.local.md`](06_cursor_to_gemini_handoff_20260626.local.md) | Strategy sync after Wave 1 ship |
| **2026-06-26** | **Wave 2 execution directive** | [`07_wave2_execution_directive_20260626.local.md`](07_wave2_execution_directive_20260626.local.md) | Phase 2a scaffold receipt |
| **2026-06-26** | **Wave 2 system live & cross-linked** | [`08_wave2_system_live_crosslinked_20260626.local.md`](08_wave2_system_live_crosslinked_20260626.local.md) | Phase 2a+2b live; Substack/IG linked |
| **2026-06-26** | **Surface ontology & SUT corridor stress test** | [`09_surface_ontology_implementation_plan_20260626.local.md`](09_surface_ontology_implementation_plan_20260626.local.md) | **Scaffold** — spatial A/B/C stubs; panel ingest pending Reference_Elite_D wash |
| **2026-06-26** | **SUT corridor stress test pipeline v2.0** | [`10_sut_stress_test_pipeline_v2_20260626.local.md`](10_sut_stress_test_pipeline_v2_20260626.local.md) | **v2.0** — Phases A–D (decouple + validation dashboard); SUT_160 wash still blocking E2E |
| **2026-06-26** | **SUT stress test interim path (Strava JSON)** | [`11_sut_stress_test_interim_path_20260626.local.md`](11_sut_stress_test_interim_path_20260626.local.md) | **Interim active** — corridor TI via Strava JSON; Phases A–D unchanged pending `18159079828.fit` wash |
| **2026-06-26** | **SUT43 terrain ontology experiment (Subject_A + Subject_B)** | [`12_sut43_terrain_ontology_experiment_20260626.local.md`](12_sut43_terrain_ontology_experiment_20260626.local.md) | **ACTIVE** — Tier 0 + Phase A complete; km 29–41 gramstad_band; SUT_160 stress test deferred |
| **2026-06-29** | **Phase E start-of-course ingest (km 0–8)** | [`16_phase_e_start_ingest_scope.md`](16_phase_e_start_ingest_scope.md) | **SCOPED** — HITL annotator milestone; panel ingest pending operator execution |
| **2026-06-30** | **Sparse gold ML suggestion pipeline (v0)** | [`17_sparse_gold_ml_suggestion_pipeline.md`](17_sparse_gold_ml_suggestion_pipeline.md) | **ACTIVE** — CLI build/train/suggest; Streamlit HITL parked |
| **2026-06-30** | **SUT_43 gold HITL low-hanging fruit** | [`18_gold_hitl_low_hanging_fruit.md`](18_gold_hitl_low_hanging_fruit.md) | **ACTIVE** — Tier 1–3 priority list; km 22–41 fully golded; KEEP QC first |
| **2026-06-30** | **Dual ontology — telemetry clusters (O₁/O₂ bridge)** | [`19_dual_ontology_telemetry_clusters.md`](19_dual_ontology_telemetry_clusters.md) | **ACTIVE** — v0 `build_telemetry_clusters.py`; Paradisskaret + road anchors |
| **2026-06-30** | **O₂ anchor run signature library** | [`20_anchor_run_signature_library.md`](20_anchor_run_signature_library.md) | **ACTIVE** — manifest + `build_anchor_features.py`; pole_policy per run |
| **2026-06-30** | **O₂ anchor run signature library** | [`20_anchor_run_signature_library.md`](20_anchor_run_signature_library.md) | **SCOPED** — manifest + `build_anchor_features.py`; 3 extra runs + Paradisskaret calibration set |
| **2026-07-01** | **Publication pipeline readiness (Gemini handoff)** | [`22_publication_pipeline_readiness.local.md`](22_publication_pipeline_readiness.local.md) | **RECONCILED (local-only)** — 17-article taxonomy committed (PR #5); gramstad_band gold ready km 29–34 & 40–41; km 34–40 HITL + Article 1 render outstanding |

## Naming convention

| Pattern | Use |
|---------|-----|
| `NN_topic_YYYYMMDD.local.md` | **Private** operator memos (real names OK) — gitignored |
| `NN_topic.md` | Sanitized memos safe to commit if ever needed publicly |

Files with `.local` in the name are never pushed to GitHub.

## How to download

- **Finder:** open this folder and copy the `.md` files anywhere, or attach directly in Gemini.
- **Path:** `Anatomy_of_Pace/docs/memos/`

## Update policy

- **Project state:** update `01_gemini_handoff.md` when pipeline, metrics, or blockers change materially.
- **Session recap:** append or replace blockers in `02_cursor_session_summary.md`.
- **Collaboration context:** add dated `.local.md` memos per donor wave; index here.

Legacy path `docs/GEMINI_HANDOFF.md` redirects here.
