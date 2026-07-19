"""Application service for the deterministic morning brief workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from futures_intelligence.analyst import (
    AggregatedMarketView,
    AnalystRouter,
    LLMAnalyst,
    MarketAnalysisAggregator,
)
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
from futures_intelligence.utils.llm_usage import LLMPricing, LLMUsageTracker


DEFAULT_DATABASE_PATH = "futures_intelligence.db"
DEFAULT_BRIEF_LOOKBACK_HOURS = 24
DEFAULT_BRIEF_OUTPUT_DIRECTORY = "data/briefs"
DEFAULT_SCHEDULER_INTERVAL_HOURS = 24
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FILE = "logs/futures_intelligence.log"
DEFAULT_HEALTH_REPORT_FILE = "data/health_report.json"
DEFAULT_HISTORY_FILE = "data/market_intelligence_history.json"
DEFAULT_LLM_PROVIDER = "openai"
DEFAULT_LLM_MODEL = "gpt-5.6-luna"
DEFAULT_LLM_SOURCE_TYPES = ("research_report",)
DEFAULT_LLM_MAX_ITEMS_PER_RUN = 5
DEFAULT_LLM_USAGE_FILE = "data/llm_usage.jsonl"
DEFAULT_LLM_PRICING_EFFECTIVE_DATE = "2026-07-19"
DEFAULT_LLM_INPUT_PER_MILLION_USD = 1.00
DEFAULT_LLM_CACHED_INPUT_PER_MILLION_USD = 0.10
DEFAULT_LLM_OUTPUT_PER_MILLION_USD = 6.00
DEFAULT_LLM_CACHE_WRITE_MULTIPLIER = 1.25


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
class LLMUsageSettings:
    """Runtime location for append-only local LLM usage records."""

    file_path: str = DEFAULT_LLM_USAGE_FILE


@dataclass(frozen=True)
class LLMPricingSettings:
    """A reviewable local pricing snapshot used for cost estimates."""

    model: str = DEFAULT_LLM_MODEL
    effective_date: str = DEFAULT_LLM_PRICING_EFFECTIVE_DATE
    input_per_million_usd: float = DEFAULT_LLM_INPUT_PER_MILLION_USD
    cached_input_per_million_usd: float = DEFAULT_LLM_CACHED_INPUT_PER_MILLION_USD
    output_per_million_usd: float = DEFAULT_LLM_OUTPUT_PER_MILLION_USD
    cache_write_multiplier: float = DEFAULT_LLM_CACHE_WRITE_MULTIPLIER


@dataclass(frozen=True)
class LLMSettings:
    """Optional local runtime settings for controlled LLM analysis."""

    enabled: bool = False
    provider: str = DEFAULT_LLM_PROVIDER
    model: str = DEFAULT_LLM_MODEL
    source_types: tuple[str, ...] = DEFAULT_LLM_SOURCE_TYPES
    max_items_per_run: int = DEFAULT_LLM_MAX_ITEMS_PER_RUN
    usage: LLMUsageSettings = field(default_factory=LLMUsageSettings)
    pricing: LLMPricingSettings = field(default_factory=LLMPricingSettings)


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
    llm: LLMSettings = field(default_factory=LLMSettings)


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
        self.runtime_configuration = _runtime_configuration(configurations.get("runtime"))
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

        llm_settings = self.runtime_configuration.llm
        llm_analyst = LLMAnalyst(
            model=llm_settings.model,
            max_items_per_run=llm_settings.max_items_per_run,
            usage_tracker=LLMUsageTracker(
                llm_settings.usage.file_path,
                LLMPricing(
                    model=llm_settings.pricing.model,
                    effective_date=llm_settings.pricing.effective_date,
                    input_per_million_usd=llm_settings.pricing.input_per_million_usd,
                    cached_input_per_million_usd=(
                        llm_settings.pricing.cached_input_per_million_usd
                    ),
                    output_per_million_usd=(
                        llm_settings.pricing.output_per_million_usd
                    ),
                    cache_write_multiplier=(
                        llm_settings.pricing.cache_write_multiplier
                    ),
                ),
            ),
        )
        self.analyses = AnalystRouter(
            llm_enabled=llm_settings.enabled and llm_settings.provider == "openai",
            llm_source_types=llm_settings.source_types,
            llm_analyst=llm_analyst,
        ).analyze(self.information)
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


def load_runtime_configuration() -> RuntimeConfiguration:
    """Load normalized runtime settings for a narrow non-service entry point."""
    return _runtime_configuration(_load_all_configurations().get("runtime"))


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
    llm_settings = value.get("llm")
    llm_usage = llm_settings.get("usage") if isinstance(llm_settings, dict) else None
    llm_pricing = (
        llm_settings.get("pricing") if isinstance(llm_settings, dict) else None
    )

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
        llm=LLMSettings(
            enabled=(
                llm_settings.get("enabled")
                if isinstance(llm_settings, dict)
                and isinstance(llm_settings.get("enabled"), bool)
                else False
            ),
            provider=(
                llm_settings.get("provider").strip().lower()
                if isinstance(llm_settings, dict)
                and isinstance(llm_settings.get("provider"), str)
                and llm_settings.get("provider").strip()
                else DEFAULT_LLM_PROVIDER
            ),
            model=(
                llm_settings.get("model").strip()
                if isinstance(llm_settings, dict)
                and isinstance(llm_settings.get("model"), str)
                and llm_settings.get("model").strip()
                else DEFAULT_LLM_MODEL
            ),
            source_types=_llm_source_types(
                llm_settings.get("source_types")
                if isinstance(llm_settings, dict)
                else None
            ),
            max_items_per_run=_positive_int(
                llm_settings.get("max_items_per_run")
                if isinstance(llm_settings, dict)
                else None,
                DEFAULT_LLM_MAX_ITEMS_PER_RUN,
            ),
            usage=LLMUsageSettings(
                file_path=_non_empty_text(
                    llm_usage.get("file_path") if isinstance(llm_usage, dict) else None,
                    DEFAULT_LLM_USAGE_FILE,
                ),
            ),
            pricing=LLMPricingSettings(
                model=_non_empty_text(
                    llm_pricing.get("model") if isinstance(llm_pricing, dict) else None,
                    DEFAULT_LLM_MODEL,
                ),
                effective_date=_non_empty_text(
                    llm_pricing.get("effective_date")
                    if isinstance(llm_pricing, dict)
                    else None,
                    DEFAULT_LLM_PRICING_EFFECTIVE_DATE,
                ),
                input_per_million_usd=_non_negative_float(
                    llm_pricing.get("input_per_million_usd")
                    if isinstance(llm_pricing, dict)
                    else None,
                    DEFAULT_LLM_INPUT_PER_MILLION_USD,
                ),
                cached_input_per_million_usd=_non_negative_float(
                    llm_pricing.get("cached_input_per_million_usd")
                    if isinstance(llm_pricing, dict)
                    else None,
                    DEFAULT_LLM_CACHED_INPUT_PER_MILLION_USD,
                ),
                output_per_million_usd=_non_negative_float(
                    llm_pricing.get("output_per_million_usd")
                    if isinstance(llm_pricing, dict)
                    else None,
                    DEFAULT_LLM_OUTPUT_PER_MILLION_USD,
                ),
                cache_write_multiplier=_non_negative_float(
                    llm_pricing.get("cache_write_multiplier")
                    if isinstance(llm_pricing, dict)
                    else None,
                    DEFAULT_LLM_CACHE_WRITE_MULTIPLIER,
                ),
            ),
        ),
    )


def _positive_int(value: object, default: int) -> int:
    """Return a positive integer configuration value or its safe default."""
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return default


def _non_empty_text(value: object, default: str) -> str:
    """Return a stripped text configuration value or a safe default."""
    return value.strip() if isinstance(value, str) and value.strip() else default


def _non_negative_float(value: object, default: float) -> float:
    """Return a non-negative numeric configuration value or a safe default."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return default


def _llm_source_types(value: object) -> tuple[str, ...]:
    """Return configured non-empty LLM source types in stable order."""
    if not isinstance(value, (list, tuple)):
        return DEFAULT_LLM_SOURCE_TYPES
    source_types = tuple(
        source_type.strip()
        for source_type in value
        if isinstance(source_type, str) and source_type.strip()
    )
    return source_types or DEFAULT_LLM_SOURCE_TYPES


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
