# Gramstad Band Lock Wave — km 34–40

**Laboratory:** The Anatomy of Pace · **Authority:** Dr. Anatomy Pace  
**Date:** 2026-07-01 · **Corridor:** SUT_43 gramstad_band (km 34–40)

---

## Executive summary

Operator gold spans already covered **100% of course metres** km 34.0–40.0 in `config/spatial_terrain_map_sut43.json` before this wave. The gap was **ledger formalization**: missing `locked_at` timestamps on six spans and stale `chunk_priority.csv` rows showing partial coverage.

This wave:

1. Added `locked_at: 2026-07-01` to spans missing timestamps (km 34.0–34.6 trail, km 37.0–38.0 Vassfjellet band, km 39.14–40.0 asphalt tail).
2. Updated `chunk_priority.csv` notes and metrics to **100% operator gold** for chunks 05–10.
3. Re-ran `hitl_nti_consistency.py --apply-gaps` km 34–38 (variance-gap deferrals on conflicting manual overrides).
4. Re-ran `hitl_chunk_triage.py` — chunk_05/06 remain **GREEN**; chunk_08 remains top **RED** (high HMM/NTI uncertainty despite gold labels).

---

## Chunk status after wave

| Chunk | km | Operator gold | Triage queue |
|-------|-----|---------------|--------------|
| chunk_05 | 34–35 | 100% | GREEN |
| chunk_06 | 35–36 | 100% | GREEN |
| chunk_07 | 36–37 | 100% | YELLOW |
| chunk_08 | 37–38 | 100% | **RED** (RPS 0.82) |
| chunk_09 | 38–39 | 100% | YELLOW |
| chunk_10 | 39–40 | 100% | YELLOW |

**Note:** RPS reflects telemetry disagreement and HMM uncertainty — not label coverage. chunk_08 RED is expected on wet-forest / bog corridor until cross-athlete NTI σ drops or reference-elite corroboration is available.

---

## Next priority

1. **chunk_08 field/topo QC** — validate Vassfjellet muddy-trail S6/F4 band against operator field notes; RED queue persists until kinematic divergence eases.
2. **Mid-course panel bridge** — km 8.0–21.9 spine rebuild (telemetry gap between Phase E start and Dale upstream).
3. **GAP module** — unlock production TI once ontology density is sufficient km 22–41.

---

*Internal memo — not public Anatomy of Pace copy.*
