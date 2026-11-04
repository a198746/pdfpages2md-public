"""Core page-selective extraction and rendering."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Callable, Iterable

import pymupdf
from pymupdf4llm.helpers import pymupdf_rag as rag

from .code import extract_code_markdown
from .ocr import (
    OcrLine,
    OcrUnavailableError,
    count_text_chars,
    is_scanned,
    ocr_page_layout,
)
from .ocr_layout import reconstruct_ocr_markdown
from .ranges import parse_pages
from .translate import TranslationUnavailableError, translate_markdown, translate_text
from .vision import (
    should_use_vision,
    vision_available,
    vision_page_markdown,
)


@dataclass
class PageResult:
    """One selected page and everything needed to render/trace it."""

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
        return render(self, fmt=fmt, marker=marker)

    def sections(self, fmt: str = "markdown", marker: str = "comment") -> list[str]:
        return [
            _render_page(result, fmt=fmt, marker=marker, total=self.total_pages)
            for result in self.pages
        ]


_MARKERS = {"none", "comment", "heading", "both"}


def page_count(path: str) -> int:
    """Return the number of pages without extracting page contents."""
    with pymupdf.open(path) as doc:
        return doc.page_count


def _markdown_for_page(doc: pymupdf.Document, index: int) -> str:
    """Extract one page as Markdown using pymupdf4llm's text path."""
    text = rag.to_markdown(doc, pages=[index]).strip()
    return text


def _ocr_text_to_markdown(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    # Collapse triple newlines but keep paragraph breaks.
    return "\n\n".join(part for part in "\n".join(lines).split("\n\n") if part.strip())


def count_content_images(page: pymupdf.Page) -> int:
    """Count meaningful image placements, ignoring scans and tiny decorations.

    A scanned page is one full-page raster: that is the page's own background
    rather than a distinct picture, so it is excluded. Small icons and wide,
    short bands (barcodes/watermarks) are ignored as noise.
    """
    page_area = max(page.rect.width * page.rect.height, 1.0)
    count = 0
    for item in page.get_image_info(xrefs=True):
        bbox = pymupdf.Rect(item["bbox"])
        if bbox.width < 24 or bbox.height < 24:
            continue
        if bbox.width > 0 and bbox.height > 0 and bbox.width / bbox.height > 4:
            continue
        if bbox.get_area() / page_area >= 0.9:
            continue
        count += 1
    return count


def extract_pages(
    path: str,
    pages: str | Iterable[int] | None = None,
    *,
    ocr: bool = True,
    min_chars: int = 50,
    dpi: int = 200,
    ocr_lang: str = "eng",
    translate: bool = False,
    translate_engine: str | None = None,
    translate_api_key: str | None = None,
    translator: Callable[[str], str] | None = None,
    translate_plain: bool = True,
    vision: bool = True,
    vision_api_key: str | None = None,
    vision_transcriber: Callable[[pymupdf.Page], str] | None = None,
) -> ConvertResult:
    """Extract only the selected pages, loading them lazily.

    ``pages`` accepts either a spec string (``"1-10,50,88-95"``), an iterable of
    1-based page numbers, or ``None`` for every page. Scanned pages are OCR'd
    automatically unless ``ocr=False``. When ``translate`` is true the extracted
    English is translated to Simplified Chinese; ``translator`` can inject a
    deterministic function for testing. ``translate_plain`` controls whether the
    plain-text field is translated too; callers exporting only Markdown can set
    it to ``False`` to avoid an extra API call per page. Memory use is
    proportional to the number of *selected* pages, not the total page count.
    ``vision`` enables a vision-model fallback for scanned code/table pages and
    pages with poor OCR confidence; it does nothing unless ``VISION_API_KEY`` is
    configured. ``vision_transcriber`` can inject a deterministic function for
    testing.
    """
    if min_chars < 0:
        raise ValueError("min_chars must be >= 0")

    with pymupdf.open(path) as doc:
        total = doc.page_count
        if isinstance(pages, str) or pages is None:
            numbers = parse_pages(pages, page_count=total) if pages is not None else list(
                range(1, total + 1)
            )
        else:
            numbers = sorted({int(p) for p in pages})

        invalid = [p for p in numbers if p < 1 or p > total]
        if invalid:
            raise ValueError(f"page(s) out of range 1..{total}: {invalid}")

        results: list[PageResult] = []
        for number in numbers:
            page = doc.load_page(number - 1)
            scanned = is_scanned(page, min_chars=min_chars)
            native_text = page.get_text("text") or ""
            markdown = extract_code_markdown(page) or _markdown_for_page(
                doc, number - 1
            )
            note: str | None = None
            used_ocr = False
            used_vision = False
            engine: str | None = None
            ocr_lines: list[OcrLine] = []
            images = count_content_images(page)

            if scanned and ocr:
                try:
                    ocr_lines, ocr_text, engine = ocr_page_layout(
                        page, lang=ocr_lang, dpi=dpi
                    )
                    markdown = (
                        reconstruct_ocr_markdown(ocr_lines)
                        if ocr_lines
                        else _ocr_text_to_markdown(ocr_text)
                    )
                    used_ocr = True
                except OcrUnavailableError as exc:
                    note = str(exc)
            elif scanned:
                note = "page appears scanned (no text layer); pass --ocr to enable OCR"

            if used_ocr and vision and should_use_vision(
                markdown, ocr_lines, page=page
            ):
                try:
                    if vision_transcriber is not None:
                        markdown = vision_transcriber(page)
                        used_vision = True
                    elif vision_available(api_key=vision_api_key):
                        markdown = vision_page_markdown(page, api_key=vision_api_key)
                        used_vision = True
                except Exception as exc:  # noqa: BLE001 - keep OCR output on failure
                    note = f"vision fallback failed: {exc}"

            translated = False
            translated_markdown: str | None = None
            translated_text: str | None = None
            page_text = ocr_text if used_ocr else native_text
            if translate:
                try:
                    translated_markdown = translate_markdown(
                        markdown,
                        engine=translate_engine,
                        translator=translator,
                        api_key=translate_api_key,
                    )
                    if translate_plain:
                        translated_text = translate_text(
                            page_text,
                            engine=translate_engine,
                            translator=translator,
                            api_key=translate_api_key,
                        )
                    translated = True
                except TranslationUnavailableError as exc:
                    note = str(exc)

            results.append(
                PageResult(
                    page=number,
                    markdown=markdown,
                    text=page_text,
                    scanned=scanned,
                    images=images,
                    used_ocr=used_ocr,
                    used_vision=used_vision,
                    ocr_engine=engine,
                    note=note,
                    translated=translated,
                    translated_markdown=translated_markdown,
                    translated_text=translated_text,
                )
            )

        return ConvertResult(
            source=path,
            total_pages=total,
            selected_pages=numbers,
            pages=results,
        )


def _page_marker(page: int, total: int, marker: str) -> str:
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


def _render_page(
    result: PageResult, *, fmt: str, marker: str, total: int
) -> str:
    if fmt == "json":
        return json.dumps(asdict(result), ensure_ascii=False)

    head = _page_marker(result.page, total, marker)
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
    result: ConvertResult, *, fmt: str = "markdown", marker: str = "comment"
) -> str:
    """Render a :class:`ConvertResult` into a single string."""
    if fmt not in {"markdown", "text", "json"}:
        raise ValueError(f"unsupported format: {fmt!r}")
    if marker not in _MARKERS:
        raise ValueError(f"unknown marker style: {marker!r}")

    sections = [
        _render_page(page, fmt=fmt, marker=marker, total=result.total_pages)
        for page in result.pages
    ]
    if fmt == "json":
        records = [json.loads(section) for section in sections]
        return json.dumps(
            {
                "source": result.source,
                "total_pages": result.total_pages,
                "selected_pages": result.selected_pages,
                "pages": records,
            },
            ensure_ascii=False,
            indent=2,
        )
    return "\n".join(section.rstrip("\n") for section in sections).rstrip() + "\n"


def convert(
    path: str,
    pages: str | Iterable[int] | None = None,
    *,
    fmt: str = "markdown",
    ocr: bool = True,
    min_chars: int = 50,
    dpi: int = 200,
    ocr_lang: str = "eng",
    translate: bool = False,
    translate_engine: str | None = None,
    translate_api_key: str | None = None,
    translator: Callable[[str], str] | None = None,
    translate_plain: bool = True,
    vision: bool = True,
    vision_api_key: str | None = None,
    vision_transcriber: Callable[[pymupdf.Page], str] | None = None,
    marker: str = "comment",
) -> str:
    """Convenience wrapper: extract selected pages and render them."""
    return render(
        extract_pages(
            path,
            pages,
            ocr=ocr,
            min_chars=min_chars,
            dpi=dpi,
            ocr_lang=ocr_lang,
            translate=translate,
            translate_engine=translate_engine,
            translate_api_key=translate_api_key,
            translator=translator,
            translate_plain=translate_plain,
            vision=vision,
            vision_api_key=vision_api_key,
            vision_transcriber=vision_transcriber,
        ),
        fmt=fmt,
        marker=marker,
    )
