"""Tests for deterministic observed market-price movement detection."""

from datetime import datetime, timezone
import unittest

from futures_intelligence.analyst.commodity_matcher import CommodityMatcher
from futures_intelligence.analyst.market_movement import MarketMovementDetector
from futures_intelligence.models import MarketInformation


def make_information(title: str, content: str = "") -> MarketInformation:
    """Create title/content-only market information for movement detection."""
    return MarketInformation(
        title=title,
        source="Test Source",
        source_type="test",
        published_time=datetime(2026, 7, 20, tzinfo=timezone.utc),
        content=content or "Market update.",
    )


class MarketMovementDetectorTests(unittest.TestCase):
    """Validate observed price movement before fundamental interpretation."""

    def setUp(self) -> None:
        self.matcher = CommodityMatcher()
        self.detector = MarketMovementDetector()

    def detect(self, title: str, content: str = "") -> object:
        """Detect movement with the same article-level commodity context as analysis."""
        information = make_information(title, content)
        return self.detector.detect(information, self.matcher.match(information))

    def test_detects_bullish_observed_price_movements(self) -> None:
        cases = (
            "WTI Futures is up 2.39%",
            "Oil prices jumped 2%",
            "Gold opens ₹733 higher",
            "Silver gains ₹2,796",
            "Crude settles higher",
            "GOLD—RALLIED!",
        )

        for title in cases:
            with self.subTest(title=title):
                signal = self.detect(title)
                self.assertEqual(signal.direction, "bullish")
                self.assertGreater(signal.priority, 0)

    def test_detects_bearish_observed_price_movements(self) -> None:
        cases = (
            "Oil Futures Settle Lower",
            "Gold falls 2%",
            "Copper closes lower",
            "Wheat futures decline",
        )

        for title in cases:
            with self.subTest(title=title):
                self.assertEqual(self.detect(title).direction, "bearish")

    def test_rejects_bare_levels_and_non_price_metric_changes(self) -> None:
        cases = (
            "Brent trades above $90",
            "Gold at $2,500",
            "WTI holds near $85",
            "Oil production is up 2%",
            "Crude inventories are down 5%",
            "Refinery throughput rose 3%",
            "Interest rates rose 25 basis points",
            "Geopolitical risk increased",
        )

        for title in cases:
            with self.subTest(title=title):
                signal = self.detect(title)
                self.assertEqual(signal.direction, "neutral")
                self.assertEqual(signal.priority, 0)

    def test_settlement_and_closing_override_earlier_intraday_movement(self) -> None:
        self.assertEqual(
            self.detect("Oil rose 2% before settling lower").direction,
            "bearish",
        )
        self.assertEqual(
            self.detect("Oil fell early but closed higher").direction,
            "bullish",
        )

    def test_equal_priority_conflicting_movements_are_neutral(self) -> None:
        signal = self.detect("Gold gains while silver falls")

        self.assertEqual(signal.direction, "neutral")
        self.assertGreater(signal.priority, 0)
        self.assertIn("Conflicting", signal.evidence)

    def test_keeps_price_and_inventory_context_separate(self) -> None:
        signal = self.detect("Oil rises as inventories fall")

        self.assertEqual(signal.direction, "bullish")
        self.assertIn("Oil rises", signal.evidence)


if __name__ == "__main__":
    unittest.main()
