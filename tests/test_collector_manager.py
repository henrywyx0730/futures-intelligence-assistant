"""Tests for collector orchestration."""

from datetime import datetime, timezone
import unittest

from futures_intelligence.collectors.base import BaseCollector
from futures_intelligence.models import MarketInformation
from futures_intelligence.pipeline.collector_manager import CollectorManager


class StaticCollector(BaseCollector):
    """Collector with fixed results for orchestration tests."""

    def __init__(self, items: list[MarketInformation]) -> None:
        self.items = items

    def collect(self) -> list[MarketInformation]:
        return self.items


class FailingCollector(BaseCollector):
    """Collector that fails during collection."""

    def collect(self) -> list[MarketInformation]:
        raise RuntimeError("source unavailable")


def make_information(title: str) -> MarketInformation:
    """Create a normalized item for an orchestration test."""
    return MarketInformation(
        title=title,
        source="Test Source",
        source_type="test",
        published_time=datetime(2026, 7, 15, tzinfo=timezone.utc),
        content="Test content",
    )


class CollectorManagerTests(unittest.TestCase):
    """Validate collector orchestration behavior."""

    def test_combines_multiple_collectors(self) -> None:
        manager = CollectorManager(
            [
                StaticCollector([make_information("First")]),
                StaticCollector([make_information("Second")]),
            ]
        )

        self.assertEqual(
            [item.title for item in manager.collect()], ["First", "Second"]
        )

    def test_failed_collector_does_not_stop_pipeline(self) -> None:
        manager = CollectorManager(
            [FailingCollector(), StaticCollector([make_information("Available")])]
        )

        with self.assertLogs(
            "futures_intelligence.pipeline.collector_manager", level="ERROR"
        ):
            items = manager.collect()

        self.assertEqual([item.title for item in items], ["Available"])

    def test_empty_collector_list_returns_empty_list(self) -> None:
        self.assertEqual(CollectorManager([]).collect(), [])


if __name__ == "__main__":
    unittest.main()
