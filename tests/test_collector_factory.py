"""Tests for collector creation from source configuration."""

from pathlib import Path
import unittest
from unittest.mock import patch

from futures_intelligence.collectors.factory import CollectorFactory
from futures_intelligence.collectors.huatai_futures_pdf import (
    HuataiFuturesPdfResearchReportCollector,
)
from futures_intelligence.collectors.market_data import MarketDataCollector
from futures_intelligence.collectors.official_data import OfficialDataCollector
from futures_intelligence.collectors.research_report import ResearchReportCollector
from futures_intelligence.collectors.research_report_pdf_adapter import (
    ResearchReportPDFMarketInformationAdapter,
)
from futures_intelligence.collectors.rss import RSSCollector
from futures_intelligence.fetchers import HuataiFuturesReportFetcher
from futures_intelligence.fetchers.huatai_pdf import (
    HuataiPdfDownloadLimits,
    HuataiPdfTextExtractor,
)


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"


HUATAI_PDF_SOURCE = {
    "name": "Huatai Futures",
    "source_type": "research_report",
    "provider": "huatai_futures",
    "collection_mode": "huatai_pdf_listing",
    "enabled": True,
    "url": "https://htfc.com/main/yjzx/ssrdph/index.shtml",
    "max_reports": 3,
    "pdf_extraction": {
        "socket_timeout_seconds": 10,
        "download_deadline_seconds": 30,
        "max_response_bytes": 20_971_520,
        "max_redirects": 3,
        "max_selected_pdfs": 3,
        "max_pages": 50,
        "max_content_stream_bytes_per_page": 8_388_608,
        "max_content_stream_bytes": 67_108_864,
        "max_extracted_characters_per_page": 20_000,
        "max_extracted_characters": 250_000,
        "parser_deadline_seconds": 20,
        "minimum_meaningful_characters": 20,
    },
    "category": ["macro", "energy"],
    "regions": ["China"],
    "reliability_score": 5,
}


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

    def test_creates_huatai_pdf_collector_for_the_exact_collection_mode(self) -> None:
        with (
            patch.object(
                HuataiFuturesReportFetcher,
                "discover_listing",
                side_effect=AssertionError("factory must not discover listings"),
            ) as discover_listing,
            patch.object(
                HuataiPdfTextExtractor,
                "extract",
                side_effect=AssertionError("factory must not extract PDFs"),
            ) as extract,
            patch.object(
                ResearchReportPDFMarketInformationAdapter,
                "to_market_information",
                side_effect=AssertionError("factory must not normalize reports"),
            ) as adapt,
            patch(
                "futures_intelligence.collectors.factory.HuataiPdfDownloadLimits",
                wraps=HuataiPdfDownloadLimits,
            ) as download_limits_factory,
        ):
            collector = CollectorFactory.create(HUATAI_PDF_SOURCE)

        self.assertIsInstance(collector, HuataiFuturesPdfResearchReportCollector)
        assert isinstance(collector, HuataiFuturesPdfResearchReportCollector)
        self.assertIsInstance(collector._listing_fetcher, HuataiFuturesReportFetcher)
        self.assertIsInstance(collector._pdf_extractor, HuataiPdfTextExtractor)
        self.assertIsInstance(collector._adapter, ResearchReportPDFMarketInformationAdapter)
        self.assertEqual(
            collector._source_metadata,
            {
                "source": "Huatai Futures",
                "provider": "huatai_futures",
                "category": ("macro", "energy"),
                "regions": ("China",),
                "reliability_score": 5,
            },
        )
        self.assertEqual(collector._max_selected_pdfs, 3)
        self.assertEqual(
            collector._pdf_extractor.download_limits.socket_timeout_seconds, 10
        )
        self.assertEqual(
            collector._pdf_extractor.download_limits.download_deadline_seconds, 30
        )
        self.assertEqual(
            collector._pdf_extractor.download_limits.max_response_bytes, 20_971_520
        )
        self.assertEqual(collector._pdf_extractor.download_limits.max_redirects, 3)
        download_limits_factory.assert_called_once()
        self.assertNotIn(
            "max_selected_pdfs",
            download_limits_factory.call_args.kwargs,
        )
        self.assertEqual(collector._pdf_extractor.parse_limits.max_pages, 50)
        self.assertEqual(
            collector._pdf_extractor.parse_limits.max_content_stream_bytes_per_page,
            8_388_608,
        )
        self.assertEqual(
            collector._pdf_extractor.parse_limits.max_content_stream_bytes,
            67_108_864,
        )
        self.assertEqual(
            collector._pdf_extractor.parse_limits.max_extracted_characters_per_page,
            20_000,
        )
        self.assertEqual(
            collector._pdf_extractor.parse_limits.max_extracted_characters, 250_000
        )
        self.assertEqual(
            collector._pdf_extractor.parse_limits.parser_deadline_seconds, 20
        )
        self.assertEqual(
            collector._pdf_extractor.parse_limits.minimum_meaningful_characters, 20
        )
        discover_listing.assert_not_called()
        extract.assert_not_called()
        adapt.assert_not_called()

    def test_rejects_huatai_provider_without_an_explicit_collection_mode(self) -> None:
        source = {key: value for key, value in HUATAI_PDF_SOURCE.items() if key != "collection_mode"}

        with self.assertRaisesRegex(ValueError, "collection_mode"):
            CollectorFactory.create(source)

    def test_rejects_huatai_provider_with_an_unsupported_collection_mode(self) -> None:
        source = {**HUATAI_PDF_SOURCE, "collection_mode": "legacy_html"}

        with self.assertRaisesRegex(ValueError, "legacy_html"):
            CollectorFactory.create(source)

    def test_rejects_huatai_pdf_mode_without_required_pdf_settings(self) -> None:
        for source in (
            {key: value for key, value in HUATAI_PDF_SOURCE.items() if key != "pdf_extraction"},
            {
                **HUATAI_PDF_SOURCE,
                "pdf_extraction": {
                    key: value
                    for key, value in HUATAI_PDF_SOURCE["pdf_extraction"].items()
                    if key != "max_selected_pdfs"
                },
            },
            {
                **HUATAI_PDF_SOURCE,
                "pdf_extraction": {
                    **HUATAI_PDF_SOURCE["pdf_extraction"],
                    "max_selected_pdfs": 0,
                },
            },
        ):
            with self.subTest(source=source):
                with self.assertRaisesRegex(ValueError, "pdf_extraction|max_selected_pdfs"):
                    CollectorFactory.create(source)

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
