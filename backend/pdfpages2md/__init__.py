"""Selective, page-exact PDF to Markdown/text/JSON conversion.

The public surface is intentionally small:

    from pdfpages2md import convert, page_count
    from pdfpages2md.ranges import parse_pages

    total = page_count("huge.pdf")
    md = convert("huge.pdf", pages="100-110")

This package wraps PyMuPDF and pymupdf4llm for the heavy lifting and adds the
pieces that matter for LLM ingestion: exact page selection, original page
markers, targeted OCR for scanned pages, and optional chunking.
"""

from __future__ import annotations

from .extract import (
    ConvertResult,
    ExtractOptions,
    PageResult,
    convert,
    extract_pages,
    page_count,
)
from .ranges import parse_pages
from .render import render

__all__ = [
    "ConvertResult",
    "ExtractOptions",
    "PageResult",
    "convert",
    "extract_pages",
    "page_count",
    "parse_pages",
    "render",
]

__version__ = "0.1.0"
