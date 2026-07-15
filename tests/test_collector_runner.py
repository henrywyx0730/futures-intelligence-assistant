"""Tests for configuration-driven collector execution."""

from pathlib import Path
import unittest

from futures_intelligence.pipeline.collector_runner import CollectorRunner


SAMPLE_RSS_URL = (Path(__file__).parent / "fixtures" / "sample_rss.xml").as_uri()


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
