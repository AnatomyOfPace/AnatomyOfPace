#!/usr/bin/env python3
"""Build rasterized brand assets from the vector sources.

Generates the favicon / app-icon set, wordmark PNG exports, and platform
crops of the synthetic hero images. Reproducible: re-run after editing any SVG.

Usage:
    python assets/branding/tools/build_assets.py

Requires: cairosvg, Pillow.
All outputs are the abstract mark or fully synthetic landscapes only,
per the Ghost Authority firewall (no real-person imagery, no location metadata).
"""
from __future__ import annotations

import io
from pathlib import Path

import cairosvg
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT / "logo" / "svg"
LOCKUP = ROOT / "lockup"
HEROES = ROOT / "heroes"
FAVICON = ROOT / "favicon"
SOCIAL = ROOT / "social"


def render_svg(svg_path: Path, width: int, height: int | None = None) -> Image.Image:
    png_bytes = cairosvg.svg2png(
        url=str(svg_path), output_width=width, output_height=height
    )
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def build_favicons() -> None:
    FAVICON.mkdir(parents=True, exist_ok=True)
    badge = SVG / "logo-badge-dark.svg"
    sizes = {
        "favicon-16.png": 16,
        "favicon-32.png": 32,
        "favicon-48.png": 48,
        "apple-touch-icon.png": 180,
        "icon-192.png": 192,
        "icon-512.png": 512,
    }
    for name, size in sizes.items():
        render_svg(badge, size, size).save(FAVICON / name)
        print("favicon:", name)

    ico = render_svg(badge, 256, 256)
    ico.save(
        FAVICON / "favicon.ico",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("favicon: favicon.ico")


def build_wordmarks() -> None:
    for variant in ("white", "dark"):
        src = LOCKUP / f"wordmark-horizontal-{variant}.svg"
        img = render_svg(src, 1800)
        img.save(LOCKUP / f"wordmark-horizontal-{variant}.png")
        print("wordmark:", src.name, "->", img.size)


def center_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        box = (left, 0, left + new_w, src_h)
    else:
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        box = (0, top, src_w, top + new_h)
    return img.crop(box).resize((target_w, target_h), Image.LANCZOS)


def circle_mask(img: Image.Image) -> Image.Image:
    from PIL import ImageDraw

    size = min(img.size)
    sq = center_crop(img, size, size)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(sq, (0, 0), mask)
    return out


def build_social() -> None:
    SOCIAL.mkdir(parents=True, exist_ok=True)
    heroes = {
        "fjord": HEROES / "hero_1_fjord_vista.png",
        "ridge": HEROES / "hero_2_peak_pulse_ridge.png",
        "plateau": HEROES / "hero_3_plateau_banner.png",
        "cairn": HEROES / "hero_4_cairn_duotone.png",
    }
    for name, path in heroes.items():
        img = Image.open(path).convert("RGBA")
        center_crop(img, 1080, 1080).save(SOCIAL / f"{name}_square_1080.png")
        print("social square:", name)

    plateau = Image.open(heroes["plateau"]).convert("RGBA")
    center_crop(plateau, 1500, 500).save(SOCIAL / "banner_1500x500.png")
    center_crop(plateau, 1280, 640).save(SOCIAL / "github_social_1280x640.png")
    print("social banner + github preview: plateau")

    fjord = Image.open(heroes["fjord"]).convert("RGBA")
    circle_mask(fjord).save(SOCIAL / "fjord_circle.png")
    print("social circle: fjord")


def main() -> None:
    build_favicons()
    build_wordmarks()
    build_social()
    print("Done.")


if __name__ == "__main__":
    main()
