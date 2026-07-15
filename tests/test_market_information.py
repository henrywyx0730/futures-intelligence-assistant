"""Tests for the normalized market-information model."""

import json
import unittest
from datetime import datetime, timezone

from futures_intelligence.models import MarketInformation


class MarketInformationTests(unittest.TestCase):
    """Validate normalization and safeguards for collected information."""

    def setUp(self) -> None:
        self.valid_fields = {
            "title": "EIA releases weekly petroleum report",
            "source": "EIA",
            "source_type": "official_data",
            "published_time": datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc),
            "content": "Weekly inventory data was published.",
        }

    def test_creates_valid_model(self) -> None:
        item = MarketInformation(
            **self.valid_fields,
            category=("energy",),
            commodities=("crude_oil",),
            regions=("United States",),
            importance="high",
            reliability_score=5,
            url="https://www.eia.gov",
        )

        self.assertEqual(item.source_type, "official_data")
        self.assertEqual(item.commodities, ("crude_oil",))

    def test_uses_default_values(self) -> None:
        item = MarketInformation(**self.valid_fields)

        self.assertEqual(item.category, ())
        self.assertEqual(item.commodities, ())
        self.assertEqual(item.regions, ())
        self.assertEqual(item.importance, "medium")
        self.assertEqual(item.reliability_score, 3)
        self.assertIsNone(item.url)

    def test_normalizes_whitespace(self) -> None:
        item = MarketInformation(
            **{
                **self.valid_fields,
                "title": "  Report title  ",
                "source": " EIA ",
                "source_type": " official_data ",
                "content": " Report content ",
                "category": (" energy ",),
                "commodities": (" crude_oil ",),
                "regions": (" United States ",),
                "importance": " high ",
                "url": " https://www.eia.gov ",
            }
        )

        self.assertEqual(item.title, "Report title")
        self.assertEqual(item.category, ("energy",))
        self.assertEqual(item.importance, "high")
        self.assertEqual(item.url, "https://www.eia.gov")

    def test_to_dict_is_json_serializable(self) -> None:
        item = MarketInformation(**self.valid_fields, category=("energy",))
        data = item.to_dict()

        self.assertEqual(data["published_time"], "2026-07-15T09:00:00+00:00")
        self.assertEqual(data["category"], ["energy"])
        json.dumps(data)

    def test_rejects_empty_required_fields(self) -> None:
        for field_name in ("title", "source", "source_type", "content"):
            with self.subTest(field_name=field_name):
                fields = {**self.valid_fields, field_name: "   "}
                with self.assertRaises(ValueError):
                    MarketInformation(**fields)

    def test_rejects_naive_datetime(self) -> None:
        with self.assertRaises(ValueError):
            MarketInformation(
                **{
                    **self.valid_fields,
                    "published_time": datetime(2026, 7, 15, 9, 0),
                }
            )

    def test_rejects_invalid_importance(self) -> None:
        with self.assertRaises(ValueError):
            MarketInformation(**self.valid_fields, importance="urgent")

    def test_rejects_reliability_score_outside_range(self) -> None:
        for score in (0, 6):
            with self.subTest(score=score):
                with self.assertRaises(ValueError):
                    MarketInformation(**self.valid_fields, reliability_score=score)

    def test_rejects_empty_tuple_values(self) -> None:
        for field_name in ("category", "commodities", "regions"):
            with self.subTest(field_name=field_name):
                with self.assertRaises(ValueError):
                    MarketInformation(**self.valid_fields, **{field_name: (" ",)})


if __name__ == "__main__":
    unittest.main()
