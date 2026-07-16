"""Tests for deterministic rule-based market analysis."""

from datetime import datetime, timezone
import unittest

from futures_intelligence.analyst.rule_based import RuleBasedAnalyst
from futures_intelligence.models import MarketInformation


def make_information(title: str, content: str) -> MarketInformation:
    """Create a normalized item for rule-based analysis tests."""
    return MarketInformation(
        title=title,
        source="Test Source",
        source_type="test",
        published_time=datetime(2026, 7, 16, tzinfo=timezone.utc),
        content=content,
    )


class RuleBasedAnalystTests(unittest.TestCase):
    """Validate deterministic keyword-based summaries."""

    def setUp(self) -> None:
        self.analyst = RuleBasedAnalyst()

    def test_detects_commodities_from_title_and_content(self) -> None:
        information = make_information(
            "Oil market update", "Copper inventory data was also released."
        )

        analysis = self.analyst.analyze([information])[0]

        self.assertIs(analysis.market_information, information)
        self.assertEqual(
            analysis.summary,
            "Detected commodity focus: Crude Oil, Copper. "
            "Review potential supply, demand, inventory, and cost implications.",
        )

    def test_returns_general_summary_without_tracked_keywords(self) -> None:
        information = make_information(
            "Central bank statement", "The policy statement was published."
        )

        analysis = self.analyst.analyze([information])[0]

        self.assertEqual(
            analysis.summary,
            "No tracked commodity keywords detected. "
            "Review the information for broader market context.",
        )

    def test_preserves_input_order_and_references(self) -> None:
        first = make_information("Gold update", "Market data")
        second = make_information("Corn update", "Crop data")

        analyses = self.analyst.analyze([first, second])

        self.assertEqual([analysis.market_information for analysis in analyses], [first, second])
        self.assertIs(analyses[0].market_information, first)
        self.assertIs(analyses[1].market_information, second)

    def test_returns_empty_list_for_empty_input(self) -> None:
        self.assertEqual(self.analyst.analyze([]), [])


if __name__ == "__main__":
    unittest.main()
