# Brand assets — The Anatomy of Pace

Committed logo files for **Dr. Anatomy Pace** / *The Anatomy of Pace* laboratory. Dark-background treatment is canonical.

## Structure

```
assets/brand/
├── logo_icon_dark.png          # Icon mark (A + EKG)
├── logo_wordmark_dark.png      # Full lockup incl. PRIVATE RESEARCH LABORATORY
├── source/                     # Original logo uploads (reference)
├── variants/                   # Production logo sizes
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

Committed terrain imagery for Substack headers, Instagram, and GitHub social previews. Clinical Nordic-trail aesthetic — no faces, no personal identifiers in filenames.

```
photography/
├── source/              # Original PNG uploads (terrain_01..05 descriptive names)
├── derivatives/         # Processed JPEGs (quality 85)
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

After adding or replacing files in `source/`, run from the repository root (requires Pillow):

```bash
python3 assets/brand/photography/generate_derivatives.py
```

## Git

Brand logos and photography are **committed** to the repository. Analysis charts in `06_Visualizations/*.png` remain gitignored.

Full channel rules: [`docs/brand_identity.md`](../../docs/brand_identity.md).
