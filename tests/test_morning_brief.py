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
            "Number of analyses: 2\n\n"
            "1. Source: Energy Desk\n"
            "   Title: Oil update\n"
            "   Summary: Oil demand remains in focus.\n\n"
            "2. Source: Metals Desk\n"
            "   Title: Gold update\n"
            "   Summary: Gold prices were mixed.",
        )

    def test_generates_empty_report(self) -> None:
        self.assertEqual(
            self.generator.generate([]),
            "Morning Futures Brief\nNumber of analyses: 0",
        )


if __name__ == "__main__":
    unittest.main()
