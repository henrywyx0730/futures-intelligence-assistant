"""Tests for the market-analysis model."""

from datetime import datetime, timezone
import unittest

from futures_intelligence.models import MarketAnalysis, MarketInformation


def make_information() -> MarketInformation:
    """Create a normalized item for analysis tests."""
    return MarketInformation(
        title="Oil inventory update",
        source="EIA",
        source_type="official_data",
        published_time=datetime(2026, 7, 16, tzinfo=timezone.utc),
        content="Weekly inventory data was published.",
    )


class MarketAnalysisTests(unittest.TestCase):
    """Validate the minimal analyst output model."""

    def test_creates_and_normalizes_analysis(self) -> None:
        information = make_information()
        analysis = MarketAnalysis(information, "  Inventory data was published.  ")

        self.assertIs(analysis.market_information, information)
        self.assertEqual(analysis.summary, "Inventory data was published.")

    def test_rejects_empty_summary(self) -> None:
        with self.assertRaises(ValueError):
            MarketAnalysis(make_information(), "   ")

    def test_rejects_invalid_market_information(self) -> None:
        with self.assertRaises(TypeError):
            MarketAnalysis("not information", "Summary")


if __name__ == "__main__":
    unittest.main()
