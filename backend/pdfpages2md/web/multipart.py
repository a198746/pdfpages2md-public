"""Multipart form parsing for the upload endpoint.

The standard library ships a battle-tested MIME parser, so there is no need to
hand-roll boundary handling. This module wraps it in the small interface the
request handler needs and adds the scalar conversions used by the form fields.
"""

from __future__ import annotations

from email.parser import BytesParser
from email.policy import default as email_default_policy

Fields = dict[str, list[str]]
Files = dict[str, tuple[str, bytes]]


def parse_multipart(content_type: str, body: bytes) -> tuple[Fields, Files]:
    """Parse a multipart request into text fields and uploaded files."""
    payload = b"Content-Type: " + content_type.encode("latin-1") + b"\r\n\r\n" + body
    message = BytesParser(policy=email_default_policy).parsebytes(payload)

    fields: Fields = {}
    files: Files = {}

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


def field(fields: Fields, name: str) -> str | None:
    """Return the last value submitted for a form field, if any."""
    values = fields.get(name)
    return values[-1] if values else None


def as_bool(value: str | None, default: bool = False) -> bool:
    """Interpret the common HTML form spellings of a boolean."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def as_int(value: str | None, default: int) -> int:
    """Parse an integer form field, keeping the server's ValueError contract."""
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{value!r} is not a valid integer") from exc
