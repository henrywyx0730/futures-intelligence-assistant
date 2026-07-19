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
        self.assertEqual(analysis.market_direction, "neutral")
        self.assertEqual(analysis.confidence_score, 0)
        self.assertEqual(analysis.reasoning_details, ())

    def test_creates_rich_analysis_with_normalized_fields(self) -> None:
        analysis = MarketAnalysis(
            make_information(),
            "Inventory data was published.",
            market_direction=" BULLISH ",
            confidence_score=85,
            reasoning_details=(" Inventory declined ", "Demand improved"),
        )

        self.assertEqual(analysis.market_direction, "bullish")
        self.assertEqual(analysis.confidence_score, 85)
        self.assertEqual(
            analysis.reasoning_details,
            ("Inventory declined", "Demand improved"),
        )

    def test_rejects_empty_summary(self) -> None:
        with self.assertRaises(ValueError):
            MarketAnalysis(make_information(), "   ")

    def test_rejects_invalid_market_information(self) -> None:
        with self.assertRaises(TypeError):
            MarketAnalysis("not information", "Summary")

    def test_rejects_invalid_rich_analysis_fields(self) -> None:
        invalid_fields = (
            {"market_direction": "sideways"},
            {"confidence_score": -1},
            {"confidence_score": 101},
            {"reasoning_details": (" ",)},
        )
        for fields in invalid_fields:
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):
                    MarketAnalysis(make_information(), "Summary", **fields)


if __name__ == "__main__":
    unittest.main()
