"""Filesystem locations used by the local web service."""

from __future__ import annotations

from pathlib import Path

# backend/pdfpages2md/web/paths.py -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
CONFIG_FILE = PROJECT_ROOT / ".pdfpages2md_config.json"
