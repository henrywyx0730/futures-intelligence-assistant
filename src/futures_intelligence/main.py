"""Application entry point for the Futures Intelligence Assistant."""

from __future__ import annotations

from typing import Any

from futures_intelligence.config.loader import load_all_configurations
from futures_intelligence.pipeline.collector_runner import CollectorRunner
from futures_intelligence.utils.logger import configure_logging


def main() -> None:
    """Load configuration and run the configured collection pipeline."""
    logger = configure_logging()
    configurations = load_all_configurations()
    source_configurations = _extract_source_configurations(
        configurations["sources"]
    )
    information = CollectorRunner(source_configurations).run()

    logger.info(
        "Futures Intelligence Assistant collected %d market information items.",
        len(information),
    )


def _extract_source_configurations(value: object) -> list[dict[str, Any]]:
    """Return source-entry dictionaries from the nested source registry."""
    if isinstance(value, dict):
        if "source_type" in value:
            return [value]
        return [
            source_config
            for child in value.values()
            for source_config in _extract_source_configurations(child)
        ]
    if isinstance(value, list):
        return [
            source_config
            for child in value
            for source_config in _extract_source_configurations(child)
        ]
    return []


if __name__ == "__main__":
    main()
