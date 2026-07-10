# Same Metres, Different Tax: Paired Residual Analysis on Sandnes Ultra Trail

**The Anatomy of Pace** · Dr. Anatomy Pace  
**Status:** Publication draft · **Case:** SUT_43 `gramstad_band` km 29–41  
**Identifiers:** `Subject_A`, `Subject_B` only  
**Voice:** Active, runner-facing English (Substack v2)

---

## Summary

When two runners finish the exact same 43 km trail race, their total times often hide the real story. In this post, the laboratory dives into the telemetry of two athletes on **Sandnes Ultra Trail (SUT_43)**. Looking at the entire race averages out the pain. For **Subject_A**, a full-race average showed only a tiny penalty on steep, technical descents (**ΔTI ≈ +0.08**). But zooming in on the brutal Gramstad section (km 29–41), the truth emerges: Subject_A was hit with a massive terrain tax (**ΔTI ≈ +0.68**), which spiked even higher on a specific 3 km bedrock descent (**ΔTI ≈ +0.97**, km 31.08–33.80).

Meanwhile, **Subject_B** flew down those exact same technical descents, actually gaining time against the cohort average (**−0.18** and **−0.12**). Interestingly, both runners were highly efficient on smooth gravel. The takeaway? Technical terrain taxes runners completely differently, and overall race pace is hiding specific weaknesses.

---

## 1. Why GAP lies to trail runners

If you run ultras, you probably look at Grade-Adjusted Pace (GAP) after a race. GAP corrects for hills, but it assumes you are running on a smooth treadmill. It doesn't care if you are bounding down soft gravel, braking hard on wet bedrock, or navigating a root-choked singletrack.

At **The Anatomy of Pace**, the **Terrain Index (TI)** measures the actual friction of the trail. TI looks beyond the steepness of the hill and measures how much the specific surface slows you down compared to running on flat asphalt at the exact same effort.

But even a race-day average TI isn't enough. The laboratory needs to know exactly how a runner performs on specific types of terrain (like a steep, highly technical descent) compared to what the cohort expects. That quantity is the **Training Residual**. If the residual is positive, extra terrain tax is being paid. If it is negative, time is being banked efficiently.

```text
ΔTI = TI_athlete − median(TI | friction_tier, grade_band, locomotion_mode)
```

Friction tiers **F0–F4** come from operator-locked course spans. Hike vs run is classified per athlete kinematics. Aid-station halts, co-waits, and asymmetric stops are masked from paired comparison. This is an exploratory **Phase B** cohort comparing two athletes—not a global population study.

---

## 2. The setup

| Element | The details |
|---------|-------------|
| **The race** | SUT_43, April 2026 edition |
| **The focus area** | The Gramstad window (km 29–41) and the hyper-technical corridor slice (km 31.08–33.80) |
| **The runners** | Subject_A and Subject_B (race-day finisher telemetry) |
| **The method** | Both runners aligned meter-by-meter on the exact same stretches of trail. Aid-station stops and traffic jams were removed |

*Note: Missing heart-rate data and external elite proficiency scaling are not in scope for this specific analysis.*

---

## 3. Finding A — the full-race average hides the pain

If Subject_A's performance is viewed across the entire 43 km race—combining every single technical hike downhill—the average penalty is just **+0.08**. At first glance, that looks like statistical noise. Subject_A might appear fine on descents.

But isolating the Gramstad window (km 29–41) changes the story completely. On this specific sector, Subject_A's penalty on technical downhill hiking jumps to **+0.68**.

**The takeaway:** Choosing where you look matters. Full-race averages act like a screen, hiding the specific sections where mechanics actually break down.

![Friction tier strip km 29–39](../06_Visualizations/sut43_gramstad_friction_strip_blog.png)

*Figure 1. The Gramstad terrain strip. Vertical lines mark the start and end of the brutal bedrock corridor (km 31.08–33.80) and the final asphalt transition.*

![Dilution effect](../06_Visualizations/sut43_trf_dilution_blog.png)

*Figure 2. Subject_A's technical downhill penalty. Notice how isolating the Gramstad sector amplifies the specific weakness that the full-race average hid.*

---

## 4. Finding B — same metres, different tax

Because the data is aligned to the exact meter, Subject_A and Subject_B can be compared on the very same technical downhill stretches (**F3** terrain) between km 29 and 41:

| Athlete | km span (F3 DH hike) | Technical downhill penalty (ΔTI) |
|---------|---------------------|----------------------------------|
| **Subject_A** | 29.82 – 39.14 | **+0.68** (paying heavy terrain tax) |
| **Subject_B** | 29.55 – 39.14 | **−0.18** (banking time efficiently) |

**Cell-key gap (A − B) ≈ +0.86.**

This isn't just a case of "Subject_A is a slower runner." When both athletes hit highly technical descents, Subject_A bled time, while Subject_B extracted speed better than the cohort average. The trail simply did not treat them equally.

![Paired residuals](../06_Visualizations/sut43_gramstad_paired_trf_blog.png)

*Figure 3. Side-by-side comparison. Notice that both runners perform well on F2 gravel, but their skills diverge drastically the moment they hit F3 technical terrain.*

| km (course) | Sector | Friction context |
|-------------|--------|------------------|
| 29.4–30.0 | Gramstad entry | Rocky approach |
| 30.1–30.35 | Pre-corridor | Technical rocky core |
| **31.08–33.80** | **Corridor slice** | Operator-locked S4/F3 bedrock descent |
| 34.0–36.7 | Post-corridor rollers | Gravel/dirt (mostly F2) |
| 36.7–39.1 | Vassfjellet → Paradisskaret | Forest tread |
| 39.14+ | Finish band | Asphalt (excluded from F3 DH cell) |

---

## 5. Finding C — the bedrock hotspot

Zooming in one final time—focusing exclusively on the most technical bedrock section of the race (the corridor slice, km 31.08–33.80)—the data becomes razor-sharp:

| Terrain type in corridor slice | Subject_A | Subject_B |
|--------------------------------|-----------|-----------|
| **F3 technical downhill · hike** | **+0.97** penalty | **−0.12** bonus |
| F3 uphill · hike | +0.23 | +0.07 |
| F2 gravel downhill · hike | −0.45 bonus | −1.03 bonus (202 m — small cell) |

Inside this specific bedrock corridor, Subject_A's technical downhill penalty spikes to **+0.97**. This is the ultimate diagnostic hotspot.

But look at the **F2 gravel downhill** numbers. Both athletes have a negative penalty here, meaning they are both highly efficient when running downhill on smooth gravel.

**The coaching mistake:** A generic prescription of "more downhill running volume" misses the signal. The data shows Subject_A is already great at gravel downhills. What Subject_A actually needs to train is eccentric control and line choice specifically on steep, uneven bedrock.

---

## 6. Limitations to keep in mind

1. **Two-runner sample** — compares two specific athletes to find diagnostic weaknesses; not a broad population study.  
2. **Internal reference** — Subject_B acts as the baseline comparison here, not an external recruited elite.  
3. **Hike-dominant window** (~89–93% hike in gramstad).  
4. **Data matching** — metre counts vary slightly based on exactly when each runner transitioned between hiking and running, not because they took different routes.  
5. **Single race edition** on stream-distance km.

---

## 7. The laboratory implication

Sandnes Ultra Trail is not just a line on a GPX map. It is a constantly shifting friction map. By comparing runners on identical sections of trail, a general feeling of "slow at the end" converts into actionable, surgical data. Don't just train for elevation—train for the specific friction of the terrain.

---

## Pull quote

> On the exact same bedrock descent, the trail exacted a massive **+0.97** terrain tax from Subject_A, while Subject_B efficiently banked a **−0.12** residual. Overall race pace is lying—the real story is hidden in the friction.

---

## Publication checklist (operator)

- [ ] Embed Figure 1–3 from `06_Visualizations/sut43_*_blog.png`  
- [ ] Paste from `docs/publications/sut43_gramstad_paired_trf_substack.md`  
- [ ] Substack header: `assets/brand/substack/`  
- [ ] Tags: terrain index, ultra running, Rogaland, biomechanics, data science  
- [ ] Internal Sync Log entry (not for publication)

---

*Draft: The Anatomy of Pace laboratory. Telemetry: SUT_43 race-day panel, TRF Phase B cohort median.*
