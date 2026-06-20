# SYNC LOGG — ANALYSE TIL PRAKSIS

**Beslutningslogg: data → endring i trening, ernæring eller kode.**

Regel (fra `master_plan.md` §8): Logg *før* lokale private treningsdokumenter oppdateres. **Publiser aldri** Sync Log-innhold eller Seig og Kjapp under The Anatomy of Pace.

**Teknikk-Røntgen:** Endring i obligatorisk donor-leveranse (nytt panel, ny versjon) loggføres her *før* outreach-pitches eller genereringsskript oppdateres. Se `docs/theory.md` §6.

---

## Mal for nye oppføringer

```markdown
### YYYY-MM-DD — [Kort tittel]

**Kilde:** (skript / løp / visualisering)
**Funn:**
**Konsekvens:** (trening / ernæring / kode / utstyr)
**Status:** [ ] Venter  [ ] Implementert  [ ] Avvist
```

---

## Logg

### 2026-06-20 — Subject_B Seed Matrix: 5k tartan calibration (Gemini directive)

**Kilde:** Gemini handoff — Telemetry Calibration Directive
**Funn:** Subject_B lacks a dedicated `Asphalt_Anchor`. APR/TI denominators were floating without a frictionless baseline. `Asphalt_Anchor_Proxy` synthesis **halted**.
**Konsekvens:**
- `seed_matrix.py` + `config/seed_matrix.local.json` — per-subject locked anchors
- `01_vaskemaskinen.py --calibration-5k` — ingest paired tartan `.fit` (Subject_A pacer + Subject_B)
- `02_terrengindeks.py`, `11_gap_engine.py`, `08_kinematic_scan.py` — resolve anchor via Seed Matrix
- **After Stadion 5k:** run wash → validate → `--lock-subject-b` before Subject_B terrain APR/TI
**Status:** [x] Pipeline ready  [ ] Calibration executed  [ ] Anchor locked

### 2026-06-20 — Teknikk-Røntgen som donor-leveranse

**Kilde:** Dokumentavklaring
**Funn:** TPR/EPR/EAR gjelder enhver analysert utøver — ikke bare én intern subjekt. Donor `.fit` byttes mot personlig Teknikk-Røntgen (varmekart, svarte hull, kollaps, TPR/EPR-paneler). Referanseløpere får samme produkt + pacing-budsjett; kalibrerer samtidig Baseline TI.
**Konsekvens:** Pipeline må produsere donor-rapporter (`06_Visualizations/` eller Streamlit v4). Elite-recruitment er gjensidig, ikke ensidig datauttak.
**Status:** [x] Implementert (docs)

### 2026-06-20 — APR/TI/TPR/EPR definert

**Kilde:** Dokumentavklaring
**Funn:** APR (implementert) ≠ TI (krever GAP). TPR = utøver vs løype (Baseline TI). EPR/EAR = utøver vs navngitt elite når parret `.fit` finnes.
**Konsekvens:** Benchmark-scripts er EAR i dag; rename/label i kode ved neste refactor. EPR aktiveres etter GAP + elite Strava-tokens.
**Status:** [x] Implementert (docs)

### 2026-06-20 — Prosjektoppsett

**Kilde:** Init
**Funn:** Makro-DB har 386 LFI 2026-resultater med splittider. Mikro-pipeline beregner **APR** (pace vs asfalt @ iso-HR), ikke **TI** (krever GAP). Benchmark-scripts kjører på FIT.
**Konsekvens:** Neste steg: GAP-pipeline → TI → TPR. Inntil da: Seed Matrix + APR på asfaltanker.
**Status:** [ ] Venter
