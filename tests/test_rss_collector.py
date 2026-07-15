"""Tests for RSS collection and normalization."""

from pathlib import Path
import unittest

from futures_intelligence.collectors.rss import RSSCollector


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"


class RSSCollectorTests(unittest.TestCase):
    """Validate RSS parsing behavior without external network access."""

    def test_parses_local_rss_fixture(self) -> None:
        collector = RSSCollector((FIXTURE_DIRECTORY / "sample_rss.xml").as_uri())

        items = collector.collect()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Oil inventory update")
        self.assertEqual(items[0].source, "Example Market News")
        self.assertEqual(items[0].source_type, "rss")
        self.assertEqual(items[0].url, "https://example.com/oil-inventory")

    def test_returns_empty_list_for_empty_feed(self) -> None:
        collector = RSSCollector((FIXTURE_DIRECTORY / "empty_rss.xml").as_uri())

        self.assertEqual(collector.collect(), [])

    def test_returns_empty_list_for_invalid_rss(self) -> None:
        collector = RSSCollector((FIXTURE_DIRECTORY / "invalid_rss.xml").as_uri())

        self.assertEqual(collector.collect(), [])


if __name__ == "__main__":
    unittest.main()
