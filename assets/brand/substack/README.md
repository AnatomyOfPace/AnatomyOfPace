# Substack brand exports — The Anatomy of Pace

Production-ready uploads for the public Substack publication (**Dr. Anatomy Pace**). Icon-only for avatars; public wordmark excludes **PRIVATE RESEARCH LABORATORY**.

Regenerate after logo or photography updates:

```bash
python3 assets/brand/substack/generate_substack_assets.py
```

Source assets: `assets/brand/logo_icon_dark.png`, `logo_wordmark_dark.png`, `photography/derivatives/terrain_peak_fjord_dark_overlay.jpg`.

---

## Substack image specs (official, 2025–2026)

| Element | Minimum / recommended | Aspect | Format |
|---------|----------------------|--------|--------|
| **Publication logo** | ≥ 256×256 | 1:1 square | PNG, transparent background preferred |
| **Wordmark** | ≥ 1344×256 | 21:4 | PNG, transparent preferred |
| **Email banner** | 1100×220 recommended | 5:1 | PNG |
| **Cover photo** | ≥ 600×600 | square | JPG or PNG |
| **Social / post preview** | ≥ 1200×630 | 14:10 | JPG or PNG |

Reference: [Substack Help — optimal image dimensions](https://support.substack.com/hc/en-us/articles/4408381685268-What-are-the-optimal-image-dimensions-for-my-Substack-publication).

---

## Upload checklist

### Settings → Website → Header (or Website editor)

| Substack field | Upload this file | Dimensions | Notes |
|----------------|------------------|------------|-------|
| **Logo** | `substack_icon_transparent_512.png` | 512×512 | Icon only. Substack displays the publication name beside the logo — do not embed title text in the logo file. |
| **Wordmark** | `substack_wordmark_header.png` | 1344×256 | Icon + *THE ANATOMY OF PACE*; no lab subtitle. Transparent PNG. |
| **Header / hero image** (optional) | `substack_header_1344x256.jpg` | 1344×256 | Terrain (`terrain_peak_fjord` dark overlay) + subtle icon watermark. No people. |

**Alternate logo (opaque):** `substack_icon_512.png` or `substack_logo_square_1080.png` if the publication theme uses a dark header and transparent logos clip poorly.

### Settings → Basics

| Field | Recommendation |
|-------|----------------|
| **Publication name** | `The Anatomy of Pace` |
| **Author / byline** | `Dr. Anatomy Pace` |
| **Short description / tagline** | `Biomechanics telemetry · terrain structure · pace decay` (or shorter: `A public biomechanics research laboratory`) |
| **Cover photo** | `substack_cover_1080.jpg` (1080×1080) |

### Settings → Email (if custom email banner enabled)

| Field | Upload | Dimensions |
|-------|--------|------------|
| **Email banner** | `substack_email_banner_1100x220.png` | 1100×220 |

### Per-post defaults (optional)

| Use | File | Dimensions |
|-----|------|------------|
| Default social preview / OG image | `substack_social_preview_1200x630.jpg` | 1200×630 |

---

## File inventory

| File | Size | Use |
|------|------|-----|
| `substack_icon_transparent_512.png` | 512×512 | **Primary logo upload** (transparent) |
| `substack_icon_512.png` | 512×512 | Logo (charcoal background) |
| `substack_logo_square_1080.png` | 1080×1080 | High-res square logo (charcoal) |
| `substack_logo_transparent_1080.png` | 1080×1080 | High-res square logo (transparent) |
| `substack_wordmark_header.png` | 1344×256 | **Wordmark upload** |
| `substack_header_1344x256.jpg` | 1344×256 | Website header / hero |
| `substack_header_1344x256.png` | 1344×256 | PNG duplicate of header |
| `substack_email_banner_1100x220.png` | 1100×220 | Email banner |
| `substack_cover_1080.jpg` | 1080×1080 | Welcome / About cover |
| `substack_social_preview_1200x630.jpg` | 1200×630 | Post preview default |

---

## Ghost Authority reminders

- **No people** in any imagery (terrain and logo marks only).
- **No personal names** in copy or filenames committed for public use.
- **No private training** — private periodization is never referenced on Substack.
- **Icon-only** for logo / avatar fields; reserve the full `logo_wordmark_dark.png` lockup (with *PRIVATE RESEARCH LABORATORY*) for laboratory-facing surfaces only.
- Attribute public copy to **Dr. Anatomy Pace** or *The Anatomy of Pace* laboratory.

Full brand rules: [`docs/brand_identity.md`](../../../docs/brand_identity.md) · Parent assets: [`../README.md`](../README.md).
