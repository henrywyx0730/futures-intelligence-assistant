"""Application entry point for the Futures Intelligence Assistant."""

from __future__ import annotations

from typing import Any

from futures_intelligence.analyst.rule_based import RuleBasedAnalyst
from futures_intelligence.config.loader import load_all_configurations
from futures_intelligence.database import (
    initialize_database,
    store_market_analysis,
    store_market_information,
)
from futures_intelligence.models import MarketAnalysis, MarketInformation
from futures_intelligence.pipeline.collector_runner import CollectorRunner
from futures_intelligence.processing.deduplicator import InformationDeduplicator
from futures_intelligence.processing.ranker import InformationRanker
from futures_intelligence.utils.logger import configure_logging


def main() -> None:
    """Load configuration and run the configured collection pipeline."""
    logger = configure_logging()
    database = initialize_database()
    database.close()
    configurations = load_all_configurations()
    source_configurations = _extract_source_configurations(
        configurations["sources"]
    )
    collected_information = CollectorRunner(source_configurations).run()
    for item in collected_information:
        store_market_information("futures_intelligence.db", item)

    logger.info(
        "Futures Intelligence Assistant collected %d market information items.",
        len(collected_information),
    )
    information = InformationDeduplicator().deduplicate(collected_information)
    logger.info(
        "Futures Intelligence Assistant retained %d market information items after deduplication.",
        len(information),
    )
    information = InformationRanker().rank(information)
    _print_information_preview(information)
    analyses = RuleBasedAnalyst().analyze(information)
    for analysis in analyses:
        store_market_analysis("futures_intelligence.db", analysis)
    _print_analysis_preview(analyses)


def _print_information_preview(information: list[MarketInformation]) -> None:
    """Print a concise preview of up to five collected information items."""
    print(f"Collected market information: {len(information)}")
    for item in information[:5]:
        category = ", ".join(item.category) or "uncategorized"
        print(
            f"- Source: {item.source} | Title: {item.title} | "
            f"Category: {category} | Published: {item.published_time.isoformat()}"
        )


def _print_analysis_preview(analyses: list[MarketAnalysis]) -> None:
    """Print a concise preview of up to five market analyses."""
    print(f"Market analyses: {len(analyses)}")
    for analysis in analyses[:5]:
        information = analysis.market_information
        print(
            f"- Source: {information.source} | Title: {information.title} | "
            f"Analysis: {analysis.summary}"
        )


def _extract_source_configurations(value: object) -> list[dict[str, Any]]:
    """Return source-entry dictionaries from the nested source registry."""
    if isinstance(value, dict):
        if "source_type" in value:
            return [value]

        source_configurations: list[dict[str, Any]] = []
        for key, child in value.items():
            if key == "rss_sources" and isinstance(child, list):
                source_configurations.extend(
                    source for source in child if isinstance(source, dict)
                )
            else:
                source_configurations.extend(_extract_source_configurations(child))
        return source_configurations
    if isinstance(value, list):
        return [
            source_config
            for child in value
            for source_config in _extract_source_configurations(child)
        ]
    return []


if __name__ == "__main__":
    main()
