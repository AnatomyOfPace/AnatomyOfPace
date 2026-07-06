# Brand assets — The Anatomy of Pace

Committed logo files for **Dr. Anatomy Pace** / *The Anatomy of Pace* laboratory. Dark-background treatment is canonical.

## Structure

```
assets/brand/
├── logo_icon_dark.png          # Icon mark (A + EKG)
├── logo_wordmark_dark.png      # Full lockup incl. PRIVATE RESEARCH LABORATORY
├── source/                     # Original logo uploads (reference)
├── variants/                   # Production logo sizes
├── video/                      # Reel builds (see video/README.md)
└── photography/                # Terrain brand imagery (see below)
```

## Which file to use

| Context | File |
|---------|------|
| Instagram / profile avatar | `variants/icon_square_512.png` |
| High-res avatar / app icon | `variants/icon_square_1024.png` |
| Browser favicon | `variants/favicon_32.png` |
| Apple touch icon | `variants/favicon_180.png` |
| Substack header, GitHub org, docs | `variants/wordmark_600w.png` or `wordmark_1200w.png` |
| Source editing | `source/logo_*_original.png` |

**Public social:** Icon-only. The wordmark lockup includes *PRIVATE RESEARCH LABORATORY* — reserved for laboratory-facing surfaces (GitHub, Substack, donor PDFs), not cropped for avatars.

### Imagery policy (logos + photography)

**No people in any public brand imagery.** All committed assets in this directory and their derivatives must contain only logo marks or terrain — never human figures.

| Forbidden | Permitted |
|-----------|-----------|
| Faces, silhouettes, partial figures, hands-only crops | Logo marks (`logo_icon_dark.png`, variants) |
| Crowd scenes, race bibs, identifiable personal gear | Terrain photography (`photography/derivatives/`) |
| AI portraits, stock athletes, lifestyle runner imagery | Telemetry charts (generated separately; no personal IDs) |

This rule applies to avatars, banners, composites, and any new asset added under `assets/brand/`. Ghost Authority alignment: the laboratory presents data and terrain, not human subjects.

## Regenerating variants

After replacing files in `source/`, run from the repository root (requires Pillow):

```bash
python3 - <<'PY'
import shutil
from pathlib import Path
from PIL import Image

BRAND = Path("assets/brand")
icon = Image.open(BRAND / "logo_icon_dark.png").convert("RGBA")
wordmark = Image.open(BRAND / "logo_wordmark_dark.png").convert("RGBA")
V = BRAND / "variants"

def center_square(img):
    w, h = img.size
    s = min(w, h)
    l, t = (w - s) // 2, (h - s) // 2
    return img.crop((l, t, l + s, t + s))

sq = center_square(icon)
R = Image.Resampling.LANCZOS
sq.resize((512, 512), R).save(V / "icon_square_512.png", optimize=True)
sq.resize((1024, 1024), R).save(V / "icon_square_1024.png", optimize=True)
sq.resize((32, 32), R).save(V / "favicon_32.png", optimize=True)
sq.resize((180, 180), R).save(V / "favicon_180.png", optimize=True)

def max_w(img, mw):
    w, h = img.size
    if w <= mw:
        return img.copy()
    return img.resize((mw, round(h * mw / w)), R)

max_w(wordmark, 1200).save(V / "wordmark_1200w.png", optimize=True)
max_w(wordmark, 600).save(V / "wordmark_600w.png", optimize=True)
print("Variants written to", V)
PY
```

## Photography (`assets/brand/photography/`)

Committed terrain imagery for Substack headers, Instagram, and GitHub social previews. Clinical Nordic-trail aesthetic.

**No people — terrain only.** No faces, silhouettes, hands-only crops, crowd scenes, AI portraits, stock athletes, or identifiable personal gear. If source material contains a human form, discard it. Filenames and public copy use generic terrain descriptors only — no personal identifiers.

```
photography/
├── source/              # Local-only original PNGs (gitignored — never commit or publish)
├── derivatives/         # Processed JPEGs (quality 85) — committed for public use
│   ├── {name}_clinical.jpg
│   ├── {name}_dark_overlay.jpg   # ~40% charcoal (#1a1a1a) overlay
│   ├── {name}_banner_16x9.jpg    # 1920×1080
│   ├── {name}_square_1080.jpg    # 1080×1080
│   └── {name}_story_9x16.jpg     # 1080×1920
├── composites/          # Banner + subtle icon watermark (bottom-right)
├── palette.json         # Dominant colors per image
└── generate_derivatives.py
```

| Source | Orientation | Typical use |
|--------|-------------|-------------|
| `terrain_valley_green` | Landscape | Substack header, wide banners |
| `terrain_peak_fjord` | Landscape | GitHub social preview, article hero |
| `terrain_range_cloud` | Landscape | General laboratory backdrop |
| `terrain_cairn_summit` | Portrait | Instagram story, vertical crop |
| `terrain_fjord_vertical` | Portrait | Instagram story, vertical crop |

**Which derivative to use**

| Context | File |
|---------|------|
| Substack / GitHub header | `derivatives/{name}_banner_16x9.jpg` or `_dark_overlay.jpg` |
| Instagram feed | `derivatives/{name}_square_1080.jpg` |
| Instagram story | `derivatives/{name}_story_9x16.jpg` (prefer portrait sources) |
| Text overlay / wordmark on image | `derivatives/{name}_dark_overlay.jpg` |
| Branded banner with icon | `composites/{name}_banner_watermark.jpg` |

### Regenerating photography derivatives

Place or replace original PNGs in `photography/source/` locally (gitignored). Run from the repository root (requires Pillow):

```bash
python3 assets/brand/photography/generate_derivatives.py
```

Only `derivatives/`, `composites/`, `palette.json`, and `generate_derivatives.py` are committed. Original landscape PNGs in `source/` must never be pushed to GitHub or published on any public channel.

See [`photography/README.md`](photography/README.md) for the full derivatives-only policy.

## Git

Brand logos, photography derivatives, and composites are **committed** to the repository. Original landscape PNGs in `photography/source/` are **gitignored** (local reference only). Analysis charts in `06_Visualizations/*.png` remain gitignored.

Full channel rules: [`docs/brand_identity.md`](../../docs/brand_identity.md).
