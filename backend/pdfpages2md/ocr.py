"""Scanned-page detection and pluggable OCR backends."""

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


_ocr_thread_state = threading.local()


def count_text_chars(page: pymupdf.Page) -> int:
    """Return the number of non-whitespace text characters on a page."""
    text = page.get_text("text") or ""
    return sum(1 for ch in text if not ch.isspace())


def is_scanned(page: pymupdf.Page, min_chars: int = 50) -> bool:
    """Heuristic: a page with very few text characters has no usable text layer."""
    return count_text_chars(page) < min_chars


def _tesseract(pix: pymupdf.Pixmap, lang: str) -> str:
    import pytesseract
    from PIL import Image

    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return pytesseract.image_to_string(img, lang=lang)


def _rapidocr_engine():
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


def _rapidocr(pix: pymupdf.Pixmap, lang: str) -> str:
    result = _rapidocr_raw(pix)
    if not result:
        return ""
    return "\n".join(item[1] for item in result if item and item[1])


_BACKENDS: list[tuple[str, Callable[[pymupdf.Pixmap, str], str]]] = [
    ("tesseract", _tesseract),
    ("rapidocr", _rapidocr),
]


def ocr_page_layout(
    page: pymupdf.Page,
    *,
    lang: str = "eng",
    dpi: int = 200,
) -> tuple[list[OcrLine], str, str]:
    """OCR a page and return positioned text regions plus the plain text.

    RapidOCR is preferred because it exposes bounding boxes. If it is not
    installed we fall back to Tesseract, which yields plain text without layout
    information (``lines`` is then empty).
    """
    pix = page.get_pixmap(dpi=dpi)
    errors: list[str] = []

    try:
        result = _rapidocr_raw(pix)
        lines: list[OcrLine] = []
        for item in result:
            box, text, score = item
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
        text = "\n".join(line.text for line in lines)
        return lines, text, "rapidocr"
    except ImportError as exc:
        errors.append(f"rapidocr: {exc}")
    except Exception as exc:  # noqa: BLE001 - surface backend failures clearly
        errors.append(f"rapidocr: {type(exc).__name__}: {exc}")

    try:
        text = _tesseract(pix, lang=lang)
        return [], text, "tesseract"
    except ImportError as exc:
        errors.append(f"tesseract: {exc}")
    except Exception as exc:  # noqa: BLE001 - surface backend failures clearly
        errors.append(f"tesseract: {type(exc).__name__}: {exc}")

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
