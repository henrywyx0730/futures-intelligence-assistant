"""Tests for deterministic morning brief generation."""

from datetime import datetime, timezone
import unittest

from futures_intelligence.analyst import AggregatedMarketView
from futures_intelligence.generator import MorningBriefGenerator
from futures_intelligence.models import MarketAnalysis, MarketInformation
from futures_intelligence.processing import MarketTrendChange


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
            "\n"
            "Market Overview\n"
            "Direction: Neutral\n"
            "Confidence: 0/100\n"
            "Reasoning:\n"
            "- No reasoning details available.\n\n"
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

    def test_includes_provided_aggregated_market_view(self) -> None:
        view = AggregatedMarketView(
            overall_market_direction="bullish",
            aggregated_confidence_score=82,
            reasoning_details=("Positive price momentum.", "Demand improved."),
            analysis_count=1,
        )

        brief = self.generator.generate(
            [make_analysis("Oil update", "Energy Desk", "Oil demand improved.")],
            view,
        )

        self.assertIn("Market Overview", brief)
        self.assertIn("Direction: Bullish", brief)
        self.assertIn("Confidence: 82/100", brief)
        self.assertIn("- Positive price momentum.", brief)
        self.assertIn("- Demand improved.", brief)
        self.assertIn("1. Oil update (Energy Desk)", brief)

    def test_includes_comparable_trend_change(self) -> None:
        trend_change = MarketTrendChange(
            previous_date="2026-07-18",
            latest_date="2026-07-19",
            previous_direction="bullish",
            latest_direction="bearish",
            direction_changed=True,
            previous_confidence_score=72,
            latest_confidence_score=58,
            confidence_change=-14,
            confidence_changed=True,
        )

        brief = self.generator.generate([], trend_change=trend_change)

        self.assertIn("Trend Change", brief)
        self.assertIn("Previous Direction: Bullish", brief)
        self.assertIn("Current Direction: Bearish", brief)
        self.assertIn("Confidence Change: -14 points", brief)

    def test_omits_trend_change_without_a_previous_view(self) -> None:
        trend_change = MarketTrendChange(
            previous_date=None,
            latest_date="2026-07-19",
            previous_direction=None,
            latest_direction="neutral",
            direction_changed=False,
            previous_confidence_score=None,
            latest_confidence_score=50,
            confidence_change=0,
            confidence_changed=False,
        )

        brief = self.generator.generate([], trend_change=trend_change)

        self.assertNotIn("Trend Change", brief)

    def test_generates_empty_report(self) -> None:
        self.assertEqual(
            self.generator.generate([]),
            "Morning Futures Brief\n"
            "\n"
            "Market Overview\n"
            "Direction: Neutral\n"
            "Confidence: 0/100\n"
            "Reasoning:\n"
            "- No analyses available for aggregation.\n\n"
            "Top analyses: 0 of 0",
        )


if __name__ == "__main__":
    unittest.main()
