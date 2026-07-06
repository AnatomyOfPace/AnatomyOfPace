# **LITTERATUR OG TEORI: DET VITENSKAPELIGE FUNDAMENTET**

**Teoretisk ryggrad for The Anatomy of Pace**

Dette dokumentet oppsummerer de fire vitenskapelige bærebjelkene som legitimerer algoritmene i prosjektet. Terrengindeksen (TI), Aerob Pace Ratio (APR) og den matematiske "Vaskemaskinen" lener seg på disse konseptene. Når koden skal forsvares – enten for eliteløpere eller i fremtidige publiseringer – er det disse fire studiene vi viser til.

## **1\. Minetti et al. (2002): Hvorfor Strava tar feil utendørs**

**Tema:** Den biomekaniske kostnaden av stigning (Grade-Adjusted Pace \- GAP). **Studien:** Forskerne plasserte løpere på en tredemølle i bratte vinkler opp og ned for å måle oksygenopptak og energikostnad ved ulike stigningsprosenter.

**Vår applikasjon (Koden):** Dette er formelen Strava og Garmin bruker for å kalkulere GAP. Vårt prosjekt utnytter svakheten i denne studien: Den er utelukkende basert på en jevn, motorisert tredemølle (vår Klasse 1: Asfalt). Den tar *null*hensyn til friksjon, underlag eller fotfeste. Når Strava påstår at GAP-en din er 5:30 min/km mens du løper i steinur (Klasse 10), bruker de Minettis tredemølle-matematikk på noe den aldri var ment for. Det er dette avviket maskinen vår isolerer for å finne Terrengindeksen (TI) — friksjon *utover* det Minetti allerede har korrigert for.

## **2\. Pinnington & Dawson (2001): Beviset for "Terrengskatten"**

**Tema:** Energikostnaden av ujevnt/mykt underlag. **Studien:** Forskerne sammenlignet det fysiologiske arbeidskravet ved løping på fast gress kontra løping i dyp sand, uavhengig av stigning.

**Vår applikasjon (Koden):** Studien utgjør det fysiologiske beviset på at underlag alene er en massiv, uavhengig variabel. De beviste at energikostnaden øker drastisk i sand – et underlag som sluker energi og fjerner akillessenens "fjæreffekt". Dette gir oss det vitenskapelige belegget for vår Terreng-Ontologi, og legitimerer at vi tildeler myr (Klasse 11\) og grov ur (Klasse 10\) en matematisk tidsstraff i pacing-budsjettet for Lysefjorden Inn.

## **3\. Giandolini et al. (2016): "The Quad-Smash Effect"**

**Tema:** Eksentrisk tretthet og strukturell svikt. **Studien:** Forskning på utmattelsen som oppstår etter langvarig løping med stigning, med særskilt fokus på den muskulære ødeleggelsen fra nedoverbakker.

**Vår applikasjon (Koden):** De fleste kommersielle algoritmer antar et lineært fartsfall (du blir jevnt saktere per kilometer). Giandolini beviser at gjentatte støt fra bratte nedkjøringer skaper mikrotraumer i quadriceps. Resultatet er at kilometerne du løper på flat mark *etter* en brutal nedkjøring, koster uforholdsmessig mye mer oksygen. Dette er beviset for hvorfor tretthetsfaktoren i koden vår ikke er en rett linje, men bruker en straffe-multiplikator som akselererer eksponentielt etter segmenter som sherpatrappene før Skilsmissen.

## **4\. Millet et al. (2011): "Når hjernen sier stopp (CNS-Drain)"**

**Tema:** Sentral utmattelse i ultraløp. **Studien:** Guillaume Millet og hans team undersøkte ikke bare perifer (muskulær) utmattelse, men hjernens og sentralnervesystemets respons på ekstreme distanser (opp mot 330 km).

**Vår applikasjon (Koden):** Millet fant ut at ved ekstreme distanser og langvarig kognitivt stress, slutter hjernen å sende sterke nok signaler til beina – selv om musklene strengt tatt har ATP/glykogen igjen til å skape kraft. I rogalandsterreng fremskyndes dette massivt av det tekniske fokuset (hvor skal jeg sette foten?). Dette gir oss belegget for å integrere "Kognitiv Friksjon" i Klasse 8 (Eksponerte fjellrygger) og Klasse 5 (Sleipe røtter). Det er også denne studien som rettferdiggjør The Sync Protocol: Hvorfor ernæringssoner fargekodes som "Hands-Free", der målet er å bestikke sentralnervesystemet (CNS) før det tvinger frem en systemkollaps.

## **5. Metrikker: TI, APR, TPR og EPR**

To pace-ratio-metrikker og to effektivitetsratiostier. **APR ≠ TI.**

### **Terrengindeks (TI) — målmetrikk (krever GAP-pipeline)**

Måler mekanisk friksjon *utover* stigning — det Pinnington-beviset som Minetti/GAP ikke fanger.

| | |
|---|---|
| **Formel** | TI = v_faktisk / v_GAP (ekvivalent: pace_faktisk / pace_GAP) |
| **Glattingsvindu** | 30 sekunder rullende gjennomsnitt |
| **Filter** | Iso-HR (aerob sone) der det er hensiktsmessig |
| **Tolkning** | TI = 1.0 → nøytral asfalt. TI = 1.5 → 50 % tregere enn GAP tilsier |
| **Kode** | Ikke implementert ennå — avhenger av GAP-modul + Barometric Shift |

### **Aerob Pace Ratio (APR) — operativ metrikk (implementert i dag)**

Pace-sammenligning mot asfaltanker ved matchet puls. Inkluderer stigning, underlag og teknikk samlet — *ikke* friksjon isolert fra grade.

| | |
|---|---|
| **Formel** | APR = pace_segment / pace_asfalt_anker @ iso-HR |
| **Anker** | Seed Matrix (f.eks. Stavanger Halvmaraton) |
| **Tolkning** | APR = 1.5 → 50 % tregere pace enn asfalt ved samme puls |
| **Bruk** | Seed Matrix-kalibrering, athlete benchmarks, sanity check mot TI |
| **Kode** | `02_terrengindeks.py`, `03_batch_analyse.py`, `04_visualiser_ti.py` |

### **Technical Proficiency Ratio (TPR) — vs løypa**

Sammenligner utøver mot løypas *objektive* terrengsignatur (Baseline TI), ikke mot en enkeltperson direkte.

| | |
|---|---|
| **Formel** | TPR = Snitt TI_utøver / Baseline TI_løype |
| **Tolkning** | TPR < 1.0 → utøveren forserer terrenget mer effektivt enn løypas norm |
| **Kode** | Avhenger av TI-pipeline + Baseline TI-matrise per løp |

**Baseline TI** bygges fra referanseløpernes telemetri, men abstraheres til løypenivå — det er løypas "skattesats", ikke én persons rå fil.

### **Elite Proficiency Ratio (EPR) — vs elitereferanse**

Direkte hode-til-hode mot navngitt referanseutøver på **samme rute og segment** når `.fit`-data finnes (Strava OAuth / `docs/outreach_referanselopere.md`).

| | |
|---|---|
| **Formel** | EPR = Snitt TI_utøver / Snitt TI_elite *(segmentparret)* |
| **Tolkning** | EPR < 1.0 → utøveren er teknisk minst like effektiv som referansen på det segmentet |
| **Krav** | Parret segment (Snap-to-Route), iso-HR eller iso-innsats, elite `.fit` tilgjengelig |
| **Kode** | Ikke implementert — etter GAP/TI-pipeline; logikk speiler `06_benchmark.py` på TI-nivå |

**Referansekart (elitereferanse → rolle → løp):**

| Utøver | Rolle | Primærløp / terreng |
|--------|-------|---------------------|
| Reference_Elite_A | Fasit teknisk flyt | SUT_80 |
| Lars Ole | Ekstrem distanse, Quad-Smash / CNS | SUT_160, OBT |
| Subject_B | Rogaland teknisk flyt, API-pilot | SUT_43, Klasse 5–11 |
| Chris Jackson | Fell + asfaltanker (UK) | 5 Valleys, London Marathon |
| Annemieke | Varme + alpin ur | Val d'Aran |

**TPR vs EPR — når bruke hva** *(gjelder enhver analysert utøver — donor, referanse eller egen)*:

| Spørsmål | Metrikk |
|----------|---------|
| Hvor hardt straffer *løypa* generelt? | Baseline TI |
| Hvor effektiv er *utøveren* vs løypas norm? | TPR |
| Hvor effektiv er *utøveren* vs *elitereferanse på samme sti*? | EPR |

### **Elite APR Ratio (EAR) — interim elite-sammenligning**

Inntil GAP/TI finnes: samme elite-logikk som EPR, men på APR-nivå. Dette er det `06_benchmark.py` og `07_batch_benchmark.py` allerede gjør (f.eks. Subject_A vs Subject_B på SUT43).

| | |
|---|---|
| **Formel** | EAR = APR_utøver / APR_elite @ iso-HR *(parret økt/segment)* |
| **Tolkning** | EAR < 1.0 → raskere pace enn referansen ved samme puls |
| **Kode** | `06_benchmark.py`, `07_batch_benchmark.py` |

**Pipeline:** APR/EAR (nå) → GAP online → TI → TPR (vs løype) + EPR (vs elite, når data finnes).

## **6. Teknikk-Røntgen — leveransen til data-donorer**

Metrikkene over er ikke bare interne research-verktøy. De er **produktet** du bytter bort mot `.fit`-telemetri.

**Valuta:** Donor gir data → maskinen returnerer en personlig **Teknikk-Røntgen** (`docs/launch_strategy.md` §3). Ingen betaling. Referanseløpere via Strava OAuth og ukjente løpere via Google Forms får samme produkt — referanseeliten får ofte *pacing-budsjett før løp* i tillegg (`docs/outreach_referanselopere.md`).

### **Hvem er "utøveren"?**

| Aktør | Gir | Får | Forskerrollen |
|-------|-----|-----|----------------|
| **Referanseløper** (Thomas, Lars Ole, …) | OAuth + nøkkelruter | Teknikk-Røntgen + pacing-budsjett | Kalibrerer Baseline TI *og* mottar egen analyse |
| **Offentlig donor** | `.fit` via Google Forms | Teknikk-Røntgen | Utvider datasett; ingen elite-forpliktelse |
| **Subject_A / Subject_B** | Egen trenings-/løpsdata | Intern analyse → *lokal privat trening* | Subjekt + med-forsker |

TPR og EPR beregnes **for donor-utøveren**, ikke bare for deg. Referanseløperen som kalibrerer Baseline TI skal fortsatt få vite *sin egen* TPR/EPR på ruten de delte.

### **Teknikk-Røntgen — obligatoriske elementer**

| # | Element | Metrikk / visual | Interim (APR-era) |
|---|---------|------------------|-------------------|
| 1 | **Terreng-Varmekartet** | Høydeprofil fargekodet etter TI per segment | APR-profil (pace vs asfalt @ iso-HR) |
| 2 | **Løypas Svarte Hull** | Segment med høyest TI (maks terrengskatt for *denne* utøveren) | Segment med høyest APR |
| 3 | **Kollaps-indikatoren** | Punkt der fart stuper til tross for stabil GAP-innsats (Eccentric Downfall) | Fart vs puls-divergens uten GAP |

### **Teknikk-Røntgen — sammenligningspaneler** *(når data finnes)*

| Panel | Innhold | Krever |
|-------|---------|--------|
| **TPR-profil** | Utøverens TPR per segment vs Baseline TI | GAP + løypas Baseline TI-matrise |
| **EPR-profil** | Utøverens EPR vs relevant elitereferanse per segment | Parret `.fit` + Snap-to-Route |
| **Pacing-budsjett** | "Terreng stjeler X min på km Y–Z" | Segment-TI + løypekart |
| **EAR-profil** *(interim)* | APR vs elite på parret økt | `06_benchmark.py`-logikk |

Referanseeliten velges per løp (se tabell i §5). Donor på SUT_80 sammenlignes mot Thomas; donor på LFI mot løypas Baseline TI + eventuelt Subject_B/Thomas der rute overlapper.

### **Dataflyt**

```
Donor .fit  →  Vaskemaskinen  →  TI/APR per segment
                                      ↓
              Baseline TI (løype) ←── TPR for donor
              Elite TI (referanse) ← EPR for donor (hvis parret)
                                      ↓
                         Teknikk-Røntgen (PDF / Streamlit / PNG)
                                      ↓
              Baseline TI oppdateres (referanseløpere) → bedre TPR for neste donor
```

**Ghost Authority:** Røntgen leveres klinisk ("algoritmen indikerer"), ikke som personlig coaching — men innholdet er **donor-spesifikt**, ikke generisk Substack-innhold.

### **Versjonering og modning**

Teknikk-Røntgen er et **levende produkt**, ikke en frossen spesifikasjon. Tabellene over er *nåværende besteforståelse* — elementer kan legges til, flyttes fra "interim" til "obligatorisk", eller erstattes når forskningsprosjektet modnes (f.eks. GAP online, Snap-to-Route, CNS-drain-fargekoding).

| Versjon | Era | Typisk innhold |
|---------|-----|----------------|
| **Røntgen v0** | APR/EAR (nå) | APR-varmekart, svarte hull, puls/fart-divergens, EAR vs elite |
| **Røntgen v1** | TI/TPR/EPR | Full GAP-basert pakke + pacing-budsjett per segment |
| **Røntgen v2+** | ML / v4.0 | Dynamic Resistance Score, prediktiv terrengskatt pre-race, m.m. |

**Regler for endring:**

1. Nytt røntgen-element krever at det kan beregnes fra eksisterende eller planlagt pipeline — ikke bare en idé.
2. Endring i obligatorisk innhold loggføres i `00_Core_Strategy/Sync_Logg_Analyse_til_Praksis.md` *før* outreach-pitches oppdateres.
3. Donorer som allerede har mottatt en rapport versjonmerkes (`Røntgen v0.3` i footer); re-analyse tilbys ikke automatisk med mindre det avtales.
4. Research-innsikt publisert på Substack kan precede røntgen-produktet — journalen er laboratoriet, røntgen er den destillerte donor-leveransen.

