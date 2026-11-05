"""Configuration resolution shared by every optional backend.

The translation and vision backends, plus the local web server, all need the
same lookup rules. Keeping them here means a value is resolved one way only:

1. the process environment,
2. a ``.env`` file next to the current directory,
3. a ``.env`` file in the project root,
4. the caller's default.

No caching is performed: reading a small file per lookup keeps tests able to
change the environment between calls and avoids surprising stale keys.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

ENV_FILE_NAME = ".env"


def dotenv_candidates() -> list[Path]:
    """Return the ``.env`` files to consult, in priority order."""
    candidates = [Path.cwd() / ENV_FILE_NAME]
    project_root = Path(__file__).resolve().parents[2]
    if project_root.resolve() != Path.cwd().resolve():
        candidates.append(project_root / ENV_FILE_NAME)
    return candidates


def load_dotenv(candidates: Iterable[Path] | None = None) -> dict[str, str]:
    """Parse ``KEY=value`` lines from the candidate ``.env`` files.

    The first file that defines a key wins, blank lines and ``#`` comments are
    ignored, and optional surrounding quotes are stripped. Malformed lines are
    skipped rather than raising, so a stray edit in ``.env`` never breaks a
    conversion.
    """
    values: dict[str, str] = {}
    for path in candidates if candidates is not None else dotenv_candidates():
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if not key:
                continue
            values.setdefault(key, value.strip().strip("\"'"))
    return values


def get_config(
    name: str,
    default: str = "",
    *,
    candidates: Iterable[Path] | None = None,
) -> str:
    """Resolve a configuration value from the environment, then ``.env``.

    ``candidates`` lets tests (and embedding applications) redirect dotenv
    discovery without touching the process environment.
    """
    value = os.environ.get(name)
    if value is not None and value.strip():
        return value.strip()
    return load_dotenv(candidates).get(name, default)
