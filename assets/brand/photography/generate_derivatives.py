#!/usr/bin/env python3
"""Generate brand photography derivatives for The Anatomy of Pace.

Reads original landscape PNGs from local ``photography/source/`` (gitignored).
Writes committed public assets only: ``derivatives/``, ``composites/``, and
``palette.json``. Originals must never be committed or published — derivatives,
composites, and AI video clips are the only photography permitted on GitHub and
public channels. See ``photography/README.md`` and ``docs/brand_identity.md``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image, ImageEnhance

REPO = Path(__file__).resolve().parents[3]
PHOTO = REPO / "assets/brand/photography"
ICON = REPO / "assets/brand/variants/icon_square_512.png"
SOURCE_DIR = PHOTO / "source"

CHARCOAL = "#1a1a1a"
JPEG_QUALITY = 85

SOURCES = [
    ("terrain_valley_green", SOURCE_DIR / "terrain_valley_green.png"),
    ("terrain_peak_fjord", SOURCE_DIR / "terrain_peak_fjord.png"),
    ("terrain_range_cloud", SOURCE_DIR / "terrain_range_cloud.png"),
    ("terrain_cairn_summit", SOURCE_DIR / "terrain_cairn_summit.png"),
    ("terrain_fjord_vertical", SOURCE_DIR / "terrain_fjord_vertical.png"),
]

PORTRAIT_NAMES = {"terrain_cairn_summit", "terrain_fjord_vertical"}


def center_crop_aspect(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    target_ratio = target_w / target_h
    w, h = img.size
    current_ratio = w / h
    if current_ratio > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        box = (left, 0, left + new_w, h)
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        box = (0, top, w, top + new_h)
    cropped = img.crop(box)
    return cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)


def clinical_tone(img: Image.Image) -> Image.Image:
    rgb = img.convert("RGB")
    rgb = ImageEnhance.Color(rgb).enhance(0.52)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.18)
    rgb = ImageEnhance.Brightness(rgb).enhance(0.96)
    r, g, b = rgb.split()
    r = r.point(lambda x: int(x * 0.90))
    g = g.point(lambda x: int(x * 0.97))
    b = b.point(lambda x: min(255, int(x * 1.10)))
    return Image.merge("RGB", (r, g, b))


def dark_overlay(img: Image.Image, alpha: float = 0.40) -> Image.Image:
    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, CHARCOAL)
    return Image.blend(base, overlay, alpha).convert("RGB")


def save_jpg(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(path, "JPEG", quality=JPEG_QUALITY, optimize=True)


def extract_palette(img: Image.Image, n: int = 6) -> list[dict]:
    small = img.convert("RGB").resize((200, 200), Image.Resampling.LANCZOS)
    quantized = small.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    palette_raw = quantized.getpalette() or []
    counts = quantized.histogram()
    entries = []
    for i in range(n):
        if counts[i] == 0:
            continue
        r, g, b = palette_raw[i * 3], palette_raw[i * 3 + 1], palette_raw[i * 3 + 2]
        entries.append(
            {
                "hex": f"#{r:02x}{g:02x}{b:02x}",
                "rgb": [r, g, b],
                "weight": round(counts[i] / sum(counts), 4),
            }
        )
    entries.sort(key=lambda e: e["weight"], reverse=True)
    return entries[:n]


def apply_watermark(img: Image.Image, icon: Image.Image) -> Image.Image:
    base = img.convert("RGBA")
    w, h = base.size
    icon_w = max(32, int(w * 0.08))
    icon_h = int(icon.size[1] * icon_w / icon.size[0])
    mark = icon.resize((icon_w, icon_h), Image.Resampling.LANCZOS)
    if mark.mode != "RGBA":
        mark = mark.convert("RGBA")
    alpha = mark.split()[3].point(lambda a: int(a * 0.70))
    mark.putalpha(alpha)
    margin = int(w * 0.04)
    pos = (w - icon_w - margin, h - icon_h - margin)
    base.paste(mark, pos, mark)
    return base.convert("RGB")


def process_name(name: str, src_path: Path, icon: Image.Image) -> dict:
    out_src = PHOTO / "source" / f"{name}.png"
    shutil.copy2(src_path, out_src)

    img = Image.open(src_path)
    deriv_dir = PHOTO / "derivatives"
    composite_dir = PHOTO / "composites"

    clinical = clinical_tone(img)
    save_jpg(clinical, deriv_dir / f"{name}_clinical.jpg")

    overlay = dark_overlay(clinical)
    save_jpg(overlay, deriv_dir / f"{name}_dark_overlay.jpg")

    banner = center_crop_aspect(clinical, 1920, 1080)
    save_jpg(banner, deriv_dir / f"{name}_banner_16x9.jpg")

    square = center_crop_aspect(clinical, 1080, 1080)
    save_jpg(square, deriv_dir / f"{name}_square_1080.jpg")

    story = center_crop_aspect(clinical, 1080, 1920)
    save_jpg(story, deriv_dir / f"{name}_story_9x16.jpg")

    composite_path = composite_dir / f"{name}_banner_watermark.jpg"
    watermarked = apply_watermark(banner, icon)
    save_jpg(watermarked, composite_path)

    return {
        "name": name,
        "source": str(out_src.relative_to(REPO)),
        "orientation": "portrait" if name in PORTRAIT_NAMES else "landscape",
        "source_size": list(img.size),
        "palette": extract_palette(clinical),
    }


def main() -> None:
    for sub in ("source", "derivatives", "composites"):
        (PHOTO / sub).mkdir(parents=True, exist_ok=True)

    icon = Image.open(ICON).convert("RGBA")
    palettes = {}
    for name, src in SOURCES:
        if not src.exists():
            raise FileNotFoundError(f"Missing source: {src}")
        palettes[name] = process_name(name, src, icon)

    palette_path = PHOTO / "palette.json"
    palette_path.write_text(json.dumps(palettes, indent=2) + "\n", encoding="utf-8")

    src_count = len(list((PHOTO / "source").glob("*.png")))
    deriv_count = len(list((PHOTO / "derivatives").glob("*.jpg")))
    comp_count = len(list((PHOTO / "composites").glob("*.jpg")))
    print(f"Sources: {src_count}")
    print(f"Derivatives: {deriv_count}")
    print(f"Composites: {comp_count}")
    print(f"Palette: {palette_path}")


if __name__ == "__main__":
    main()
