"""Local HTTP API and static frontend host.

The package is split by responsibility:

- :mod:`pdfpages2md.web.app` bootstraps the server,
- :mod:`pdfpages2md.web.handler` owns HTTP routing and responses,
- :mod:`pdfpages2md.web.service` performs conversions,
- :mod:`pdfpages2md.web.multipart` parses uploads,
- :mod:`pdfpages2md.web.config_store` persists the UI-managed API keys.
"""

from .app import create_server, main

__all__ = ["create_server", "main"]
