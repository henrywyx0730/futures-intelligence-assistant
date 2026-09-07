"""Tests for SQLite repository functions."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from futures_intelligence.database.sqlite import initialize_database
from futures_intelligence.database.repository import (
    get_recent_market_analysis,
    get_recent_market_information,
    store_market_analysis,
    store_market_information,
)
from futures_intelligence.models import (
    CommodityDirectionalEvidence,
    MarketAnalysis,
    MarketInformation,
)


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

    def test_round_trips_directional_provenance(self) -> None:
        cases = (
            ("structural_only", "neutral", 60),
            ("direct_fundamental", "bullish", 75),
            ("external_analyst", "neutral", 45),
            ("unspecified", "bearish", 65),
        )

        for provenance, direction, confidence in cases:
            with self.subTest(provenance=provenance):
                database_path = (
                    Path(self.temporary_directory.name) / f"{provenance}.db"
                )
                analysis = MarketAnalysis(
                    make_information(datetime.now(timezone.utc)),
                    "Inventory data was published.",
                    market_direction=direction,
                    confidence_score=confidence,
                    reasoning_details=("Persisted reasoning",),
                    directional_provenance=provenance,
                )

                store_market_analysis(database_path, analysis)
                loaded = get_recent_market_analysis(database_path, hours=1)

                self.assertEqual(len(loaded), 1)
                self.assertEqual(
                    loaded[0].market_information, analysis.market_information
                )
                self.assertEqual(loaded[0].summary, analysis.summary)
                self.assertEqual(loaded[0].market_direction, direction)
                self.assertEqual(loaded[0].confidence_score, confidence)
                self.assertEqual(
                    loaded[0].reasoning_details, analysis.reasoning_details
                )
                self.assertEqual(loaded[0].directional_provenance, provenance)

    def test_round_trips_ordered_commodity_directional_evidence(self) -> None:
        crude_bullish = CommodityDirectionalEvidence(
            "crude_oil",
            "Crude Oil",
            "bullish",
        )
        fuel_bullish = CommodityDirectionalEvidence(
            "fuel_oil",
            "Fuel Oil",
            "bullish",
        )
        fuel_bearish = CommodityDirectionalEvidence(
            "fuel_oil",
            "Fuel Oil",
            "bearish",
        )
        cases = (
            (
                "one",
                "bullish",
                "direct_fundamental",
                (crude_bullish,),
            ),
            (
                "two_ordered",
                "bullish",
                "direct_fundamental",
                (crude_bullish, fuel_bullish),
            ),
            (
                "opposing",
                "neutral",
                "cross_commodity_abstention",
                (crude_bullish, fuel_bearish),
            ),
        )

        for name, direction, provenance, evidence in cases:
            with self.subTest(name=name):
                database_path = Path(self.temporary_directory.name) / f"{name}.db"
                analysis = MarketAnalysis(
                    make_information(datetime.now(timezone.utc)),
                    "Persisted scoped evidence.",
                    market_direction=direction,
                    confidence_score=75 if direction != "neutral" else 60,
                    reasoning_details=("Persisted reasoning",),
                    directional_provenance=provenance,
                    commodity_directional_evidence=evidence,
                )

                store_market_analysis(database_path, analysis)
                loaded = get_recent_market_analysis(database_path, hours=1)

                self.assertEqual(len(loaded), 1)
                self.assertEqual(
                    loaded[0].market_information,
                    analysis.market_information,
                )
                self.assertEqual(loaded[0].summary, analysis.summary)
                self.assertEqual(loaded[0].market_direction, direction)
                self.assertEqual(
                    loaded[0].confidence_score,
                    analysis.confidence_score,
                )
                self.assertEqual(
                    loaded[0].reasoning_details,
                    analysis.reasoning_details,
                )
                self.assertEqual(loaded[0].directional_provenance, provenance)
                self.assertEqual(loaded[0].commodity_directional_evidence, evidence)

    def test_upgrades_legacy_analysis_row_to_unspecified(self) -> None:
        now = datetime.now(timezone.utc)
        connection = sqlite3.connect(self.database_path)
        try:
            connection.executescript(
                """
                CREATE TABLE market_information (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    published_time TEXT NOT NULL,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '[]',
                    commodities TEXT NOT NULL DEFAULT '[]',
                    regions TEXT NOT NULL DEFAULT '[]',
                    importance TEXT NOT NULL,
                    reliability_score INTEGER NOT NULL,
                    url TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE market_analysis (
                    id INTEGER PRIMARY KEY,
                    market_information_id INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    market_direction TEXT NOT NULL DEFAULT 'neutral',
                    confidence_score INTEGER NOT NULL DEFAULT 0,
                    reasoning_details TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (market_information_id) REFERENCES market_information(id)
                );
                """
            )
            connection.execute(
                """
                INSERT INTO market_information (
                    title, source, source_type, published_time, content, category,
                    commodities, regions, importance, reliability_score, url, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Legacy oil analysis",
                    "EIA",
                    "official_data",
                    now.isoformat(),
                    "Legacy inventory content.",
                    '["energy"]',
                    '["crude_oil"]',
                    '["United States"]',
                    "medium",
                    5,
                    "https://www.eia.gov",
                    '{"series_id": "legacy"}',
                ),
            )
            connection.execute(
                """
                INSERT INTO market_analysis (
                    market_information_id, summary, market_direction,
                    confidence_score, reasoning_details
                ) VALUES (1, ?, ?, ?, ?)
                """,
                (
                    "Legacy analysis summary.",
                    "bullish",
                    70,
                    '["Legacy reasoning"]',
                ),
            )
            connection.commit()
        finally:
            connection.close()

        first_connection = initialize_database(self.database_path)
        first_connection.close()
        second_connection = initialize_database(self.database_path)
        second_connection.close()
        loaded = get_recent_market_analysis(self.database_path, hours=1)

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].market_information.title, "Legacy oil analysis")
        self.assertEqual(loaded[0].summary, "Legacy analysis summary.")
        self.assertEqual(loaded[0].market_direction, "bullish")
        self.assertEqual(loaded[0].confidence_score, 70)
        self.assertEqual(loaded[0].reasoning_details, ("Legacy reasoning",))
        self.assertEqual(loaded[0].directional_provenance, "unspecified")
        self.assertEqual(loaded[0].commodity_directional_evidence, ())

    def test_rejects_invalid_persisted_directional_provenance(self) -> None:
        analysis = MarketAnalysis(
            make_information(datetime.now(timezone.utc)),
            "Inventory data was published.",
            directional_provenance="no_directional_signal",
        )
        analysis_id = store_market_analysis(self.database_path, analysis)
        connection = initialize_database(self.database_path)
        try:
            connection.execute(
                """
                UPDATE market_analysis
                SET directional_provenance = 'not_a_real_provenance'
                WHERE id = ?
                """,
                (analysis_id,),
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(ValueError):
            get_recent_market_analysis(self.database_path, hours=1)

    def test_rejects_invalid_persisted_commodity_directional_evidence(self) -> None:
        analysis = MarketAnalysis(
            make_information(datetime.now(timezone.utc)),
            "Inventory data was published.",
            market_direction="bullish",
            directional_provenance="direct_fundamental",
            commodity_directional_evidence=(
                CommodityDirectionalEvidence(
                    "crude_oil",
                    "Crude Oil",
                    "bullish",
                ),
            ),
        )
        analysis_id = store_market_analysis(self.database_path, analysis)
        connection = initialize_database(self.database_path)
        try:
            connection.execute(
                """
                UPDATE market_analysis_commodity_directional_evidence
                SET market_direction = 'neutral'
                WHERE market_analysis_id = ?
                """,
                (analysis_id,),
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(ValueError):
            get_recent_market_analysis(self.database_path, hours=1)

    def test_rolls_back_parent_when_evidence_insertion_fails(self) -> None:
        evidence = CommodityDirectionalEvidence(
            "crude_oil",
            "Crude Oil",
            "bullish",
        )
        analysis = MarketAnalysis(
            make_information(datetime.now(timezone.utc)),
            "Inventory data was published.",
            market_direction="bullish",
            directional_provenance="direct_fundamental",
            commodity_directional_evidence=(evidence,),
        )
        analysis.commodity_directional_evidence = (evidence, evidence)

        with self.assertRaises(sqlite3.IntegrityError):
            store_market_analysis(self.database_path, analysis)

        connection = initialize_database(self.database_path)
        try:
            information_count = connection.execute(
                "SELECT COUNT(*) FROM market_information"
            ).fetchone()[0]
            analysis_count = connection.execute(
                "SELECT COUNT(*) FROM market_analysis"
            ).fetchone()[0]
            evidence_count = connection.execute(
                "SELECT COUNT(*) FROM "
                "market_analysis_commodity_directional_evidence"
            ).fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(
            (information_count, analysis_count, evidence_count),
            (0, 0, 0),
        )


if __name__ == "__main__":
    unittest.main()
