"""Conversion orchestration for the web API.

The HTTP layer only deals with transports: this module turns a validated upload
plus a :class:`ConvertRequest` into a :class:`ConversionOutcome`. Keeping it
independent of ``BaseHTTPRequestHandler`` makes the conversion path reusable
(e.g. from tests or an alternative server) and keeps temp-file cleanup in one
place.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from ..extract import extract_pages
from ..render import render
from .multipart import Fields, as_bool, as_int, field

logger = logging.getLogger("pdfpages2md.server")

DEFAULT_MIN_CHARS = 50
DEFAULT_DPI = 200
DEFAULT_OCR_LANG = "eng"


@dataclass(frozen=True)
class ConvertRequest:
    """Validated conversion parameters submitted by the browser."""

    pages: str | None = None
    fmt: str = "markdown"
    marker: str = "comment"
    ocr: bool = True
    ocr_lang: str = DEFAULT_OCR_LANG
    min_chars: int = DEFAULT_MIN_CHARS
    dpi: int = DEFAULT_DPI
    translate: bool = False
    translate_engine: str | None = None
    vision: bool = True
    translate_api_key: str | None = None
    vision_api_key: str | None = None

    @classmethod
    def from_fields(
        cls,
        fields: Fields,
        *,
        translate_api_key: str | None = None,
        vision_api_key: str | None = None,
    ) -> "ConvertRequest":
        """Build a request from multipart fields, resolving keys beforehand."""
        engine = field(fields, "translate_engine") or None
        if engine == "auto":
            engine = None
        return cls(
            pages=field(fields, "pages") or None,
            fmt=field(fields, "format") or "markdown",
            marker=field(fields, "marker") or "comment",
            ocr=as_bool(field(fields, "ocr"), default=True),
            ocr_lang=field(fields, "ocr_lang") or DEFAULT_OCR_LANG,
            min_chars=as_int(field(fields, "min_chars"), DEFAULT_MIN_CHARS),
            dpi=as_int(field(fields, "dpi"), DEFAULT_DPI),
            translate=as_bool(field(fields, "translate"), default=False),
            translate_engine=engine,
            vision=as_bool(field(fields, "vision"), default=True),
            translate_api_key=translate_api_key,
            vision_api_key=vision_api_key,
        )


@dataclass(frozen=True)
class ConversionOutcome:
    """Everything the browser needs to show and download the result."""

    source: str
    total_pages: int
    selected_pages: list[int]
    scanned_pages: int
    ocr_pages: int
    translated_pages: int
    vision_pages: int
    format: str
    output: str
    download_name: str

    def to_payload(self) -> dict:
        """Return the JSON response body, without the outer ``ok`` flag."""
        return asdict(self)


def convert_upload(filename: str, data: bytes, request: ConvertRequest) -> ConversionOutcome:
    """Convert an uploaded PDF and clean up the temporary file afterwards."""
    stem = Path(filename).stem
    suffix = Path(filename).suffix or ".pdf"
    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=suffix,
            prefix="pdfpages2md_",
        ) as temp_file:
            temp_file.write(data)
            temp_path = Path(temp_file.name)

        result = extract_pages(
            str(temp_path),
            request.pages,
            ocr=request.ocr,
            min_chars=request.min_chars,
            dpi=request.dpi,
            ocr_lang=request.ocr_lang,
            translate=request.translate,
            translate_engine=request.translate_engine,
            translate_api_key=request.translate_api_key,
            translate_plain=request.fmt != "markdown",
            vision=request.vision,
            vision_api_key=request.vision_api_key,
        )
        output = render(result, fmt=request.fmt, marker=request.marker)

        ext = request.fmt if request.fmt != "text" else "txt"
        download_name = (
            f"{stem}.zh.{ext}" if request.translate else f"{stem}.{ext}"
        )

        return ConversionOutcome(
            source=filename,
            total_pages=result.total_pages,
            selected_pages=result.selected_pages,
            scanned_pages=sum(1 for page in result.pages if page.scanned),
            ocr_pages=sum(1 for page in result.pages if page.used_ocr),
            translated_pages=sum(1 for page in result.pages if page.translated),
            vision_pages=sum(1 for page in result.pages if page.used_vision),
            format=request.fmt,
            output=output,
            download_name=download_name,
        )
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("could not remove temporary file %s", temp_path)
