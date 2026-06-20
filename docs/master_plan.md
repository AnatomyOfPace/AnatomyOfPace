# **MASTERDOKUMENT: THE ANATOMY OF PACE (v3.5)**

**Offisiell prosjektarkitektur, README og strategisk kjøreplan**

## **1\. PROSJEKTETS KJERNE OG FILOSOFI**

Dette dokumentet er "Single Source of Truth" for data science-prosjektet *The Anatomy of Pace*. Prosjektet er dedikert til å dekonstruere og optimalisere løpsøkonomi i tekniske fjell-ultraløp, og tetter gapet mellom asfaltdominert idrettsfysiologi og de brutale mekaniske kravene i rogalandsterrenget.

Tradisjonell "even-pace" er en illusjon i fjellet. Suksess krever et paradigmeskifte til "even-effort" styrt av Grade Adjusted Pace (GAP), kontinuerlig kalibrert mot underlagets iboende friksjon. Forskningen under *The Anatomy of Pace* (Dr. Anatomy Pace) leverer den kvantitative basen; anvendelse i privat treningsplanlegging skjer **lokalt** og publiseres aldri under dette merkenavnet.

## **2\. DET MATEMATISKE RAMMEVERKET**

All dataprosessering bygger på å isolere utøverens tekniske ferdigheter fra deres aerobe kapasitet:

* **Terrengindeks (TI):** Måler den mekaniske friksjonen *utover* stigning. TI = v_faktisk / v_GAP. En TI på 1.0 \= Nøytral asfalt. En TI på 1.5 \= Terrenget tvinger farten ned 50 %. Maskinen benytter et 30-sekunders rullende gjennomsnitt for å glatte ut GPS-støy. Krever GAP-pipeline (se `docs/theory.md` §5).  
* **Aerob Pace Ratio (APR):** Interimmetrikk til GAP er på plass. APR = pace_segment / pace_asfalt_anker ved iso-HR. Brukes i Seed Matrix og benchmarks. **APR ≠ TI** — APR inkluderer stigning og underlag samlet.  
* **Baseline TI:** Løypas objektive "terrengskatt" uavhengig av den enkelte utøver — abstrahert løypasignatur kalibrert mot referanseløpere (Thomas Gauthier for SUT, Subject_B for teknisk flyt i Klasse 5–11).  
* **Technical Proficiency Ratio (TPR):** Måler teknisk effektivitet mot løypa. TPR = Snitt TI / Baseline TI. TPR < 1.0 → utøveren forserer terrenget mer effektivt enn løypas norm.  
* **Elite Proficiency Ratio (EPR):** Måler teknisk effektivitet mot navngitt elitereferanse på *samme rute/segment* når data finnes. EPR = Snitt TI / Elite TI. EPR < 1.0 → utøveren matcher eller slår referansen teknisk. Se `docs/theory.md` §5 og `docs/outreach_referanselopere.md`.  
* **Teknikk-Røntgen:** Personlig leveranse til alle data-donorer — innholdet versjoneres etter hvert som pipelinen modnes (`Røntgen v0` → `v1` …). Se `docs/theory.md` §6.

## **3\. HYPOTESER OG TEORETISK FUNDAMENT**

Den statistiske analysen bygger på tre kjernefunn basert på fysiologisk biomekanikk (inkl. Minetti, Pinnington & Dawson, Giandolini og Millet):

* **H1 \- Innsatsparadokset:** I krevende klatringer oppstår en asymmetri der farten stuper, mens den fysiologiske arbeidsbelastningen forblir stabil. Å tvinge opp farten her resulterer i umiddelbar overskridelse av laktatterskel.  
* **H2 \- Kumulativ Gjeld (Terrengskatten):** Friksjonen fra underlaget er en kontinuerlig biologisk tappekran. Denne akkumuleres og akselererer eksponentielt etter 50 km på grunn av kognitiv utmattelse i sentralnervesystemet (CNS-drain).  
* **H3 \- The Eccentric Downfall:** De massive fartsfallene i siste fjerdedel av tekniske ultraløp (f.eks. på asfalten inn mot Lysebotn) skyldes primært strukturell svikt og mikrotraumer i quadriceps etter forutgående eksentrisk juling, ikke sentral aerob utmattelse.

## **4\. TERRENG-ONTOLOGIEN (DEN 11-TRINNS SKALAEN)**

For å mate algoritmen med presise data, klassifiseres underlaget i en streng 11-trinns skala sortert etter biomekanisk og kognitiv friksjon:

1. **Asfalt (TI=1.0):** Perfekt energiretur. Fasit: Stavanger Halvmaraton, London Marathon.  
2. **Grus og hardpakket jord:** Lett rullende, minimal energilekkasje i frasparket. Fasit: Nordmarka Skogsmaraton, transportetapper i SUT.  
3. **Svaberg (Tørt):** Hardt og solid, krever kontinuerlig stabilisering i anklene. Fasit: Det eksponerte strekket ved Hoppet (LFI), Kjerag-platået.  
4. **Gress og lyng:** Mykt og seigt. Gradvis tømming av hoftebøyere. Fasit: Peak District Challenge, SUT mot Eikenuten.  
5. **Teknisk sti med sleipe røtter/jord:** Bryter løpsrytmen, krever konstant visuelt fokus. Fasit: Bratteli-bakken (LFI), KRS Ultra.  
6. **Teknisk sti med grov stein:** Nådeløst mot muskulaturen utfor. Skaper "The Eccentric Downfall". Fasit: Bakken ned mot Dalevatn (SUT).  
7. **Sand og løs masse:** Underlaget gir etter, fjerner akillessenens fjær-effekt. Fasit: Kystpartier, løs grus i alpine bratter.  
8. **Eksponert fjellrygg / Luftig egg:** Kognitiv friksjon. Farten dikteres av frykt og konsekvens. Fasit: Hamperokken (Tromsø Skyrace), Lofoten Skyrace.  
9. **Høye Sherpatrapper:** Total isolasjon av lår/sete. Sprenger VAM-kapasiteten. Fasit: Siste bakke mot Skilsmissen (LFI), Stoltzekleiven.  
10. **Grov ur og klyving:** Løping blir balansering og bruk av hender. Fasit: Stranden før Songesand (LFI), Hornindal Rundt.  
11. **Dyp myr:** Vakuum-effekt. Makspuls, men tilnærmet null fart. Det fysiologiske svarte hullet. Fasit: Lord of the Rings-myra (LFI), Svalandsgubben.

## **5\. DATAHIERARKI (MAKRO, MESO, MIKRO)**

Prosjektet opererer med en tredelt datagranularitet støttet av aerobe ankere:

* **Makro (Helikopterperspektivet):** Scraping av resultatlister for hele feltet fra 38 internasjonale/nasjonale referanseløp. Lagres i en relasjonell SQLite-database (`anatomy_macro.db`) med Long Format for splittider.  
* **Meso (KM-splits og taktikk):** Kilometertider med aggregert stigning, hentet via Strava API. Identifiserer nøyaktig *hvor* The Eccentric Downfall inntreffer (ofte knyttet til skotøy-valg, f.eks. VJ Ultra 3 sin respons på Klasse 6 terreng).  
* **Mikro (Telemetrisk nivå):** Hyper-granulær FIT-data (GPS, puls, kadens, høyde). Komprimeres lokalt som Parquet-filer for tungprosessering i DuckDB. Dette er råmaterialet for å utlede TI.

## **6\. INFRASTRUKTUR OG MAPPESTRUKTUR**

Prosjektet kjøres lokalt i et isolert Python-miljø (`venv`) på Mac. Rørgaten styres av en rigid, låst mappestruktur:

* `00_Core_Strategy/` *(Sync Logg — bro mellom research og lokal privat trening; aldri publiser)*  
* `01_Geo_Blueprints/` *(Kartverkets N50 shapefiler)*  
* `02_Raw_Data/` *(Ubehandlede .fit filer og JSON scrapes)*  
* `03_Processed_Data/` *(Rensede CSV og lynraske Parquet-filer)*  
* `04_Python_Scripts/` *(Vaskemaskinen, Radaren og Mikroskopet)*  
* `05_Macro_Database/` *(SQLite-databasen `anatomy_macro.db`)*  
* `06_Visualizations/` *(Kryptonitt-kartet, Teknikk-Røntgen, ferdigrendret grafikk)*  
* `07_ML_Models/` *(Fremtidig hjem for maskinlæring/prediksjon)*  
* `docs/` *(master_plan, theory, outreach — nummereres ikke)*  
* `config/` *(`races_radar_config.csv` og miljøvariabler)*

**Databasekonvensjon (Distanser):** I kode og konfigurasjon benyttes kilometer som fast måleenhet for presisjon. "SUT 50" \= `SUT_80`. "SUT 100" \= `SUT_160`.

## **7\. "VASKEMASKINEN" (TEKNISKE FORSVARSVERK)**

For å sikre vitenskapelig validitet i telemetrien, kjøres dataene gjennom autonome forsvarsmekanismer i Pandas/GeoPandas:

1. **The Seed Matrix:** Algoritmen mates først med flate asfaltløp (Stavanger Halvmaraton, 3-Sjøers) for å kalibrere det aerobe ankeret før rogalandsterrenget introduseres.  
2. **The Barometric Shift:** Høydedata og GAP forskyves i tid via `shift(-3)` for å kompensere for klokkens barometriske treghet i bratte kneiker, slik at vGAP​ og vfaktisk​ synkroniseres eksakt.  
3. **Snap-to-Route:** For å motvirke GPS-drift i loddrette fjellvegger benytter GeoPandas `sjoin_nearest`, som tvinger avvikende punkter tilbake på det faktiske stinettverket.  
4. **Privacy Zones:** Alle `.fit`\-filer som importeres fra andre løpere klippes automatisk for de første og siste 500 meterne av ruten for å ivareta personvern.

## **8\. THE SYNC PROTOCOL (BESLUTNINGSLOGG)**

Koblingen mellom den kalde dataanalysen og den operative treningsfilosofien styres via en sentral logg: `00_Core_Strategy/Sync_Logg_Analyse_til_Praksis.md`. Enhver oppdagelse gjort av Vaskemaskinen som krever endring i ernæringsstrategi (f.eks. justering av Cola Protocol / Fuel of Norway-inntak under CNS-drain), trening, eller parameter-tuning i koden, skal loggføres her før *Seig og kjapp*\-manualen oppdateres.

## **9\. FREMTIDIG UTVIKLING (V4.0)**

Når den deskriptive databasen er fylt opp og kalibrert (etter treningsleir i Algarve, juli 2026), skalerer prosjektet til en prediktiv, autonom infrastruktur:

* **Sky-migrering:** Flytting fra lokal SQLite til PostgreSQL, og fra lokal lagring til S3/GCP-buckets.  
* **Machine Learning (`07_ML_Models/`):** Trening av Random Forest/Gradient Boosting-modeller på etablerte *Baseline TI*\-matriser. Målet er en "Dynamic Resistance Score" som predikerer terrengskatten før start.  
* **Web-Fabrikken:** Et Streamlit-dashboard som automatiserer genereringen av "Teknikk-Røntgen", kollaps-indikatorer og dynamiske TPR-sammenligninger (f.eks. TPR-differanser mot treningspartnere i Klasse 10-terreng).

