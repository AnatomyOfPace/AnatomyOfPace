# Donor Pipeline Architecture

**Status:** Active design (Gemini directive 2026-06-20)  
**Owner:** Dr. Anatomy Pace / The Anatomy of Pace laboratory  
**Target:** Automatic intake live before **16 July 2026** (Algarve calibration window)

---

## Value exchange (core loop)

```
Donor authorizes Strava (one click)
    → Laboratory passively harvests .fit
    → Privacy clip (500 m) + wash + GAP/TI
    → Kinematic_Scan deliverable (Tier 1 → 2 → 3)
    → Donor receives clinical report; laboratory expands Baseline TI matrix
```

Manual `.fit` email/DM transfer is **deprecated** for reference elites. Google Form remains fallback for anonymous public donors until Strava app review (if needed).

---

## Vector 1 — Frictionless intake

| Component | File | Status |
|-----------|------|--------|
| OAuth + token store | `04_Python_Scripts/12_strava_fetcher.py` | Scaffold |
| Token registry (local) | `config/strava_tokens.local.json` | Template ready |
| Credentials | `.env` (`STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`) | Template ready |
| Privacy clip (500 m) | `04_Python_Scripts/donor_io.py` | Implemented |
| Wash pipeline | `01_vaskemaskinen.py` | Existing |
| Orchestrator (poll → scan) | `13_intake_runner.py` | **Planned** |

**Script numbering:** Outreach docs reference `01_strava_fetcher.py`. Wash pipeline occupies `01_vaskemaskinen.py`. Strava intake is **`12_strava_fetcher.py`** to avoid collision.

### Donor onboarding flow

1. Laboratory generates link:  
   `python 12_strava_fetcher.py --authorize-url --donor Reference_Elite_A`
2. Donor clicks → Strava consent (`activity:read_all`)
3. Donor returns redirect URL; laboratory extracts `code=`  
   `python 12_strava_fetcher.py --exchange-code CODE --donor Reference_Elite_A`
4. Cron / manual poll:  
   `python 12_strava_fetcher.py --poll-all --download-new`

### Storage layout (gitignored)

```
02_Raw_Data/
  inbox/strava/{donor_id}/activity_{id}.fit   # raw export
  donors/{donor_id}/activity_{id}.fit         # privacy-processed copy
```

Internal Subject_A/B `.fit` files stay in `02_Raw_Data/` root — not routed through Strava inbox.

---

## Vector 2 — Kinematic_Scan tiers

GAP module (`11_gap_engine.py`) and Kinematic_Scan v1 (`08_kinematic_scan.py`) are **online**. Tier rollout:

### Tier 1 — Diagnostic isolation *(v1.0 — partial)*

| Deliverable | Implementation | Status |
|-------------|----------------|--------|
| Black Hole (max TI sector) | `build_segment_table_ti` + highlight in `render_scan` | ✅ |
| Collapse / Eccentric Downfall | `detect_collapse_points_v1` | ✅ |
| Geo coordinates at black hole | Lat/lon from FIT record at segment midpoint | **Planned v1.1** |
| 3-panel dark-mode PNG | `08_kinematic_scan.py` | ✅ |

**v1.1 tasks:** Add lat/lon callout on black-hole panel; export segment bounds as `black_hole.geojson` (local only).

### Tier 2 — Terrain tax signature *(v1.2)*

| Deliverable | Requires |
|-------------|----------|
| TI heatmap by 11-class terrain ontology | Snap-to-Route + surface classifier OR grade/roughness proxy |
| Ascent vs descent vulnerability split | Segment-level TI grouped by `grade_pct` sign + variance |
| Radar / bar chart per terrain class | Aggregated TI matrix per master_plan §4 scale |

**Blocker:** Full 11-class mapping needs GeoPandas trail overlay (master_plan §7). **Interim:** bin segments by grade (climb / flat / descent) and report mean TI per bin.

### Tier 3 — Prescriptive pacing budgets *(v2.0)*

| Deliverable | Requires |
|-------------|----------|
| km-by-km pacing matrix for target race | Baseline TI matrix for course + donor TPR profile |
| "Terrain steals X min on km Y–Z" | Historical elite + donor segment TI vs Baseline TI |
| Pre-race PDF for reference elites | Tier 1+2 + course blueprint |

**Blocker:** Baseline TI per course not yet built. **Dependency chain:** reference elite Strava intake → Baseline TI calibration → TPR → pacing budget.

---

## Kinematic_Scan version roadmap

| Version | Tiers | Key additions |
|---------|-------|---------------|
| **v1.0** | Tier 1 core | TI panels, black hole, collapse flags (current) |
| **v1.1** | Tier 1 complete | Lat/lon black hole, clinical PDF wrapper, Ghost Authority copy |
| **v1.2** | Tier 2 interim | Grade-bin terrain signature panel |
| **v2.0** | Tier 2 full + Tier 3 | Baseline TI integration, pacing budget matrix |

---

## Brand parameters (all tiers)

- **Visual:** Dark background `#0A0A0A`, high-contrast data lines (existing in `08_kinematic_scan.py`)
- **Copy:** Passive clinical framing — "The telemetry indicates…", never personal coaching tone
- **IDs:** Clinical donor IDs only in outputs (`Reference_Elite_A`, not real names)
- **Scope:** Seig og Kjapp content never appears in donor deliverables

---

## Integration with Seed Matrix

External donors require their **own** asphalt/tartan anchor before TI is valid:

1. First flat race or calibration effort → `seed_matrix.lock_anchor(donor_clinical_id, fit)`
2. Until locked, Kinematic_Scan runs with `--legacy-apr` or borrowed anchor flagged `INTERIM`

Reference elites with London Marathon + fell data (Reference_Elite_C) supply both anchor and terrain in one recruitment.

---

## Pre–16 July checklist

- [ ] `.env` populated with Strava app credentials
- [ ] Subject_B API pilot connected (internal test of OAuth loop)
- [ ] First reference elite token stored
- [ ] `13_intake_runner.py`: poll → wash → GAP → Kinematic_Scan
- [ ] Kinematic_Scan v1.1 PDF + coordinates
- [ ] Daily `launchd` job on Mac for `--poll-all --download-new`
- [ ] Google Form fallback for non-Strava donors
