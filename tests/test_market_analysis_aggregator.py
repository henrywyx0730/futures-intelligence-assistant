"""Tests for deterministic market-analysis aggregation."""

from datetime import datetime, timezone
import unittest

from futures_intelligence.analyst import MarketAnalysisAggregator
from futures_intelligence.models import MarketAnalysis, MarketInformation


def make_analysis(
    direction: str,
    confidence_score: int,
    reasoning_details: tuple[str, ...],
) -> MarketAnalysis:
    """Create an analysis with the requested aggregate inputs."""
    information = MarketInformation(
        title="Market update",
        source="Test Source",
        source_type="test",
        published_time=datetime(2026, 7, 19, tzinfo=timezone.utc),
        content="Test content.",
    )
    return MarketAnalysis(
        information,
        "Summary.",
        market_direction=direction,
        confidence_score=confidence_score,
        reasoning_details=reasoning_details,
    )


class MarketAnalysisAggregatorTests(unittest.TestCase):
    """Validate aggregated directional views and reasoning."""

    def setUp(self) -> None:
        self.aggregator = MarketAnalysisAggregator()

    def test_uses_confidence_weighted_direction_and_combined_reasoning(self) -> None:
        view = self.aggregator.aggregate(
            [
                make_analysis("bullish", 80, ("Shared signal.", "Bullish signal.")),
                make_analysis("bearish", 70, ("Shared signal.", "Bearish signal.")),
                make_analysis("neutral", 60, ("Neutral context.",)),
            ]
        )

        self.assertEqual(view.overall_market_direction, "bullish")
        self.assertEqual(view.aggregated_confidence_score, 70)
        self.assertEqual(
            view.reasoning_details,
            (
                "Shared signal.",
                "Bullish signal.",
                "Bearish signal.",
                "Neutral context.",
            ),
        )
        self.assertEqual(view.analysis_count, 3)

    def test_returns_neutral_view_for_tied_directional_weight(self) -> None:
        view = self.aggregator.aggregate(
            [
                make_analysis("bullish", 75, ("Positive evidence.",)),
                make_analysis("bearish", 75, ("Negative evidence.",)),
            ]
        )

        self.assertEqual(view.overall_market_direction, "neutral")
        self.assertEqual(view.aggregated_confidence_score, 75)

    def test_returns_empty_neutral_view(self) -> None:
        view = self.aggregator.aggregate([])

        self.assertEqual(view.overall_market_direction, "neutral")
        self.assertEqual(view.aggregated_confidence_score, 0)
        self.assertEqual(
            view.reasoning_details, ("No analyses available for aggregation.",)
        )
        self.assertEqual(view.analysis_count, 0)

    def test_rejects_non_analysis_values(self) -> None:
        with self.assertRaises(TypeError):
            self.aggregator.aggregate(["not an analysis"])  # type: ignore[list-item]


if __name__ == "__main__":
    unittest.main()
