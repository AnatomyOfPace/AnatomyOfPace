# Brand Assets — The Anatomy of Pace

Public visual identity for *The Anatomy of Pace*. Every asset here is the
abstract **peak-and-pulse** mark (a mountain forming the letter "A", with an
ECG pulse as its crossbar) or a fully synthetic landscape. Attribution is to
**Dr. Anatomy Pace** / the laboratory only.

> **Firewall rule (non-negotiable):** No real-person photography, names, or
> location metadata may be added to this directory or used in public output.
> See `docs/brand_identity.md`.

## Palette

| Token | Hex | Use |
|-------|-----|-----|
| Charcoal | `#0D0F12` | Primary background / dark mark |
| Off-white | `#F2F5F7` | Light background / light mark |
| Cyan | `#7FE9E6` → `#2C8C8A` | Telemetry accent |

## Structure

```
assets/branding/
├── logo/
│   ├── svg/                     # vector sources (scalable, recolorable)
│   │   ├── logo.svg             # master — uses currentColor
│   │   ├── logo-mono-white.svg  # white, for dark backgrounds
│   │   ├── logo-mono-dark.svg   # charcoal, for light backgrounds
│   │   ├── logo-cyan.svg        # gradient accent
│   │   └── logo-badge-dark.svg  # white mark on dark rounded square
│   └── logo_variation_*.png     # raster concept variations
├── lockup/                      # horizontal wordmark (mark + name)
│   ├── wordmark-horizontal-white.svg  (+ .png)
│   └── wordmark-horizontal-dark.svg   (+ .png)
├── avatars/                     # square/circular profile avatars
├── favicon/                     # 16–512px icons + favicon.ico
├── heroes/                      # synthetic landscape hero images
├── social/                      # platform crops (square, circle, banner)
├── mockups/                     # product mockups (cap)
└── tools/build_assets.py        # regenerates favicon/lockup/social rasters
```

## Primary assets

- **Logo:** `logo/svg/logo-mono-white.svg` (dark bg) / `logo-mono-dark.svg` (light bg)
- **Avatar:** `avatars/avatar_1_dark_primary.png`
- **Favicon:** `favicon/favicon.ico` + `favicon/apple-touch-icon.png`
- **Wordmark:** `lockup/wordmark-horizontal-white.svg`

## Regenerating rasters

```bash
python assets/branding/tools/build_assets.py   # requires: cairosvg, Pillow
```

Edit the SVGs, then re-run to refresh the favicon set, wordmark PNGs, and
social crops.
