"""Tests for local aggregated market-intelligence history storage."""

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from futures_intelligence.analyst import AggregatedMarketView
from futures_intelligence.models import MarketInformation
from futures_intelligence.utils.market_history import append_market_intelligence_history


def make_information(
    commodities: tuple[str, ...], categories: tuple[str, ...]
) -> MarketInformation:
    """Create source information for history tests."""
    return MarketInformation(
        title="Market update",
        source="Test Source",
        source_type="test",
        published_time=datetime(2026, 7, 19, tzinfo=timezone.utc),
        content="Test content.",
        commodities=commodities,
        category=categories,
    )


class MarketIntelligenceHistoryTests(unittest.TestCase):
    """Validate append-only local JSON market-view history."""

    def test_appends_aggregated_view_with_source_context(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "data" / "history.json"
            view = AggregatedMarketView(
                overall_market_direction="bullish",
                aggregated_confidence_score=78,
                reasoning_details=("Demand improved.",),
                analysis_count=2,
            )

            entry = append_market_intelligence_history(
                path,
                view,
                [
                    make_information(("gold", "crude_oil"), ("metals",)),
                    make_information(("crude_oil",), ("energy", "metals")),
                ],
                timestamp=datetime(2026, 7, 19, 8, tzinfo=timezone.utc),
            )

            self.assertEqual(entry.date, "2026-07-19")
            self.assertEqual(entry.commodities, ("gold", "crude_oil"))
            self.assertEqual(entry.categories, ("metals", "energy"))
            self.assertEqual(entry.overall_direction, "bullish")
            self.assertEqual(entry.confidence_score, 78)
            self.assertEqual(
                json.loads(path.read_text()),
                [
                    {
                        "date": "2026-07-19",
                        "commodities": ["gold", "crude_oil"],
                        "categories": ["metals", "energy"],
                        "overall_direction": "bullish",
                        "confidence_score": 78,
                        "reasoning_details": ["Demand improved."],
                    }
                ],
            )

    def test_preserves_existing_history_entries(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            path.write_text('[{"date": "2026-07-18"}]', encoding="utf-8")
            view = AggregatedMarketView("neutral", 0, (), 0)

            append_market_intelligence_history(
                path,
                view,
                [],
                timestamp=datetime(2026, 7, 19, tzinfo=timezone.utc),
            )

            history = json.loads(path.read_text())
            self.assertEqual(len(history), 2)
            self.assertEqual(history[0], {"date": "2026-07-18"})
            self.assertEqual(history[1]["date"], "2026-07-19")


if __name__ == "__main__":
    unittest.main()
