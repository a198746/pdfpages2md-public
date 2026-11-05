"""Result data structures shared by extraction, rendering and the web layer.

These are plain dataclasses: they carry data but know nothing about PyMuPDF or
HTTP. Rendering is delegated to :mod:`pdfpages2md.render`, which keeps the
extraction pipeline and the output formats independent of each other.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PageResult:
    """One selected page plus everything needed to render or trace it."""

    page: int
    markdown: str
    text: str
    scanned: bool
    images: int = 0
    used_ocr: bool = False
    used_vision: bool = False
    ocr_engine: str | None = None
    note: str | None = None
    translated: bool = False
    translated_markdown: str | None = None
    translated_text: str | None = None


@dataclass
class ConvertResult:
    """Result of a conversion run, including source-level metadata."""

    source: str
    total_pages: int
    selected_pages: list[int]
    pages: list[PageResult]

    def render(self, fmt: str = "markdown", marker: str = "comment") -> str:
        """Render every page into one document."""
        from .render import render

        return render(self, fmt=fmt, marker=marker)

    def sections(self, fmt: str = "markdown", marker: str = "comment") -> list[str]:
        """Render one section per page, for chunked output."""
        from .render import render_page

        return [
            render_page(result, fmt=fmt, marker=marker) for result in self.pages
        ]
