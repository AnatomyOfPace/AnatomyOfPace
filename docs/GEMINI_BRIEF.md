# Gemini Brief — The Anatomy of Pace

**Paste this into Gemini at session start.** Full context: [`GEMINI_HANDOFF.md`](GEMINI_HANDOFF.md).  
**Date:** 2026-08-31  
**Public owner:** Dr. Anatomy Pace  
**Branch (meso scaffold):** `cursor/meso-fast-finish-eval-0c6a` (PR #26)

---

## Role

Assist on *The Anatomy of Pace* research lab: telemetry pipelines, TI/TPR/EPR metrics, spatial HITL, race ecology. Attribute public work to **Dr. Anatomy Pace**. Never publish private training content under this brand.

---

## Hard rules

1. **Ghost Authority** — Clinical IDs only: `Subject_A`, `Reference_Elite_A`, … No personal names, no private training titles, no operator pronouns (I/we/my) in external copy.
2. **English only** — Except immutable proper nouns (Lysefjorden, Sandnes Ultra Trail, Rogaland, official Strava segment names).
3. **APR ≠ TI** — APR is interim iso-HR pace ratio. TI is `v_actual / v_GAP` (friction beyond grade). Do not conflate.
4. **Do not commit** unless the operator explicitly asks. Never commit `.fit`, `.db`, `panel_1m.parquet`, or `subject_registry.local.json`.

---

## Architecture (do not mix layers)

| Layer | What it holds | Status |
|-------|---------------|--------|
| **Macro** | Race results (`anatomy_macro.db`: `races`, `athletes`, `race_results`) | Partial |
| **Meso** | Session tags, weekly compliance, training blueprint | **Scaffold live** — local only |
| **Micro** | Washed FIT → Parquet (`15_fit_micro_wash.py`) | Partial |
| **Spatial** | Multi-FIT panels + HITL gold (`panel_1m.parquet`, terrain maps) | Built for key corridors |

**Macro DB = race ecology only.** Do not `ALTER TABLE` for workouts, body weight, protein/carbs, or weekly plans.

---

## Meso scaffold (built 2026-08-31) — confirmed on operator Mac

| Artifact | Location | Commit? |
|----------|----------|---------|
| Blueprint template | `config/training_blueprint.local.example.json` | Yes (example only) |
| Session tags template | `config/session_metadata.local.example.json` | Yes (example only) |
| Operator copies | `*.local.json` | **Never** (gitignored) |
| Compliance DB init | `04_Python_Scripts/init_training_compliance_local.py` | Yes |
| Compliance DB file | `training_compliance.local.db` | **Never** (gitignored) |
| Fast-finish evaluator | `04_Python_Scripts/evaluate_fast_finish.py` | Yes (reads local config only) |
| Recovery override logger | `04_Python_Scripts/log_recovery_compliance.py` | Yes — inserts `compliance_flags` only |
| Unit tests | `04_Python_Scripts/test_evaluate_fast_finish.py` | Yes — recovery_exempt + flag insert |

**Recovery week (current):** top-level `is_recovery_week: true`; Sunday note *"Sunday capped at 12 km, no fast finish."*; next standard simulator FIT **2026-09-13**.

**2026-09-13 execution protocol (private blueprint):** Store/Lille Stokkavatnet — base 12.5–13.5 km @ 5:35–5:50; trigger ~13 km → 4:44; hold 1.5–2 km depleted; carbs 45–60 g/hr. Stream distance only (not 3_sjoerslopet projection). Encoded in `training_blueprint.local.example.json` → `execution_protocols.2026-09-13`.

**2026-10 peak simulator (private blueprint):** Store Stokkavatnet + Hålandsvatnet — total 16–18 km (combo ~16–17); base 11–15 km @ 5:35–5:50; fast finish **3–5 km @ 4:44** depleted; mandatory early carbs 45–60 g/hr (expanded finish vs September). → `execution_protocols.2026-10-peak`.

**First live eval (Subject_A):** activity `3_Sjoerslopet_20251108` tagged `sunday_simulator`.

| Field | Result |
|-------|--------|
| Stream distance | 21.25 km |
| Fast-finish window | 1.75 km (2026-09 progression midpoint) |
| Median finish pace | 4:59 min/km |
| Target | 4:44 min/km |
| Delta | +15.4 s/km |
| Cardiac drift | +6.2 bpm |
| Compliance | 0.0 / not held |

**Interpretation for Gemini:** This was **race-anchor** telemetry used as a Sub-1:40 finish baseline, not a weekly Sunday sim miss. Score zeros when pace delta ≥ ~3× tolerance (5 s/km). Do not propose writing these personal targets into `anatomy_macro.db`.

**Reject still:**

| Request | Verdict |
|---------|---------|
| `ALTER TABLE` on `anatomy_macro.db` for workouts / nutrition | **Reject** |
| Project all training FITs onto `3_sjoerslopet` course axis | **Reject** (only race-anchor / explicit sims) |
| Commit body-mass / protein / pace targets to GitHub | **Reject** |
| Extend `evaluate_fast_finish.py` with hard-coded personal numbers | **Reject** — keep reading local blueprint |

---

## Related: Stavanger Halvmarathon YoY (separate branch)

`cursor/stavanger-halvmarathon-compare-0c6a` — compare version `2026-08-31-gps-yoy`, method `operator_locked_yoy`, two route windows (km 9.60–13.10, 16.40–17.60), stable route 16,541 m. F0/F1 substrate bands show modest speed gains YoY.

---

## Metrics order

`APR / EAR (now)` → GAP module → **TI** → **TPR** + **EPR**

Donor product name: **Kinematic_Scan** (default).

---

## Key paths

| Path | Role |
|------|------|
| `docs/master_plan.md`, `docs/theory.md`, `docs/brand_identity.md` | Source of truth |
| `docs/GEMINI_HANDOFF.md` | Full status + HITL detail |
| `04_Python_Scripts/` | All scripts; spatial HITL under `spatial/` |
| `06_Visualizations/` | Charts / report PNGs |
| `config/spatial_*.json` | Align manifests + terrain maps |

---

## Active research goal (internal)

Sub-10:50 at Lysefjorden Inn 2027. Sanitize personal race targets in any external-facing copy.

---

## When unsure

1. Prefer high-level architecture advice over inventing new SQLite schemas.
2. Ask whether the request is **research (public)** or **private training (local)** before proposing files.
3. Meso work → local blueprint / compliance DB / `evaluate_fast_finish.py` only.
