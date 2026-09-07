"""SQLite database initialization for the Futures Intelligence Assistant."""

from __future__ import annotations

from pathlib import Path
import sqlite3


def initialize_database(
    database_path: str | Path = "futures_intelligence.db",
) -> sqlite3.Connection:
    """Create or open a local SQLite database and initialize its schema."""
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS market_information (
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

        CREATE TABLE IF NOT EXISTS market_analysis (
            id INTEGER PRIMARY KEY,
            market_information_id INTEGER NOT NULL,
            summary TEXT NOT NULL,
            market_direction TEXT NOT NULL DEFAULT 'neutral',
            confidence_score INTEGER NOT NULL DEFAULT 0,
            reasoning_details TEXT NOT NULL DEFAULT '[]',
            directional_provenance TEXT NOT NULL DEFAULT 'unspecified',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (market_information_id) REFERENCES market_information(id)
        );

        CREATE TABLE IF NOT EXISTS market_analysis_commodity_directional_evidence (
            market_analysis_id INTEGER NOT NULL,
            ordinal INTEGER NOT NULL,
            commodity_key TEXT NOT NULL,
            commodity_label TEXT NOT NULL,
            market_direction TEXT NOT NULL,
            PRIMARY KEY (market_analysis_id, ordinal),
            UNIQUE (market_analysis_id, commodity_key),
            FOREIGN KEY (market_analysis_id) REFERENCES market_analysis(id)
                ON DELETE CASCADE
        );
        """
    )
    _add_metadata_column_if_needed(connection)
    _add_market_analysis_columns_if_needed(connection)
    connection.commit()
    return connection


def _add_metadata_column_if_needed(connection: sqlite3.Connection) -> None:
    """Upgrade existing local databases with structured source metadata."""
    columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(market_information)")
    }
    if "metadata" not in columns:
        connection.execute(
            "ALTER TABLE market_information "
            "ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'"
        )


def _add_market_analysis_columns_if_needed(connection: sqlite3.Connection) -> None:
    """Upgrade existing local databases with richer analysis fields."""
    columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(market_analysis)")
    }
    additions = {
        "market_direction": "TEXT NOT NULL DEFAULT 'neutral'",
        "confidence_score": "INTEGER NOT NULL DEFAULT 0",
        "reasoning_details": "TEXT NOT NULL DEFAULT '[]'",
        "directional_provenance": "TEXT NOT NULL DEFAULT 'unspecified'",
    }
    for column, definition in additions.items():
        if column not in columns:
            connection.execute(
                f"ALTER TABLE market_analysis ADD COLUMN {column} {definition}"
            )
