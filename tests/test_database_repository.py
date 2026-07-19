"""Tests for SQLite repository functions."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from futures_intelligence.database.sqlite import initialize_database
from futures_intelligence.database.repository import (
    get_recent_market_analysis,
    get_recent_market_information,
    store_market_analysis,
    store_market_information,
)
from futures_intelligence.models import MarketAnalysis, MarketInformation


def make_information(
    published_time: datetime | None = None,
) -> MarketInformation:
    """Create a market-information item for persistence tests."""
    return MarketInformation(
        title="Oil inventory update",
        source="EIA",
        source_type="official_data",
        published_time=published_time
        or datetime(2026, 7, 16, 9, 0, tzinfo=timezone.utc),
        content="Weekly inventory data was published.",
        category=("energy",),
        commodities=("crude_oil",),
        regions=("United States",),
        reliability_score=5,
        url="https://www.eia.gov",
        metadata={"series_id": "WCESTUS1", "units": "barrels"},
    )


class DatabaseRepositoryTests(unittest.TestCase):
    """Validate model serialization and related-row persistence."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "assistant.db"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_stores_market_information_with_serialized_fields(self) -> None:
        information = make_information()

        information_id = store_market_information(self.database_path, information)

        connection = initialize_database(self.database_path)
        try:
            row = connection.execute(
                """
                SELECT title, published_time, category, commodities, regions, metadata
                FROM market_information WHERE id = ?
                """,
                (information_id,),
            ).fetchone()
        finally:
            connection.close()

        self.assertEqual(row[0], "Oil inventory update")
        self.assertEqual(row[1], "2026-07-16T09:00:00+00:00")
        self.assertEqual(json.loads(row[2]), ["energy"])
        self.assertEqual(json.loads(row[3]), ["crude_oil"])
        self.assertEqual(json.loads(row[4]), ["United States"])
        self.assertEqual(
            json.loads(row[5]), {"series_id": "WCESTUS1", "units": "barrels"}
        )

    def test_stores_analysis_with_referenced_information(self) -> None:
        analysis = MarketAnalysis(
            make_information(),
            "Inventory data was published.",
            market_direction="bullish",
            confidence_score=75,
            reasoning_details=("Inventories declined",),
        )

        analysis_id = store_market_analysis(self.database_path, analysis)

        connection = initialize_database(self.database_path)
        try:
            row = connection.execute(
                """
                SELECT market_analysis.summary, market_analysis.market_direction,
                       market_analysis.confidence_score,
                       market_analysis.reasoning_details, market_information.title
                FROM market_analysis
                JOIN market_information
                    ON market_analysis.market_information_id = market_information.id
                WHERE market_analysis.id = ?
                """,
                (analysis_id,),
            ).fetchone()
        finally:
            connection.close()

        self.assertEqual(
            row,
            (
                "Inventory data was published.",
                "bullish",
                75,
                '["Inventories declined"]',
                "Oil inventory update",
            ),
        )

    def test_gets_recent_market_information_as_models(self) -> None:
        now = datetime.now(timezone.utc)
        store_market_information(self.database_path, make_information(now))
        store_market_information(
            self.database_path, make_information(now - timedelta(hours=48))
        )

        information = get_recent_market_information(self.database_path, hours=24)

        self.assertEqual(len(information), 1)
        self.assertIsInstance(information[0], MarketInformation)
        self.assertEqual(information[0].category, ("energy",))
        self.assertEqual(
            information[0].metadata,
            {"series_id": "WCESTUS1", "units": "barrels"},
        )
        self.assertEqual(information[0].published_time, now)

    def test_gets_recent_market_analysis_as_models(self) -> None:
        analysis = MarketAnalysis(
            make_information(datetime.now(timezone.utc)),
            "Inventory data was published.",
            market_direction="bearish",
            confidence_score=65,
            reasoning_details=("Demand weakened",),
        )
        store_market_analysis(self.database_path, analysis)

        analyses = get_recent_market_analysis(self.database_path, hours=1)

        self.assertEqual(len(analyses), 1)
        self.assertIsInstance(analyses[0], MarketAnalysis)
        self.assertEqual(analyses[0].summary, "Inventory data was published.")
        self.assertEqual(analyses[0].market_direction, "bearish")
        self.assertEqual(analyses[0].confidence_score, 65)
        self.assertEqual(analyses[0].reasoning_details, ("Demand weakened",))
        self.assertEqual(analyses[0].market_information.title, "Oil inventory update")
        self.assertEqual(
            analyses[0].market_information.metadata,
            {"series_id": "WCESTUS1", "units": "barrels"},
        )


if __name__ == "__main__":
    unittest.main()
