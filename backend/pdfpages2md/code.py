"""Layout-aware extraction for PDF pages containing code listings.

``pymupdf4llm`` handles prose very well, but code listings that carry a line
number column are often flattened into a confusing mixture of numbers and code
fragments. This module reconstructs those listings from positioned text spans:
line numbers in the left margin are dropped, indentation is recovered from the
x position, and the result is wrapped in a fenced Markdown code block.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pymupdf


_MONO_HINTS = (
    "mono",
    "courier",
    "consolas",
    "menlo",
    "cmtt",
    "typewriter",
    "fixed",
    "console",
    "code",
    "hack",
    "fira",
    "inconsolata",
    "sourcecode",
    "robotomono",
    "liberationmono",
    "nimbusmono",
    "ptmono",
    "cousine",
    "dejavusansmono",
)

_CODE_HINTS = (
    "#include",
    "#define",
    "int main",
    "printf(",
    "fprintf(",
    "malloc(",
    "free(",
    "sizeof(",
    "char *",
    "void ",
    "struct ",
    "typedef ",
    "return ",
    "while (",
    "for (",
    "if (",
    "switch (",
    "else {",
    "} else",
    "->",
    "==",
    "!=",
    ");",
    "};",
)

_NUMBER = re.compile(r"\s*\d{1,4}\s*")


@dataclass
class _Span:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    baseline: float
    font: str
    size: float


def _collect_spans(page: pymupdf.Page) -> list[_Span]:
    spans: list[_Span] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            for raw in line.get("spans", []):
                text = raw.get("text", "")
                if not text or not text.strip():
                    continue
                bbox = raw.get("bbox") or (0.0, 0.0, 0.0, 0.0)
                origin = raw.get("origin") or (bbox[0], bbox[3])
                spans.append(
                    _Span(
                        text=text,
                        x0=float(bbox[0]),
                        y0=float(bbox[1]),
                        x1=float(bbox[2]),
                        y1=float(bbox[3]),
                        baseline=float(origin[1]),
                        font=raw.get("font", ""),
                        size=float(raw.get("size", 0.0)),
                    )
                )
    return spans


def _is_mono(font: str) -> bool:
    name = (font or "").lower()
    return any(hint in name for hint in _MONO_HINTS)


def _is_number(text: str) -> bool:
    return bool(_NUMBER.fullmatch(text))


def _looks_like_code(text: str) -> bool:
    return any(hint in text for hint in _CODE_HINTS)


def _group_visual_lines(spans: list[_Span]) -> list[list[_Span]]:
    ordered = sorted(spans, key=lambda span: (span.baseline, span.x0))
    lines: list[list[_Span]] = []
    for span in ordered:
        if not lines:
            lines.append([span])
            continue
        current = lines[-1]
        baseline = sum(item.baseline for item in current) / len(current)
        tolerance = max(2.0, max(item.size for item in current) * 0.4)
        if abs(span.baseline - baseline) <= tolerance:
            current.append(span)
        else:
            lines.append([span])
    for line in lines:
        line.sort(key=lambda span: span.x0)
    return lines


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _reconstruct(spans: list[_Span], code_x: float, char_width: float) -> str:
    if not spans:
        return ""
    first = spans[0]
    text = first.text
    if not text[:1].isspace():
        indent = max(0, round((first.x0 - code_x) / char_width))
        if indent:
            text = " " * indent + text
    previous_x1 = first.x1
    for span in spans[1:]:
        gap = span.x0 - previous_x1
        if gap > char_width * 0.6 and not text.endswith(" ") and not span.text.startswith(" "):
            text += " " * max(1, round(gap / char_width))
        text += span.text
        previous_x1 = max(previous_x1, span.x1)
    return text.rstrip()


def _detect_language(code: str) -> str:
    if any(hint in code for hint in ("#include", "int main", "printf(", "char *", "struct ")):
        return "c"
    if any(hint in code for hint in ("def ", "import ", "print(")):
        return "python"
    if any(hint in code for hint in ("function ", "const ", "let ", "=>")):
        return "javascript"
    if any(hint in code for hint in ("public class", "System.out", "void main")):
        return "java"
    if "SELECT " in code and "FROM " in code:
        return "sql"
    return ""


def _strip_leading_line_numbers(lines: list[str]) -> list[str]:
    """Strip a sequential ``1 ...`` / ``2 ...`` prefix left inside the text."""
    matches: list[tuple[int, re.Match[str]]] = []
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)(\d{1,3})[ \t](.*)$", line)
        if match and match.group(3).strip():
            matches.append((index, match))
    if len(matches) < 5:
        return lines
    numbers = [int(match.group(2)) for _, match in matches]
    if numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        return lines
    cleaned = list(lines)
    for index, match in matches:
        cleaned[index] = match.group(1) + match.group(3)
    return cleaned


def extract_code_markdown(page: pymupdf.Page) -> str | None:
    """Return a Markdown rendering for a code-heavy page, or ``None``.

    The function is intentionally conservative: pages without enough monospace
    text or code syntax return ``None`` so the normal prose extractor can run.
    """
    spans = _collect_spans(page)
    if not spans:
        return None

    mono = [span for span in spans if _is_mono(span.font) and not _is_number(span.text)]
    total_chars = sum(len(span.text) for span in spans)
    mono_chars = sum(len(span.text) for span in mono)
    hint_count = sum(text.count(hint) for hint in _CODE_HINTS for text in [span.text for span in mono])

    if not mono or mono_chars / max(total_chars, 1) < 0.35 or hint_count < 2:
        return None

    code_x = min(span.x0 for span in mono)
    char_width = max(1.0, _median([span.size for span in mono]) * 0.6)
    lines = _group_visual_lines(spans)

    rendered: list[tuple[bool, str]] = []
    for line in lines:
        content = [
            span
            for span in line
            if not (_is_number(span.text) and span.x0 < code_x - 3)
        ]
        if not content:
            rendered.append((True, ""))
            continue
        text = _reconstruct(content, code_x, char_width)
        is_code = any(_is_mono(span.font) for span in content) or _looks_like_code(text)
        rendered.append((is_code, text))

    blocks: list[str] = []
    code_lines: list[str] = []

    def flush_code() -> None:
        if not code_lines:
            return
        cleaned = _strip_leading_line_numbers(code_lines)
        language = _detect_language("\n".join(cleaned))
        blocks.append(f"```{language}\n" + "\n".join(cleaned) + "\n```")
        code_lines.clear()

    for is_code, text in rendered:
        if is_code:
            code_lines.append(text)
        else:
            flush_code()
            prose = re.sub(r"[ \t]+", " ", text).strip()
            if prose:
                blocks.append(prose)
    flush_code()

    if not any(block.startswith("```") for block in blocks):
        return None
    return "\n\n".join(blocks)
