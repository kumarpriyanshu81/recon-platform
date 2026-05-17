"""
Centralised logging configuration for recon-platform.

All modules obtain their logger via:
    from core.logger import get_logger
    log = get_logger(__name__)
"""

import logging
import sys
from typing import Optional

from config import settings


def _build_formatter() -> logging.Formatter:
    return logging.Formatter(
        fmt=settings.LOG_FORMAT,
        datefmt=settings.LOG_DATE_FORMAT,
    )


def configure_root_logger(level: Optional[str] = None) -> None:
    """
    Configure the root logger once at application startup.
    Subsequent calls are safe (handlers are not duplicated).
    """
    root = logging.getLogger()
    if root.handlers:
        return  # already configured

    effective_level = level or settings.LOG_LEVEL
    root.setLevel(effective_level.upper())

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_build_formatter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger, ensuring the root is configured."""
    configure_root_logger()
    return logging.getLogger(name)
