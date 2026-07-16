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
            url TEXT
        );

        CREATE TABLE IF NOT EXISTS market_analysis (
            id INTEGER PRIMARY KEY,
            market_information_id INTEGER NOT NULL,
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (market_information_id) REFERENCES market_information(id)
        );
        """
    )
    connection.commit()
    return connection
