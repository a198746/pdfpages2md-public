"""Server bootstrap: argument parsing plus the threading HTTP server."""

from __future__ import annotations

import argparse
import logging
from http.server import ThreadingHTTPServer

from .handler import PdfPagesRequestHandler


def create_server(host: str, port: int) -> ThreadingHTTPServer:
    """Create (but do not start) the local HTTP server."""
    return ThreadingHTTPServer((host, port), PdfPagesRequestHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local pdfpages2md web server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
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
