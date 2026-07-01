# **LAUNCH STRATEGY OG MERKEVARE**

**Økosystem, Estetikk og "Ghost Authority" for The Anatomy of Pace**

---

## **0. PUBLIC BRAND (English — authoritative for all channels)**

| Field | Value |
|-------|-------|
| **Project** | The Anatomy of Pace |
| **Owner / public face** | **Dr. Anatomy Pace** |
| **GitHub** | `AnatomyOfPace` / `anatomypace@gmail.com` |
| **Substack** | *The Anatomy of Pace* |
| **Instagram** | `@anatomyofpace` |

**Scope firewall:** *Seig og Kjapp* is a **private** training project. It does **not** belong under The Anatomy of Pace and must **never** appear on GitHub, Substack, Instagram, or in donor-facing material. Full rules: [`brand_identity.md`](brand_identity.md).

---

Dette dokumentet definerer hvordan prosjektet kommuniseres utad. Målet er ikke å samle "likes" eller bygge en personlig merkevare som en tradisjonell influencer. Målet er å bygge en faglig autoritet der maskinens rådata og **Dr. Anatomy Paces** analytiske konklusjoner snakker for seg selv.

Prosjektet frontes via en kompromissløs, klinisk "Dark Mode"-estetikk under **Dr. Anatomy Pace** — aldri under private treningsprosjekter.

## **1\. THE ECOSYSTEM LOOP (PUBLISERINGSHIERARKIET)**

Prosjektet distribueres gjennom en lukket sirkel i tre lag. Du produserer innholdet én gang, men distribuerer det systematisk for å bygge maksimal troverdighet.

1. **Laboratoriet (GitHub):**  
   * **Funksjon:** Ditt tekniske bevis.  
   * **Handling:** Når du har kodet en ny funksjon (f.eks. Myr-algoritmen), committer du Python-koden her. Det viser at prosjektet er fundamentert i ekte matematikk, ikke bare meninger.  
2. **Journalen (Substack):**  
   * **Funksjon:** Analysen og dybdeforståelsen.  
   * **Handling:** Du bruker koden til å analysere et spesifikt segment (f.eks. Bratteli-bakken). Du skriver ned logikken, TI-kalkylene og konklusjonen i et klinisk nyhetsbrev. Dette er hovedproduktet ditt.  
3. **Discovery (Instagram):**  
   * **Funksjon:** Den visuelle kroken.  
   * **Handling:** Du tar ett "screenshot" av den viktigste grafen fra Substack-analysen (f.eks. Kryptonitt-kartet). Du poster det med en kort, iskald bildetekst som peker direkte til den fulle analysen på Substack.

## **2\. REGLER FOR "GHOST AUTHORITY"**

For å beskytte operatørenes anonymitet og skille forskning fra privat trening, skal all **offentlig** kommunikasjon være strengt frakoblet realpersoner. **Dr. Anatomy Pace** er det eneste offentlige ansiktet — ikke en influencer, men laboratoriets kliniske stemme.

* **Stemme:** Attribuer analyse til *The Anatomy of Pace* eller **Dr. Anatomy Pace**. Unngå "jeg tror" / "jeg føler" fra realpersoner.
* **Forbudt offentlig:** Ethvert innhold fra *Seig og Kjapp* (privat treningsprosjekt).
* **Svar i kommentarfelt:** Hvis noen stiller et spørsmål på Instagram, svar kort og klinisk.  
  * *Feil:* "Takk kompis\! Ja, jeg ble skikkelig sliten i den bakken 😂"  
  * *Riktig:* "Interessant observasjon. Dataene fra Vaskemaskinen v2.0 tyder på at overgangen fra Klasse 4 til Klasse 6 terreng krever 14 % høyere puls for å opprettholde samme GAP. Se full analyse i ukens Substack-post."  
* **Estetikk:** Visualiseringene (som genereres fra `06_Visualizations` i Python) skal ha mørk bakgrunn ("Dark Mode"), knallrøde/neonfargede data-linjer, og ingen unødvendig pynt. Det skal se ut som telemetri fra en Formel 1-bil.

## **3\. VERDIBYTTET (DATA-DONASJONER)**

Når prosjektet skalerer og ukjente løpere ønsker sine data analysert, er valutaen telemetri, ikke penger. Deltakere som donerer `.fit`\-filer til maskinen (Google Forms eller Strava OAuth — se `docs/outreach_referanselopere.md`) mottar i retur en personlig **"Teknikk-Røntgen"**.

Referanseløpere er **ikke** gratis kalibrering: de får samme produkt (ofte med *pacing-budsjett* før kommende løp) i bytte mot telemetrien som samtidig forbedner Baseline TI for alle.

Metrikkene TPR, EPR og (inntil GAP er klart) EAR er **donor-spesifikke** — beregnet *for den som deler data*, ikke bare for prosjektets interne subjekt. Full spesifikasjon og versjonering: `docs/theory.md` §6. Innholdet utvides etter hvert som forskningen modnes; dagens liste er *Røntgen v0*, ikke en endelig kontrakt.

Denne inneholder tre elementer:

1. **Terreng-Varmekartet:** Høydeprofil fargekodet utelukkende etter mekanisk friksjon (TI), ikke stigningsprosent.  
2. **Løypas Svarte Hull:** Nøyaktig identifisering av segmentet som krevde den hardeste terrengskatten.  
3. **Kollaps-indikatoren:** En matematisk markør for *The Eccentric Downfall* – punktet der den reelle farten stupte til tross for stabil GAP-innsats.

**Utvidet når pipeline tillater det** (se `docs/theory.md` §6):

4. **TPR-profil:** Donorens effektivitet vs løypas Baseline TI per segment.  
5. **EPR-profil:** Donorens effektivitet vs relevant elitereferanse (f.eks. Thomas på SUT_80).  
6. **Pacing-budsjett:** Konkret tidskost per segment — løftet i outreach-pitchene.

## **4\. LAUNCH-SJEKKLISTE**

Når den lokale Python-fabrikken din produserer feilfrie CSV-filer, er dette stegene for å gå "live" på nett:

* \[ \] **Opprett GitHub-repo:** Navngi det `AnatomyOfPace`. Skriv en `README.md` som kort definerer prosjektets mål (LFI sub-10:50). Hold selve databasen (`.fit` og `.db`) skjult via `.gitignore`.  
* \[ \] **Sett opp Substack:** Navngi den *The Anatomy of Pace*. Publiser selve Masterdokumentets Kapittel 1-4 som din aller første "Manifest"-post.  
* \[ \] **Instagram-oppsett:** Opprett kontoen `@anatomyofpace`. Last opp en mørk graf som profilbilde. Legg en "Linktree" eller direkte lenke til Substack/GitHub i bioen.  
* \[ \] **Første innholdssyklus (Case Study \#001):** Kjør koden for Bratteli-bakken eller Kjerag-starten. Publiser den tunge analysen på Substack. Ta hovedgrafen og legg ut på Instagram. Sirkelen er i gang.

## **5. EDITORIAL HORIZON — SECOND-WAVE SERIES (English)**

Long-term editorial horizon for the Substack and Instagram layers. Full 22-candidate taxonomy and per-article data/analysis requirements live in [`publication_pipeline.md`](publication_pipeline.md); the two series below extend it into environmental and biomechanical variables that traditional pacing models ignore. Attribution: Dr. Anatomy Pace / the laboratory. Nomenclature: `Kinematic_Scan`, Terrain Index (TI), Terrain Tax. Clinical IDs only (`Subject_*`, `Reference_Elite_*`).

### VIII. Environmental & Cognitive Multipliers

**18. The Dark Tax: Visual Deprivation and Kinematic Atrophy**
- **Description:** TI measures friction and grade — but what happens when visual input is restricted? Examines the "Dark Tax": how an identical terrain segment extracts a higher metabolic cost at night. Without peripheral horizon lines, stride length shortens, ground-contact time increases, and TI balloons despite identical surface conditions.
- **Data Requirements:** Multi-lap or multi-year telemetry over the identical route (e.g. `Reference_Elite_B` on SUT_160, contrasting a daylight pass against a 02:00 pass).
- **Analysis Requirements:** Isolation of identical spatial spans via Snap-to-Route; TI and speed variance plotted chronologically to demonstrate the divergence of physical friction vs cognitive visual load.

**19. The Moisture Multiplier: When Structure Holds but Friction Fails**
- **Description:** A rock garden is a different biomechanical puzzle when wet. Explores the volatility of the Friction Index (F0–F4), showing how precipitation shifts an S4 (technical) trail from an F1 (dry/grip) to an F3 (slick/yielding) tax rate — proving that static route profiles are insufficient without environmental modeling.
- **Data Requirements:** Subject telemetry on a known technical course under dry vs saturated/rain conditions (e.g. historical LFI data cross-referenced with meteorological records).
- **Analysis Requirements:** Comparative `Kinematic_Scan` on paired segments showing the APR/TI delta driven strictly by moisture.

### IX. Biomechanical Flow & Disruption

**20. The Gait-Switch Penalty: The Cost of Fragmented Terrain**
- **Description:** Most pacing models assume continuous motion. Introduces the "Gait-Switch Penalty": when a trail oscillates rapidly between S1 (smooth) and S4 (technical) — forcing continuous transitions between running gait, power hike, and scramble — metabolic cost exceeds steady state in either extreme. The tax is in the variance.
- **Data Requirements:** High-resolution multi-FIT panel data (`panel_1m.parquet`) on highly fragmented terrain sections vs homogeneous sections of equal average difficulty.
- **Analysis Requirements:** Rolling-window variance of TI and speed; correlation between the frequency of categorical S-class changes (the "DNA" mutation rate) and elevated physiological debt.

**21. Negative Gradient, Positive Tax: The Elite Downhill Signature**
- **Description:** Amateurs brake; elites flow. Applies the Elite Performance Ratio (EPR) exclusively to steep, technical descents, visualizing how amateur subjects incur a large Terrain Tax through eccentric braking forces while reference elites decouple speed from gradient — preserving the quadriceps by minimizing ground-contact time.
- **Data Requirements:** Paired `.fit` files (`Subject_A` vs `Reference_Elite_A`) mapped to high-grade negative segments (e.g. the descent from Paradisskaret).
- **Analysis Requirements:** `06_benchmark.py` execution isolated to negative gradients; speed-vs-TI scatter plots contrasting the amateur "braking cluster" against the elite "flow line."

**22. The Ghost Minutes: Aggregating Micro-Halts in Technical Corridors**
- **Description:** Why does the laboratory insist on zero/halt masking in its visual outputs? Because the illusion of slow movement often masks stationary time. Reveals that in S5/S6 terrain, athletes do not merely move slowly — they spend a material fraction of the segment at 0.0 m/s conducting micro-navigation and line-selection.
- **Data Requirements:** Raw `.fit` telemetry from highly technical sectors (Class 5/6) processed through `01_vaskemaskinen.py`.
- **Analysis Requirements:** Temporal aggregation of 0.0 m/s epochs; a visual breakdown of "Time in Motion" vs "Time Navigating" within a specific kilometre block, justifying the laboratory's data-scrubbing protocols.

