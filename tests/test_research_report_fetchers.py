"""Tests for research-report content fetchers."""

from pathlib import Path
import unittest

from futures_intelligence.fetchers import (
    LocalFileResearchReportFetcher,
    ResearchReportFetcher,
)


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"


class ResearchReportFetcherTests(unittest.TestCase):
    """Validate the local research-report fetching foundation."""

    def test_abstract_fetcher_cannot_be_instantiated(self) -> None:
        with self.assertRaises(TypeError):
            ResearchReportFetcher()

    def test_reads_configured_local_content_path(self) -> None:
        fetcher = LocalFileResearchReportFetcher(
            FIXTURE_DIRECTORY / "sample_research_report.txt"
        )

        content = fetcher.fetch()

        self.assertIsNotNone(content)
        assert content is not None
        self.assertIn("Crude oil inventories declined", content)

    def test_returns_none_when_local_content_path_is_missing(self) -> None:
        fetcher = LocalFileResearchReportFetcher(
            FIXTURE_DIRECTORY / "missing_report.txt"
        )

        self.assertIsNone(fetcher.fetch())


if __name__ == "__main__":
    unittest.main()
