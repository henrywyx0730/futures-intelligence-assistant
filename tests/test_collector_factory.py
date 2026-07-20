"""Tests for collector creation from source configuration."""

from pathlib import Path
import unittest

from futures_intelligence.collectors.factory import CollectorFactory
from futures_intelligence.collectors.market_data import MarketDataCollector
from futures_intelligence.collectors.official_data import OfficialDataCollector
from futures_intelligence.collectors.research_report import ResearchReportCollector
from futures_intelligence.collectors.rss import RSSCollector
from futures_intelligence.fetchers import HuataiFuturesReportFetcher


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"


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

    def test_creates_research_report_collector(self) -> None:
        collector = CollectorFactory.create(
            {
                "name": "Research Desk",
                "source_type": "research_report",
                "enabled": True,
                "content_path": str(
                    FIXTURE_DIRECTORY / "sample_research_report.txt"
                ),
                "category": ["energy"],
                "commodities": ["crude_oil"],
                "reliability_score": 5,
            }
        )

        self.assertIsInstance(collector, ResearchReportCollector)
        assert isinstance(collector, ResearchReportCollector)
        self.assertEqual(collector.source, "Research Desk")
        self.assertEqual(collector.category, ("energy",))
        self.assertEqual(collector.commodities, ("crude_oil",))
        self.assertEqual(collector.reliability_score, 5)

    def test_rejects_research_report_without_local_content_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "local content_path"):
            CollectorFactory.create(
                {
                    "source_type": "research_report",
                    "enabled": True,
                    "url": "https://example.com/report.html",
                }
            )

    def test_creates_disabled_by_default_huatai_collector_when_explicitly_enabled(self) -> None:
        collector = CollectorFactory.create(
            {
                "name": "Huatai Futures",
                "source_type": "research_report",
                "provider": "huatai_futures",
                "enabled": True,
                "url": "https://htfc.com/main/yjzx/ssrdph/index.shtml",
                "max_reports": 3,
                "category": ["macro"],
                "regions": ["China"],
                "reliability_score": 5,
            }
        )

        self.assertIsInstance(collector, ResearchReportCollector)
        assert isinstance(collector, ResearchReportCollector)
        self.assertIsInstance(collector.structured_fetcher, HuataiFuturesReportFetcher)
        self.assertEqual(collector.commodities, ())

    def test_creates_official_data_collector(self) -> None:
        collector = CollectorFactory.create(
            {
                "name": "Official Statistics Office",
                "source_type": "official_data",
                "enabled": True,
                "content_path": str(FIXTURE_DIRECTORY / "sample_official_data.json"),
                "category": ["macro"],
                "regions": ["United States"],
                "reliability_score": 5,
            }
        )

        self.assertIsInstance(collector, OfficialDataCollector)
        assert isinstance(collector, OfficialDataCollector)
        self.assertEqual(collector.source, "Official Statistics Office")
        self.assertEqual(collector.category, ("macro",))
        self.assertEqual(collector.regions, ("United States",))
        self.assertEqual(collector.reliability_score, 5)

    def test_rejects_official_data_without_local_json_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "local content_path"):
            CollectorFactory.create(
                {
                    "source_type": "official_data",
                    "enabled": True,
                    "content_path": "https://example.com/data.json",
                }
            )

    def test_creates_market_data_collector(self) -> None:
        collector = CollectorFactory.create(
            {
                "name": "Local Futures Quotes",
                "source_type": "market_data",
                "enabled": True,
                "content_path": str(FIXTURE_DIRECTORY / "sample_market_data.json"),
                "category": ["futures"],
                "commodities": ["crude_oil"],
                "reliability_score": 4,
            }
        )

        self.assertIsInstance(collector, MarketDataCollector)
        assert isinstance(collector, MarketDataCollector)
        self.assertEqual(collector.source, "Local Futures Quotes")
        self.assertEqual(collector.category, ("futures",))
        self.assertEqual(collector.commodities, ("crude_oil",))
        self.assertEqual(collector.reliability_score, 4)

    def test_rejects_market_data_without_local_json_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "local content_path"):
            CollectorFactory.create(
                {
                    "source_type": "market_data",
                    "enabled": True,
                    "content_path": "https://example.com/quotes.json",
                }
            )

    def test_rejects_unsupported_source_type(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported source type"):
            CollectorFactory.create(
                {"source_type": "financial_news", "enabled": True}
            )


if __name__ == "__main__":
    unittest.main()
