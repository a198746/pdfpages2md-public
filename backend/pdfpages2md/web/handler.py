"""HTTP request handler for the JSON API and the static frontend.

The handler is intentionally thin: it validates transport-level input, delegates
conversion to :mod:`pdfpages2md.web.service`, and serialises responses. That
keeps the routing table readable and makes the conversion path testable without
a live socket.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import shutil
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import config_store
from .multipart import field, parse_multipart
from .paths import FRONTEND_DIR
from .service import ConvertRequest, convert_upload

logger = logging.getLogger("pdfpages2md.server")

MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
MAX_CONFIG_BYTES = 64 * 1024

# Only files the frontend actually ships are served; anything else under
# frontend/ (or a path escaping it) is rejected.
STATIC_SUFFIXES = frozenset(
    {".html", ".js", ".mjs", ".css", ".svg", ".png", ".ico", ".json", ".map", ".woff", ".woff2"}
)

_JSON_HEADERS = {"Content-Type": "application/json; charset=utf-8"}

# Explicit types keep ES modules working even when the OS MIME database maps
# ``.js`` to ``text/plain`` (some Windows registries do exactly that).
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
}


def _content_type(target: Path) -> str:
    suffix = target.suffix.lower()
    if suffix in _CONTENT_TYPES:
        return _CONTENT_TYPES[suffix]
    return mimetypes.guess_type(str(target))[0] or "application/octet-stream"


def resolve_static(path: str) -> Path | None:
    """Map a URL path to a file inside ``frontend/``, or ``None`` if unsafe."""
    relative = unquote(path).lstrip("/") or "index.html"
    base = FRONTEND_DIR.resolve()
    candidate = (base / relative).resolve()

    if candidate.suffix.lower() not in STATIC_SUFFIXES:
        return None
    if not candidate.is_relative_to(base) or not candidate.is_file():
        return None
    return candidate


class PdfPagesRequestHandler(BaseHTTPRequestHandler):
    server_version = "pdfpages2md/0.1"

    # ------------------------------------------------------------------ GET

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self._handle_health()
            return
        if path == "/api/config":
            self._send_json(HTTPStatus.OK, self._config_status())
            return

        target = resolve_static(path)
        if target is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        self._send_static(target)

    # ----------------------------------------------------------------- POST

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/config":
            self._handle_config_post()
            return
        if path == "/api/convert":
            self._handle_convert_post()
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def _handle_convert_post(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Content-Type must be multipart/form-data"},
            )
            return

        body = self._read_content(limit=MAX_UPLOAD_BYTES, too_large="file is too large")
        if body is None:
            return

        try:
            fields, files = parse_multipart(content_type, body)
        except Exception as exc:  # noqa: BLE001 - malformed multipart should be 400
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": f"invalid multipart body: {exc}"},
            )
            return

        if "file" not in files:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "missing file field"})
            return

        filename, data = files["file"]
        if not filename.lower().endswith(".pdf"):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "only PDF files are supported"},
            )
            return

        try:
            request = ConvertRequest.from_fields(
                fields,
                translate_api_key=(
                    field(fields, "deepseek_api_key")
                    or config_store.effective_api_key(
                        "DEEPSEEK_API_KEY", "deepseek_api_key"
                    )
                    or None
                ),
                vision_api_key=(
                    field(fields, "glm_api_key")
                    or config_store.effective_api_key("VISION_API_KEY", "glm_api_key")
                    or None
                ),
            )
            outcome = convert_upload(filename, data, request)
        except (ValueError, OSError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 - return a stable JSON error for the UI
            logger.exception("conversion failed")
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": str(exc)},
            )
            return

        self._send_json(HTTPStatus.OK, {"ok": True, **outcome.to_payload()})

    def _handle_health(self) -> None:
        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "service": "pdfpages2md",
                "deepseek_available": bool(
                    config_store.effective_api_key(
                        "DEEPSEEK_API_KEY", "deepseek_api_key"
                    )
                ),
                "vision_available": bool(
                    config_store.effective_api_key("VISION_API_KEY", "glm_api_key")
                ),
            },
        )

    # --------------------------------------------------------------- config

    def _config_status(self) -> dict:
        return {
            "deepseek_configured": bool(
                config_store.effective_api_key("DEEPSEEK_API_KEY", "deepseek_api_key")
            ),
            "vision_configured": bool(
                config_store.effective_api_key("VISION_API_KEY", "glm_api_key")
            ),
        }

    def _handle_config_post(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("application/json"):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Content-Type must be application/json"},
            )
            return

        body = self._read_content(limit=MAX_CONFIG_BYTES, too_large="config is too large")
        if body is None:
            return

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": f"invalid JSON body: {exc}"},
            )
            return
        if not isinstance(payload, dict):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "config body must be an object"},
            )
            return

        updates: dict[str, str] = {}
        for key in config_store.SECRET_FIELDS:
            if key not in payload:
                continue
            value = payload[key]
            if value is None:
                continue
            if not isinstance(value, str):
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": f"{key} must be a string"},
                )
                return
            updates[key] = value

        config_store.save(updates)
        self._send_json(HTTPStatus.OK, self._config_status())

    # --------------------------------------------------------------- helpers

    def _read_content(self, *, limit: int, too_large: str) -> bytes | None:
        """Read the request body, sending a JSON error and returning ``None``."""
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid Content-Length header"},
            )
            return None
        if length <= 0:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "empty request"})
            return None
        if length > limit:
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": too_large},
            )
            return None
        return self.rfile.read(length)

    def _send_static(self, target: Path) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", _content_type(target))
        self.send_header("Content-Length", str(target.stat().st_size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with target.open("rb") as handle:
            shutil.copyfileobj(handle, self.wfile)

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        for name, value in _JSON_HEADERS.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        logger.info("%s - %s", self.address_string(), fmt % args)
