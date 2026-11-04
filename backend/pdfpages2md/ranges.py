"""Page-range specification parsing."""

from __future__ import annotations

import re

_TOKEN = re.compile(r"\s*(?P<a>\d+)?\s*(?:(?P<sep>-)\s*(?P<b>\d+)?)?\s*")


def parse_pages(spec: str | None, page_count: int | None = None) -> list[int]:
    """Parse a page spec such as ``"1-10,50,88-95"``.

    Returns a sorted list of unique 1-based page numbers. ``page_count`` is
    required to resolve the ``"all"`` keyword and open-ended ranges (``"5-"``).

    Supported forms per comma-separated token:
      - ``5``      a single page
      - ``5-20``   an inclusive range
      - ``5-``     page 5 through the end (needs ``page_count``)
      - ``-10``    page 1 through 10
      - ``all``    every page (needs ``page_count``)
    """
    if spec is None:
        raise ValueError("page specification must not be None")

    text = str(spec).strip()
    if not text:
        raise ValueError("page specification is empty")

    if text.lower() in {"all", "*"}:
        if page_count is None:
            raise ValueError("'all' requires a known page count")
        return list(range(1, page_count + 1))

    selected: set[int] = set()
    for raw in text.split(","):
        token = raw.strip()
        if not token:
            continue
        match = _TOKEN.fullmatch(token)
        if match is None:
            raise ValueError(f"invalid page token: {token!r}")

        a = match.group("a")
        sep = match.group("sep")
        b = match.group("b")

        if sep is None:
            # Single page.
            start = end = int(a)
        elif a is None and b is None:
            raise ValueError(f"invalid page token: {token!r}")
        elif a is None:
            # "-10" -> 1..10
            start, end = 1, int(b)
        elif b is None:
            # "5-" -> 5..page_count
            if page_count is None:
                raise ValueError(
                    f"open-ended range {token!r} requires a known page count"
                )
            start, end = int(a), page_count
        else:
            start, end = int(a), int(b)

        if start < 1 or end < 1:
            raise ValueError(f"page numbers must be >= 1: {token!r}")
        if start > end:
            raise ValueError(f"range start is after range end: {token!r}")

        selected.update(range(start, end + 1))

    return sorted(selected)
