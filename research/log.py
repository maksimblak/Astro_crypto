"""Shared logging setup for the project."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_CONFIGURED = False


def get_logger(name: str) -> logging.Logger:
    """Get a project logger with consistent formatting."""
    global _CONFIGURED
    if not _CONFIGURED:
        _setup_root()
        _CONFIGURED = True
    return logging.getLogger(name)


def _setup_root():
    root = logging.getLogger()
    if root.handlers:
        return

    root.setLevel(logging.INFO)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "[%(asctime)s] %(name)s %(levelname)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    console.setFormatter(fmt)
    root.addHandler(console)

    log_dir = Path(__file__).resolve().parent.parent / "data"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "astrobtc.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s",
    ))
    root.addHandler(file_handler)
