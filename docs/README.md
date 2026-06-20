# Documentation Index

**Public project:** *The Anatomy of Pace* — Principal Investigator: **Dr. Anatomy Pace**

Private training periodization (*Seig og Kjapp*) is **not** part of this repository's public scope and must never be published. See [`brand_identity.md`](brand_identity.md).

---

## Project layout

```
00_Core_Strategy/   Sync Log (research → local training application)
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
| [`master_plan.md`](master_plan.md) | Architecture, data hierarchy, Vaskemaskinen, v4.0 roadmap |
| [`theory.md`](theory.md) | Scientific foundation (Minetti, Pinnington, Giandolini, Millet) |
| [`race_ecology.md`](race_ecology.md) | Reference races for the macro database |
| [`outreach_referanselopere.md`](outreach_referanselopere.md) | Strava OAuth pitches for baseline athletes |
| [`launch_strategy.md`](launch_strategy.md) | Substack, Instagram, Ghost Authority, data-donation model |

**Also (outside `docs/`):**

| Path | Purpose |
|------|---------|
| [`00_Core_Strategy/Sync_Logg_Analyse_til_Praksis.md`](../00_Core_Strategy/Sync_Logg_Analyse_til_Praksis.md) | Bridge log: research findings → *local* training updates *(never publish)* |

---

## Race manuals (course intelligence — public research asset)

Tactical terrain matrices for reference races. These describe **courses**, not private athletes.

| Document | Purpose |
|----------|---------|
| [`lopsmanual_lfi_v2.2.md`](lopsmanual_lfi_v2.2.md) | Current LFI race manual (Master-Matrix v2.0) |
| [`lopsmanual_lfi_v2.1_historisk.md`](lopsmanual_lfi_v2.1_historisk.md) | Archived LFI manual (historical reference) |

---

## Local-only (never GitHub / never public)

| Item | Notes |
|------|-------|
| `docs/seig_og_kjapp.md` | Private training project — **not** under The Anatomy of Pace |
| `config/subject_registry.local.json` | Real-name ↔ Subject ID mapping |
| `02_Raw_Data/**/*.fit` | Personal telemetry |
| `06_Visualizations/reports/` | Private donor PDFs with real names |

Clinical ID mapping template: [`config/subject_registry.example.json`](../config/subject_registry.example.json)

---

## Internal data flow (not for publication)

```
The Anatomy of Pace (research, public)
    → findings logged in Sync Log (local bridge)
        → private training manual updated (Seig og Kjapp — local only)
            → training produces FIT files & race results
                → fed back into The Anatomy of Pace pipeline
```

**Rule:** Log discoveries in the Sync Log before changing local private training docs. Never reverse-publish training content to Anatomy of Pace channels.
