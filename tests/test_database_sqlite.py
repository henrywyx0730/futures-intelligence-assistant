"""Tests for SQLite database initialization."""

from pathlib import Path
import sqlite3
import tempfile
import unittest

from futures_intelligence.database.sqlite import initialize_database


class SQLiteDatabaseTests(unittest.TestCase):
    """Validate local SQLite database schema setup."""

    def test_creates_database_file_and_required_tables(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "data" / "assistant.db"
            connection = initialize_database(database_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            finally:
                connection.close()

            self.assertTrue(database_path.is_file())
            self.assertTrue({"market_information", "market_analysis"} <= tables)

    def test_creates_expected_table_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "assistant.db"
            connection = initialize_database(database_path)
            try:
                information_columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(market_information)")
                }
                analysis_column_details = {
                    row[1]: row
                    for row in connection.execute("PRAGMA table_info(market_analysis)")
                }
            finally:
                connection.close()

            self.assertTrue(
                {"title", "source", "published_time", "content", "metadata"}
                <= information_columns
            )
            self.assertTrue(
                {
                    "market_information_id",
                    "summary",
                    "market_direction",
                    "confidence_score",
                    "reasoning_details",
                    "directional_provenance",
                    "created_at",
                }
                <= analysis_column_details.keys()
            )
            provenance_column = analysis_column_details["directional_provenance"]
            self.assertEqual(provenance_column[3], 1)
            self.assertEqual(provenance_column[4], "'unspecified'")

    def test_upgrades_existing_market_information_table_with_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "assistant.db"
            connection = sqlite3.connect(database_path)
            try:
                connection.execute(
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
                        url TEXT
                    )
                    """
                )
                connection.commit()
            finally:
                connection.close()

            connection = initialize_database(database_path)
            try:
                columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(market_information)")
                }
            finally:
                connection.close()

            self.assertIn("metadata", columns)

    def test_upgrades_existing_market_analysis_table_with_rich_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "assistant.db"
            connection = sqlite3.connect(database_path)
            try:
                connection.execute(
                    """
                    CREATE TABLE market_analysis (
                        id INTEGER PRIMARY KEY,
                        market_information_id INTEGER NOT NULL,
                        summary TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                connection.commit()
            finally:
                connection.close()

            connection = initialize_database(database_path)
            try:
                column_details = {
                    row[1]: row
                    for row in connection.execute("PRAGMA table_info(market_analysis)")
                }
            finally:
                connection.close()

            self.assertTrue(
                {
                    "market_direction",
                    "confidence_score",
                    "reasoning_details",
                    "directional_provenance",
                }
                <= column_details.keys()
            )
            provenance_column = column_details["directional_provenance"]
            self.assertEqual(provenance_column[3], 1)
            self.assertEqual(provenance_column[4], "'unspecified'")

            connection = initialize_database(database_path)
            connection.close()


if __name__ == "__main__":
    unittest.main()
