"""Application service for the deterministic morning brief workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from futures_intelligence.analyst import AggregatedMarketView, MarketAnalysisAggregator
from futures_intelligence.analyst.rule_based import RuleBasedAnalyst
from futures_intelligence.database import (
    initialize_database,
    store_market_analysis,
    store_market_information,
)
from futures_intelligence.generator import MorningBriefGenerator
from futures_intelligence.models import MarketAnalysis, MarketInformation
from futures_intelligence.pipeline.collector_runner import CollectorRunner
from futures_intelligence.processing.deduplicator import InformationDeduplicator
from futures_intelligence.processing.ranker import InformationRanker
from futures_intelligence.processing.trend_detector import (
    MarketTrendChange,
    MarketTrendChangeDetector,
)
from futures_intelligence.utils.brief_storage import save_morning_brief
from futures_intelligence.utils.health import HealthReport, write_health_report
from futures_intelligence.utils.logger import configure_logging
from futures_intelligence.utils.market_history import (
    MarketIntelligenceHistoryEntry,
    append_market_intelligence_history,
)


DEFAULT_DATABASE_PATH = "futures_intelligence.db"
DEFAULT_BRIEF_LOOKBACK_HOURS = 24
DEFAULT_BRIEF_OUTPUT_DIRECTORY = "data/briefs"
DEFAULT_SCHEDULER_INTERVAL_HOURS = 24
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FILE = "logs/futures_intelligence.log"
DEFAULT_HEALTH_REPORT_FILE = "data/health_report.json"
DEFAULT_HISTORY_FILE = "data/market_intelligence_history.json"


@dataclass(frozen=True)
class SchedulerSettings:
    """Runtime settings reserved for a future scheduler implementation."""

    enabled: bool = False
    interval_hours: int = DEFAULT_SCHEDULER_INTERVAL_HOURS


@dataclass(frozen=True)
class LoggingSettings:
    """Runtime settings for application logging."""

    level: str = DEFAULT_LOG_LEVEL
    file_path: str = DEFAULT_LOG_FILE


@dataclass(frozen=True)
class HealthSettings:
    """Runtime settings for the local application health report."""

    file_path: str = DEFAULT_HEALTH_REPORT_FILE


@dataclass(frozen=True)
class HistorySettings:
    """Runtime settings for local aggregated market-view history."""

    file_path: str = DEFAULT_HISTORY_FILE


@dataclass(frozen=True)
class RuntimeConfiguration:
    """Normalized application runtime configuration with safe defaults."""

    database_path: str = DEFAULT_DATABASE_PATH
    brief_lookback_hours: int = DEFAULT_BRIEF_LOOKBACK_HOURS
    brief_output_directory: str = DEFAULT_BRIEF_OUTPUT_DIRECTORY
    scheduler: SchedulerSettings = field(default_factory=SchedulerSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    health: HealthSettings = field(default_factory=HealthSettings)
    history: HistorySettings = field(default_factory=HistorySettings)


class MorningBriefService:
    """Run the configured market-information workflow."""

    def __init__(self) -> None:
        """Initialize the latest pipeline outputs for CLI presentation."""
        self.information: list[MarketInformation] = []
        self.analyses: list[MarketAnalysis] = []
        self.aggregated_market_view: AggregatedMarketView | None = None
        self.runtime_configuration = RuntimeConfiguration()
        self.health_report: HealthReport | None = None
        self.brief_output_path: Path | None = None
        self.market_intelligence_history_entry: MarketIntelligenceHistoryEntry | None = None
        self.market_trend_change: MarketTrendChange | None = None

    def run(self) -> str:
        """Collect, process, persist, analyze, and return a morning brief."""
        configurations = _load_all_configurations()
        self.runtime_configuration = _runtime_configuration(
            configurations.get("runtime")
        )
        logger = configure_logging(
            self.runtime_configuration.logging.level,
            self.runtime_configuration.logging.file_path,
        )
        database_path = self.runtime_configuration.database_path
        database = initialize_database(database_path)
        database.close()

        source_configurations = _extract_source_configurations(
            configurations["sources"]
        )
        collected_information = CollectorRunner(source_configurations).run()
        for item in collected_information:
            store_market_information(database_path, item)

        logger.info(
            "Futures Intelligence Assistant collected %d market information items.",
            len(collected_information),
        )
        information = InformationDeduplicator().deduplicate(collected_information)
        logger.info(
            "Futures Intelligence Assistant retained %d market information items after deduplication.",
            len(information),
        )
        self.information = InformationRanker().rank(information)

        self.analyses = RuleBasedAnalyst().analyze(self.information)
        for analysis in self.analyses:
            store_market_analysis(database_path, analysis)

        self.aggregated_market_view = MarketAnalysisAggregator().aggregate(self.analyses)
        self.market_trend_change = MarketTrendChangeDetector().detect(
            self.runtime_configuration.history.file_path
        )
        brief = MorningBriefGenerator().generate(
            self.analyses,
            self.aggregated_market_view,
            self.market_trend_change,
        )
        self.brief_output_path = save_morning_brief(
            brief,
            self.runtime_configuration.brief_output_directory,
        )
        self.market_intelligence_history_entry = append_market_intelligence_history(
            self.runtime_configuration.history.file_path,
            self.aggregated_market_view,
            self.information,
        )
        self.health_report = write_health_report(
            self.runtime_configuration.health.file_path,
            collected_information_count=len(collected_information),
            generated_analysis_count=len(self.analyses),
            generated_brief_path=self.brief_output_path,
        )
        logger.info("Morning brief health report persisted successfully.")
        return brief


def _load_all_configurations() -> dict[str, dict[str, Any]]:
    """Load configuration lazily to keep this service easy to test."""
    from futures_intelligence.config.loader import load_all_configurations

    return load_all_configurations()


def _runtime_configuration(value: object) -> RuntimeConfiguration:
    """Normalize optional runtime settings without enabling scheduling."""
    if not isinstance(value, dict):
        return RuntimeConfiguration()

    database_path = value.get("database_path")
    brief = value.get("brief")
    scheduler = value.get("scheduler")
    logging_settings = value.get("logging")
    health_settings = value.get("health")
    history_settings = value.get("history")

    return RuntimeConfiguration(
        database_path=(
            database_path.strip()
            if isinstance(database_path, str) and database_path.strip()
            else DEFAULT_DATABASE_PATH
        ),
        brief_lookback_hours=_positive_int(
            brief.get("lookback_hours") if isinstance(brief, dict) else None,
            DEFAULT_BRIEF_LOOKBACK_HOURS,
        ),
        brief_output_directory=(
            brief.get("output_directory").strip()
            if isinstance(brief, dict)
            and isinstance(brief.get("output_directory"), str)
            and brief.get("output_directory").strip()
            else DEFAULT_BRIEF_OUTPUT_DIRECTORY
        ),
        scheduler=SchedulerSettings(
            enabled=(
                scheduler.get("enabled")
                if isinstance(scheduler, dict)
                and isinstance(scheduler.get("enabled"), bool)
                else False
            ),
            interval_hours=_positive_int(
                scheduler.get("interval_hours") if isinstance(scheduler, dict) else None,
                DEFAULT_SCHEDULER_INTERVAL_HOURS,
            ),
        ),
        logging=LoggingSettings(
            level=_log_level(
                logging_settings.get("level")
                if isinstance(logging_settings, dict)
                else None
            ),
            file_path=(
                logging_settings.get("file_path").strip()
                if isinstance(logging_settings, dict)
                and isinstance(logging_settings.get("file_path"), str)
                and logging_settings.get("file_path").strip()
                else DEFAULT_LOG_FILE
            ),
        ),
        health=HealthSettings(
            file_path=(
                health_settings.get("file_path").strip()
                if isinstance(health_settings, dict)
                and isinstance(health_settings.get("file_path"), str)
                and health_settings.get("file_path").strip()
                else DEFAULT_HEALTH_REPORT_FILE
            ),
        ),
        history=HistorySettings(
            file_path=(
                history_settings.get("file_path").strip()
                if isinstance(history_settings, dict)
                and isinstance(history_settings.get("file_path"), str)
                and history_settings.get("file_path").strip()
                else DEFAULT_HISTORY_FILE
            ),
        ),
    )


def _positive_int(value: object, default: int) -> int:
    """Return a positive integer configuration value or its safe default."""
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return default


def _log_level(value: object) -> str:
    """Return a supported log level or the safe default."""
    if isinstance(value, str) and value.upper() in {
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    }:
        return value.upper()
    return DEFAULT_LOG_LEVEL


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
