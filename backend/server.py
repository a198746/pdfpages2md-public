"""Local HTTP API and static frontend server for pdfpages2md.

This intentionally uses only the Python standard library so the project keeps
its lightweight dependency profile. The handler exposes ``POST /api/convert``
and serves the files in ``frontend/``.
"""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import shutil
import tempfile
from email.parser import BytesParser
from email.policy import default as email_default_policy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from pdfpages2md.extract import extract_pages, render
from pdfpages2md.translate import _config


logger = logging.getLogger("pdfpages2md.server")

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
MAX_CONFIG_BYTES = 64 * 1024
CONFIG_FILE = BASE_DIR / ".pdfpages2md_config.json"

STATIC_FILES = {
    "index.html": "index.html",
    "app.js": "app.js",
    "styles.css": "styles.css",
    "favicon.svg": "favicon.svg",
}


def _load_server_config() -> dict[str, str]:
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
    for key in ("deepseek_api_key", "glm_api_key"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value.strip()
    return result


def _save_server_config(updates: dict[str, str]) -> dict[str, str]:
    """Persist only the API-key fields supplied in ``updates``."""
    current = _load_server_config()
    for key in ("deepseek_api_key", "glm_api_key"):
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


def _effective_api_key(env_name: str, config_name: str) -> str:
    """Resolve a key with precedence: environment, frontend config, .env."""
    env_value = os.environ.get(env_name)
    if env_value and env_value.strip():
        return env_value.strip()

    config_value = _load_server_config().get(config_name)
    if config_value:
        return config_value

    return _config(env_name).strip()


def _field(form: dict[str, list[str]], name: str) -> str | None:
    values = form.get(name)
    return values[-1] if values else None


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{value!r} is not a valid integer") from exc


def _parse_multipart(content_type: str, body: bytes) -> tuple[dict[str, list[str]], dict[str, tuple[str, bytes]]]:
    """Parse a multipart request with email's battle-tested MIME parser."""
    payload = b"Content-Type: " + content_type.encode("latin-1") + b"\r\n\r\n" + body
    message = BytesParser(policy=email_default_policy).parsebytes(payload)

    fields: dict[str, list[str]] = {}
    files: dict[str, tuple[str, bytes]] = {}

    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue

        filename = part.get_filename()
        data = part.get_payload(decode=True) or b""
        if filename:
            files[name] = (filename, data)
        else:
            fields.setdefault(name, []).append(data.decode("utf-8", "replace"))

    return fields, files


class PdfPagesRequestHandler(BaseHTTPRequestHandler):
    server_version = "pdfpages2md/0.1"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._send_static("index.html")
            return
        if path in {"/app.js", "/styles.css", "/favicon.svg"}:
            self._send_static(STATIC_FILES[path.lstrip("/")])
            return
        if path == "/api/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "service": "pdfpages2md",
                    "deepseek_available": bool(
                        _effective_api_key("DEEPSEEK_API_KEY", "deepseek_api_key")
                    ),
                    "vision_available": bool(
                        _effective_api_key("VISION_API_KEY", "glm_api_key")
                    ),
                },
            )
            return
        if path == "/api/config":
            self._send_json(HTTPStatus.OK, self._config_status())
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/config":
            self._handle_config_post()
            return
        if path != "/api/convert":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Content-Type must be multipart/form-data"},
            )
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "empty request"})
            return
        if content_length > MAX_UPLOAD_BYTES:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "file is too large"})
            return

        body = self.rfile.read(content_length)
        try:
            fields, files = _parse_multipart(content_type, body)
        except Exception as exc:  # noqa: BLE001 - malformed multipart should be 400
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"invalid multipart body: {exc}"})
            return

        if "file" not in files:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "missing file field"})
            return

        filename, data = files["file"]
        if not filename.lower().endswith(".pdf"):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "only PDF files are supported"})
            return

        suffix = Path(filename).suffix or ".pdf"
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix,
                prefix="pdfpages2md_",
            ) as temp_file:
                temp_file.write(data)
                temp_path = Path(temp_file.name)

            pages = _field(fields, "pages") or None
            fmt = _field(fields, "format") or "markdown"
            marker = _field(fields, "marker") or "comment"
            ocr = _as_bool(_field(fields, "ocr"), default=True)
            ocr_lang = _field(fields, "ocr_lang") or "eng"
            min_chars = _as_int(_field(fields, "min_chars"), 50)
            dpi = _as_int(_field(fields, "dpi"), 200)
            translate = _as_bool(_field(fields, "translate"), default=False)
            translate_engine = _field(fields, "translate_engine") or None
            if translate_engine == "auto":
                translate_engine = None
            vision = _as_bool(_field(fields, "vision"), default=True)
            translate_api_key = (
                _field(fields, "deepseek_api_key")
                or _effective_api_key("DEEPSEEK_API_KEY", "deepseek_api_key")
                or None
            )
            vision_api_key = (
                _field(fields, "glm_api_key")
                or _effective_api_key("VISION_API_KEY", "glm_api_key")
                or None
            )

            result = extract_pages(
                str(temp_path),
                pages,
                ocr=ocr,
                min_chars=min_chars,
                dpi=dpi,
                ocr_lang=ocr_lang,
                translate=translate,
                translate_engine=translate_engine,
                translate_api_key=translate_api_key,
                translate_plain=fmt != "markdown",
                vision=vision,
                vision_api_key=vision_api_key,
            )
            output = render(result, fmt=fmt, marker=marker)

            stem = Path(filename).stem
            ext = fmt if fmt != "text" else "txt"
            download_name = f"{stem}.zh.{ext}" if translate else f"{stem}.{ext}"
            scanned_count = sum(1 for page in result.pages if page.scanned)
            ocr_count = sum(1 for page in result.pages if page.used_ocr)
            translated_count = sum(1 for page in result.pages if page.translated)
            vision_count = sum(1 for page in result.pages if page.used_vision)
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "source": filename,
                    "total_pages": result.total_pages,
                    "selected_pages": result.selected_pages,
                    "scanned_pages": scanned_count,
                    "ocr_pages": ocr_count,
                    "translated_pages": translated_count,
                    "vision_pages": vision_count,
                    "format": fmt,
                    "output": output,
                    "download_name": download_name,
                },
            )
        except (ValueError, OSError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - return a stable JSON error for the UI
            logger.exception("conversion failed")
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("could not remove temporary file %s", temp_path)

    def _config_status(self) -> dict:
        return {
            "deepseek_configured": bool(
                _effective_api_key("DEEPSEEK_API_KEY", "deepseek_api_key")
            ),
            "vision_configured": bool(
                _effective_api_key("VISION_API_KEY", "glm_api_key")
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

        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "empty request"})
            return
        if content_length > MAX_CONFIG_BYTES:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "config is too large"})
            return

        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"invalid JSON body: {exc}"})
            return
        if not isinstance(payload, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "config body must be an object"})
            return

        updates: dict[str, str] = {}
        for key in ("deepseek_api_key", "glm_api_key"):
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

        _save_server_config(updates)
        self._send_json(HTTPStatus.OK, self._config_status())

    def _send_static(self, filename: str) -> None:
        target = FRONTEND_DIR / filename
        if not target.is_file():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(target.stat().st_size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with target.open("rb") as handle:
            shutil.copyfileobj(handle, self.wfile)

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        logger.info("%s - %s", self.address_string(), fmt % args)


def create_server(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), PdfPagesRequestHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local pdfpages2md web server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    httpd = create_server(args.host, args.port)
    print(f"pdfpages2md server running at http://{args.host}:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
