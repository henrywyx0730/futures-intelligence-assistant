"""Tests for local official-data collection."""

import json
from pathlib import Path
import tempfile
import unittest

from futures_intelligence.collectors.official_data import OfficialDataCollector


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"


class OfficialDataCollectorTests(unittest.TestCase):
    """Validate JSON official-data normalization."""

    def test_collects_json_records_with_record_metadata(self) -> None:
        collector = OfficialDataCollector(
            FIXTURE_DIRECTORY / "sample_official_data.json",
            source="Official Statistics Office",
            category=("configured",),
            reliability_score=3,
        )

        items = collector.collect()

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.title, "Weekly Petroleum Status Report")
        self.assertEqual(item.source, "Official Statistics Office")
        self.assertEqual(item.source_type, "official_data")
        self.assertEqual(item.published_time.isoformat(), "2026-07-18T09:30:00+00:00")
        self.assertEqual(
            item.content,
            "Commercial crude oil inventories decreased by 2.1 million barrels.",
        )
        self.assertEqual(item.category, ("energy", "official_data"))
        self.assertEqual(item.commodities, ("crude_oil",))
        self.assertEqual(item.regions, ("United States",))
        self.assertEqual(item.importance, "high")
        self.assertEqual(item.reliability_score, 5)
        self.assertEqual(item.url, "https://example.gov/petroleum-status")
        self.assertEqual(
            item.metadata,
            {"series_id": "WCESTUS1", "unit": "million barrels"},
        )

    def test_uses_configured_metadata_when_record_omits_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            content_path = Path(directory) / "official_data.json"
            content_path.write_text(
                json.dumps(
                    [
                        {
                            "title": "Economic Release",
                            "published_time": "2026-07-18T10:00:00+00:00",
                            "content": "Official economic data release.",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            collector = OfficialDataCollector(
                content_path,
                source="Official Statistics Office",
                category=("macro",),
                commodities=("gold",),
                regions=("global",),
                reliability_score=4,
            )

            item = collector.collect()[0]

            self.assertEqual(item.category, ("macro",))
            self.assertEqual(item.commodities, ("gold",))
            self.assertEqual(item.regions, ("global",))
            self.assertEqual(item.reliability_score, 4)

    def test_returns_empty_list_for_missing_json_file(self) -> None:
        collector = OfficialDataCollector(
            FIXTURE_DIRECTORY / "missing_official_data.json",
            source="Official Statistics Office",
        )

        self.assertEqual(collector.collect(), [])

    def test_returns_empty_list_for_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            content_path = Path(directory) / "official_data.json"
            content_path.write_text("not valid json", encoding="utf-8")
            collector = OfficialDataCollector(
                content_path,
                source="Official Statistics Office",
            )

            self.assertEqual(collector.collect(), [])


if __name__ == "__main__":
    unittest.main()
