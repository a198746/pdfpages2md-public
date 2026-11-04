"""Command-line entry point for pdfpages2md."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .extract import ConvertResult, extract_pages, page_count, render


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdfpages2md",
        description=(
            "Extract only selected pages from a PDF and convert them to "
            "LLM-friendly Markdown (or text/JSON), preserving original page numbers."
        ),
    )
    parser.add_argument("input", help="path to the input PDF")
    parser.add_argument(
        "--pages",
        "--page-range",
        dest="pages",
        metavar="SPEC",
        help='page selection, e.g. "1-10,50,88-95" or "5-20" (default: all)',
    )
    parser.add_argument(
        "-o",
        "--output",
        help="output file path; omit to write to stdout",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=("markdown", "text", "json"),
        default="markdown",
        help="output format (default: markdown)",
    )
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="disable automatic OCR of pages detected as scanned",
    )
    parser.add_argument(
        "--no-vision",
        action="store_true",
        help=(
            "disable vision fallback for scanned code/table/low-quality pages "
            "(requires VISION_API_KEY when enabled)"
        ),
    )
    parser.add_argument(
        "--ocr-lang",
        default="eng",
        help="Tesseract/RapidOCR language code (default: eng)",
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=50,
        help="pages with fewer non-space text chars are treated as scanned (default: 50)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="render DPI used for OCR (default: 200)",
    )
    parser.add_argument(
        "--marker",
        choices=("none", "comment", "heading", "both"),
        default="comment",
        help="page marker style (default: comment -> '<!-- page N -->')",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        metavar="CHARS",
        help="split output into files of at most CHARS characters at page boundaries",
    )
    parser.add_argument(
        "--translate",
        action="store_true",
        help="translate extracted English text to Simplified Chinese",
    )
    parser.add_argument(
        "--translate-engine",
        choices=("deepseek",),
        default="deepseek",
        help="translation backend (only DeepSeek is supported)",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="print the total page count and exit",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def _write_chunks(
    result: ConvertResult,
    *,
    output: Path,
    chunk_size: int,
    fmt: str,
    marker: str,
) -> None:
    sections = result.sections(fmt=fmt, marker=marker)
    base = output.with_suffix("")
    suffix = output.suffix or ".md"

    buffer: list[str] = []
    size = 0
    index = 0

    def flush() -> None:
        nonlocal buffer, size, index
        if not buffer:
            return
        index += 1
        name = f"{base}_{index:04d}{suffix}"
        _write_file(name, "\n".join(buffer))
        buffer, size = [], 0

    for section in sections:
        if buffer and size + len(section) + 1 > chunk_size:
            flush()
        buffer.append(section.rstrip("\n"))
        size += len(section) + 1
    flush()


def _write_file(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        total = page_count(args.input)
    except Exception as exc:  # noqa: BLE001 - CLI should print a clean message
        parser.error(f"cannot open {args.input!r}: {exc}")

    if args.info:
        print(total)
        return 0

    if args.chunk_size is not None and args.chunk_size < 1:
        parser.error("--chunk-size must be a positive integer")

    try:
        result = extract_pages(
            args.input,
            args.pages,
            ocr=not args.no_ocr,
            min_chars=args.min_chars,
            dpi=args.dpi,
            ocr_lang=args.ocr_lang,
            translate=args.translate,
            translate_engine=args.translate_engine,
            translate_plain=args.format != "markdown",
            vision=not args.no_vision,
        )
    except (ValueError, OSError) as exc:
        parser.error(str(exc))

    if args.chunk_size is not None and args.output:
        _write_chunks(
            result,
            output=Path(args.output),
            chunk_size=args.chunk_size,
            fmt=args.format,
            marker=args.marker,
        )
        return 0

    text = render(result, fmt=args.format, marker=args.marker)
    if args.output:
        _write_file(args.output, text)
    else:
        sys.stdout.write(text)
    return 0
