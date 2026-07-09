# Same Metres, Different Tax: Paired Residual Analysis on Sandnes Ultra Trail

**The Anatomy of Pace** · Dr. Anatomy Pace  
**Status:** Publication draft (Ghost Authority safe) · **Case:** SUT_43 `gramstad_band` km 29–41  
**Identifiers:** `Subject_A`, `Subject_B` only

---

## Summary

In this analysis of **Sandnes Ultra Trail (SUT_43)**, paired **Training Residual Framework (TRF)** residuals are examined within a Phase B cohort (**n = 2**). Global race aggregation is shown to mask isolated biomechanical degradation. While full-lap aggregation indicated a marginal **F3 · downhill · hike** penalty for Subject_A (**ΔTI ≈ +0.08**), localized analysis within the **gramstad_band** (km 29–41) revealed severe structural friction (**ΔTI ≈ +0.68**). This penalty was further amplified within the **corridor slice** (km 31.08–33.80) to **ΔTI ≈ +0.97**. Conversely, negative residual friction was maintained by Subject_B throughout identical technical descents (**−0.18** and **−0.12**, respectively). Below-cohort residuals on **F2 gravel descents** were observed for both athletes. These findings indicate that localized technical segments inflict disproportionate, idiosyncratic friction penalties that remain obscured by full-race median metrics. The result is **diagnostic**, not a public ranking.

---

## 1. Grade-only models and the residual question

When two athletes complete the same 43 km Rogaland ultra, summary statistics often collapse performance into a single efficiency narrative. **Grade-Adjusted Pace (GAP)** applies hill correction on a conceptual smooth belt; it does not encode surface friction, root grip, eccentric braking on bedrock steps, or hike–run transition tax. The laboratory’s **Terrain Index (TI)** measures friction *beyond* Minetti-grade physics via an asphalt anchor at matched effort—but even a session mean blends intrinsic course friction, athlete-specific tread skill, fatigue, and sensor noise. **Training residuals** isolate a narrower quantity: on a fixed friction tier, grade band, and locomotion mode, the deviation of observed TI from cohort median expectation.

```text
ΔTI = TI_athlete − median(TI | friction_tier, grade_band, locomotion_mode)
```

Friction tiers **F0–F4** derive from operator-locked ontology spans on the course axis. Locomotion mode (hike vs run) is classified per subject kinematics. Aid-station halts, co-waits, and asymmetric stops are masked from paired comparison. This is **Phase B** TRF: cohort median baseline on a **two-athlete race panel**—exploratory, not a population norm.

---

## 2. Method

| Element | Specification |
|---------|----------------|
| **Race** | SUT_43, April 2026 edition (stream-distance course km) |
| **Analysis window** | `gramstad_band` km **29.0–41.0**; **corridor slice** km **31.08–33.80** (primary F3 DH span; analysis envelope km 31.0–34.0) |
| **Athletes** | `Subject_A`, `Subject_B` — race-day finisher telemetry |
| **Alignment** | Shared reference spine (`ref_chainage_m`) for cross-athlete comparison |
| **Ground truth** | Operator gold friction tiers on `config/spatial_terrain_map_sut43.json` |
| **Baseline** | Cohort median (Subject_A + Subject_B, same window) |
| **Exclusions** | Food/drink CP corridors, STILE-31 co-wait, single-athlete halt asymmetry |

**Not in scope for this case:** iso-HR cardiovascular drift where heart rate was absent, or inferential statistics beyond **n = 2**.

---

## 3. Finding A — full lap dilutes the signal

Aggregating TRF across km 0.5–43 merges every **F3 · downhill · hike** metre into one cell spanning roughly km 4.5–39. For Subject_A, that cell reports **ΔTI ≈ +0.08**—a magnitude readily dismissed as noise.

Re-running TRF on the **gramstad_band** window alone (km 29–41) elevates the same cell to **ΔTI ≈ +0.68** on km **29.82–39.14** (cell terminates at the asphalt transition near km 39.14).

**Interpretation:** window selection is part of the measurement. Full-race heatmaps screen; sector windows prescribe.

![Friction tier strip km 29–39](../06_Visualizations/sut43_gramstad_friction_strip_blog.png)

*Figure 1. Locked friction tiers on the gramstad_band spine. Vertical markers: corridor slice onset (km 31.08), corridor slice terminus (km 33.80), asphalt onset (km 39.14).*

![Dilution effect](../06_Visualizations/sut43_trf_dilution_blog.png)

*Figure 2. Subject_A — F3 · downhill · hike: full-race ΔTI vs gramstad-only ΔTI. Sector localization amplifies the residual.*

---

## 4. Finding B — paired same-metre geometry

On the shared spine, **F3 · downhill · hike** occupies nearly the same course shell for both athletes:

| Athlete | km span (F3 DH hike) | ΔTI vs cohort |
|---------|----------------------|---------------|
| **Subject_A** | 29.82 – 39.14 | **+0.68** |
| **Subject_B** | 29.55 – 39.14 | **−0.18** |

**Cell-key gap (A − B) ≈ +0.86.** Spine-wide cross-athlete summary over km 29–41 reports mean **ΔTI gap (A − B) ≈ +0.40**, including all tier × grade × mode cells—not only F3 descents.

On identical ontology geometry, elevated terrain tax on **F3 technical descents under hike locomotion** is observed for Subject_A; speed extraction below cohort expectation on the same cell key is observed for Subject_B. Performance degradation on F3 friction tiers is indicated independently of general lap-speed narrative.

![Paired residuals](../06_Visualizations/sut43_gramstad_paired_trf_blog.png)

*Figure 3. Paired ΔTI by cell key, gramstad_band km 29–41. Below-cohort residuals on F2 gravel descents are maintained by both athletes; divergence concentrates on F3.*

| km (course) | Sector | Friction context |
|-------------|--------|------------------|
| 29.4–30.0 | Gramstad entry | Rocky approach |
| 30.1–30.35 | Pre-corridor | Technical rocky core |
| **31.08–33.80** | **Corridor slice** | Operator-locked S4/F3 bedrock descent |
| 34.0–36.7 | Post-corridor rollers | Gravel/dirt (mostly F2) |
| 36.7–39.1 | Vassfjellet → Paradisskaret | Forest tread |
| 39.14+ | Finish band | Asphalt (excluded from F3 DH cell) |

---

## 5. Finding C — corridor slice sharpens the hotspot

Restricting TRF to the **corridor slice** (km **31.08–33.80**; analysis envelope km 31.0–34.0) targets the densest F3 descent material:

| Cell | Subject_A | Subject_B |
|------|-----------|-----------|
| **F3 · downhill · hike** | **ΔTI +0.97** · km **31.08–33.80** | **ΔTI −0.12** · km **31.08–33.80** |
| F3 · uphill · hike | +0.23 | +0.07 |
| F2 · downhill · hike | −0.45 | −1.03 (202 m — small cell) |

Within the corridor slice, the F3 downhill residual for Subject_A is amplified from **+0.68** (gramstad) to **≈ +0.97**—the primary diagnostic hotspot on operator-locked bedrock descent geometry.

On **F2 · downhill · hike** across gramstad, below-cohort residuals (negative ΔTI) are maintained by both athletes. A **tier-asymmetric** pattern is indicated: elevated tax on **F3** descent cells; efficient extraction on **F2** gravel descent cells. Generic downhill volume is a common misinterpretation of such telemetry; eccentric control and line choice on operator-locked **F3** descents within the corridor slice (km 31.08–33.80) are indicated by the residual structure, with F2 gravel efficiency preserved.

---

## 6. Limitations

1. **Cohort n = 2.** Residuals rank cells for diagnostic focus; population inference is not supported.  
2. **Internal paired reference only.** Subject_B serves as cohort median co-athlete, not an external proficiency anchor.  
3. **Hike-dominant window** (~89–93% hike in gramstad). Run-mode cells exist but are secondary.  
4. **Cell metre counts** in TRF JSON are deduplicated panel-row totals on `ref_chainage_m` per subject and must not exceed the analysis envelope (~3,000 m for km 31.0–34.0). Corridor tables report telemetric km bounds; metre volumes are QC-checked at render via `verify_trf_corridor_blog_cells.py`.  
5. **Single race edition** on stream-distance km; cross-year pairing assumptions apply if extended.  
6. **QC cells** (e.g. F0 downhill artefacts on small spans) are excluded from narrative claims.

---

## 7. Laboratory implication

Sandnes Ultra Trail is not only a GPX polyline. It is a **friction ontology**: operator-locked tiers on a course axis. Paired residuals convert Kinematic_Scan heatmaps into **cell keys** (`F3 · downhill · hike`) that survive contact with mesocycle design. A subsequent maturity step—**ΔTI against Baseline TI / TFI_expected** at course-level expected tax—extends the same decomposition beyond a two-athlete cohort median without invalidating this case.

---

## Pull quote

> On identical bedrock descent parameters, a **+0.97** terrain tax above the cohort median was exacted on F3 technical descent for Subject_A, whereas a **−0.12** residual was maintained by Subject_B on the same cell geometry. Divergent **friction signatures** were indicated independently of aggregate lap-speed narrative.

---

## Publication checklist (operator)

- [ ] Embed Figure 1–3 from `06_Visualizations/sut43_*_blog.png` (operator Mac — run `enrich_trf_blog_v1.sh`)  
- [x] Ghost Authority scan: PASS (`python3 04_Python_Scripts/ghost_authority_scan.py --strict docs/sut43_gramstad_paired_trf_blog.md`)  
- [ ] Paste from `docs/publications/sut43_gramstad_paired_trf_substack.md`; upload figures in Substack editor  
- [ ] Substack header: `assets/brand/substack/`  
- [ ] Tags: terrain index, ultra running, Rogaland, biomechanics, data science  
- [ ] Social preview: `assets/brand/substack/substack_social_preview_1200x630.jpg` (or figure crop)  
- [ ] Internal Sync Log entry (not for publication)

---

*Draft generated by The Anatomy of Pace laboratory. Telemetry: SUT_43 race-day panel, TRF Phase B cohort median. Figures require local render via `enrich_trf_blog_v1.sh`.*
