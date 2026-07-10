#!/usr/bin/env python3
"""
Render Substack markdown to PDF with embedded blog figures.

Usage (repo root):
    python3 04_Python_Scripts/render_sut43_substack_pdf.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from fpdf import FPDF

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = BASE_DIR / "docs" / "publications" / "sut43_gramstad_paired_trf_substack.md"
DEFAULT_OUTPUT = BASE_DIR / "docs" / "publications" / "sut43_gramstad_paired_trf_substack.pdf"
VIS_DIR = BASE_DIR / "06_Visualizations"

FIGURE_MAP = {
    "sut43_gramstad_friction_strip_blog.png": VIS_DIR / "sut43_gramstad_friction_strip_blog.png",
    "sut43_trf_dilution_blog.png": VIS_DIR / "sut43_trf_dilution_blog.png",
    "sut43_gramstad_paired_trf_blog.png": VIS_DIR / "sut43_gramstad_paired_trf_blog.png",
}

DILUTION_FULL = 0.08
DILUTION_GRAMSTAD = 0.68

MARGIN = 18
PAGE_W = 210
CONTENT_W = PAGE_W - 2 * MARGIN


def ensure_dilution_figure(path: Path) -> Path:
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    labels = ["Full race\nkm 0.5-43", "Gramstad\nkm 29-41"]
    vals = [DILUTION_FULL, DILUTION_GRAMSTAD]
    fig, ax = plt.subplots(figsize=(6, 4))
    fig.patch.set_facecolor("#0A0A0A")
    ax.set_facecolor("#111111")
    bars = ax.bar(labels, vals, color="#FFB74D", edgecolor="#333333")
    ax.axhline(0, color="#888888", linewidth=1)
    ax.set_ylabel("delta-TI vs cohort median", color="#E0E0E0")
    ax.set_title("Subject_A - F3 downhill hike (window dilution)", color="#E0E0E0", fontsize=11)
    for bar, val in zip(bars, vals):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.02,
            f"{val:+.2f}",
            ha="center",
            color="#E0E0E0",
            fontsize=10,
        )
    ax.tick_params(colors="#E0E0E0")
    for spine in ax.spines.values():
        spine.set_color("#333333")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  Generated missing figure -> {path.relative_to(BASE_DIR)}")
    return path


def ascii_normalize(text: str) -> str:
    for old, new in (
        ("Δ", "delta"),
        ("−", "-"),
        ("–", "-"),
        ("—", "-"),
        ("≈", "~"),
        ("·", " - "),
        ("→", "->"),
        ("\u2019", "'"),
        ("\u201c", '"'),
        ("\u201d", '"'),
    ):
        text = text.replace(old, new)
    return text


def strip_metadata(text: str) -> str:
    text = re.sub(r"^<!-- SUBSTACK METADATA.*?-->\s*", "", text, count=1, flags=re.DOTALL)
    # Restore figure paths from Substack upload placeholders.
    text = re.sub(
        r"!\[([^\]]*)\]\(\s*<!-- UPLOAD:\s*06_Visualizations/([^>]+?)\s*-->\s*\)",
        r"![\1](06_Visualizations/\2)",
        text,
    )
    return text


def resolve_image(line: str) -> Path | None:
    m = re.search(r"06_Visualizations/([^\s)]+)", line)
    if m:
        return FIGURE_MAP.get(m.group(1), VIS_DIR / m.group(1))
    for name, path in FIGURE_MAP.items():
        if name in line:
            return path
    return None


class SubstackPDF(FPDF):
    def __init__(self) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=MARGIN)
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self.set_font("Helvetica", size=10)

    def write_heading(self, text: str, level: int) -> None:
        sizes = {1: 16, 2: 13, 3: 11}
        self.set_font("Helvetica", "B", sizes.get(level, 11))
        self.multi_cell(CONTENT_W, 7, ascii_normalize(text))
        self.ln(2)
        self.set_font("Helvetica", size=10)

    def write_body(self, text: str, *, bold: bool = False) -> None:
        style = "B" if bold else ""
        self.set_font("Helvetica", style, 10)
        plain = ascii_normalize(re.sub(r"\*\*([^*]+)\*\*", r"\1", text))
        self.multi_cell(CONTENT_W, 5.5, plain)
        self.ln(1)

    def write_table(self, rows: list[list[str]]) -> None:
        if not rows:
            return
        ncols = len(rows[0])
        col_w = CONTENT_W / ncols
        self.set_font("Helvetica", "B", 9)
        for i, cell in enumerate(rows[0]):
            self.cell(col_w, 7, ascii_normalize(cell)[:40], border=1)
        self.ln()
        self.set_font("Helvetica", size=9)
        for row in rows[1:]:
            for cell in row:
                self.cell(col_w, 7, ascii_normalize(re.sub(r"\*\*([^*]+)\*\*", r"\1", cell))[:45], border=1)
            self.ln()
        self.ln(2)

    def write_image(self, path: Path, caption: str | None = None) -> None:
        if not path.exists():
            self.write_body(f"[Figure missing: {path.name}]", bold=True)
            return
        from PIL import Image

        with Image.open(path) as im:
            w_px, h_px = im.size
        aspect = h_px / w_px
        img_w = CONTENT_W
        img_h = img_w * aspect
        max_h = 95
        if img_h > max_h:
            img_h = max_h
            img_w = img_h / aspect
        if self.get_y() + img_h > 297 - MARGIN:
            self.add_page()
        x = MARGIN + (CONTENT_W - img_w) / 2
        self.image(str(path), x=x, w=img_w, h=img_h)
        self.ln(2)
        if caption:
            self.set_font("Helvetica", "I", 9)
            self.multi_cell(CONTENT_W, 5, ascii_normalize(caption))
            self.ln(2)
            self.set_font("Helvetica", size=10)


def render_pdf(source: Path, output: Path) -> Path:
    ensure_dilution_figure(FIGURE_MAP["sut43_trf_dilution_blog.png"])
    missing = [n for n, p in FIGURE_MAP.items() if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing figures: {', '.join(missing)}")

    pdf = SubstackPDF()
    pdf.add_page()

    lines = strip_metadata(source.read_text(encoding="utf-8")).splitlines()
    in_code = False
    code_lines: list[str] = []
    table_rows: list[list[str]] = []
    pending_caption: str | None = None

    def flush_code() -> None:
        nonlocal code_lines
        if not code_lines:
            return
        pdf.set_font("Courier", size=9)
        for cl in code_lines:
            pdf.multi_cell(CONTENT_W, 4.5, ascii_normalize(cl))
        pdf.ln(2)
        pdf.set_font("Helvetica", size=10)
        code_lines = []

    def flush_table() -> None:
        nonlocal table_rows
        if table_rows:
            pdf.write_table(table_rows)
            table_rows = []

    for raw in lines:
        line = raw.rstrip()

        if line.startswith("```"):
            if in_code:
                in_code = False
                flush_code()
            else:
                flush_table()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue

        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not all(set(c) <= {"-", ":"} for c in cells):
                table_rows.append(cells)
            continue
        flush_table()

        if not line.strip():
            continue
        if line.strip() == "---":
            pdf.ln(2)
            continue

        img = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", line)
        if img:
            path = resolve_image(line)
            if path:
                pdf.write_image(path, pending_caption)
                pending_caption = None
            continue

        if line.startswith("*") and line.endswith("*") and not line.startswith("**"):
            pending_caption = line.strip("*")
            continue

        if line.startswith("# "):
            pdf.write_heading(line[2:], 1)
        elif line.startswith("## "):
            pdf.write_heading(line[3:], 2)
        elif line.startswith("### "):
            pdf.write_heading(line[4:], 3)
        elif line.startswith("> "):
            pdf.set_font("Helvetica", "I", 10)
            pdf.multi_cell(CONTENT_W, 5.5, ascii_normalize(line[2:]))
            pdf.ln(2)
            pdf.set_font("Helvetica", size=10)
        elif line.startswith("**") and line.endswith("**"):
            pdf.write_body(line.strip("*"), bold=True)
        else:
            pdf.write_body(line)

    flush_code()
    flush_table()

    output.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output))
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render SUT_43 Substack post as PDF with figures.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    source = args.source if args.source.is_absolute() else BASE_DIR / args.source
    output = args.output if args.output.is_absolute() else BASE_DIR / args.output
    if not source.exists():
        print(f"Missing source: {source}", file=sys.stderr)
        return 1
    out = render_pdf(source, output)
    print(f"OK PDF -> {out.relative_to(BASE_DIR)} ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
