"""Reconstruct OCR output into readable Markdown, with fenced code regions.

RapidOCR returns one bounding box per detected text region. A scanned code page
usually exposes a left column of short numbers and a right column of code
fragments. This module groups those boxes into visual rows, removes the line
number column, recovers indentation from x positions, and fences the code so
translation never rewrites it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median
from typing import Iterable

from .ocr import OcrLine
from .ocr_cleanup import (
    detect_language,
    normalize_code_text,
    normalize_shell_lines,
    repair_c_braces,
    tidy_blank_lines,
)


_STRONG_CODE_HINTS = (
    "#include",
    "main(",
    "printf(",
    "fprintf(",
    "exit(",
    "square(",
    "return",
    "while",
    "char *",
    "argv",
    "stderr",
    "prompt>",
    "gcc ",
    "./cpu",
    "!=",
    "->",
)

_WEAK_CODE_HINTS = ("int", "{", "}", ";", "if", "else", "for")

_NUMBER = re.compile(r"\d{1,3}")
_CJK_RE = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\u3000-\u303f]")
_TERMINAL_PUNCT = "。！？；：，、,.;:"


def _is_cjk(char: str) -> bool:
    return bool(char) and bool(_CJK_RE.match(char))


def _join_text(parts: Iterable[str]) -> str:
    """Join OCR fragments the way the source script would.

    Latin text needs a space where the scan/line wrapped; CJK text does not,
    because a line break inside a Chinese paragraph is purely typographic.
    Treating them the same is what produced spaces like ``大伦理 学家`` and
    ``历 史实际中``.
    """
    result = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if result and not (_is_cjk(result[-1]) or _is_cjk(part[0])):
            result += " "
        result += part
    return result


@dataclass
class _Row:
    lines: list[OcrLine]
    y: float
    height: float

    @property
    def text(self) -> str:
        lines = sorted(self.lines, key=lambda item: item.x0)
        result = ""
        previous: OcrLine | None = None
        for line in lines:
            text = line.text.strip()
            if not text:
                continue
            if previous is not None:
                gap = line.x0 - previous.x1
                height = max(line.y1 - line.y0, previous.y1 - previous.y0)
                # Large horizontal gaps are deliberate spacing (e.g. a page
                # number beside a running header); small gaps are just how OCR
                # boxed up Chinese characters.
                if gap > max(height * 0.6, 18.0) or not (
                    _is_cjk(result[-1]) or _is_cjk(text[0])
                ):
                    result += " "
            result += text
            previous = line
        return result

    @property
    def x0(self) -> float:
        return min(line.x0 for line in self.lines)

    @property
    def x1(self) -> float:
        return max(line.x1 for line in self.lines)


def _group_rows(lines: list[OcrLine]) -> list[_Row]:
    ordered = sorted(lines, key=lambda line: (line.y0 + line.y1) / 2)
    rows: list[_Row] = []
    for line in ordered:
        center = (line.y0 + line.y1) / 2
        height = max(1.0, line.y1 - line.y0)
        if rows:
            row = rows[-1]
            tolerance = max(4.0, max(row.height, height) * 0.55)
            if abs(center - row.y) <= tolerance:
                row.lines.append(line)
                count = len(row.lines)
                row.y = (row.y * (count - 1) + center) / count
                row.height = max(row.height, height)
                continue
        rows.append(_Row([line], center, height))
    for row in rows:
        row.lines.sort(key=lambda item: item.x0)
    return rows


def _is_number(text: str) -> bool:
    return bool(_NUMBER.fullmatch(text.strip()))


def _number_threshold(lines: list[OcrLine]) -> float | None:
    numbers = [line for line in lines if _is_number(line.text)]
    if len(numbers) < 3:
        return None
    numeric_x = median(line.x0 for line in numbers)
    strong = [
        line
        for line in lines
        if not _is_number(line.text)
        and any(hint in line.text for hint in _STRONG_CODE_HINTS)
    ]
    if not strong:
        return None
    code_x = median(line.x0 for line in strong)
    if code_x - numeric_x < 25:
        return None
    return numeric_x + max(25.0, (code_x - numeric_x) * 0.45)


def _row_is_code_like(row: _Row) -> bool:
    text = row.text.strip()
    if not text:
        return False
    if any(hint in text for hint in _STRONG_CODE_HINTS):
        return True
    if len(text) <= 12 and any(hint in text for hint in _WEAK_CODE_HINTS):
        return True
    return all(_is_number(line.text) for line in row.lines)


def _row_is_command_output(row: _Row) -> bool:
    text = row.text.strip()
    if not text:
        return False
    if re.fullmatch(r"\[\d+\]\s*\d+(?:\s+\d+)*", text):
        return True
    if re.fullmatch(r"\[\d+\]", text):
        return True
    return bool(
        len(text) <= 20
        and re.fullmatch(r"[A-Za-z0-9^~._/:\-\[\]\s]+", text)
    )


def _find_main_region(
    rows: list[_Row], number_threshold: float | None
) -> tuple[int, int] | None:
    numeric = [
        index
        for index, row in enumerate(rows)
        if number_threshold is not None
        and any(
            _is_number(line.text) and line.x0 < number_threshold
            for line in row.lines
        )
    ]
    if numeric:
        start, end = numeric[0], numeric[-1]
        while start > 0 and _row_is_code_like(rows[start - 1]):
            start -= 1
        while end + 1 < len(rows) and _row_is_code_like(rows[end + 1]):
            end += 1
        if end - start + 1 >= 3:
            return start, end

    runs: list[tuple[int, int]] = []
    current: list[int] = []
    for index, row in enumerate(rows):
        if _row_is_code_like(row):
            current.append(index)
        else:
            if len(current) >= 3:
                runs.append((current[0], current[-1]))
            current = []
    if len(current) >= 3:
        runs.append((current[0], current[-1]))
    if runs:
        return max(runs, key=lambda run: run[1] - run[0])

    return None


def _find_prompt_regions(rows: list[_Row]) -> list[tuple[int, int]]:
    if not rows:
        return []
    line_height = median(row.height for row in rows) or 30.0
    prompts = [
        index
        for index, row in enumerate(rows)
        if "prompt>" in row.text and len(row.text.strip()) <= 120
    ]
    regions: list[tuple[int, int]] = []
    for index in prompts:
        start = end = index
        while start > 0:
            previous = rows[start - 1]
            if rows[start].y - previous.y > line_height * 2.0:
                break
            if (
                _row_is_code_like(previous)
                or _row_is_command_output(previous)
                or "prompt>" in previous.text
            ):
                start -= 1
            else:
                break
        while end + 1 < len(rows):
            following = rows[end + 1]
            if following.y - rows[end].y > line_height * 2.0:
                break
            if (
                _row_is_code_like(following)
                or _row_is_command_output(following)
                or "prompt>" in following.text
            ):
                end += 1
            else:
                break
        regions.append((start, end))

    merged: list[tuple[int, int]] = []
    for start, end in sorted(regions):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _find_code_regions(
    rows: list[_Row], number_threshold: float | None
) -> list[tuple[int, int]]:
    regions: list[tuple[int, int]] = []
    main = _find_main_region(rows, number_threshold)
    if main is not None:
        regions.append(main)
    regions.extend(_find_prompt_regions(rows))
    if not regions:
        return []
    merged: list[tuple[int, int]] = []
    for start, end in sorted(regions):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _render_code_rows(
    rows: list[_Row], number_threshold: float | None
) -> str:
    content_rows: list[tuple[_Row, list[OcrLine]]] = []
    for row in rows:
        content = [
            line
            for line in row.lines
            if not (
                number_threshold is not None
                and _is_number(line.text)
                and line.x0 < number_threshold
            )
        ]
        content.sort(key=lambda item: item.x0)
        content_rows.append((row, content))

    heights = [
        line.y1 - line.y0 for _, content in content_rows for line in content
    ]
    char_width = max(4.0, median(heights) * 0.6) if heights else 10.0
    code_x = min(
        (line.x0 for _, content in content_rows for line in content), default=0.0
    )
    row_height = (
        median(row.height for row, _ in content_rows) if content_rows else 30.0
    )

    code_lines: list[str] = []
    previous_y: float | None = None
    for row, content in content_rows:
        if previous_y is not None and row.y - previous_y > row_height * 1.6:
            code_lines.append("")
        previous_y = row.y
        if not content:
            code_lines.append("")
            continue
        first = content[0]
        indent = max(0, round((first.x0 - code_x) / (char_width * 4))) * 4
        text = " " * indent + first.text.strip()
        previous_x1 = first.x1
        for item in content[1:]:
            gap = item.x0 - previous_x1
            if (
                gap > char_width * 0.35
                and not text.endswith(" ")
                and not item.text.startswith(" ")
            ):
                text += " "
            text += item.text
            previous_x1 = max(previous_x1, item.x1)
        code_lines.append(normalize_code_text(text.rstrip()))

    code = "\n".join(code_lines).strip("\n")
    language = detect_language(code)
    if language == "c":
        repaired = repair_c_braces(code.splitlines())
        code = "\n".join(tidy_blank_lines(repaired))
    elif language == "shell":
        code = "\n".join(normalize_shell_lines(code.splitlines()))
    return f"```{language}\n{code}\n```"


def _estimate_left_margin(rows: list[_Row]) -> float | None:
    """Estimate the body-text left edge from the leftmost rows.

    The 10th percentile is robust against a stray hanging character while still
    finding the true margin: indented paragraphs and narrower quotations sit to
    the right of it, so they must not be mistaken for the body margin.
    """
    xs = sorted(row.x0 for row in rows if row.text.strip())
    if not xs:
        return None
    return xs[min(len(xs) - 1, int(len(xs) * 0.1))]


def _estimate_right_margin(rows: list[_Row]) -> float | None:
    """Return a robust right edge, ignoring a few short/centered lines."""
    xs = sorted(row.x1 for row in rows if row.text.strip())
    if not xs:
        return None
    return xs[min(len(xs) - 1, int(len(xs) * 0.9))]


def _looks_like_heading(
    row: _Row,
    *,
    base_height: float,
    body_height: float,
) -> bool:
    """A heading is a short, noticeably larger line without sentence punctuation.

    Centered page headers/footers are *not* headings, and neither are ordinary
    paragraph lines: both used to be promoted to ``##`` because a noisy
    line-gap heuristic had split them into single-row groups.
    """
    text = row.text.strip()
    if not text or len(text) > 100:
        return False
    if text[-1] in _TERMINAL_PUNCT:
        return False
    if re.fullmatch(r"[\d\s\-—–]+", text):
        return False
    return row.height >= max(base_height * 1.15, body_height * 1.15)


def _render_prose_rows(rows: list[_Row]) -> list[str]:
    rows = [row for row in rows if row.text.strip()]
    if not rows:
        return []
    heights = [row.height for row in rows]
    ordered_heights = sorted(heights)
    base_height = ordered_heights[len(ordered_heights) // 4]
    body_height = median(ordered_heights)

    left_margin = _estimate_left_margin(rows)
    right_margin = _estimate_right_margin(rows)
    indent_threshold = max(body_height * 0.9, 10.0)
    # Normal line spacing is ~1.5 body heights in Chinese books; paragraph
    # spacing is larger. The old 1.45 threshold split mid-sentence whenever OCR
    # jitter pushed one line down by a pixel or two.
    gap_threshold = body_height * 1.65

    groups: list[list[_Row]] = []
    current: list[_Row] = []
    previous: _Row | None = None

    for row in rows:
        new_paragraph = False
        if current and previous is not None:
            if row.y - previous.y > gap_threshold:
                # Extra vertical space: a blank line between paragraphs.
                new_paragraph = True
            elif (
                left_margin is not None
                and row.x0 - previous.x0 > indent_threshold
            ):
                # A local rightward jump in the left edge marks a first-line
                # indent. The next line normally returns to the margin, which
                # is a continuation, not a new paragraph; hence only positive
                # jumps count. Comparing with the previous row rather than the
                # page margin keeps every line of an indented quotation from
                # becoming its own paragraph.
                new_paragraph = True
            elif (
                right_margin is not None
                and previous.x1 < right_margin - max(body_height * 1.5, 24.0)
                and left_margin is not None
                and previous.x0 - left_margin <= indent_threshold * 0.4
                and row.x0 - left_margin <= indent_threshold * 0.4
            ):
                # Previous line started at the body margin and ended well short
                # of the right edge, and this line starts at the margin too:
                # the previous paragraph ended. A short *indented* first line is
                # not a paragraph end, so it is excluded by the x0 checks.
                new_paragraph = True

        if new_paragraph:
            groups.append(current)
            current = []

        current.append(row)
        previous = row

    if current:
        groups.append(current)

    blocks: list[str] = []
    for group in groups:
        text = _join_text(row.text for row in group)
        if len(group) == 1 and _looks_like_heading(
            group[0], base_height=base_height, body_height=body_height
        ):
            blocks.append(f"## {text}")
        else:
            blocks.append(text)
    return blocks


def reconstruct_ocr_markdown(lines: list[OcrLine]) -> str:
    """Turn positioned OCR regions into Markdown with fenced code blocks."""
    rows = _group_rows(lines)
    if not rows:
        return ""

    threshold = _number_threshold(lines)
    regions = _find_code_regions(rows, threshold)
    if not regions:
        return "\n\n".join(_render_prose_rows(rows))

    blocks: list[str] = []
    cursor = 0
    for start, end in regions:
        blocks.extend(_render_prose_rows(rows[cursor:start]))
        blocks.append(_render_code_rows(rows[start : end + 1], threshold))
        cursor = end + 1
    blocks.extend(_render_prose_rows(rows[cursor:]))
    return "\n\n".join(block for block in blocks if block.strip())
