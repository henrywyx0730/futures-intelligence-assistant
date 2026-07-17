"""Tests for command-line output in the application entry point."""

from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import unittest
from unittest.mock import Mock, patch

from futures_intelligence.main import _parse_arguments, main
from futures_intelligence.models import MarketAnalysis, MarketInformation
from futures_intelligence.utils.health import HealthReport


class MainTests(unittest.TestCase):
    """Validate CLI presentation without running the pipeline."""

    @patch("futures_intelligence.main.MorningBriefService")
    def test_default_command_prints_previews_and_returned_brief(
        self, service_class: Mock
    ) -> None:
        information = MarketInformation(
            title="Gold market update",
            source="Test Source",
            source_type="test",
            published_time=datetime(2026, 7, 17, tzinfo=timezone.utc),
            content="Gold inventory data was released.",
            category=("metals",),
        )
        service = service_class.return_value
        service.information = [information]
        service.analyses = [
            MarketAnalysis(information, "Detected commodity focus: Gold.")
        ]
        service.run.return_value = "Morning Futures Brief\nTop analyses: 1 of 1"
        service.health_report = HealthReport(
            last_run_timestamp="2026-07-17T00:00:00+00:00",
            execution_status="success",
            collected_information_count=1,
            generated_analysis_count=1,
            brief_generation_status="success",
        )

        output = StringIO()
        with redirect_stdout(output):
            main([])

        service.run.assert_called_once_with()
        self.assertIn("Collected market information: 1", output.getvalue())
        self.assertIn("Market analyses: 1", output.getvalue())
        self.assertIn("Morning Futures Brief", output.getvalue())
        self.assertIn("Run status: success", output.getvalue())

    def test_parses_explicit_morning_brief_command(self) -> None:
        self.assertEqual(_parse_arguments(["morning-brief"]).command, "morning-brief")


if __name__ == "__main__":
    unittest.main()
