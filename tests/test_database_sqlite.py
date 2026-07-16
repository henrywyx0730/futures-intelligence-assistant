"""Tests for SQLite database initialization."""

from pathlib import Path
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
                analysis_columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(market_analysis)")
                }
            finally:
                connection.close()

            self.assertTrue(
                {"title", "source", "published_time", "content"}
                <= information_columns
            )
            self.assertTrue(
                {"market_information_id", "summary", "created_at"}
                <= analysis_columns
            )


if __name__ == "__main__":
    unittest.main()
