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
2. **English only** — Except immutable proper nouns (Lysefjorden, Sandnes Ultra Trail, Rogaland, Store/Lille Stokkavatnet, Hålandsvatnet, official Strava segment names).
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

## Period instructions: now → 2026-11-07 (Sub-1:40 block)

**Horizon:** Subject_A Sub-1:40 on reference course `3_sjoerslopet` (~21.25 km), target finish pace **4:44 min/km**, **race date 2026-11-07**.  
Weekly venues use **stream distance** — never project training FITs onto the 3_sjoerslopet course axis unless the session is an explicit course simulation or race day.

All periodization lives in **gitignored** `training_blueprint.local.json` / `session_metadata.local.json` / `training_compliance.local.db`. Public scripts only: `evaluate_fast_finish.py`, `log_recovery_compliance.py`, `apply_october_local_overrides.py`.

### Calendar (operator meso)

| Window | Phase | Gemini / Cursor instructions |
|--------|-------|------------------------------|
| **Now (≈2026-W36)** | Recovery | `is_recovery_week: true`. Tue = `tuesday_rest`. Wed ≈ 8.2 km. Fri 5–7 km + 80% lift. Sun ≤ 12 km, **no** fast finish. `evaluate_fast_finish` → `recovery_exempt` / N/A (not a 0.0 miss). Log via `log_recovery_compliance.py`. |
| **2026-09-13** | First post-recovery simulator | Wash FIT → tag `sunday_simulator`, `is_recovery_week: false`, `month_key: 2026-09`. Protocol: Store/Lille Stokkavatnet — base **12.5–13.5 km @ 5:35–5:50**; trigger ~**13 km** → **4:44**; hold **1.5–2 km**; carbs **45–60 g/hr**. Then `evaluate_fast_finish.py --activity-id <real_id> --write-db`. |
| **Remainder of September** | Build | Keep 4-day matrix (Tue micro / Wed recovery / Fri aerobic+lift / Sun sim). Sunday fast-finish band **1.5–2 km @ 4:44**. Every 4th week = recovery (drop fast finish). Do not invent new SQLite tables. |
| **October** | Peak race simulator | Apply local override: `python3 04_Python_Scripts/apply_october_local_overrides.py` → base **6:45** easy companion cruise; total **16–18 km** (Store Stokkavatnet + Hålandsvatnet ~16–17); finish **3–5 km @ 4:44**; **mandatory early** carbs 45–60 g/hr (longer TOF). Evaluator scores **finish only** — base pace ignored. Tag with `month_key: 2026-10`, `execution_protocol_id: 2026-10-peak`. |
| **≈2026-11-01 → 2026-11-06** | Taper | Protocol id `2026-11-taper`: volume **10–14 km**; optional short **1–2 km @ 4:44** touch only — **not** a 3–5 km peak sim. Rehearse fueling 45–60 g/hr at lower volume. Prefer freshness over new peak TOF. |
| **2026-11-07** | Race day | Race-anchor telemetry for `3_sjoerslopet` / Sub-1:40. Wash FIT into micro Parquet. Optional post-race tag for baseline vs 4:44 — **do not** treat open race effort as a weekly compliance miss. May later compare to `3_Sjoerslopet_20251108` baseline (+15.4 s/km at last 1.75 km historically). |

### Operator command pattern (after a real FIT exists)

```bash
# 1) wash FIT (existing micro pipeline)
# 2) tag activity in config/session_metadata.local.json
# 3) score (skip during recovery weeks)
python3 04_Python_Scripts/evaluate_fast_finish.py --activity-id REAL_ACTIVITY_ID --write-db
```

**Never** paste angle-bracket placeholders (`<id>`, `ACTUAL_ID_HERE`) into zsh — use the exact washed `activity_*` stem.

### Success criteria toward 2026-11-07

1. Close the race-anchor finish gap (baseline was **4:59** vs **4:44**, +15.4 s/km on `3_Sjoerslopet_20251108`).
2. September sims: hold **1.5–2 km @ 4:44** with controlled drift.
3. October peak: hold **3–5 km @ 4:44** after slow 6:45 base + early fueling.
4. Taper: protect that finish competence; no last-minute volume spike.
5. Race day: execute Sub-1:40 plan; log fueling locally only.

---

## Meso scaffold (tools)

| Artifact | Location | Commit? |
|----------|----------|---------|
| Blueprint template | `config/training_blueprint.local.example.json` | Yes (example only) |
| Session tags template | `config/session_metadata.local.example.json` | Yes (example only) |
| Operator copies | `*.local.json` | **Never** (gitignored) |
| Compliance DB | `training_compliance.local.db` | **Never** |
| `evaluate_fast_finish.py` | scores Sunday finish vs local blueprint | Yes |
| `log_recovery_compliance.py` | recovery override → `compliance_flags` | Yes |
| `apply_october_local_overrides.py` | patches local Oct base to 6:45 | Yes |

**Reject still:**

| Request | Verdict |
|---------|---------|
| `ALTER TABLE` on `anatomy_macro.db` for workouts / nutrition | **Reject** |
| Project all training FITs onto `3_sjoerslopet` course axis | **Reject** (only race-anchor / explicit sims / race day) |
| Commit body-mass / protein / pace targets to GitHub | **Reject** |
| Hard-code personal numbers in public Python | **Reject** — local blueprint only |
| Score a missing future parquet with placeholder ids | **Reject** — wait for washed FIT |

---

## Related: Stavanger Halvmarathon YoY (separate branch)

`cursor/stavanger-halvmarathon-compare-0c6a` — compare version `2026-08-31-gps-yoy`, method `operator_locked_yoy`, two route windows (km 9.60–13.10, 16.40–17.60), stable route 16,541 m.

---

## Metrics order

`APR / EAR (now)` → GAP module → **TI** → **TPR** + **EPR**

Donor product name: **Kinematic_Scan** (default).

---

## Active research goal (internal)

Sub-10:50 at Lysefjorden Inn 2027. Near-term meso horizon: **Sub-1:40 by 2026-11-07**. Sanitize personal race targets in any external-facing copy.

---

## When unsure

1. Ask: **research (public)** vs **private training (local)** before proposing files.
2. For anything before 2026-11-07 training execution → meso local JSON/DB + evaluators above.
3. Prefer architecture advice over new SQLite schemas.
