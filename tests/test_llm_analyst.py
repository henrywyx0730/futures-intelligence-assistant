"""Tests for the deterministic LLM analyst placeholder."""

from datetime import datetime, timezone
import unittest

from futures_intelligence.analyst import BaseAnalyst, LLMAnalyst
from futures_intelligence.models import MarketInformation


def make_information(title: str) -> MarketInformation:
    """Create normalized information for placeholder analyst tests."""
    return MarketInformation(
        title=title,
        source="Test Source",
        source_type="rss",
        published_time=datetime(2026, 7, 19, tzinfo=timezone.utc),
        content="Test content.",
    )


class LLMAnalystTests(unittest.TestCase):
    """Validate API-free deterministic placeholder behavior."""

    def setUp(self) -> None:
        self.analyst = LLMAnalyst()

    def test_implements_base_analyst(self) -> None:
        self.assertIsInstance(self.analyst, BaseAnalyst)

    def test_returns_neutral_unavailable_analyses(self) -> None:
        information = [make_information("First update"), make_information("Second update")]

        analyses = self.analyst.analyze(information)

        self.assertEqual(len(analyses), 2)
        self.assertEqual(
            [analysis.market_information for analysis in analyses], information
        )
        self.assertTrue(
            all(analysis.market_direction == "neutral" for analysis in analyses)
        )
        self.assertTrue(all(analysis.confidence_score == 0 for analysis in analyses))
        self.assertTrue(all("unavailable" in analysis.summary for analysis in analyses))

    def test_is_deterministic_and_handles_empty_input(self) -> None:
        information = [make_information("Market update")]

        self.assertEqual(self.analyst.analyze(information), self.analyst.analyze(information))
        self.assertEqual(self.analyst.analyze([]), [])


if __name__ == "__main__":
    unittest.main()
