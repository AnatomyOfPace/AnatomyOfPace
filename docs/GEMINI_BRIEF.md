# Gemini Brief — The Anatomy of Pace

**Paste this into Gemini at session start.** Full context: [`GEMINI_HANDOFF.md`](GEMINI_HANDOFF.md).  
**Date:** 2026-08-31  
**Public owner:** Dr. Anatomy Pace

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
| **Meso** | Session tags, weekly compliance, training blueprint | **Not built** — local only when built |
| **Micro** | Washed FIT → Parquet (`15_fit_micro_wash.py`) | Partial |
| **Spatial** | Multi-FIT panels + HITL gold (`panel_1m.parquet`, terrain maps) | Built for key corridors |

**Macro DB = race ecology only.** Do not `ALTER TABLE` for workouts, body weight, protein/carbs, or weekly plans.

---

## Private training blueprint (redirect)

A Sub-1:40 / 4-day matrix (Tue micro / Wed recovery / Fri aerobic+lifting / Sun simulator + fast-finish) is **private**:

| Correct | Wrong |
|---------|-------|
| `config/training_blueprint.local.json` (gitignored) | Schema changes to `anatomy_macro.db` |
| `config/session_metadata.local.json` (gitignored) | Personal pace targets in public Python |
| `training_compliance.local.db` (gitignored) | Nutrition / body-comp fields in public repo |
| Future public `evaluate_fast_finish.py` reading **local** blueprint + micro Parquet | SQL on empty tables before FIT wash |

**3_sjoerslopet** in this repo = O₂ race anchor (~21.25 km) for TI calibration — **not** a weekly training planner. Project training FITs onto that course **only** when the session is an explicit race-course simulation.

Findings that change training → Sync Log → private manual. Never reverse-publish.

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

1. Read [`GEMINI_HANDOFF.md`](GEMINI_HANDOFF.md) §5.1 and §13.1 for meso/blueprint boundaries.
2. Prefer high-level architecture advice over inventing new SQLite schemas.
3. Ask whether the request is **research (public)** or **private training (local)** before proposing files.
