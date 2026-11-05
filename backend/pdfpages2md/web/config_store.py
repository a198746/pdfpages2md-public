"""Persistent API-key configuration owned by the local web UI.

Only the two secret fields managed by the frontend are read or written. The file
is created with owner-only permissions where the platform supports it, and any
malformed content degrades to "not configured" instead of breaking the server.
"""

from __future__ import annotations

import json
import logging
import os

from ..config import get_config
from .paths import CONFIG_FILE

logger = logging.getLogger("pdfpages2md.server")

SECRET_FIELDS = ("deepseek_api_key", "glm_api_key")


def load() -> dict[str, str]:
    """Read the frontend-managed API-key config, returning only valid values."""
    if not CONFIG_FILE.is_file():
        return {}
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("could not read %s: %s", CONFIG_FILE, exc)
        return {}
    if not isinstance(data, dict):
        return {}

    result: dict[str, str] = {}
    for key in SECRET_FIELDS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value.strip()
    return result


def save(updates: dict[str, str]) -> dict[str, str]:
    """Persist only the API-key fields supplied in ``updates``."""
    current = load()
    for key in SECRET_FIELDS:
        if key not in updates:
            continue
        value = updates[key].strip()
        if value:
            current[key] = value
        else:
            current.pop(key, None)

    CONFIG_FILE.write_text(
        json.dumps(current, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass
    return current


def effective_api_key(env_name: str, config_name: str) -> str:
    """Resolve a key with precedence: environment, frontend config, ``.env``."""
    env_value = os.environ.get(env_name)
    if env_value and env_value.strip():
        return env_value.strip()

    config_value = load().get(config_name)
    if config_value:
        return config_value

    return get_config(env_name).strip()
