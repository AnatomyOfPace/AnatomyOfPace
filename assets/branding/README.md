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
├── logo-primary.svg             # PRIMARY logo (dark bg)
├── logo-primary-on-light.svg    # PRIMARY logo (light bg)
├── avatar-primary.png           # PRIMARY social avatar
├── avatar-primary-badge.png     # PRIMARY app icon
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

## Primary assets (selected)

Canonical primaries live at the root of this directory for easy grabbing:

- **Logo:** `logo-primary.svg` (vector mono-white, for dark backgrounds) —
  use `logo-primary-on-light.svg` on light backgrounds. The vector is the
  single source of geometry for the favicon, wordmark, and badge, so the whole
  system stays consistent and scales/recolors without loss.
- **Avatar (app icon):** `avatar-primary-badge.png` — matches the favicon set.
- **Avatar (social profile):** `avatar-primary.png`.
- **Favicon:** `favicon/favicon.ico` + `favicon/apple-touch-icon.png`.
- **Wordmark:** `lockup/wordmark-horizontal-white.svg`.

The cyan gradient (`logo/svg/logo-cyan.svg`) and other variations remain
available as secondary/accent options.

## Regenerating rasters

```bash
python assets/branding/tools/build_assets.py   # requires: cairosvg, Pillow
```

Edit the SVGs, then re-run to refresh the favicon set, wordmark PNGs, and
social crops.
