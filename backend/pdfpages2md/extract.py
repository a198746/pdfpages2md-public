"""Page-selective extraction pipeline.

The pipeline deliberately loads one page at a time (``doc.load_page``) so memory
use tracks the number of *selected* pages rather than the PDF's total size.
Optional work (OCR, vision fallback, translation) happens only for pages that
need it and fails soft: the extracted text is kept and a note is attached to the
page instead of aborting the whole conversion.

Rendering lives in :mod:`pdfpages2md.render`; the result containers live in
:mod:`pdfpages2md.models`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import pymupdf
from pymupdf4llm.helpers import pymupdf_rag as rag

from .code import extract_code_markdown
from .models import ConvertResult, PageResult
from .ocr import (
    OcrLine,
    OcrUnavailableError,
    is_scanned,
    ocr_page_layout,
)
from .ocr_layout import reconstruct_ocr_markdown
from .ranges import parse_pages
from .render import render
from .translate import TranslationUnavailableError, translate_markdown, translate_text
from .vision import should_use_vision, vision_available, vision_page_markdown

__all__ = [
    "ConvertResult",
    "ExtractOptions",
    "PageResult",
    "convert",
    "extract_pages",
    "page_count",
    "render",
]


@dataclass(frozen=True)
class ExtractOptions:
    """Every knob that affects an extraction run.

    The public functions still accept individual keyword arguments; this bundle
    exists so the pipeline can pass one object between its stages and so a new
    option only has to be added here and in the constructor call.
    """

    ocr: bool = True
    min_chars: int = 50
    dpi: int = 200
    ocr_lang: str = "eng"
    translate: bool = False
    translate_engine: str | None = None
    translate_api_key: str | None = None
    translate_plain: bool = True
    vision: bool = True
    vision_api_key: str | None = None
    translator: Callable[[str], str] | None = None
    vision_transcriber: Callable[[pymupdf.Page], str] | None = None


def page_count(path: str) -> int:
    """Return the number of pages without extracting page contents."""
    with pymupdf.open(path) as doc:
        return doc.page_count


def _markdown_for_page(doc: pymupdf.Document, index: int) -> str:
    """Extract one page as Markdown using pymupdf4llm's text path."""
    return rag.to_markdown(doc, pages=[index]).strip()


def _ocr_text_to_markdown(text: str) -> str:
    """Normalise plain OCR text into paragraphs separated by blank lines."""
    lines = [line.rstrip() for line in text.splitlines()]
    # Collapse triple newlines but keep paragraph breaks.
    return "\n\n".join(part for part in "\n".join(lines).split("\n\n") if part.strip())


def _ocr_markdown(lines: list[OcrLine], text: str) -> str:
    """Prefer layout reconstruction; fall back to plain OCR text."""
    return reconstruct_ocr_markdown(lines) if lines else _ocr_text_to_markdown(text)


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


def _resolve_page_numbers(
    pages: str | Iterable[int] | None,
    total: int,
) -> list[int]:
    """Turn a page spec, an iterable, or ``None`` into sorted 1-based numbers."""
    if pages is None:
        return list(range(1, total + 1))
    if isinstance(pages, str):
        return parse_pages(pages, page_count=total)
    return sorted({int(number) for number in pages})


def _vision_markdown(
    page: pymupdf.Page,
    markdown: str,
    options: ExtractOptions,
) -> tuple[str, bool, str | None]:
    """Try the vision fallback, returning the markdown to keep and any note."""
    try:
        if options.vision_transcriber is not None:
            return options.vision_transcriber(page), True, None
        if vision_available(api_key=options.vision_api_key):
            return (
                vision_page_markdown(page, api_key=options.vision_api_key),
                True,
                None,
            )
    except Exception as exc:  # noqa: BLE001 - keep OCR output on failure
        return markdown, False, f"vision fallback failed: {exc}"
    return markdown, False, None


def _apply_translation(
    page_text: str,
    markdown: str,
    options: ExtractOptions,
) -> tuple[bool, str | None, str | None, str | None]:
    """Translate the page, returning ``(translated, markdown, text, note)``."""
    try:
        translated_markdown = translate_markdown(
            markdown,
            engine=options.translate_engine,
            translator=options.translator,
            api_key=options.translate_api_key,
        )
        translated_text: str | None = None
        if options.translate_plain:
            translated_text = translate_text(
                page_text,
                engine=options.translate_engine,
                translator=options.translator,
                api_key=options.translate_api_key,
            )
        return True, translated_markdown, translated_text, None
    except TranslationUnavailableError as exc:
        return False, None, None, str(exc)


def _extract_page(
    doc: pymupdf.Document,
    number: int,
    options: ExtractOptions,
) -> PageResult:
    """Extract, OCR, enhance and translate exactly one page."""
    page = doc.load_page(number - 1)
    scanned = is_scanned(page, min_chars=options.min_chars)
    native_text = page.get_text("text") or ""
    markdown = extract_code_markdown(page) or _markdown_for_page(doc, number - 1)
    images = count_content_images(page)

    note: str | None = None
    used_ocr = False
    used_vision = False
    engine: str | None = None
    ocr_lines: list[OcrLine] = []
    ocr_text = ""

    if scanned and options.ocr:
        try:
            ocr_lines, ocr_text, engine = ocr_page_layout(
                page, lang=options.ocr_lang, dpi=options.dpi
            )
            markdown = _ocr_markdown(ocr_lines, ocr_text)
            used_ocr = True
        except OcrUnavailableError as exc:
            note = str(exc)
    elif scanned:
        note = "page appears scanned (no text layer); pass --ocr to enable OCR"

    if used_ocr and options.vision and should_use_vision(markdown, ocr_lines, page=page):
        markdown, used_vision, vision_note = _vision_markdown(page, markdown, options)
        if vision_note:
            note = vision_note

    page_text = ocr_text if used_ocr else native_text

    translated = False
    translated_markdown: str | None = None
    translated_text: str | None = None
    if options.translate:
        translated, translated_markdown, translated_text, translation_note = (
            _apply_translation(page_text, markdown, options)
        )
        if translation_note:
            note = translation_note

    return PageResult(
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

    options = ExtractOptions(
        ocr=ocr,
        min_chars=min_chars,
        dpi=dpi,
        ocr_lang=ocr_lang,
        translate=translate,
        translate_engine=translate_engine,
        translate_api_key=translate_api_key,
        translate_plain=translate_plain,
        vision=vision,
        vision_api_key=vision_api_key,
        translator=translator,
        vision_transcriber=vision_transcriber,
    )

    with pymupdf.open(path) as doc:
        total = doc.page_count
        numbers = _resolve_page_numbers(pages, total)

        invalid = [number for number in numbers if number < 1 or number > total]
        if invalid:
            raise ValueError(f"page(s) out of range 1..{total}: {invalid}")

        results = [_extract_page(doc, number, options) for number in numbers]

        return ConvertResult(
            source=path,
            total_pages=total,
            selected_pages=numbers,
            pages=results,
        )


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
