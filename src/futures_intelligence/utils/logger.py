"""Logging setup shared by application entry points and future components."""

from __future__ import annotations

import logging
import os


def configure_logging() -> logging.Logger:
    """Configure and return the application logger."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logger = logging.getLogger("futures_intelligence")
    logger.setLevel(level)
    return logger

