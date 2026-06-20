# Documentation Index

This repository carries **two distinct but connected plans**. Do not merge them into a single master document.

## Project layout

```
00_Core_Strategy/   Sync Log (research → Endurance_Protocol)
01_Geo_Blueprints/
02_Raw_Data/
03_Processed_Data/
04_Python_Scripts/
05_Macro_Database/
06_Visualizations/
07_ML_Models/
docs/               Research & training documentation (unnumbered)
config/
```

---

## 1. The Anatomy of Pace (Research)

**Question:** *What does the data show?*

Data science framework for deconstructing running economy in technical mountain ultras. Code, databases, and visualizations live here. When in doubt about architecture, metrics, or pipelines — these docs lead.

| Document | Purpose |
|----------|---------|
| [`master_plan.md`](master_plan.md) | Architecture, data hierarchy, Vaskemaskinen, v4.0 roadmap |
| [`theory.md`](theory.md) | Scientific foundation (Minetti, Pinnington, Giandolini, Millet) |
| [`race_ecology.md`](race_ecology.md) | Reference races for the macro database |
| [`outreach_referanselopere.md`](outreach_referanselopere.md) | Strava OAuth pitches for baseline athletes |
| [`launch_strategy.md`](launch_strategy.md) | Substack, Instagram, Ghost Authority, data-donation model |

**Also (outside `docs/`):**

| Path | Purpose |
|------|---------|
| [`00_Core_Strategy/Sync_Logg_Analyse_til_Praksis.md`](../00_Core_Strategy/Sync_Logg_Analyse_til_Praksis.md) | Bridge log: research findings → training changes |

---

## 2. Endurance_Protocol (Training — local only)

**Question:** *What do we do this week — and on race day?*

Internal periodization and race tactics for Subject_A & Subject_B (2026–2028). Learns from Anatomy of Pace; does not define research architecture.

| Document | Purpose |
|----------|---------|
| Local Endurance_Protocol manual *(gitignored)* | Periodization, zones, strength, milestones |
| [`lopsmanual_lfi_v2.2.md`](lopsmanual_lfi_v2.2.md) | Current LFI race manual (Master-Matrix v2.0) |
| [`lopsmanual_lfi_v2.1_historisk.md`](lopsmanual_lfi_v2.1_historisk.md) | Archived LFI manual (historical reference) |

Clinical ID ↔ identity mapping: `config/subject_registry.local.json` *(never commit)*.

---

## How they connect

```
Anatomy of Pace (research)
    → findings logged in Sync Log
        → Endurance_Protocol manual updated (local)
            → training produces FIT files & race results
                → fed back into Anatomy of Pace
```

**Rule:** Log discoveries in the Sync Log *before* updating local Endurance_Protocol docs or race manuals.
