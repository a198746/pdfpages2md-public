"""Language-aware cleanup for code reconstructed from a scanned page.

OCR output needs small, language-specific repairs before it is placed in a
Markdown fence: full-width punctuation must be folded back to ASCII, common C
typos fixed, missing braces reinserted from indentation, and background-job
markers normalised for shell transcripts.

The layout logic in :mod:`pdfpages2md.ocr_layout` decides *where* code blocks
are; this module decides how a block's text should be tidied. Keeping the two
apart makes it possible to add another language without touching geometry code.
"""

from __future__ import annotations

import re

FULLWIDTH_TRANSLATION = str.maketrans(
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

_FUNCTION_SIGNATURE = re.compile(
    r"^(?:[A-Za-z_][\w\s\*]+)?[A-Za-z_]\w*\s*\([^;]*\)\s*$"
)


def normalize_code_text(text: str) -> str:
    """Fold full-width punctuation and fix frequent OCR mistakes in C code."""
    text = text.translate(FULLWIDTH_TRANSLATION)
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


def detect_language(code: str) -> str:
    """Guess a fenced-block language tag from the reconstructed code."""
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


def repair_c_braces(lines: list[str]) -> list[str]:
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


def tidy_blank_lines(lines: list[str]) -> list[str]:
    """Drop blank lines that sit directly after ``{`` or before ``}``."""
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


def normalize_shell_lines(lines: list[str]) -> list[str]:
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
