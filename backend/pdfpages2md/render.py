"""Rendering of extracted pages into Markdown, plain text or JSON.

Rendering is intentionally separate from extraction: a :class:`ConvertResult`
can be rendered any number of times, in any supported format, without touching
the PDF again.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from .models import ConvertResult, PageResult

FORMATS = frozenset({"markdown", "text", "json"})
MARKERS = frozenset({"none", "comment", "heading", "both"})


def page_marker(page: int, marker: str) -> str:
    """Return the page marker prefix for the requested style."""
    if marker == "none":
        return ""
    comment = f"<!-- page {page} -->"
    if marker == "comment":
        return comment + "\n\n"
    if marker == "heading":
        return f"## Page {page}\n\n"
    if marker == "both":
        return comment + "\n\n" + f"## Page {page}\n\n"
    raise ValueError(f"unknown marker style: {marker!r}")


def _image_placeholder(count: int, fmt: str) -> str:
    if count <= 0:
        return ""
    label = "此处为图片" if count == 1 else f"此处为图片 (共 {count} 张)"
    if fmt == "text":
        return f"[{label}]"
    return f"<!-- {label} -->"


def render_page(
    result: PageResult,
    *,
    fmt: str = "markdown",
    marker: str = "comment",
) -> str:
    """Render a single page. JSON pages are emitted as standalone objects."""
    if fmt == "json":
        return json.dumps(asdict(result), ensure_ascii=False)

    head = page_marker(result.page, marker)
    if result.translated:
        body = (result.translated_markdown or result.markdown).strip()
        if fmt == "text":
            body = (result.translated_text or result.text).strip()
    else:
        body = result.markdown.strip()
        if fmt == "text":
            body = result.text.strip()

    parts: list[str] = []
    if head:
        parts.append(head.rstrip("\n"))
    if body:
        parts.append(body)
    image_note = _image_placeholder(result.images, fmt)
    if image_note:
        parts.append(image_note)
    if result.note:
        parts.append(f"<!-- note: {result.note} -->")

    return "\n\n".join(parts) + "\n"


def render(
    result: ConvertResult,
    *,
    fmt: str = "markdown",
    marker: str = "comment",
) -> str:
    """Render a :class:`ConvertResult` into a single string."""
    if fmt not in FORMATS:
        raise ValueError(f"unsupported format: {fmt!r}")
    if marker not in MARKERS:
        raise ValueError(f"unknown marker style: {marker!r}")

    pages = [render_page(page, fmt=fmt, marker=marker) for page in result.pages]
    if fmt == "json":
        return json.dumps(
            {
                "source": result.source,
                "total_pages": result.total_pages,
                "selected_pages": result.selected_pages,
                "pages": [json.loads(page) for page in pages],
            },
            ensure_ascii=False,
            indent=2,
        )
    return "\n".join(page.rstrip("\n") for page in pages).rstrip() + "\n"
