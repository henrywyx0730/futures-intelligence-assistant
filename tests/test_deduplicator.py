"""Tests for market-information deduplication."""

from datetime import datetime, timezone
import unittest

from futures_intelligence.models import MarketInformation
from futures_intelligence.processing.deduplicator import InformationDeduplicator


def make_information(title: str, source: str = "Source") -> MarketInformation:
    """Create a valid market-information item for testing."""
    return MarketInformation(
        title=title,
        source=source,
        source_type="test",
        published_time=datetime(2026, 7, 15, tzinfo=timezone.utc),
        content="Test content",
    )


class InformationDeduplicatorTests(unittest.TestCase):
    """Validate market-information cleanup behavior."""

    def setUp(self) -> None:
        self.deduplicator = InformationDeduplicator()

    def test_removes_duplicate_titles(self) -> None:
        first = make_information("Oil update", "Source A")
        duplicate = make_information("Oil update", "Source B")

        result = self.deduplicator.deduplicate([first, duplicate])

        self.assertEqual(result, [first])

    def test_preserves_original_order(self) -> None:
        first = make_information("First")
        duplicate = make_information("First", "Another Source")
        second = make_information("Second")

        result = self.deduplicator.deduplicate([first, duplicate, second])

        self.assertEqual(result, [first, second])

    def test_removes_empty_content(self) -> None:
        empty_content = make_information("Empty content")
        empty_content.content = "   "
        valid = make_information("Valid content")

        result = self.deduplicator.deduplicate([empty_content, valid])

        self.assertEqual(result, [valid])

    def test_returns_empty_list_for_empty_input(self) -> None:
        self.assertEqual(self.deduplicator.deduplicate([]), [])


if __name__ == "__main__":
    unittest.main()
