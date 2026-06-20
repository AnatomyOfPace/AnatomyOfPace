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

