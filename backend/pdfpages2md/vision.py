"""Optional vision-model fallback for hard scanned pages.

Only code/table pages and pages with poor OCR confidence are sent to the
vision model. Normal prose continues through RapidOCR + DeepSeek. The backend
is OpenAI-compatible, so GLM-4V, Qwen-VL and Doubao Vision can all be used by
changing ``VISION_BASE_URL`` and ``VISION_MODEL``.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from statistics import mean

import pymupdf

from .config import get_config as _config
from .ocr import OcrLine


class VisionUnavailableError(RuntimeError):
    """Raised when the vision fallback is requested but not configured."""


_SYSTEM_PROMPT = (
    "You are a precise document transcription engine. Transcribe the page image "
    "into GitHub-flavored Markdown. Keep the original language; do not translate. "
    "Preserve headings, paragraphs, lists, tables, and code. Wrap code and "
    "terminal listings in fenced code blocks with an appropriate language tag. "
    "Do not add explanations or content that is not visible in the image. "
    "Return only the Markdown."
)

_USER_PROMPT = "Transcribe this page into Markdown."

_TABLE_SEPARATOR = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)


def vision_available(api_key: str | None = None) -> bool:
    return bool((api_key or "").strip() or _config("VISION_API_KEY"))


def _has_table(markdown: str) -> bool:
    lines = markdown.splitlines()
    return any(
        "|" in line and _TABLE_SEPARATOR.match(lines[index + 1])
        for index, line in enumerate(lines[:-1])
    )


def _page_has_table(page: pymupdf.Page) -> bool:
    try:
        return bool(page.find_tables().tables)
    except Exception:  # noqa: BLE001 - table detection is best effort
        return False


def _ocr_quality_is_poor(lines: list[OcrLine]) -> bool:
    if not lines:
        return False
    scores = [max(0.0, min(1.0, line.score)) for line in lines]
    average = mean(scores)
    low_ratio = sum(1 for score in scores if score < 0.6) / len(scores)
    garbled = sum(
        1 for line in lines if "\ufffd" in line.text or "��" in line.text
    )
    return average < 0.75 or low_ratio > 0.4 or garbled / len(lines) > 0.1


def should_use_vision(
    markdown: str,
    lines: list[OcrLine],
    *,
    page: pymupdf.Page | None = None,
) -> bool:
    """Decide whether a scanned page is hard enough to justify vision cost."""
    if "```" in markdown:
        return True
    if _has_table(markdown):
        return True
    if page is not None and _page_has_table(page):
        return True
    return _ocr_quality_is_poor(lines)


def _extract_content(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    content = choices[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return str(content).strip()


def vision_page_markdown(
    page: pymupdf.Page,
    *,
    dpi: int = 150,
    timeout: int = 120,
    api_key: str | None = None,
) -> str:
    """Transcribe one rendered page with an OpenAI-compatible vision model."""
    api_key = (api_key or "").strip() or _config("VISION_API_KEY")
    if not api_key:
        raise VisionUnavailableError(
            "VISION_API_KEY is not set; add it to the environment or .env file"
        )

    base_url = _config(
        "VISION_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
    ).rstrip("/")
    model = _config("VISION_MODEL", "glm-4v-flash")
    timeout = int(_config("VISION_TIMEOUT", str(timeout)))
    max_tokens = int(_config("VISION_MAX_TOKENS", "1024"))

    pix = page.get_pixmap(dpi=dpi)
    image = base64.b64encode(pix.tobytes("png")).decode("ascii")
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image}"
                            },
                        },
                        {"type": "text", "text": _USER_PROMPT},
                    ],
                },
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
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
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise VisionUnavailableError(
            f"vision API returned HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise VisionUnavailableError(
            f"vision API connection error: {exc.reason}"
        ) from exc

    content = _extract_content(data)
    if not content:
        raise VisionUnavailableError("vision API returned an empty transcription")
    if content.startswith("```markdown") and content.endswith("```"):
        content = content[len("```markdown") : -3].strip()
    return content
