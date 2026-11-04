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

from .ocr import OcrLine


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

_FULLWIDTH = str.maketrans(
    {
        "（": "(",
        "）": ")",
        "，": ",",
        "；": ";",
        "｛": "{",
        "｝": "}",
        "　": " ",
    }
)

_NUMBER = re.compile(r"\d{1,3}")
_FUNCTION_SIGNATURE = re.compile(
    r"^(?:[A-Za-z_][\w\s\*]+)?[A-Za-z_]\w*\s*\([^;]*\)\s*$"
)


@dataclass
class _Row:
    lines: list[OcrLine]
    y: float
    height: float

    @property
    def text(self) -> str:
        return " ".join(
            line.text.strip() for line in sorted(self.lines, key=lambda item: item.x0)
        )


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


def _clean_ocr_code(text: str) -> str:
    text = text.translate(_FULLWIDTH)
    text = text.replace("#includee <", "#include <")
    text = text.replace("#include e <", "#include <")
    text = text.replace("argv[l]", "argv[1]")
    text = text.replace("exit(l));", "exit(1);")
    text = text.replace("exit(l);", "exit(1);")
    text = text.replace("while(l)(", "while (1) {")
    text = text.replace("return ;", "return 0;")
    text = re.sub(r"\b(if|while|for|switch)\(", r"\1 (", text)
    text = re.sub(r"\)\{", ") {", text)
    return text


def _detect_language(code: str) -> str:
    if any(
        hint in code
        for hint in ("#include", "main(", "printf(", "char *", "struct ")
    ):
        return "c"
    if any(hint in code for hint in ("def ", "import ", "print(")):
        return "python"
    if any(hint in code for hint in ("function ", "const ", "let ", "=>")):
        return "javascript"
    if any(hint in code for hint in ("prompt>", "gcc ", "./job", "ls ", "cd ")):
        return "shell"
    return ""


def _repair_c_braces(lines: list[str]) -> list[str]:
    """Reinsert braces that OCR missed, using indentation as the signal."""
    result: list[str] = []
    stack: list[int] = []

    def indent_of(text: str) -> int:
        return len(text) - len(text.lstrip(" "))

    def drop_trailing_blanks() -> None:
        while result and not result[-1].strip():
            result.pop()

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue
        indent = indent_of(line)
        if stripped.startswith("}"):
            if stack and stack[-1] >= indent:
                stack.pop()
            result.append(line)
            continue
        while stack and indent <= stack[-1]:
            drop_trailing_blanks()
            result.append(" " * stack.pop() + "}")
        result.append(line)
        if stripped.endswith("{"):
            stack.append(indent)
        elif _FUNCTION_SIGNATURE.match(stripped):
            next_line = next(
                (item for item in lines[index + 1 :] if item.strip()), ""
            )
            if next_line and indent_of(next_line) > indent:
                result.append(" " * indent + "{")
                stack.append(indent)
    while stack:
        drop_trailing_blanks()
        result.append(" " * stack.pop() + "}")
    return result


def _tidy_code_blank_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    for index, line in enumerate(lines):
        if not line.strip():
            previous = next(
                (item for item in reversed(cleaned) if item.strip()), ""
            )
            following = next(
                (item for item in lines[index + 1 :] if item.strip()), ""
            )
            if previous.rstrip().endswith("{") or following.lstrip().startswith("}"):
                continue
        cleaned.append(line)
    return cleaned


def _clean_shell_lines(lines: list[str]) -> list[str]:
    """Normalise background-job markers that OCR split across lines."""
    cleaned: list[str] = []
    last_index: int | None = None
    for line in lines:
        text = line.strip()
        if not text:
            continue
        match = re.fullmatch(r"\[(\d+)\]\s*(\d+)", text)
        if match:
            last_index = int(match.group(1))
            cleaned.append(f"[{last_index}] {match.group(2)}")
            continue
        if last_index is not None and re.fullmatch(r"\d+", text):
            last_index += 1
            cleaned.append(f"[{last_index}] {text}")
            continue
        if text.startswith("prompt>"):
            last_index = None
        cleaned.append(text)
    return cleaned


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
        code_lines.append(_clean_ocr_code(text.rstrip()))

    code = "\n".join(code_lines).strip("\n")
    language = _detect_language(code)
    if language == "c":
        repaired = _repair_c_braces(code.splitlines())
        code = "\n".join(_tidy_code_blank_lines(repaired))
    elif language == "shell":
        code = "\n".join(_clean_shell_lines(code.splitlines()))
    return f"```{language}\n{code}\n```"


def _render_prose_rows(rows: list[_Row]) -> list[str]:
    if not rows:
        return []
    heights = [row.height for row in rows if row.text.strip()]
    if heights:
        ordered_heights = sorted(heights)
        base_height = ordered_heights[len(ordered_heights) // 4]
        body_height = median(ordered_heights)
    else:
        base_height = body_height = 30.0

    groups: list[list[_Row]] = []
    current: list[_Row] = []
    previous_y: float | None = None
    for row in rows:
        if not row.text.strip():
            continue
        if current and previous_y is not None and row.y - previous_y > body_height * 1.45:
            groups.append(current)
            current = []
        current.append(row)
        previous_y = row.y
    if current:
        groups.append(current)

    blocks: list[str] = []
    for group in groups:
        text = " ".join(row.text.strip() for row in group)
        if (
            len(group) == 1
            and group[0].height > base_height * 1.15
            and len(text) <= 100
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
