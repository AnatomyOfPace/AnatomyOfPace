# Brand Identity & Public Boundary

**Single source of truth for how *The Anatomy of Pace* appears to the world.**

---

## Public owner

| Role | Identity |
|------|----------|
| **Project** | The Anatomy of Pace |
| **Principal Investigator (public face)** | **Dr. Anatomy Pace** |
| **Git / technical account** | `AnatomyOfPace` |
| **Contact (commits, infrastructure)** | `anatomypace@gmail.com` |

Dr. Anatomy Pace owns and represents **everything public** under the Anatomy of Pace brand:

- This GitHub repository (code, docs, research architecture)
- Substack (*The Anatomy of Pace*)
- Instagram (`@anatomyofpace`)
- Donor deliverables (*Kinematic_Scan*, *Telemetry_Audit*)
- All Ghost Authority copy (clinical, third-person, no real personal names)

---

## What is **not** part of The Anatomy of Pace

The private training project **Seig og Kjapp** is a **separate entity**:

- Periodization, zones, strength programming, and race-week tactics for Eirik and Sølvi
- Stored locally only (`docs/seig_og_kjapp.md` — gitignored)
- **Must never** be published, referenced, or implied on any public Anatomy of Pace channel
- **Must never** be merged into GitHub, Substack, Instagram, or donor-facing material
- **Must never** use the Anatomy of Pace name, logo, or Dr. Anatomy Pace persona

Research may inform private training via the local Sync Log — but that bridge is **internal only**. The public never sees it.

---

## Ghost Authority (public voice)

When writing for an external audience, attribute work to the laboratory or Dr. Anatomy Pace — never to real individuals.

| Do | Don't |
|----|-------|
| "The telemetry reveals…" | "I felt…" / "We trained…" |
| "Dr. Anatomy Pace / The laboratory" | Real names, private training titles |
| Clinical Subject IDs (`Subject_A`) | Personal identifiers in charts or copy |
| Third-person, passive framing | Influencer tone, emoji, personal anecdotes |

---

## Channel map

```
PUBLIC (Dr. Anatomy Pace / The Anatomy of Pace)
├── GitHub     — code & research docs
├── Substack   — long-form analysis
├── Instagram  — visual hooks → Substack
└── Donor PDFs — Kinematic_Scan deliverables

PRIVATE (never publish)
├── Seig og Kjapp manual
├── Subject registry (real names)
├── .fit telemetry & personal reports
└── Sync Log → training updates (local application only)
```

---

## Brand assets

Canonical logo files live in `assets/brand/`. Dark-background originals are the primary brand treatment; do not invert or lighten without visual QA.

| Asset | Path | Dimensions | Usage |
|-------|------|------------|-------|
| **Icon mark** | `assets/brand/logo_icon_dark.png` | 543×503 | A + EKG symbol on dark field. Default for social avatars, favicons, and compact placements. |
| **Full wordmark** | `assets/brand/logo_wordmark_dark.png` | 686×692 | Icon + *THE ANATOMY OF PACE* + **PRIVATE RESEARCH LABORATORY** lockup. |
| **Source originals** | `assets/brand/source/` | — | Unmodified uploads; reference only — prefer canonical or `variants/` for production. |

### Size variants (`assets/brand/variants/`)

| File | Dimensions | Use case |
|------|------------|----------|
| `icon_square_512.png` | 512×512 | Instagram / profile avatar (center-cropped square) |
| `icon_square_1024.png` | 1024×1024 | High-resolution square icon |
| `wordmark_1200w.png` | 686×692 | Docs, Substack header (source width &lt; 1200 — no upscale) |
| `wordmark_600w.png` | 600×605 | Narrow headers, email signatures |
| `favicon_32.png` | 32×32 | Browser tab favicon |
| `favicon_180.png` | 180×180 | Apple touch icon |

### Channel guidance

- **Instagram / social discovery:** Icon-only per [`launch_strategy.md`](launch_strategy.md) — use `variants/icon_square_512.png` or `icon_square_1024.png` as the profile image. Do not crop the wordmark for avatars.
- **GitHub / Substack / docs:** Wordmark acceptable where horizontal space allows; icon alone is fine in repo README badges or tight layouts.
- **Lab lockup (internal):** The wordmark subtitle **PRIVATE RESEARCH LABORATORY** signals laboratory scope. Suitable for GitHub org pages, internal decks, and donor-facing PDF covers — not required on public social avatars.
- **Telemetry charts:** Generated figures remain in `06_Visualizations/` (gitignored). Brand logos are separate committed assets.

Regenerate variants after replacing source files in `assets/brand/source/` (Pillow LANCZOS resize; see `assets/brand/README.md`).

### Photography (`assets/brand/photography/`)

Terrain-only imagery for public channels — clinical, desaturated, cool-toned derivatives aligned with the charcoal + white logo palette.

| Rule | Detail |
|------|--------|
| **Subject matter** | Landscape and trail terrain only. No faces, no identifiable people, no race bibs or personal gear markers. |
| **Naming** | Generic terrain descriptors (`terrain_valley_green`, `terrain_peak_fjord`, …). No personal names or geo-specific identifiers in filenames or public copy. |
| **Aesthetic** | Nordic trail mood is acceptable as a generic laboratory backdrop; do not name specific locations in captions unless required (e.g. official race names in editorial context). |
| **Derivatives** | Prefer `_clinical` or `_dark_overlay` for text legibility; `_banner_16x9` for Substack/GitHub; `_square_1080` / `_story_9x16` for Instagram. |
| **Watermark** | Optional `composites/*_banner_watermark.jpg` — icon only, bottom-right, subtle. |

Dominant colors per image: `assets/brand/photography/palette.json`. Regenerate via `assets/brand/photography/generate_derivatives.py`.

---

## Pre-publish checklist

Before any commit destined for GitHub, or any Substack / Instagram post:

1. Zero real personal names (runners, collaborators, operators).
2. Zero mention of **Seig og Kjapp** or private training content.
3. Copy attributed to **Dr. Anatomy Pace** or *The Anatomy of Pace* laboratory — not a private individual.
4. Charts and filenames use clinical IDs only.
5. Social avatars use icon-only variants — not the full wordmark lockup.
