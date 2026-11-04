"""Generate a large sample PDF for demonstrating page-selective extraction.

Creates a 520-page PDF where pages carry a text layer, except for a handful of
image-only pages (no text layer) that exercise the scanned-page detection path.
"""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw


TOTAL_PAGES = 520
SCANNED_PAGES = {105, 300}


def _image_only_page(doc: pymupdf.Document, label: str) -> None:
    page = doc.new_page(width=595, height=842)  # A4 portrait
    img = Image.new("RGB", (1190, 1684), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle((80, 80, 1110, 1604), outline="black", width=4)
    draw.text((180, 220), "SCANNED DOCUMENT", fill="black")
    draw.text((180, 320), label, fill="black")
    draw.text((180, 420), "This page intentionally has no text layer.", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    page.insert_image(page.rect, stream=buf.getvalue())


def _text_page(doc: pymupdf.Document, number: int) -> None:
    page = doc.new_page(width=595, height=842)
    y = 72
    page.insert_text(
        (72, y), f"Section {number} Report", fontsize=18, fontname="hebo"
    )
    y += 40
    body = [
        f"This is page {number} of the constructed sample document.",
        "It is intended to verify that only the requested pages are read,",
        "that original page numbers are preserved in the output Markdown,",
        "and that extraction stays fast and memory-proportional for large PDFs.",
        "",
        "The quick brown fox jumps over the lazy dog.",
        "Alpha bravo charlie delta echo foxtrot golf hotel.",
    ]
    for line in body:
        page.insert_text((72, y), line, fontsize=11, fontname="helv")
        y += 22


def build(path: str | Path) -> Path:
    path = Path(path)
    doc = pymupdf.open()
    try:
        for number in range(1, TOTAL_PAGES + 1):
            if number in SCANNED_PAGES:
                _image_only_page(doc, f"page {number}")
            else:
                _text_page(doc, number)
        doc.save(str(path))
    finally:
        doc.close()
    return path


if __name__ == "__main__":
    target = Path(__file__).with_name("sample_520.pdf")
    build(target)
    print(f"wrote {target} with {TOTAL_PAGES} pages")
