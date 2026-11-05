"""English-to-Chinese translation backed by DeepSeek.

Translation follows the same philosophy as :mod:`pdfpages2md.ocr`: the heavy
work is lazy and optional, so converting without ``--translate`` never imports
or configures the translation engine. The only backend is DeepSeek (an
OpenAI-compatible ``chat/completions`` endpoint), configured through the
``DEEPSEEK_API_KEY`` environment variable, a ``.env`` file in the project root,
or an explicit API key passed by the web server.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Callable

from .config import dotenv_candidates as _dotenv_candidates
from .config import get_config


class TranslationUnavailableError(RuntimeError):
    """Raised when translation is requested but no backend can run."""


_CHUNK_LIMIT = 4000
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_BLOCKQUOTE_RE = re.compile(r"^(>\s?)(.*)$")
_UNORDERED_RE = re.compile(r"^(\s*[-*+])\s+(.+)$")
_ORDERED_RE = re.compile(r"^(\s*\d+[.)])\s+(.+)$")
_HR_RE = re.compile(r"^\s*(?:[-*_]\s*){3,}$")
_FENCE_RE = re.compile(r"^\s*```")
_FENCED_BLOCK_RE = re.compile(r"(```[^\n]*\n.*?```)", re.DOTALL)


def _config(name: str, default: str = "") -> str:
    """Read a DeepSeek setting through the shared configuration resolver.

    ``_dotenv_candidates`` stays a module attribute so callers and tests can
    redirect where ``.env`` is discovered.
    """
    return get_config(name, default, candidates=_dotenv_candidates())


def _deepseek(text: str, source: str, target: str, api_key: str | None = None) -> str:
    api_key = (api_key or "").strip() or _config("DEEPSEEK_API_KEY")
    if not api_key:
        raise TranslationUnavailableError(
            "DEEPSEEK_API_KEY is not set; put it in the environment or in a "
            ".env file in the project root"
        )
    base_url = _config("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = _config("DEEPSEEK_MODEL", "deepseek-chat")
    temperature = float(_config("DEEPSEEK_TEMPERATURE", "0.2"))

    system = (
        "You are a professional translator. Translate the user's text from "
        f"{source} to {target}. Preserve meaning, tone and paragraph breaks, "
        "and return only the translated text with no explanation or preamble."
    )
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            "temperature": temperature,
            "stream": False,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise TranslationUnavailableError(
            f"DeepSeek API returned HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise TranslationUnavailableError(
            f"DeepSeek API connection error: {exc.reason}"
        ) from exc

    choices = data.get("choices") or []
    content = choices[0].get("message", {}).get("content") if choices else ""
    if not content:
        raise TranslationUnavailableError("DeepSeek returned an empty translation")
    return content.strip()


_BACKENDS: list[tuple[str, Callable[..., str]]] = [
    ("deepseek", _deepseek),
]


def _chunk(text: str, limit: int = _CHUNK_LIMIT) -> list[str]:
    text = text.strip()
    if len(text) <= limit:
        return [text]

    sentences = _SENTENCE_SPLIT.split(text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if current and len(candidate) > limit:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _try_backends(
    chunk: str,
    source: str,
    target: str,
    errors: list[str],
    api_key: str | None = None,
) -> tuple[Callable[..., str] | None, str | None]:
    for name, func in _BACKENDS:
        try:
            kwargs = {"api_key": api_key} if api_key else {}
            return func, func(chunk, source, target, **kwargs)
        except Exception as exc:  # noqa: BLE001 - surface backend failures clearly
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    return None, None


def translate_text(
    text: str,
    *,
    source: str = "en",
    target: str = "zh",
    engine: str | None = None,
    translator: Callable[[str], str] | None = None,
    api_key: str | None = None,
) -> str:
    """Translate plain text using the first available backend.

    ``translator`` lets callers inject a deterministic function (useful in
    tests); when provided, backend resolution is skipped entirely. ``api_key``
    overrides the configured DeepSeek key for this call.
    """
    text = (text or "").strip()
    if not text:
        return ""
    if translator is not None:
        return translator(text)

    if engine == "auto":
        engine = None

    func: Callable[[str, str, str], str] | None = None
    errors: list[str] = []

    if engine:
        func = next((fn for name, fn in _BACKENDS if name == engine), None)
        if func is None:
            raise ValueError(f"unknown translation engine: {engine!r}")

    outputs: list[str] = []
    for chunk in _chunk(text):
        if func is None:
            func, output = _try_backends(chunk, source, target, errors, api_key=api_key)
            if func is None:
                break
            if output is not None:
                outputs.append(output)
            continue
        try:
            kwargs = {"api_key": api_key} if api_key else {}
            outputs.append(func(chunk, source, target, **kwargs))
        except Exception as exc:  # noqa: BLE001 - give callers a stable error
            raise TranslationUnavailableError(
                f"translation failed with backend {engine!r}: {exc}"
            ) from exc

    if func is None:
        detail = "; ".join(errors) or "no translation backend configured"
        raise TranslationUnavailableError(
            "translation requested but no backend is available "
            f"(configure DEEPSEEK_API_KEY). {detail}"
        )

    return " ".join(output for output in outputs if output)


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return stripped.split("|")


def _is_table_separator(line: str) -> bool:
    cells = [cell.strip() for cell in _split_table_row(line)]
    if not cells or not any(cells):
        return False
    return all(re.fullmatch(r":?-{1,}:?", cell) for cell in cells if cell)


def _translate_line(line: str, translate: Callable[[str], str]) -> str:
    heading = _HEADING_RE.match(line)
    if heading:
        return f"{heading.group(1)} {translate(heading.group(2))}"

    quote = _BLOCKQUOTE_RE.match(line)
    if quote:
        return f"{quote.group(1)}{translate(quote.group(2))}"

    unordered = _UNORDERED_RE.match(line)
    if unordered:
        return f"{unordered.group(1)} {translate(unordered.group(2))}"

    ordered = _ORDERED_RE.match(line)
    if ordered:
        return f"{ordered.group(1)} {translate(ordered.group(2))}"

    return translate(line)


def _translate_table(lines: list[str], translate: Callable[[str], str]) -> str:
    output: list[str] = []
    for line in lines:
        if _is_table_separator(line):
            output.append(line)
            continue
        cells = _split_table_row(line)
        translated = [
            translate(cell) if cell.strip() else cell
            for cell in cells
        ]
        output.append("| " + " | ".join(translated) + " |")
    return "\n".join(output)


def _looks_like_list(lines: list[str]) -> bool:
    content = [line for line in lines if line.strip()]
    if not content:
        return False
    return all(_UNORDERED_RE.match(line) or _ORDERED_RE.match(line) for line in content)


def _translate_block(block: str, translate: Callable[[str], str]) -> str:
    lines = block.splitlines()
    if not lines:
        return block

    if any(_FENCE_RE.match(line) for line in lines):
        return block
    if len(lines) == 1 and _HR_RE.match(lines[0]):
        return block
    if any("|" in line for line in lines):
        return _translate_table(lines, translate)
    if _looks_like_list(lines):
        return "\n".join(_translate_line(line, translate) for line in lines)
    if len(lines) == 1:
        return _translate_line(lines[0], translate)
    return translate(block)


def translate_markdown(
    markdown: str,
    *,
    source: str = "en",
    target: str = "zh",
    engine: str | None = None,
    translator: Callable[[str], str] | None = None,
    api_key: str | None = None,
) -> str:
    """Translate Markdown while preserving page and structural markers.

    Blocks are translated independently so headings, list markers, table
    separators, blockquotes, code fences and horizontal rules survive the
    round-trip. Blank-line paragraph separation is retained for readable,
    re-laid-out output.
    """
    if not markdown or not markdown.strip():
        return markdown

    def translate(segment: str) -> str:
        return translate_text(
            segment,
            source=source,
            target=target,
            engine=engine,
            translator=translator,
            api_key=api_key,
        )

    output: list[str] = []
    for part in _FENCED_BLOCK_RE.split(markdown):
        if not part:
            continue
        if _FENCED_BLOCK_RE.fullmatch(part):
            output.append(part.strip())
            continue
        blocks = [
            block for block in re.split(r"\n\s*\n", part.strip()) if block.strip()
        ]
        output.extend(_translate_block(block, translate) for block in blocks)
    return "\n\n".join(output)
