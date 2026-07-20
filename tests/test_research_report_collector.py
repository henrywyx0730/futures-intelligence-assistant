"""Tests for local research-report collection."""

from datetime import datetime, timezone
from pathlib import Path
import unittest

from futures_intelligence.collectors.research_report import ResearchReportCollector
from futures_intelligence.fetchers import FetchedResearchReport, HuataiFetchResult


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"
PUBLISHED_TIME = datetime(2026, 7, 18, tzinfo=timezone.utc)


class ResearchReportCollectorTests(unittest.TestCase):
    """Validate local text and HTML research-report normalization."""

    def test_collects_local_text_report_with_metadata(self) -> None:
        collector = ResearchReportCollector(
            FIXTURE_DIRECTORY / "sample_research_report.txt",
            source="Research Desk",
            title="Energy outlook",
            published_time=PUBLISHED_TIME,
            category=("energy",),
            commodities=("crude_oil",),
            reliability_score=5,
        )

        items = collector.collect()

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.title, "Energy outlook")
        self.assertEqual(item.source, "Research Desk")
        self.assertEqual(item.source_type, "research_report")
        self.assertEqual(item.published_time, PUBLISHED_TIME)
        self.assertEqual(
            item.content,
            "Crude oil inventories declined while refinery demand improved. "
            "Supply risks remain elevated.",
        )
        self.assertEqual(item.category, ("energy",))
        self.assertEqual(item.commodities, ("crude_oil",))
        self.assertEqual(item.reliability_score, 5)
        self.assertTrue(item.url.startswith("file://"))

    def test_collects_visible_text_from_local_html_report(self) -> None:
        collector = ResearchReportCollector(
            FIXTURE_DIRECTORY / "sample_research_report.html",
            source="Metals Desk",
            published_time=PUBLISHED_TIME,
        )

        item = collector.collect()[0]

        self.assertEqual(item.title, "Sample Research Report")
        self.assertEqual(
            item.content,
            "Metals outlook Gold outlook Gold demand remains resilient.",
        )
        self.assertNotIn("internalOnly", item.content)
        self.assertNotIn("color: black", item.content)

    def test_returns_empty_list_for_missing_local_report(self) -> None:
        collector = ResearchReportCollector(
            FIXTURE_DIRECTORY / "missing_report.txt",
            source="Research Desk",
        )

        self.assertEqual(collector.collect(), [])

    def test_normalizes_structured_huatai_reports_without_source_scope_commodities(self) -> None:
        report = FetchedResearchReport(
            title="Huatai outlook",
            published_time=PUBLISHED_TIME,
            content="Abstract and core viewpoints.",
            url="https://htfc.com/main/yjzx/ssrdph/report.shtml",
            report_type="Strategy",
            author="Analyst",
        )

        class StructuredFetcher:
            def fetch_reports(self) -> HuataiFetchResult:
                return HuataiFetchResult(1, (report.url,), (report,))

        collector = ResearchReportCollector(
            None,
            source="Huatai Futures",
            category=("macro",),
            commodities=("crude_oil",),
            regions=("China",),
            reliability_score=5,
            structured_fetcher=StructuredFetcher(),
        )

        item = collector.collect()[0]

        self.assertEqual(item.source, "Huatai Futures")
        self.assertEqual(item.published_time, PUBLISHED_TIME)
        self.assertEqual(item.url, report.url)
        self.assertEqual(item.commodities, ())
        self.assertEqual(item.metadata, {"report_type": "Strategy", "author": "Analyst"})


if __name__ == "__main__":
    unittest.main()
