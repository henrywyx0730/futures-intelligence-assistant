"""Tests for deterministic morning brief generation."""

from datetime import datetime, timezone
import unittest

from futures_intelligence.generator import MorningBriefGenerator
from futures_intelligence.models import MarketAnalysis, MarketInformation


def make_analysis(title: str, source: str, summary: str) -> MarketAnalysis:
    """Create a market analysis for morning brief tests."""
    information = MarketInformation(
        title=title,
        source=source,
        source_type="test",
        published_time=datetime(2026, 7, 16, tzinfo=timezone.utc),
        content="Test market information.",
    )
    return MarketAnalysis(market_information=information, summary=summary)


class MorningBriefGeneratorTests(unittest.TestCase):
    """Validate morning brief report formatting."""

    def setUp(self) -> None:
        self.generator = MorningBriefGenerator()

    def test_generates_report_for_analyses(self) -> None:
        analyses = [
            make_analysis("Oil update", "Energy Desk", "Oil demand remains in focus."),
            make_analysis("Gold update", "Metals Desk", "Gold prices were mixed."),
        ]

        brief = self.generator.generate(analyses)

        self.assertEqual(
            brief,
            "Morning Futures Brief\n"
            "Top analyses: 2 of 2\n\n"
            "1. Oil update (Energy Desk)\n"
            "   Oil demand remains in focus.\n\n"
            "2. Gold update (Metals Desk)\n"
            "   Gold prices were mixed.",
        )

    def test_limits_report_to_first_five_analyses(self) -> None:
        analyses = [
            make_analysis(f"Update {index}", "Test Source", f"Summary {index}.")
            for index in range(1, 7)
        ]

        brief = self.generator.generate(analyses)

        self.assertIn("Top analyses: 5 of 6", brief)
        self.assertIn("1. Update 1 (Test Source)", brief)
        self.assertIn("5. Update 5 (Test Source)", brief)
        self.assertNotIn("Update 6", brief)

    def test_generates_empty_report(self) -> None:
        self.assertEqual(
            self.generator.generate([]),
            "Morning Futures Brief\nTop analyses: 0 of 0",
        )


if __name__ == "__main__":
    unittest.main()
