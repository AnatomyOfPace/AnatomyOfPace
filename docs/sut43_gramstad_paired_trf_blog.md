# Same Metres, Different Tax: Paired Residual Analysis on Sandnes Ultra Trail

**The Anatomy of Pace** · Dr. Anatomy Pace  
**Status:** Publication draft (Ghost Authority safe) · **Case:** SUT_43 `gramstad_band` km 29–41  
**Identifiers:** `Subject_A`, `Subject_B` only

---

## Summary

Commercial grade-adjusted pacing treats an ultra as a single efficiency problem. Telemetry from two race-day athletes on **Sandnes Ultra Trail (SUT_43)** shows a sharper structure: excess **terrain tax** concentrates on **locked friction tiers**, not uniformly across the lap. Using the laboratory’s **Training Residual Framework (TRF)**—observed Terrain Index minus cohort expectation on the same friction tier, grade band, and locomotion mode—**Subject_A** pays substantial residual tax on **F3 technical descents** while **Subject_B** sits below cohort on the same cell geometry. Full-lap aggregation masks the signal; a **gramstad_band** window (km 29–41) and a **bedrock / late_braking** slice (km 31.08–33.80) sharpen it further. Both athletes remain efficient on **F2 gravel descents**. The finding is **diagnostic**, not a public ranking—and it does not yet invoke reference-elite proficiency ratios.

---

## 1. The paradox

When two athletes finish the same 43 km Rogaland ultra, summary statistics often collapse performance into one narrative: fit or unfit, fast or slow. Grade-Adjusted Pace (GAP) offers a single correction for hills on a conceptual smooth belt. It does not encode surface friction, line choice, or eccentric braking on bedrock steps.

The laboratory’s **Terrain Index (TI)** measures friction *beyond* what Minetti-grade physics already explains, using an asphalt anchor at matched effort. Even TI, taken as one session mean, blends:

- intrinsic course friction (the terrain’s “tax rate”),
- athlete skill on that tread,
- fatigue and state,
- and sensor noise.

**Training residuals** ask a narrower question: *on this exact tier of tread, this grade, this locomotion mode, how much more or less TI did the athlete pay than cohort expectation?*

---

## 2. What grade adjustment misses

On trail, observed pace diverges from treadmill-grade fiction because:

| GAP assumes | Trail adds |
|-------------|------------|
| Smooth belt kinematics | Root grip, rock, bog extraction |
| Grade-only metabolic cost | Eccentric braking on technical descents |
| Steady effort | Hike–run transitions and line-choice tax |

TRF formalises the decomposition:

```text
ΔTI = TI_athlete − median(TI | friction_tier, grade_band, locomotion_mode)
```

Friction tiers **F0–F4** come from operator-locked ontology spans on the course axis—not from a commercial surface label. Locomotion mode (hike vs run) is classified per subject kinematics. Where aid-station halts, co-waits, or asymmetric stops dominate, those metres are masked from paired comparison.

This is **Phase B** TRF: cohort median baseline on a **two-athlete race panel**. It is exploratory, not a population norm.

---

## 3. Method

| Element | Specification |
|---------|----------------|
| **Race** | SUT_43, April 2026 edition (stream-distance course km) |
| **Analysis window** | `gramstad_band` km **29.0–41.0**; corridor slice km **31.0–34.0** |
| **Athletes** | `Subject_A`, `Subject_B` — race-day finisher telemetry |
| **Alignment** | Shared reference spine (`ref_chainage_m`) for cross-athlete comparison |
| **Ground truth** | Operator gold friction tiers on `config/spatial_terrain_map_sut43.json` |
| **Baseline** | Cohort median (Subject_A + Subject_B, same window) |
| **Exclusions** | Food/drink CP corridors, STILE-31 co-wait, single-athlete halt asymmetry |

**Not in scope for this case:** reference-elite **EPR** (no distinct elite paired stream on this race), iso-HR cardiovascular drift where heart rate was absent, or inferential statistics beyond **n = 2**.

---

## 4. Finding A — full lap dilutes the signal

Aggregating TRF across km 0.5–43 merges every **F3 · downhill · hike** metre into one cell spanning roughly km 4.5–39. For **Subject_A**, that cell shows **ΔTI ≈ +0.08**—easy to dismiss as noise.

Re-running TRF on the **gramstad_band** window alone (km 29–41) raises the same cell to **ΔTI ≈ +0.68** on km **29.82–39.14** (cell terminates at the asphalt transition near km 39.14).

**Interpretation:** window choice is part of the measurement. Full-race heatmaps screen; sector windows prescribe.

![Friction tier strip km 29–39](../06_Visualizations/sut43_gramstad_friction_strip_blog.png)

*Figure 1. Locked friction tiers on the gramstad_band spine. Vertical markers: bedrock onset (~km 31), late_braking core (~km 33.2), asphalt onset (km 39.14).*

![Dilution effect](../06_Visualizations/sut43_trf_dilution_blog.png)

*Figure 2. Subject_A — F3 · downhill · hike: full-race ΔTI vs gramstad-only ΔTI. Sector localization amplifies the residual.*

---

## 5. Finding B — paired same-metre geometry

On the shared spine, **F3 · downhill · hike** occupies nearly the same course shell for both athletes:

| Athlete | km span (F3 DH hike) | ΔTI vs cohort |
|---------|----------------------|---------------|
| **Subject_A** | 29.82 – 39.14 | **+0.68** |
| **Subject_B** | 29.55 – 39.14 | **−0.18** |

**Cell-key gap (A − B) ≈ +0.86.** Spine-wide cross-athlete summary over km 29–41 reports mean **ΔTI gap (A − B) ≈ +0.40**, including all tier × grade × mode cells—not only F3 descents.

This is not “Subject_A is slow.” On identical ontology geometry, **Subject_A overpays terrain tax on F3 technical descents under hike locomotion**; **Subject_B extracts speed below cohort expectation on the same cell key.**

![Paired residuals](../06_Visualizations/sut43_gramstad_paired_trf_blog.png)

*Figure 3. Paired ΔTI by cell key, gramstad_band km 29–41. Both athletes sit below cohort on F2 gravel descents; divergence concentrates on F3.*

### Geographic anchors (km 29–39)

| km | Sector |
|----|--------|
| 29.4–30.0 | Gramstad entry — rocky approach |
| 30.1–30.35 | Technical rocky core |
| **31.0–33.8** | **Bedrock band** (operator-locked S4/F3) |
| **33.2–33.8** | **`late_braking`** technical core |
| 34.0–36.7 | Gravel/dirt rollers (mostly F2) |
| 36.7–39.1 | Vassfjellet approach → Paradisskaret forest tread |
| 39.14+ | Asphalt finish band (excluded from F3 DH cell) |

---

## 6. Finding C — bedrock corridor sharpens the hotspot

Restricting TRF to km **31.0–34.0** (bedrock + `late_braking`) targets the densest F3 descent material:

| Cell | Subject_A | Subject_B |
|------|-----------|-----------|
| **F3 · downhill · hike** | **ΔTI +0.97** · km **31.08–33.80** · 955 m | **ΔTI −0.12** · 4,422 m |
| F3 · uphill · hike | +0.23 | +0.07 |
| F2 · downhill · hike | −0.45 | −1.03 (202 m — small cell) |

The corridor slice raises **Subject_A**’s F3 downhill residual from **+0.68** (gramstad) to **≈ +0.97** on the **tightest bedrock span**—the trainable hotspot for mesocycle design.

**Relative strength:** on **F2 · downhill · hike** across gramstad, both athletes sit **below** cohort (negative ΔTI). The race-day story is **tier-asymmetric**: weak on **F3 bedrock brakes**, efficient on **F2 gravel brakes**.

**Training misread:** more generic downhill volume.  
**Training read aligned to telemetry:** eccentric control and line choice on **operator-locked F3 descents** km **31–34**; preserve F2 gravel efficiency.

---

## 7. Limitations

1. **Cohort n = 2.** Residuals rank cells for diagnostic focus; they do not support population inference.  
2. **Not reference-elite EPR.** Subject_B is an internal paired reference, not a recruited elite proficiency anchor.  
3. **Hike-dominant window** (~89–93% hike in gramstad). Run-mode cells exist but are secondary.  
4. **Metre counts differ within cells** (e.g. 955 vs 4,422 F3 DH metres in km 31–34) due to locomotion classification and grade-bin assignment—not proof of different routes on the paired spine.  
5. **Single race edition** on stream-distance km; cross-year pairing assumptions apply if extended.  
6. **QC cells** (e.g. F0 downhill artefacts on small spans) are excluded from narrative claims.

---

## 8. Laboratory implication

Sandnes Ultra Trail is not only a GPX polyline. It is a **friction ontology**: operator-locked tiers on a course axis. Paired residuals convert Kinematic_Scan heatmaps into **cell keys** (`F3 · downhill · hike`) that survive contact with training focus.

The next maturity step—**ΔTI against Baseline TI / TFI_expected** when reference-elite streams enter the panel—does not invalidate this case. It extends the same decomposition with course-level expected tax instead of a two-athlete cohort.

---

## Pull quote

> On the same bedrock descent metres, one athlete paid **+0.97** terrain tax above cohort; the other banked **−0.12**. The trail did not treat them equally—their **friction signatures** did not either.

---

## Publication checklist (operator)

- [ ] Embed Figure 1–3 from `06_Visualizations/sut43_*_blog.png`  
- [ ] Ghost Authority scan: zero personal names; clinical voice only  
- [ ] Substack header: `assets/brand/substack/`  
- [ ] Tags: terrain index, ultra running, Rogaland, biomechanics, data science  
- [ ] Internal Sync Log entry (not for publication)

---

*Draft generated by The Anatomy of Pace laboratory. Telemetry: SUT_43 race-day panel, TRF Phase B cohort median. Figures require local render via `enrich_trf_blog_v1.sh`.*
