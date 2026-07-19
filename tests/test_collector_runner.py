"""Tests for configuration-driven collector execution."""

from pathlib import Path
import unittest

from futures_intelligence.pipeline.collector_runner import CollectorRunner


SAMPLE_RSS_URL = (Path(__file__).parent / "fixtures" / "sample_rss.xml").as_uri()
SAMPLE_RESEARCH_REPORT_PATH = (
    Path(__file__).parents[1]
    / "data"
    / "research_reports"
    / "sample_crude_oil_outlook.txt"
)


class CollectorRunnerTests(unittest.TestCase):
    """Validate collector creation and execution from source configuration."""

    def test_enabled_rss_source_creates_information(self) -> None:
        runner = CollectorRunner(
            [
                {
                    "name": "Configured RSS",
                    "source_type": "rss",
                    "enabled": True,
                    "url": SAMPLE_RSS_URL,
                }
            ]
        )

        items = runner.run()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source, "Configured RSS")

    def test_disabled_source_is_ignored(self) -> None:
        runner = CollectorRunner(
            [
                {
                    "source_type": "rss",
                    "enabled": False,
                    "url": SAMPLE_RSS_URL,
                }
            ]
        )

        self.assertEqual(runner.run(), [])

    def test_enabled_local_research_report_creates_information(self) -> None:
        runner = CollectorRunner(
            [
                {
                    "name": "Sample Local Research Desk",
                    "source_type": "research_report",
                    "enabled": True,
                    "content_path": str(SAMPLE_RESEARCH_REPORT_PATH),
                    "title": "Sample Crude Oil Outlook",
                    "category": ["energy", "macro"],
                    "commodities": ["crude_oil"],
                    "regions": ["global"],
                    "reliability_score": 4,
                }
            ]
        )

        items = runner.run()

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.source, "Sample Local Research Desk")
        self.assertEqual(item.title, "Sample Crude Oil Outlook")
        self.assertIn("Crude oil inventories declined", item.content)
        self.assertEqual(item.category, ("energy", "macro"))
        self.assertEqual(item.commodities, ("crude_oil",))
        self.assertEqual(item.regions, ("global",))
        self.assertEqual(item.reliability_score, 4)

    def test_invalid_source_type_is_logged_and_skipped(self) -> None:
        runner = CollectorRunner(
            [{"source_type": "unsupported", "enabled": True}]
        )

        with self.assertLogs(
            "futures_intelligence.pipeline.collector_runner", level="WARNING"
        ):
            self.assertEqual(runner.run(), [])


if __name__ == "__main__":
    unittest.main()
