# Documentation Index

**Public project:** *The Anatomy of Pace* — Principal Investigator: **Dr. Anatomy Pace**

Private training periodization is **not** part of this repository's public scope and must never be published. See [`brand_identity.md`](brand_identity.md).

---

## Project layout

```
01_Geo_Blueprints/
02_Raw_Data/
03_Processed_Data/
04_Python_Scripts/
05_Macro_Database/
06_Visualizations/
07_ML_Models/
docs/               Research documentation (unnumbered)
config/
```

---

## The Anatomy of Pace (Research — public)

**Question:** *What does the data show?*

Data science framework for deconstructing running economy in technical mountain ultras. Code, databases, and visualizations live here. When in doubt about architecture, metrics, or pipelines — these docs lead.

| Document | Purpose |
|----------|---------|
| [`brand_identity.md`](brand_identity.md) | Public owner (Dr. Anatomy Pace), Ghost Authority, scope firewall |
| [`theory.md`](theory.md) | Scientific foundation (Minetti, Pinnington, Giandolini, Millet) |
| [`race_ecology.md`](race_ecology.md) | Reference races for the macro database |
| [`donor_pipeline_architecture.md`](donor_pipeline_architecture.md) | Strava intake, Kinematic_Scan tiers, donor deliverable architecture |
| [`hitl_annotator.md`](hitl_annotator.md) | Human-in-the-loop terrain ontology annotator runbook |
| [`corridor_lock_policy.md`](corridor_lock_policy.md) | Geographic corridor lock and version policy |
| [`GEMINI_BRIEF.md`](GEMINI_BRIEF.md) | Paste-ready Gemini session brief |
| [`GEMINI_HANDOFF.md`](GEMINI_HANDOFF.md) | Internal Gemini handoff (status + layer boundaries) |

Meso (private) templates — copy to gitignored `*.local.json` / `*.local.db`, never publish:

| Template | Purpose |
|----------|---------|
| [`config/training_blueprint.local.example.json`](../config/training_blueprint.local.example.json) | 4-day Sub-1:40 matrix + fast-finish progression |
| [`config/session_metadata.local.example.json`](../config/session_metadata.local.example.json) | `activity_id` → session_type tags |

---

## Local-only (never GitHub / never public)

| Item | Notes |
|------|-------|
| Private training manual | Local operators — **not** under The Anatomy of Pace |
| `config/subject_registry.local.json` | Real-name ↔ Subject ID mapping |
| `02_Raw_Data/**/*.fit` | Personal telemetry |
| `03_Processed_Data/**/*.parquet` | Subject-aligned processed telemetry |
| `06_Visualizations/reports/` | Private donor PDFs with real names |
| `docs/memos/`, `00_Core_Strategy/` | Internal collaboration and Sync Log |
| `docs/master_plan.md`, `docs/launch_strategy.md` | Norwegian operational strategy (local) |

Clinical ID mapping template: [`config/subject_registry.example.json`](../config/subject_registry.example.json)

---

## Internal data flow (not for publication)

```
The Anatomy of Pace (research, public)
    → findings logged in Sync Log (local bridge)
        → private training manual updated (local operators only)
            → training produces FIT files & race results
                → fed back into The Anatomy of Pace pipeline
```

**Rule:** Log discoveries in the Sync Log before changing local private training docs. Never reverse-publish training content to Anatomy of Pace channels.
