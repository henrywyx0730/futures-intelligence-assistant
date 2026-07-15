"""Application entry point for the Futures Intelligence Assistant."""

from __future__ import annotations

from futures_intelligence.config.loader import load_all_configurations
from futures_intelligence.utils.logger import configure_logging


def main() -> None:
    """Initialize the application foundation and report startup."""
    logger = configure_logging()
    configurations = load_all_configurations()
    logger.info(
        "Futures Intelligence Assistant started with %d configuration sets.",
        len(configurations),
    )


if __name__ == "__main__":
    main()

