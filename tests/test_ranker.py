"""Tests for deterministic market-information ranking."""

from datetime import datetime, timedelta, timezone
import unittest

from futures_intelligence.models import MarketInformation
from futures_intelligence.processing.ranker import InformationRanker


REFERENCE_TIME = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)


def make_information(
    title: str,
    *,
    reliability_score: int = 3,
    category: tuple[str, ...] = (),
    commodities: tuple[str, ...] = (),
    published_time: datetime = REFERENCE_TIME,
) -> MarketInformation:
    """Create a normalized item with ranking-specific values."""
    return MarketInformation(
        title=title,
        source="Test Source",
        source_type="test",
        published_time=published_time,
        content="Test content",
        category=category,
        commodities=commodities,
        reliability_score=reliability_score,
    )


class InformationRankerTests(unittest.TestCase):
    """Validate reliability, relevance, freshness, and object preservation."""

    def setUp(self) -> None:
        self.ranker = InformationRanker(
            relevant_categories=("energy",),
            relevant_commodities=("crude_oil",),
            reference_time=REFERENCE_TIME,
        )

    def test_ranks_by_reliability_and_relevance(self) -> None:
        low_relevance = make_information("General", reliability_score=4)
        relevant = make_information(
            "Oil",
            reliability_score=4,
            category=("energy",),
            commodities=("crude_oil",),
        )

        self.assertEqual(self.ranker.rank([low_relevance, relevant]), [relevant, low_relevance])

    def test_ranks_fresher_items_higher_when_other_scores_match(self) -> None:
        older = make_information(
            "Older", published_time=REFERENCE_TIME - timedelta(hours=30)
        )
        fresher = make_information(
            "Fresher", published_time=REFERENCE_TIME - timedelta(hours=1)
        )

        self.assertEqual(self.ranker.rank([older, fresher]), [fresher, older])

    def test_preserves_original_objects_and_input_list(self) -> None:
        first = make_information("First", reliability_score=2)
        second = make_information("Second", reliability_score=5)
        information = [first, second]

        ranked = self.ranker.rank(information)

        self.assertEqual(information, [first, second])
        self.assertIs(ranked[0], second)
        self.assertIs(ranked[1], first)

    def test_returns_empty_list_for_empty_input(self) -> None:
        self.assertEqual(self.ranker.rank([]), [])


if __name__ == "__main__":
    unittest.main()
