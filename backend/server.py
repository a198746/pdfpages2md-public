"""Entry point for the local web server.

The implementation now lives in :mod:`pdfpages2md.web`; this file is kept as a
stable launch path because ``deploy.ps1``, the README and existing shortcuts run
``python backend/server.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    # Allow ``python backend/server.py`` to import the sibling package.
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdfpages2md.web.app import create_server, main
from pdfpages2md.web.handler import PdfPagesRequestHandler

__all__ = ["PdfPagesRequestHandler", "create_server", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
