"""Scanned-page detection and pluggable OCR backends.

Both backends are optional and imported lazily, so native-text PDFs never pay
the import or rendering cost. RapidOCR is preferred because it exposes bounding
boxes; Tesseract is the fallback and yields plain text only.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable

import pymupdf

logger = logging.getLogger(__name__)


class OcrUnavailableError(RuntimeError):
    """Raised when OCR is requested but no backend can be imported."""


@dataclass(frozen=True)
class OcrLine:
    """One OCR text region with its pixel-space bounding box."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    score: float = 1.0


# (lines, plain text, engine name)
LayoutOutcome = tuple[list[OcrLine], str, str]
LayoutBackend = Callable[[pymupdf.Pixmap, str], LayoutOutcome]

_ocr_thread_state = threading.local()


def count_text_chars(page: pymupdf.Page) -> int:
    """Return the number of non-whitespace text characters on a page."""
    text = page.get_text("text") or ""
    return sum(1 for ch in text if not ch.isspace())


def is_scanned(page: pymupdf.Page, min_chars: int = 50) -> bool:
    """Heuristic: a page with very few text characters has no usable text layer."""
    return count_text_chars(page) < min_chars


def _tesseract_text(pix: pymupdf.Pixmap, lang: str) -> str:
    import pytesseract
    from PIL import Image

    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return pytesseract.image_to_string(img, lang=lang)


def _rapidocr_engine():
    """Return a per-thread RapidOCR engine (model loading is expensive)."""
    engine = getattr(_ocr_thread_state, "rapidocr_engine", None)
    if engine is None:
        from rapidocr_onnxruntime import RapidOCR

        engine = RapidOCR()
        _ocr_thread_state.rapidocr_engine = engine
    return engine


def _rapidocr_raw(pix: pymupdf.Pixmap) -> list:
    engine = _rapidocr_engine()
    # RapidOCR expects an encoded image (or a path/array); raw Pixmap samples
    # are not valid image bytes for Pillow's decoder.
    result, _ = engine(pix.tobytes("png"))
    return result or []


def _rapidocr_lines(pix: pymupdf.Pixmap) -> list[OcrLine]:
    """Convert RapidOCR's ``(box, text, score)`` tuples into ``OcrLine``."""
    lines: list[OcrLine] = []
    for box, text, score in _rapidocr_raw(pix):
        if not text:
            continue
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        lines.append(
            OcrLine(
                text=text,
                x0=min(xs),
                y0=min(ys),
                x1=max(xs),
                y1=max(ys),
                score=float(score),
            )
        )
    return lines


def _rapidocr_layout(pix: pymupdf.Pixmap, lang: str) -> LayoutOutcome:
    lines = _rapidocr_lines(pix)
    return lines, "\n".join(line.text for line in lines), "rapidocr"


def _tesseract_layout(pix: pymupdf.Pixmap, lang: str) -> LayoutOutcome:
    return [], _tesseract_text(pix, lang=lang), "tesseract"


_LAYOUT_BACKENDS: tuple[tuple[str, LayoutBackend], ...] = (
    ("rapidocr", _rapidocr_layout),
    ("tesseract", _tesseract_layout),
)


def ocr_page_layout(
    page: pymupdf.Page,
    *,
    lang: str = "eng",
    dpi: int = 200,
) -> LayoutOutcome:
    """OCR a page and return positioned text regions plus the plain text.

    Backends are tried in priority order. If none can run,
    :class:`OcrUnavailableError` carries the reason for every attempt.
    """
    pix = page.get_pixmap(dpi=dpi)
    errors: list[str] = []

    for name, backend in _LAYOUT_BACKENDS:
        try:
            return backend(pix, lang)
        except ImportError as exc:
            errors.append(f"{name}: {exc}")
        except Exception as exc:  # noqa: BLE001 - surface backend failures clearly
            errors.append(f"{name}: {type(exc).__name__}: {exc}")

    detail = "; ".join(errors) or "no OCR backend configured"
    raise OcrUnavailableError(
        "OCR requested but no backend is available "
        f"(install pytesseract + Tesseract, or rapidocr-onnxruntime). {detail}"
    )


def ocr_page(
    page: pymupdf.Page,
    *,
    lang: str = "eng",
    dpi: int = 200,
) -> tuple[str, str]:
    """OCR a rendered page with the first available backend.

    Returns ``(text, engine_name)``. Raises :class:`OcrUnavailableError` when no
    backend is installed. OCR is intentionally lazy so that native-text pages
    never pay the rendering/OCR cost.
    """
    _, text, engine = ocr_page_layout(page, lang=lang, dpi=dpi)
    return text, engine
