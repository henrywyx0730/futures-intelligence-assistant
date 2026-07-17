"""Logging setup shared by application entry points and future components."""

from __future__ import annotations

import logging
from pathlib import Path


DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FILE = "logs/futures_intelligence.log"
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging(
    level_name: str = DEFAULT_LOG_LEVEL,
    log_file: str | Path = DEFAULT_LOG_FILE,
) -> logging.Logger:
    """Configure application logging to both the console and a local file."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logger = logging.getLogger("futures_intelligence")
    logger.setLevel(level)
    logger.propagate = False

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(LOG_FORMAT)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger
