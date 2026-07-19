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
from futures_intelligence.utils.health import HealthReport


class MorningBriefServiceTests(unittest.TestCase):
    """Validate the application service workflow without external I/O."""

    @patch("futures_intelligence.services.morning_brief_service.store_market_analysis")
    @patch("futures_intelligence.services.morning_brief_service.store_market_information")
    @patch("futures_intelligence.services.morning_brief_service.write_health_report")
    @patch("futures_intelligence.services.morning_brief_service.save_morning_brief")
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
            },
        }
        collector_runner.return_value.run.return_value = [information]
        database = Mock()
        initialize_db.return_value = database
        brief_output_path = Path("data/test-briefs/2026-07-17.md")
        save_brief.return_value = brief_output_path
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
        write_health.assert_called_once_with(
            "data/test-health.json",
            collected_information_count=1,
            generated_analysis_count=1,
            generated_brief_path=brief_output_path,
        )
        self.assertIn("Morning Futures Brief", brief)
        self.assertIn("Gold market update (Test Source)", brief)
        self.assertEqual(service.information, [information])
        self.assertEqual(len(service.analyses), 1)
        self.assertIs(service.analyses[0].market_information, information)
        self.assertIsNotNone(service.aggregated_market_view)
        assert service.aggregated_market_view is not None
        self.assertEqual(service.aggregated_market_view.analysis_count, 1)
        self.assertEqual(service.runtime_configuration.brief_lookback_hours, 12)
        self.assertEqual(
            service.runtime_configuration.brief_output_directory,
            "data/test-briefs",
        )
        self.assertEqual(service.brief_output_path, brief_output_path)
        self.assertTrue(service.runtime_configuration.scheduler.enabled)
        self.assertEqual(service.runtime_configuration.scheduler.interval_hours, 6)
        self.assertIs(service.health_report, health_report)
        configure_logger.return_value.info.assert_called()

    def test_uses_safe_defaults_for_missing_or_invalid_runtime_settings(self) -> None:
        runtime = _runtime_configuration(
            {
                "database_path": " ",
                "brief": {"lookback_hours": 0},
                "scheduler": {"enabled": "yes", "interval_hours": -1},
                "logging": {"level": "verbose", "file_path": " "},
                "health": {"file_path": " "},
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


if __name__ == "__main__":
    unittest.main()
