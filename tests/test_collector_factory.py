"""Tests for collector creation from source configuration."""

import unittest

from futures_intelligence.collectors.factory import CollectorFactory
from futures_intelligence.collectors.rss import RSSCollector


class CollectorFactoryTests(unittest.TestCase):
    """Validate supported collector construction."""

    def test_creates_rss_collector(self) -> None:
        collector = CollectorFactory.create(
            {
                "name": "Example News",
                "source_type": "rss",
                "enabled": True,
                "url": "https://example.com/feed.xml",
                "category": ["energy"],
                "commodities": ["crude_oil"],
                "regions": ["United States"],
                "reliability_score": 5,
            }
        )

        self.assertIsInstance(collector, RSSCollector)
        assert isinstance(collector, RSSCollector)
        self.assertEqual(collector.rss_url, "https://example.com/feed.xml")
        self.assertEqual(collector.source, "Example News")
        self.assertEqual(collector.category, ("energy",))
        self.assertEqual(collector.commodities, ("crude_oil",))
        self.assertEqual(collector.regions, ("United States",))
        self.assertEqual(collector.reliability_score, 5)

    def test_skips_disabled_source(self) -> None:
        collector = CollectorFactory.create(
            {
                "source_type": "rss",
                "enabled": False,
                "url": "https://example.com/feed.xml",
            }
        )

        self.assertIsNone(collector)

    def test_rejects_unsupported_source_type(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported source type"):
            CollectorFactory.create(
                {"source_type": "financial_news", "enabled": True}
            )


if __name__ == "__main__":
    unittest.main()
