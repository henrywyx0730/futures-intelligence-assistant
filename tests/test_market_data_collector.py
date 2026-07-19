"""Tests for local market-data collection."""

import json
from pathlib import Path
import tempfile
import unittest

from futures_intelligence.collectors.market_data import MarketDataCollector


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"


class MarketDataCollectorTests(unittest.TestCase):
    """Validate local JSON market-data normalization."""

    def test_collects_quote_fields_into_metadata(self) -> None:
        collector = MarketDataCollector(
            FIXTURE_DIRECTORY / "sample_market_data.json",
            source="Local Futures Quotes",
            category=("futures",),
            commodities=("crude_oil",),
            reliability_score=4,
        )

        items = collector.collect()

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.title, "Market data: CL=F")
        self.assertEqual(item.source, "Local Futures Quotes")
        self.assertEqual(item.source_type, "market_data")
        self.assertEqual(item.published_time.isoformat(), "2026-07-18T09:45:00+00:00")
        self.assertEqual(item.category, ("futures",))
        self.assertEqual(item.commodities, ("crude_oil",))
        self.assertEqual(item.reliability_score, 4)
        self.assertEqual(
            item.metadata,
            {
                "symbol": "CL=F",
                "price": 81.25,
                "price_change": -0.75,
                "volume": 182345,
                "open_interest": 247891,
                "timestamp": "2026-07-18T09:45:00+00:00",
            },
        )

    def test_uses_file_time_when_timestamp_is_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            content_path = Path(directory) / "market_data.json"
            content_path.write_text(
                json.dumps([{"symbol": "GC=F", "price": 2400.5}]),
                encoding="utf-8",
            )
            collector = MarketDataCollector(content_path, source="Local Quotes")

            item = collector.collect()[0]

            self.assertIsNotNone(item.published_time.tzinfo)
            self.assertNotIn("timestamp", item.metadata)
            self.assertEqual(item.metadata, {"symbol": "GC=F", "price": 2400.5})

    def test_returns_empty_list_for_invalid_records_or_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            content_path = Path(directory) / "market_data.json"
            content_path.write_text(
                json.dumps([{"symbol": "CL=F", "price": "not-a-number"}]),
                encoding="utf-8",
            )
            collector = MarketDataCollector(content_path, source="Local Quotes")

            self.assertEqual(collector.collect(), [])

            content_path.write_text("not valid json", encoding="utf-8")
            self.assertEqual(collector.collect(), [])


if __name__ == "__main__":
    unittest.main()
