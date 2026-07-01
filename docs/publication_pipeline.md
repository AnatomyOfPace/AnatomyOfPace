# Publication Pipeline — Article Candidates

**Laboratory:** The Anatomy of Pace · **Authority:** Dr. Anatomy Pace
**Scope:** External distribution (Substack, Instagram, donor deliverables) under the Ghost Authority protocol.
**Related:** `docs/master_plan.md` · `docs/theory.md` · `docs/friction_index_spec.md` · `docs/race_ecology.md` · `docs/launch_strategy.md` · `docs/brand_identity.md`

---

## Ground rules (apply to every candidate)

- **Voice:** Clinical, third-person, passive framing. Attribute all findings to *The Anatomy of Pace* laboratory or **Dr. Anatomy Pace** — never to a real individual.
- **Nomenclature:** Clinical English only. Use `Kinematic_Scan`, Terrain Index (TI), Terrain Tax. Legacy Norwegian terms (e.g. Teknikk-Røntgen, Terrengindeks) are prohibited in public copy. Race names and raw geographic tokens are permitted proper nouns.
- **Identifiers:** Subjects as `Subject_A`, `Subject_B`, …; reference athletes as `Reference_Elite_A`, `Reference_Elite_B`, … Charts and filenames use clinical IDs only.
- **Firewall:** Any concept touching fueling, CNS "bribery" (Cola Protocol), zones, or race-week tactics routes through the internal Sync Log into the private training project and is **excluded** from public output. Never publish or imply that bridge.
- **Visuals:** High-contrast, data-dense, dark-mode outputs routed to `06_Visualizations/`. Apply zero/halt masking to speed traces to preserve axis integrity.

---

## I. Core Publication Pipeline

### 1. The DNA of the Trail: Decoding the Terrain Sequence
- **Description:** Foundational article introducing the trail's structural signature — how surface friction, gradient, and technical complexity act as a categorical sequence (the "DNA") that dictates metabolic cost, replacing the concept of linear pacing.
- **Data Requirements:** Locked operator gold spans for the Gramstad band (`spatial_terrain_map_sut43.json`); cleaned Parquet micro-data (`panel_1m.parquet`).
- **Analysis Requirements:** Final validation of the S1–S6 (technical) and F0–F4 (friction) classifications via the HITL annotator; custom Python visualization in `06_Visualizations/` mapping the categorical HMM draft sequence against the continuous Terrain Index (TI) trace.

### 2. The Effort Paradox: Why Pace Is a Flawed Metric in Technical Terrain
- **Description:** An exploration of Hypothesis 1 (H1). Deconstructs the fallacy of "even pace" in mountain ultramarathons, showing that speed drops precipitously on steep, technical climbs while internal physiological load stays constant.
- **Data Requirements:** Raw `.fit` telemetry processed through `01_vaskemaskinen.py`.
- **Analysis Requirements:** Fully operational Aerobic Pace Ratio (APR) calculations (`02_terrengindeks.py`); comparative analysis isolating iso-HR segments, contrasting flat asphalt anchor pacing against high-gradient technical terrain.

### 3. Cumulative Debt and the Eccentric Downfall
- **Description:** A synthesis of Hypotheses 2 and 3 (H2, H3). Addresses the biological drain of continuous surface friction and the resulting structural pacing decay — pacing collapse on late-race flat sections from eccentric quad damage, not central aerobic failure.
- **Data Requirements:** Macro database ingestion of race results (e.g. Lysefjorden Inn 2026 checkpoint splits) via `anatomy_macro.db`.
- **Analysis Requirements:** Execution of `07_plot_decay.py` for macro checkpoint decay visualizations; continuous TI plotting over a distance exceeding 50 km to visualize the inflection point of cumulative CNS fatigue.

### 4. The Kinematic Scan: A New Paradigm for Telemetry Audits
- **Description:** Official introduction of the laboratory's primary donor product. Explains how athletes submit raw telemetry to receive a biomechanical X-ray of their performance, benchmarked against the course baseline and reference elites.
- **Data Requirements:** Automated `.fit` intake from reference elites via the planned Strava OAuth fetcher; subject telemetry for comparative analysis.
- **Analysis Requirements:** Completion of the Grade Adjusted Pace (GAP) module to unlock production-grade TI; calculation of Terrain Performance Ratio (TPR) and Elite Performance Ratio (EPR) using paired `.fit` files on identical course segments (`06_benchmark.py`).

---

## III. Methodology & Metric Series (extends I.1–I.4)

### 5. The Two Rulers: Why APR Is Not TI
- **Description:** Clarifies the laboratory's two pace-ratio metrics — the interim Aerobic Pace Ratio (APR) and the target Terrain Index (TI) — and why conflating surface friction with gradient corrupts every downstream conclusion. Positions APR as the operational bridge until the GAP pipeline lands.
- **Data Requirements:** Seed Matrix asphalt anchors (Stavanger Halvmaraton, 3-Sjøers) at iso-HR; a matched technical segment from the SUT_43 `gramstad_band`.
- **Analysis Requirements:** Side-by-side APR vs draft-TI trace on identical metres (`02_terrengindeks.py`); annotation of the grade-vs-friction decomposition that separates Minetti-corrected cost from residual Terrain Tax.

### 6. Baseline TI: Measuring the Course, Not the Runner
- **Description:** Introduces the course's objective "tax rate" — the Baseline TI abstracted from reference telemetry — and explains how it becomes the denominator for Technical Proficiency Ratio (TPR).
- **Data Requirements:** `Reference_Elite_A` / `Reference_Elite_B` locked gold spans on paired course segments; `panel_1m.parquet`.
- **Analysis Requirements:** Aggregation of per-metre friction into a course-level Baseline TI matrix; a TPR worked example (`TPR = mean TI_subject / Baseline TI`) with TPR < 1.0 interpretation.

### 7. Head-to-Head on the Same Rock: The Elite Proficiency Ratio
- **Description:** Explains segment-paired benchmarking — contrasting a subject against a named reference elite on the *identical* course metres to isolate pure technical efficiency (EPR), with the interim EAR variant while GAP matures.
- **Data Requirements:** Paired `.fit` files on a shared segment via Strava OAuth intake; Snap-to-Route alignment.
- **Analysis Requirements:** `06_benchmark.py` EAR run at iso-HR; migration path from APR-level EAR to TI-level EPR once GAP is online.

---

## IV. Terrain Ontology Deep-Dives (the 11-class scale, one specimen at a time)

### 8. The Black Hole: Deep Bog as the Physiological Null Zone (Class 11)
- **Description:** Dissects the highest-friction terrain class — the vacuum effect where heart rate maxes while forward velocity approaches zero — using Pinnington & Dawson as the physiological anchor.
- **Data Requirements:** Bog-dominant segments (Svalandsgubben, KRS Ultra, LFI marsh sections) telemetry via `01_vaskemaskinen.py`.
- **Analysis Requirements:** Isolation of iso-HR metres where TI spikes with collapsed speed; zero/halt masking applied to the speed trace to preserve axis integrity; visualization routed to `06_Visualizations/`.

### 9. Cognitive Friction: When Fear Sets the Pace (Class 8)
- **Description:** Explores exposed-ridge terrain where speed is governed by consequence and visual load rather than aerobic ceiling — the Millet CNS argument applied to Tromsø / Lofoten Skyrace profiles.
- **Data Requirements:** Alpine ridge telemetry with concurrent HR/cadence; reference-elite comparison where a paired file exists.
- **Analysis Requirements:** Divergence analysis of stable HR against depressed speed on exposed segments; contrast against a physically comparable but non-exposed climb to isolate the cognitive component.

### 10. The Broken Ladder: Sherpa Stairs and VAM Saturation (Class 9)
- **Description:** Quantifies pure concentric vertical work on high-step terrain and the breakpoint where the aerobic ceiling caps vertical ascent rate.
- **Data Requirements:** Vertical-climb telemetry (Stoltzekleiven-class, LFI final climb toward Skilsmissen); pure-ascent references (Skåla Opp, Galdhøpiggen Opp).
- **Analysis Requirements:** VAM (vertical ascent metres/hour) vs HR ceiling curve; identification of the run-to-power-hike crossover where hiking is cheaper in both time and HR.

---

## V. Pipeline Transparency & Methods (the "Laboratory" GitHub → Substack loop)

### 11. Inside the Data Pipeline: Four Defenses for Honest Telemetry
- **Description:** A methods piece explaining the four wash-pipeline safeguards — Seed Matrix calibration, Barometric Shift, Snap-to-Route, and the 500 m Privacy Zone clip — that make the numbers defensible.
- **Data Requirements:** A raw `.fit` file before/after wash; a GPS-drift example on steep terrain.
- **Analysis Requirements:** Before/after visual of `shift(-3)` barometric synchronization and `sjoin_nearest` route-snapping; documentation of the privacy clip as an ethics guarantee.

### 12. Friction First: Why Surface Labels Lie
- **Description:** Presents the Friction Index thesis — that intrinsic friction tiers (F0–F4) outrank descriptive surface classes (S1–S6), e.g. chunky gravel presenting as "gravel" while carrying an F3 mechanical tax.
- **Data Requirements:** `gramstad_band` operator friction-tier gold; `consensus_nti` across the donor panel.
- **Analysis Requirements:** Many-to-one mapping of S-class onto friction tier; a non-identifiability example where identical surface labels yield divergent observed TI.

### 13. Two Ontologies, One Trail: Course Truth vs Telemetry Behavior
- **Description:** Explains the O₁ (operator/course: surface × friction) vs O₂ (telemetry clusters: substrate × locomotion × grade × effort) split and the probabilistic bridge between them.
- **Data Requirements:** Windowed kinematic features (`ti_mean`, `ti_std`, `walk_fraction`, `pace_residual_mean`) from `build_telemetry_clusters.py`; road + Paradisskaret anchors.
- **Analysis Requirements:** Grade-conditioned clustering so uphill walking does not masquerade as a surface class; overlay of unsupervised clusters against operator gold spans.

---

## VI. Macro / Comparative & Predictive (v4.0 horizon)

### 14. Exponential, Not Linear: Reading Fatigue Across 38 Races
- **Description:** A macro-database synthesis demonstrating that biomechanical fatigue compounds exponentially rather than linearly, using field-wide checkpoint splits (Hornindal Rundt, Meråker as the reference horror-cases).
- **Data Requirements:** Macro checkpoint splits in `anatomy_macro.db` (Long Format); elevation-gain aggregates per race.
- **Analysis Requirements:** `07_plot_decay.py` cross-race decay curves; fit of an accelerating penalty multiplier against a linear null model.

### 15. The Dynamic Resistance Score: Predicting the Terrain Tax Before the Gun
- **Description:** A forward-looking piece on the planned ML layer — training gradient-boosted / random-forest models on Baseline TI matrices to predict per-segment terrain tax pre-race.
- **Data Requirements:** Labeled SUT_43 friction gold; geo-blueprint (N50) terrain features; multi-donor panel.
- **Analysis Requirements:** Model draft in `07_ML_Models/`; predicted vs observed TI validation with masked-unlabeled handling; framed strictly as descriptive-to-predictive research, not coaching.

### 16. Cardiac Drift Under Load: Quantifying the Heat Tax
- **Description:** Isolates temperature-driven HR drift (Western States, Val d'Aran references) to explain why iso-HR pacing budgets must widen under thermal stress.
- **Data Requirements:** Warm-race telemetry with ambient temperature where available; a temperate baseline for the same subject.
- **Analysis Requirements:** HR-vs-time drift at fixed GAP effort; separation of thermal drift from terrain-driven TI so the two taxes are not double-counted.

---

## VII. Discovery-layer framing (Instagram hooks → Substack)

### 17. Corridor QC: How a 150-Metre Gap Gets Locked
- **Description:** A short, methods-flavored hook on course-relative spatial reasoning — early/late, upstream/downstream, stream km vs organiser course km — that keeps segment analysis honest.
- **Data Requirements:** A `race_corridors.json` gap lock (e.g. the Paradisskaret finish band) and its stream→GPX axis map.
- **Analysis Requirements:** A single dark-mode sector figure demonstrating why "east on the map" ≠ "late in the race," with the finish anchored at km 161.

---

## VIII. Environmental & Cognitive Multipliers

### 18. The Dark Tax: Visual Deprivation and Kinematic Atrophy
- **Description:** Terrain Index (TI) measures friction and grade — but what happens when visual input is restricted? Examines the "Dark Tax": how an identical terrain segment extracts a higher metabolic cost at night. Without peripheral horizon lines, stride length shortens, ground-contact time increases, and TI balloons despite identical surface conditions.
- **Data Requirements:** Multi-lap or multi-year telemetry over the identical route (e.g. `Reference_Elite_B` on SUT_160, contrasting a daylight pass against a 02:00 pass).
- **Analysis Requirements:** Isolation of identical spatial spans via Snap-to-Route; TI and speed variance plotted chronologically to demonstrate the divergence of physical friction vs cognitive visual load.

### 19. The Moisture Multiplier: When Structure Holds but Friction Fails
- **Description:** A rock garden is a different biomechanical puzzle when wet. Explores the volatility of the Friction Index (F0–F4), showing how precipitation shifts an S4 (technical) trail from an F1 (dry/grip) to an F3 (slick/yielding) tax rate — proving that static route profiles are insufficient without environmental modeling.
- **Data Requirements:** Subject telemetry on a known technical course under dry vs saturated/rain conditions (e.g. historical LFI data cross-referenced with meteorological records).
- **Analysis Requirements:** Comparative `Kinematic_Scan` on paired segments showing the APR/TI delta driven strictly by moisture.

---

## IX. Biomechanical Flow & Disruption

### 20. The Gait-Switch Penalty: The Cost of Fragmented Terrain
- **Description:** Most pacing models assume continuous motion. Introduces the "Gait-Switch Penalty": when a trail oscillates rapidly between S1 (smooth) and S4 (technical) — forcing continuous transitions between running gait, power hike, and scramble — metabolic cost exceeds steady state in either extreme. The tax is in the variance.
- **Data Requirements:** High-resolution multi-FIT panel data (`panel_1m.parquet`) on highly fragmented terrain sections vs homogeneous sections of equal average difficulty.
- **Analysis Requirements:** Rolling-window variance of TI and speed; correlation between the frequency of categorical S-class changes (the "DNA" mutation rate) and elevated physiological debt.

### 21. Negative Gradient, Positive Tax: The Elite Downhill Signature
- **Description:** Amateurs brake; elites flow. Applies the Elite Performance Ratio (EPR) exclusively to steep, technical descents, visualizing how amateur subjects incur a large Terrain Tax through eccentric braking forces while reference elites decouple speed from gradient — preserving the quadriceps by minimizing ground-contact time.
- **Data Requirements:** Paired `.fit` files (`Subject_A` vs `Reference_Elite_A`) mapped to high-grade negative segments (e.g. the descent from Paradisskaret).
- **Analysis Requirements:** `06_benchmark.py` execution isolated to negative gradients; speed-vs-TI scatter plots contrasting the amateur "braking cluster" against the elite "flow line."

### 22. The Ghost Minutes: Aggregating Micro-Halts in Technical Corridors
- **Description:** Why does the laboratory insist on zero/halt masking in its visual outputs? Because the illusion of slow movement often masks stationary time. Reveals that in S5/S6 terrain, athletes do not merely move slowly — they spend a material fraction of the segment at 0.0 m/s conducting micro-navigation and line-selection.
- **Data Requirements:** Raw `.fit` telemetry from highly technical sectors (Class 5/6) processed through `01_vaskemaskinen.py`.
- **Analysis Requirements:** Temporal aggregation of 0.0 m/s epochs; a visual breakdown of "Time in Motion" vs "Time Navigating" within a specific kilometre block, justifying the laboratory's data-scrubbing protocols.

---

## Editorial sequencing note

A defensible cadence:

1. Publish the **methodology series (5–7)** first to establish metric literacy.
2. Release **terrain deep-dives (8–10)** as recurring "specimen" posts (one class each — high visual reuse for the Instagram layer).
3. Interleave **pipeline transparency (11–13)** as the GitHub-anchored credibility proof.
4. Reserve **14–16** for once the macro DB and GAP module mature.
5. Use **17** as a lightweight bridge post.
6. Layer the **environmental & cognitive multipliers (18–19)** and **biomechanical flow & disruption (20–22)** as second-wave depth once the core metric vocabulary (5–7) and terrain ontology (8–10) are established; 21 depends on the same GAP/EPR maturity as 6–7, and 22 doubles as the narrative justification for the zero/halt masking rule.

Every candidate keeps visuals in `06_Visualizations/` with zero/halt masking on speed traces, uses `Kinematic_Scan` / Terrain Index (TI) / Terrain Tax nomenclature, and attributes all findings to the laboratory rather than any operator.
