"""Repository functions for normalized market information and analysis."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from futures_intelligence.database.sqlite import initialize_database
from futures_intelligence.models import MarketAnalysis, MarketInformation


def store_market_information(
    database_path: str | Path, information: MarketInformation
) -> int:
    """Store one normalized market-information item and return its database ID."""
    connection = initialize_database(database_path)
    try:
        with connection:
            return _insert_market_information(connection, information)
    finally:
        connection.close()


def store_market_analysis(database_path: str | Path, analysis: MarketAnalysis) -> int:
    """Store an analysis and its referenced market-information item."""
    connection = initialize_database(database_path)
    try:
        with connection:
            information_id = _insert_market_information(
                connection, analysis.market_information
            )
            cursor = connection.execute(
                """
                INSERT INTO market_analysis (market_information_id, summary)
                VALUES (?, ?)
                """,
                (information_id, analysis.summary),
            )
            return int(cursor.lastrowid)
    finally:
        connection.close()


def get_recent_market_information(
    database_path: str | Path, hours: float = 24
) -> list[MarketInformation]:
    """Return stored market-information items published within the given hours."""
    cutoff = _recent_cutoff(hours)
    connection = initialize_database(database_path)
    try:
        rows = connection.execute(
            """
            SELECT title, source, source_type, published_time, content, category,
                   commodities, regions, importance, reliability_score, url
            FROM market_information
            """
        ).fetchall()
    finally:
        connection.close()

    information = [_market_information_from_row(row) for row in rows]
    return sorted(
        (item for item in information if item.published_time >= cutoff),
        key=lambda item: item.published_time,
        reverse=True,
    )


def get_recent_market_analysis(
    database_path: str | Path, hours: float = 24
) -> list[MarketAnalysis]:
    """Return stored analyses created within the given hours."""
    cutoff = _recent_cutoff(hours)
    connection = initialize_database(database_path)
    try:
        rows = connection.execute(
            """
            SELECT market_information.title, market_information.source,
                   market_information.source_type, market_information.published_time,
                   market_information.content, market_information.category,
                   market_information.commodities, market_information.regions,
                   market_information.importance,
                   market_information.reliability_score, market_information.url,
                   market_analysis.summary, market_analysis.created_at
            FROM market_analysis
            JOIN market_information
                ON market_analysis.market_information_id = market_information.id
            """
        ).fetchall()
    finally:
        connection.close()

    recent_rows = [
        row for row in rows if _analysis_created_at(row[-1]) >= cutoff
    ]
    return [
        MarketAnalysis(_market_information_from_row(row[:11]), str(row[11]))
        for row in reversed(recent_rows)
    ]


def _insert_market_information(
    connection: sqlite3.Connection, information: MarketInformation
) -> int:
    """Insert a market-information item using an open transaction."""
    cursor = connection.execute(
        """
        INSERT INTO market_information (
            title, source, source_type, published_time, content, category,
            commodities, regions, importance, reliability_score, url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            information.title,
            information.source,
            information.source_type,
            information.published_time.isoformat(),
            information.content,
            json.dumps(information.category),
            json.dumps(information.commodities),
            json.dumps(information.regions),
            information.importance,
            information.reliability_score,
            information.url,
        ),
    )
    return int(cursor.lastrowid)


def _recent_cutoff(hours: float) -> datetime:
    """Return a UTC cutoff for a non-negative recent-hours window."""
    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or hours < 0:
        raise ValueError("hours must be a non-negative number")
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _market_information_from_row(row: tuple[object, ...]) -> MarketInformation:
    """Reconstruct a market-information model from a stored database row."""
    return MarketInformation(
        title=str(row[0]),
        source=str(row[1]),
        source_type=str(row[2]),
        published_time=datetime.fromisoformat(str(row[3])),
        content=str(row[4]),
        category=tuple(json.loads(str(row[5]))),
        commodities=tuple(json.loads(str(row[6]))),
        regions=tuple(json.loads(str(row[7]))),
        importance=str(row[8]),
        reliability_score=int(row[9]),
        url=row[10] if isinstance(row[10], str) else None,
    )


def _analysis_created_at(value: object) -> datetime:
    """Parse SQLite's UTC analysis creation timestamp."""
    return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc
    )
