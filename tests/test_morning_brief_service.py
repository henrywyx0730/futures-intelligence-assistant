"""Tests for morning brief service orchestration."""

from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from futures_intelligence.models import MarketInformation
from futures_intelligence.services.morning_brief_service import (
    MorningBriefService,
    _runtime_configuration,
)
from futures_intelligence.processing import MarketTrendChange
from futures_intelligence.utils.health import HealthReport


class MorningBriefServiceTests(unittest.TestCase):
    """Validate the application service workflow without external I/O."""

    @patch("futures_intelligence.services.morning_brief_service.store_market_analysis")
    @patch("futures_intelligence.services.morning_brief_service.store_market_information")
    @patch("futures_intelligence.services.morning_brief_service.write_health_report")
    @patch("futures_intelligence.services.morning_brief_service.save_morning_brief")
    @patch("futures_intelligence.services.morning_brief_service.append_market_intelligence_history")
    @patch("futures_intelligence.services.morning_brief_service.MarketTrendChangeDetector")
    @patch("futures_intelligence.services.morning_brief_service.initialize_database")
    @patch("futures_intelligence.services.morning_brief_service.configure_logging")
    @patch("futures_intelligence.services.morning_brief_service.CollectorRunner")
    @patch("futures_intelligence.services.morning_brief_service._load_all_configurations")
    def test_runs_pipeline_persists_results_and_returns_brief(
        self,
        load_configurations: Mock,
        collector_runner: Mock,
        configure_logger: Mock,
        initialize_db: Mock,
        trend_detector: Mock,
        append_history: Mock,
        save_brief: Mock,
        write_health: Mock,
        store_information: Mock,
        store_analysis: Mock,
    ) -> None:
        source_configuration = {
            "name": "Test RSS",
            "source_type": "rss",
            "enabled": True,
            "url": "https://example.test/feed.xml",
        }
        information = MarketInformation(
            title="Gold market update",
            source="Test Source",
            source_type="rss",
            published_time=datetime(2026, 7, 17, tzinfo=timezone.utc),
            content="Gold inventory data was released.",
            category=("metals",),
        )
        load_configurations.return_value = {
            "sources": {"financial_news": [source_configuration]},
            "runtime": {
                "database_path": "test-runtime.db",
                "brief": {
                    "lookback_hours": 12,
                    "output_directory": "data/test-briefs",
                },
                "scheduler": {"enabled": True, "interval_hours": 6},
                "logging": {"level": "DEBUG", "file_path": "logs/test.log"},
                "health": {"file_path": "data/test-health.json"},
                "history": {"file_path": "data/test-history.json"},
                "llm": {
                    "enabled": True,
                    "provider": "openai",
                    "model": "test-model",
                    "source_types": ["research_report"],
                    "min_reliability_score": 4,
                    "max_items_per_run": 2,
                    "usage": {"file_path": "data/test-llm-usage.jsonl"},
                    "pricing": {
                        "model": "test-model",
                        "effective_date": "2026-07-19",
                        "input_per_million_usd": 1.0,
                        "cached_input_per_million_usd": 0.1,
                        "output_per_million_usd": 6.0,
                        "cache_write_multiplier": 1.25,
                    },
                },
            },
        }
        collector_runner.return_value.run.return_value = [information]
        database = Mock()
        initialize_db.return_value = database
        brief_output_path = Path("data/test-briefs/2026-07-17.md")
        save_brief.return_value = brief_output_path
        append_history.return_value = Mock()
        trend_detector.return_value.detect.return_value = MarketTrendChange(
            previous_date="2026-07-16",
            latest_date="2026-07-17",
            previous_direction="neutral",
            latest_direction="bullish",
            direction_changed=True,
            previous_confidence_score=50,
            latest_confidence_score=67,
            confidence_change=17,
            confidence_changed=True,
        )
        health_report = HealthReport(
            last_run_timestamp="2026-07-17T00:00:00+00:00",
            execution_status="success",
            collected_information_count=1,
            generated_analysis_count=1,
            brief_generation_status="success",
            generated_brief_path="data/test-briefs/2026-07-17.md",
        )
        write_health.return_value = health_report

        service = MorningBriefService()
        brief = service.run()

        database.close.assert_called_once_with()
        collector_runner.assert_called_once_with([source_configuration])
        initialize_db.assert_called_once_with("test-runtime.db")
        configure_logger.assert_called_once_with("DEBUG", "logs/test.log")
        store_information.assert_called_once_with("test-runtime.db", information)
        store_analysis.assert_called_once()
        save_brief.assert_called_once_with(brief, "data/test-briefs")
        append_history.assert_called_once_with(
            "data/test-history.json",
            service.aggregated_market_view,
            [information],
        )
        trend_detector.return_value.detect.assert_called_once_with("data/test-history.json")
        write_health.assert_called_once_with(
            "data/test-health.json",
            collected_information_count=1,
            generated_analysis_count=1,
            generated_brief_path=brief_output_path,
        )
        self.assertIn("Morning Futures Brief", brief)
        self.assertIn("Gold market update (Test Source)", brief)
        self.assertIn("Trend Change", brief)
        self.assertIn("Previous Direction: Neutral", brief)
        self.assertIn("Current Direction: Bullish", brief)
        self.assertIn("Confidence Change: +17 points", brief)
        self.assertEqual(service.information, [information])
        self.assertEqual(len(service.analyses), 1)
        self.assertIs(service.analyses[0].market_information, information)
        self.assertIsNotNone(service.aggregated_market_view)
        assert service.aggregated_market_view is not None
        self.assertEqual(service.aggregated_market_view.analysis_count, 1)
        self.assertEqual(len(service.commodity_market_views), 1)
        self.assertEqual(service.commodity_market_views[0].commodity_key, "gold")
        self.assertEqual(service.runtime_configuration.brief_lookback_hours, 12)
        self.assertEqual(
            service.runtime_configuration.brief_output_directory,
            "data/test-briefs",
        )
        self.assertEqual(service.brief_output_path, brief_output_path)
        self.assertTrue(service.runtime_configuration.scheduler.enabled)
        self.assertEqual(service.runtime_configuration.scheduler.interval_hours, 6)
        self.assertTrue(service.runtime_configuration.llm.enabled)
        self.assertEqual(service.runtime_configuration.llm.model, "test-model")
        self.assertEqual(service.runtime_configuration.llm.source_types, ("research_report",))
        self.assertEqual(service.runtime_configuration.llm.min_reliability_score, 4)
        self.assertEqual(service.runtime_configuration.llm.max_items_per_run, 2)
        self.assertEqual(
            service.runtime_configuration.llm.usage.file_path,
            "data/test-llm-usage.jsonl",
        )
        self.assertEqual(service.runtime_configuration.llm.pricing.model, "test-model")
        self.assertIs(service.health_report, health_report)
        self.assertIs(service.market_intelligence_history_entry, append_history.return_value)
        self.assertIs(
            service.market_trend_change,
            trend_detector.return_value.detect.return_value,
        )
        configure_logger.return_value.info.assert_called()
        configure_logger.return_value.info.assert_any_call(
            "LLM routing: %d eligible candidates, %d selected candidates, "
            "%d rule-based items, maximum %d.",
            0,
            0,
            1,
            2,
        )

    def test_uses_safe_defaults_for_missing_or_invalid_runtime_settings(self) -> None:
        runtime = _runtime_configuration(
            {
                "database_path": " ",
                "brief": {"lookback_hours": 0},
                "scheduler": {"enabled": "yes", "interval_hours": -1},
                "logging": {"level": "verbose", "file_path": " "},
                "health": {"file_path": " "},
                "history": {"file_path": " "},
                "llm": {
                    "enabled": "yes",
                    "provider": "other",
                    "model": " ",
                    "source_types": [" ", 1],
                    "min_reliability_score": 0,
                    "max_items_per_run": 0,
                },
            }
        )

        self.assertEqual(runtime.database_path, "futures_intelligence.db")
        self.assertEqual(runtime.brief_lookback_hours, 24)
        self.assertEqual(runtime.brief_output_directory, "data/briefs")
        self.assertFalse(runtime.scheduler.enabled)
        self.assertEqual(runtime.scheduler.interval_hours, 24)
        self.assertEqual(runtime.logging.level, "INFO")
        self.assertEqual(runtime.logging.file_path, "logs/futures_intelligence.log")
        self.assertEqual(runtime.health.file_path, "data/health_report.json")
        self.assertEqual(
            runtime.history.file_path, "data/market_intelligence_history.json"
        )
        self.assertFalse(runtime.llm.enabled)
        self.assertEqual(runtime.llm.provider, "other")
        self.assertEqual(runtime.llm.model, "gpt-5.6-luna")
        self.assertEqual(runtime.llm.source_types, ("research_report",))
        self.assertEqual(runtime.llm.min_reliability_score, 4)
        self.assertEqual(runtime.llm.max_items_per_run, 3)
        self.assertEqual(runtime.llm.usage.file_path, "data/llm_usage.jsonl")
        self.assertEqual(runtime.llm.pricing.model, "gpt-5.6-luna")


if __name__ == "__main__":
    unittest.main()
