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

A **private training project** (local operators only) is a **separate entity**:

- Periodization, zones, strength programming, and race-week tactics for enrolled subjects
- Stored locally only (gitignored private manual — never committed)
- **Must never** be published, referenced, or implied on any public Anatomy of Pace channel
- **Must never** be merged into GitHub, Substack, Instagram, or donor-facing material
- **Must never** use the Anatomy of Pace name, logo, or Dr. Anatomy Pace persona

Research may inform private training via a local Sync Log — but that bridge is **internal only**. The public never sees it.

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
├── Private training manual (local operators)
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

### Photography & public imagery (`assets/brand/photography/`)

**Hard rule — no people in any public brand imagery.** Applies to all Anatomy of Pace surfaces: Substack, Instagram, GitHub social previews, donor PDFs, and any AI-generated or stock assets. The laboratory presents data and terrain — not athletes, operators, or human subjects.

| Rule | Detail |
|------|--------|
| **No people (zero exceptions)** | No faces, silhouettes, partial figures, hands-only crops, crowd scenes, race bibs, identifiable personal gear, AI portraits, or stock athletes. If a human form appears in source material, discard it — do not crop around it. |
| **Permitted subject matter** | Terrain and landscape only; committed logo marks (`assets/brand/`); telemetry and data charts (`06_Visualizations/` — gitignored, never with personal identifiers). |
| **Naming** | Generic terrain descriptors (`terrain_valley_green`, `terrain_peak_fjord`, …). No personal names or geo-specific identifiers in filenames or public copy. |
| **Aesthetic** | Clinical, desaturated, cool-toned derivatives aligned with the charcoal + white logo palette. Nordic trail mood is acceptable as a generic laboratory backdrop; do not name specific locations in captions unless required (e.g. official race names in editorial context). |
| **Derivatives** | Prefer `_clinical` or `_dark_overlay` for text legibility; `_banner_16x9` for Substack/GitHub; `_square_1080` / `_story_9x16` for Instagram. |
| **Watermark** | Optional `composites/*_banner_watermark.jpg` — icon only, bottom-right, subtle. Never watermark over people (there should be none). |
| **Ghost Authority alignment** | Imagery reinforces the clinical laboratory persona — terrain as data context, not lifestyle or influencer content. No emotional human storytelling in visuals. |
| **Originals — local only** | Unprocessed landscape PNGs live in `assets/brand/photography/source/` (gitignored). Never commit, push, or publish originals. |
| **Public repo — derivatives only** | GitHub and all public channels receive processed JPEG derivatives, logo-watermark composites, and AI-generated video clips only — never raw source photography. |

Dominant colors per image: `assets/brand/photography/palette.json`. Regenerate via `assets/brand/photography/generate_derivatives.py` (reads local `source/`; writes `derivatives/` and `composites/`). For AI-assisted asset generation, use prompts in [`brand_gemini_prompts.md`](brand_gemini_prompts.md) — all include the no-humans constraint. Originals may inform style reference locally; they must never appear in commits or public output.

---

## Pre-publish checklist

Before any commit destined for GitHub, or any Substack / Instagram post:

1. Zero real personal names (runners, collaborators, operators).
2. Zero mention of private training projects or operator-specific periodization.
3. Copy attributed to **Dr. Anatomy Pace** or *The Anatomy of Pace* laboratory — not a private individual.
4. Charts and filenames use clinical IDs only.
5. Social avatars use icon-only variants — not the full wordmark lockup.
6. Zero people in any imagery (photography, AI-generated, stock, or composite) — terrain, data charts, and logo marks only.
7. Zero original landscape photography in commits or public output — derivatives, composites, and AI clips only (`photography/source/` stays local).
