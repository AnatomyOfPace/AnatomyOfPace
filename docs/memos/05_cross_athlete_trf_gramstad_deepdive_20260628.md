# Cross-Athlete TRF Deep-Dive — gramstad_band km 29–41

**Laboratory:** The Anatomy of Pace · **Authority:** Dr. Anatomy Pace  
**Date:** 2026-06-28 · **Axis:** `ref_chainage_m` (spine panel)  
**Subjects:** Subject_A vs Subject_B · **Corridor:** gramstad_band (SUT_43 km 29–41)

---

## Executive summary

- **11,998 paired metres** on `ref_chainage_m`; mean |ΔTI gap| = **0.39** (A−B residual); 26% of metres exceed |ΔTI| > 0.5.
- **Largest gaps are behavioral, not terrain:** top two contiguous hotspots (km 30.38–30.44, km 33.07–33.12) show **Subject_A-only stops** while Subject_B continues — TRF must exclude these windows.
- **Genuine cross-athlete terrain deltas** concentrate on **operator-gold locked tiers**: chunk_02 bedrock S4/F3 (km ~31.8), Vassfjellet muddy/bog S6/F4 (km ~37.7–38.0), and post-stile asphalt tail (km ~39.2).
- **Four variance-gap spans** (km 29.28–30.0 partial, 36.6–36.72, 36.89–37.0, 38.0–39.135) carry deferred operator guidance — cross-athlete |ΔTI| here reflects **tier uncertainty**, not skill gap.
- **Kinematic anchors:** drink CP (34.64) is well-aligned post-spine (|ΔTI| ≈ 0.15); food CP and STILE-31 show stop asymmetry requiring TRF exclusion; Paradisskaret (39.135) shows Subject_B elevated ΔTI on locked S2/F3 gravel.

---

## Hotspot table (top 10 by mean |ΔTI gap|)

| Rank | ref_chainage km | S/F (operator gold) | mean \|ΔTI\| | ΔTI gap (A−B) | Classification | Recommendation |
|------|-----------------|---------------------|--------------|---------------|----------------|----------------|
| 1 | 30.383–30.435 | S4/F3 | 1.875 | −1.875 | **Behavioral** | TRF exclude — Subject_A-only stop (44 m) in rocky core; Subject_B through-hiking |
| 2 | 33.073–33.115 | S4/F3 | 1.798 | +1.798 | **Behavioral** | TRF exclude — Subject_A-only stop (32 m) at granite transition |
| 3 | 31.800–31.899 | S4/F3 | 1.223 | +1.203 | **Terrain-driven** | Genuine cross-athlete delta — chunk_02 bedrock lock; stop asym 17% |
| 4 | 39.200–39.299 | S1/F0 | 1.164 | −1.164 | **Terrain-driven** | Genuine delta — Subject_B higher ΔTI on asphalt tail post-stile |
| 5 | 37.700–37.799 | S6/F4 | 1.013 | +1.013 | **Terrain-driven** | Genuine delta — Vassfjellet muddy trail (chunk_08); both hiking |
| 6 | 38.100–38.199 | — (variance gap) | 0.979 | −0.974 | **Tier uncertainty** | Tier lock needed — spans operator deferred guidance km 38.0–39.135 |
| 7 | 37.900–37.999 | S5/F4 | 0.968 | +0.876 | **Terrain-driven** | Genuine delta — rocky-muddy descent (chunk_08 tail) |
| 8 | 38.629–38.753 | S2/F3 | 0.927 | +0.927 | **Tier uncertainty** | Tier lock needed — Paradisskaret gravel approach inside variance gap |
| 9 | 33.400–33.499 | S4/F3 | 0.820 | −0.745 | **Terrain-driven** | Genuine delta — high-friction trail post gravel crossing |
| 10 | 33.200–33.299 | S5/F3 | 0.807 | −0.807 | **Behavioral** | TRF exclude — asymmetric stops (31%) at exposed granite band entry |

---

## Kinematic anchor findings

| Anchor | ref_chainage km | Operator gold | mean \|ΔTI gap\| | Stop pattern | Verdict |
|--------|-----------------|---------------|------------------|--------------|---------|
| **food_cp** | 30.52 | S3/F2 (ease pre-CP) | 0.630 | A-only 64 m, B-only 5 m, both 14 m | **TRF exclude** — Subject_A dominant stop cluster; stream-km offset B +298 m |
| **STILE-31** | 31.16 | S4/F3 (bedrock lock) | 0.439 | both 23 m, A-only 45 m | **TRF exclude** — behavioral_exclusion_only anchor; co-wait partially confirmed |
| **drink_cp** | 34.64 | S2/F1 (Gramstad gravel) | 0.151 | A stop 34.64–34.68, B stop 34.59–34.68 (overlap) | **Baseline/pacing** — spine alignment good; residual noise only |
| **Paradisskaret** | 39.135 | S2/F3 (gravel→stile) | 0.703 | B-only 11 m, A-only 1 m; 50% variance gap | **Mixed** — Subject_B higher ΔTI (0.50 vs 0.12); tier lock + TRF exclude B-only stop metres |

---

## Actionable recommendations

1. **TRF exclude** all metres with single-athlete stop asymmetry >25% in CP corridors (food 30.35–30.85, drink 34.55–35.05) and STILE-31 window (31.10–31.50).
2. **Tier lock priority:** variance-gap spans km 38.0–39.135 (Paradisskaret gravel approach) before interpreting cross-athlete residuals downstream of Vassfjellet.
3. **Genuine training focus:** chunk_02 bedrock S4/F3 km 31.0–33.2 (especially km 31.8 band) — Subject_A lower ΔTI on locked tier; chunk_08 bog/mud km 37.4–38.0 — Subject_B elevated friction tax.
4. **Do not use Subject_B kinematics** as terrain authority in km 30.0–30.35 rocky core (operator gold note confirmed by A-only stop artifact).
5. **Drink CP anchor validated** — ref_chainage spine resolves stream-km offset; cross-athlete TRF usable on Gramstad gravel S2/F1 km 34.6–36.3 excluding stop windows.

---

*Inputs: `cross_athlete_trf_summary.json`, `panel_race_1m_spine.parquet`, `training_residual_Subject_{A,B}.parquet`, `config/spatial_terrain_map_sut43.json` operator gold spans, `reference_spine_meta.json` kinematic anchors.*
