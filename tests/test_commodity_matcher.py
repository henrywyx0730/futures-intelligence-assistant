"""Tests for deterministic article-level commodity matching."""

from datetime import datetime, timezone
import unittest

from futures_intelligence.analyst.commodity_matcher import CommodityMatcher
from futures_intelligence.models import MarketInformation


def make_information(title: str, content: str, **fields: object) -> MarketInformation:
    """Create normalized information for article-level commodity matching."""
    return MarketInformation(
        title=title,
        source="Test Source",
        source_type="test",
        published_time=datetime(2026, 7, 20, tzinfo=timezone.utc),
        content=content,
        **fields,
    )


class CommodityMatcherTests(unittest.TestCase):
    """Validate immutable, knowledge-ordered article-level commodity matches."""

    def setUp(self) -> None:
        self.matcher = CommodityMatcher()

    def test_returns_configured_ordered_matches_from_title_and_content(self) -> None:
        information = make_information(
            "Gold and crude oil outlook", "Copper inventory data was released."
        )

        matches = self.matcher.match(information)

        self.assertEqual(
            [(match.commodity_key, match.commodity_label) for match in matches],
            [
                ("crude_oil", "Crude Oil"),
                ("copper", "Copper"),
                ("gold", "Gold"),
            ],
        )
        self.assertEqual(
            self.matcher.commodity_order,
            tuple(match.commodity_key for match in self.matcher.commodity_ordered_matches),
        )

    def test_ignores_source_scope_commodities_without_article_evidence(self) -> None:
        information = make_information(
            "Central bank statement",
            "The policy statement was published.",
            commodities=("crude_oil", "gold", "wheat"),
        )

        self.assertEqual(self.matcher.match(information), ())

    def test_preserves_ambiguous_alias_exclusions(self) -> None:
        information = make_information("Soybean oil update", "Agricultural products.")

        self.assertEqual(self.matcher.match(information), ())


if __name__ == "__main__":
    unittest.main()
