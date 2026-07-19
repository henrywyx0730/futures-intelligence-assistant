"""Tests for deterministic market-intelligence trend-change detection."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from futures_intelligence.processing import MarketTrendChangeDetector


class MarketTrendChangeDetectorTests(unittest.TestCase):
    """Validate comparisons of persisted aggregate market views."""

    def setUp(self) -> None:
        self.detector = MarketTrendChangeDetector()

    def test_detects_direction_and_confidence_changes(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "date": "2026-07-18",
                            "overall_direction": "bullish",
                            "confidence_score": 72,
                        },
                        {
                            "date": "2026-07-19",
                            "overall_direction": "bearish",
                            "confidence_score": 58,
                        },
                    ]
                ),
                encoding="utf-8",
            )

            change = self.detector.detect(path)

            self.assertEqual(change.previous_date, "2026-07-18")
            self.assertEqual(change.latest_date, "2026-07-19")
            self.assertTrue(change.direction_changed)
            self.assertEqual(change.previous_direction, "bullish")
            self.assertEqual(change.latest_direction, "bearish")
            self.assertTrue(change.confidence_changed)
            self.assertEqual(change.confidence_change, -14)

    def test_reports_no_change_for_matching_latest_views(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "date": "2026-07-18",
                            "overall_direction": "neutral",
                            "confidence_score": 50,
                        },
                        {
                            "date": "2026-07-19",
                            "overall_direction": "neutral",
                            "confidence_score": 50,
                        },
                    ]
                ),
                encoding="utf-8",
            )

            change = self.detector.detect(path)

            self.assertFalse(change.direction_changed)
            self.assertFalse(change.confidence_changed)
            self.assertEqual(change.confidence_change, 0)

    def test_returns_empty_change_for_missing_or_invalid_history(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"

            self.assertIsNone(self.detector.detect(path).latest_date)

            path.write_text('[{"date": "2026-07-19"}]', encoding="utf-8")
            self.assertIsNone(self.detector.detect(path).latest_date)


if __name__ == "__main__":
    unittest.main()
