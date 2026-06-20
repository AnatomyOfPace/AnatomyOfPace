# **OUTREACH OG NETTVERK: REFERANSELØPERE**

**Kommunikasjonsstrategi og API-Autentisering for The Anatomy of Pace**

Dette dokumentet inneholder de standardiserte meldingene (pitchene) som brukes for å rekruttere referanseløpere til datafabrikken. Formålet med meldingene er å sikre autorisasjon via Strava API-et (OAuth 2.0) slik at maskinen autonomt kan hente ut hyper-granulære `.fit`\-filer fra deres nøkkeløkter.

Hver løper fyller en spesifikk fysiologisk eller teknisk rolle i kalibreringen av Terrengindeksen (TI).

## **1\. THOMAS GAUTHIER**

**Rolle:** Elitereferanse ("Fasiten"). Definerer selve terrengskatten for Sandnes Ultra Trail 50 Miles. Når farten hans dropper, er det fordi terrenget fysisk krever det, ikke på grunn av tekniske mangler.

**Pitch (Klar til kopiering):**

Hei Thomas\! Skal du bryne deg på SUT 50 neste år? Rått\! Jeg sikter på samme ruten i 2028, og holder på å kode en egen datamodell for å forberede meg.

Greia er at Strava-farten din er en illusjon i terrenget. Algoritmene bruker matematikk fra tredemøller, og skjønner ikke at det koster massivt mye mer energi å løpe i Sandnes-myrene enn på grus, selv på samme puls.

Jeg bygger et Python-program som regner ut akkurat hva denne usynlige "Terrengskatten" er for ulikt underlag. For at modellen skal fungere, trenger jeg å kalibrere den mot fasiten: løpere som har så bra teknisk flyt at farten utelukkende dropper fordi terrenget blir stygt. Her er jo du maskinen.

Hvis du er gira på å la meg bruke telemetrien din som "baseline" (krever bare to klikk for å godkjenne en Strava-tilkobling), så kan jeg kjøre SUT 50-løypa gjennom skriptet for deg før løpet ditt i retur. Da får du et budsjett som viser nøyaktig hvor mye tid terrenget egentlig kommer til å stjele fra deg, og hvor du må justere farten for å ikke sprekke.

Lyst til å være prøvekanin?

## **2\. LARS OLE**

**Rolle:** Elitereferanse og ekstrem distanse. Definerer terrengskatten for 100 miles og Oslo Bergen Trail (OBT). Viser hvordan systemet håndterer ekstrem akkumulert tretthet ("Quad-Smash" og "CNS-drain") over flere døgn.

**Pitch (Klar til kopiering):**

Hei Lars Ole\! Hører rykter om SUT 100 og OBT på deg neste år. Helt sykt opplegg\!

Jeg sitter og nerder skikkelig med et privat dataprosjekt i Python om dagen, og med den kalenderen din tenkte jeg at dette er midt i blinken for deg. Kort fortalt: Jeg koder en modell som fikser det Strava og Garmin suger på. Klokka skjønner jo bare stigning, og fatter ikke at vi vasser i dyp myr eller knoter i ur med makspuls (og at farten dør deretter).

Jeg bygger en algoritme som regner ut den nøyaktige "Terrengskatten", men jeg har også lagt inn to fysiologiske faktorer:

1. Modellen predikerer "Quad-Smash" – den forteller deg når lårene kommer til å totalhavarere etter juling i utforbakkene, slik at du kan pace deg riktig.  
2. "CNS-Drain" – Den fargekoder ruten din og viser når hjernen kommer til å koke over av teknisk sti, slik at du vet hvor du må stappe i deg næring før du mister fokus.

For å kalibrere modellen trenger jeg data fra noen som er en ren fasit på teknisk flyt – der farten dropper kun fordi terrenget er brutalt. Der er du og Thomas G. gullstandarden min.

Hvis du gidder å koble deg til Strava-appen min med et par klikk, så skal jeg kjøre SUT 100- og OBT-rutene dine gjennom maskinen og gi deg et vanntett pacing-budsjett.

Lyst til å dele litt Strava-gull?

## **3\. SØLVI**

**Rolle:** Teknisk referanse, API-pilot og treningspartner. Utgjør den umiddelbare referansen for teknisk flyt på stiene i Rogaland og fungerer som første testsubjekt for godkjenningskoden til Python-skriptet.

**Pitch (Klar til kopiering):**

Hei\! Jeg holder på å koble det nye data-prosjektet mitt (der jeg regner ut terrengskatt og tretthet) direkte mot Strava for å slippe manuelle GPX-filer.

Har du lyst til å være prøvekanin for tilkoblingen? Trykker du på denne lenken og godkjenner, får skriptet mitt tilgang til å lese øktene dine. (Du blir sendt til en blank side etterpå – bare kopier den nye nettadressen du havner på og send den til meg i retur, så er vi i gang\!)

Lenke: [https://www.strava.com/oauth/authorize?client\_id=257636\&redirect\_uri=http://localhost\&response\_type=code\&scope=activity:read\_all](https://www.google.com/search?q=https://www.strava.com/oauth/authorize%3Fclient_id%3D257636%26redirect_uri%3Dhttp://localhost%26response_type%3Dcode%26scope%3Dactivity:read_all)

## **4\. CHRIS JACKSON**

**Rolle:** "Fell running"-referanse og det aerobe ankeret. Isolerer forskjellen mellom nøytral asfaltfart (London Marathon) og seig, britisk friksjon (Lake District / 5 Valleys). Nødvendig for å bygge `uk_baseline_matrix.csv`.

**Pitch (Klar til kopiering):**

Hi Chris\! I hear you're tackling the 5 Valleys next year. That's a massive challenge\!

I’m currently building a private data science project in Python aimed at fixing the flaws in how Strava and Garmin calculate effort. Their Grade Adjusted Pace (GAP) assumes we run on treadmills, completely ignoring the massive energy drain from deep bogs, roots, and fell running terrain.

I’m coding an algorithm that calculates the exact "Terrain Tax" of different surfaces. To make it work for UK conditions, I need to calibrate it against someone who has both a solid flat baseline (like your London Marathon data) and strong technical fell running skills.

If you're open to letting my script read your Strava telemetry (it just takes two clicks to authorize), I can run your 5 Valleys route through the machine. In return, I'll give you a pacing budget that shows exactly where the terrain will steal your time, and where you need to hold back to save your quads for the final descents.

Up for being a guinea pig?

## **5\. ANNEMIEKE**

**Rolle:** Termisk og alpin referanse. Gjennom løp som Val d'Aran by UTMB, setter hun standarden for varmekompensasjon kombinert med teknisk ur. Dataene hennes fungerer som bro mellom norsk granitt og de termiske forholdene som kreves for Algarve-kalibreringen.

**Pitch (Klar til kopiering):**

Hei Annemieke\! Håper treningen mot fjellene går bra.

Jeg holder på med et datavitenskap-prosjekt der jeg bygger en algoritme som regner ut den nøyaktige "Terrengskatten" vi betaler i fjellet – altså hvor mye tid underlaget og varmen stjeler fra oss, selv når vi presser på samme puls.

For at modellen min skal bli nøyaktig, trenger jeg data fra noen som mestrer kombinasjonen av stekende varme og brutalt teknisk terreng. Her er dine data fra Pyreneene (som Val d'Aran) den absolutte fasiten jeg trenger for å kalibrere "varmestress-faktoren" i koden min før jeg selv skal ned til Algarve for å trene.

Hvis du har lyst til å bidra (det krever bare to klikk for å la skriptet mitt hente telemetrien din fra Strava), skal jeg kjøre dine nøkkeløkter gjennom maskinen. Som takk kan jeg gi deg en "Teknikk-Røntgen" som viser nøyaktig i hvilke stigninger/temperaturer farten din faller mer enn pulsen tilsier, slik at du kan finjustere pacingen din i varmen.

Lyst til å koble på og dele litt data?

**Operativ rutine for alle referanseløpere:** Når løperen returnerer nettadressen (eksempel: `http://localhost/?state=&code=LAAANG_KODE_HER...`), skal strengen etter `code=` kopieres og mates direkte inn i mikroskop-motoren (`01_strava_fetcher.py`) for å generere et permanent Refresh Token for den spesifikke utøveren. Deretter genereres donor-spesifikk **Teknikk-Røntgen** (se `docs/theory.md` §6) — inkludert pacing-budsjett der det er lovet i pitchen.

