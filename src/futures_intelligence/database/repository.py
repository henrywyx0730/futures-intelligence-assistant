"""Repository functions for normalized market information and analysis."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from futures_intelligence.database.sqlite import initialize_database
from futures_intelligence.models import (
    CommodityDirectionalEvidence,
    MarketAnalysis,
    MarketInformation,
)


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
                INSERT INTO market_analysis (
                    market_information_id, summary, market_direction,
                    confidence_score, reasoning_details, directional_provenance
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    information_id,
                    analysis.summary,
                    analysis.market_direction,
                    analysis.confidence_score,
                    json.dumps(analysis.reasoning_details),
                    analysis.directional_provenance,
                ),
            )
            analysis_id = int(cursor.lastrowid)
            connection.executemany(
                """
                INSERT INTO market_analysis_commodity_directional_evidence (
                    market_analysis_id, ordinal, commodity_key,
                    commodity_label, market_direction
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    (
                        analysis_id,
                        ordinal,
                        evidence.commodity_key,
                        evidence.commodity_label,
                        evidence.market_direction,
                    )
                    for ordinal, evidence in enumerate(
                        analysis.commodity_directional_evidence
                    )
                ),
            )
            return analysis_id
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
                   commodities, regions, importance, reliability_score, url, metadata
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
                   market_information.metadata,
                   market_analysis.summary, market_analysis.market_direction,
                   market_analysis.confidence_score, market_analysis.reasoning_details,
                   market_analysis.directional_provenance, market_analysis.id,
                   market_analysis.created_at
            FROM market_analysis
            JOIN market_information
                ON market_analysis.market_information_id = market_information.id
            """
        ).fetchall()
        recent_rows = [
            row for row in rows if _analysis_created_at(row[-1]) >= cutoff
        ]
        evidence_by_analysis_id = _commodity_directional_evidence_by_analysis_id(
            connection,
            tuple(int(row[17]) for row in recent_rows),
        )
    finally:
        connection.close()

    return [
        MarketAnalysis(
            market_information=_market_information_from_row(row[:12]),
            summary=str(row[12]),
            market_direction=str(row[13]),
            confidence_score=int(row[14]),
            reasoning_details=tuple(json.loads(str(row[15]))),
            directional_provenance=str(row[16]),
            commodity_directional_evidence=evidence_by_analysis_id.get(
                int(row[17]),
                (),
            ),
        )
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
            commodities, regions, importance, reliability_score, url, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            json.dumps(information.metadata),
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
        metadata=json.loads(str(row[11])),
    )


def _analysis_created_at(value: object) -> datetime:
    """Parse SQLite's UTC analysis creation timestamp."""
    return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc
    )


def _commodity_directional_evidence_by_analysis_id(
    connection: sqlite3.Connection,
    analysis_ids: tuple[int, ...],
) -> dict[int, tuple[CommodityDirectionalEvidence, ...]]:
    """Load ordered scoped evidence for the selected persisted analyses."""
    if not analysis_ids:
        return {}
    placeholders = ", ".join("?" for _ in analysis_ids)
    rows = connection.execute(
        """
        SELECT market_analysis_id, commodity_key, commodity_label, market_direction
        FROM market_analysis_commodity_directional_evidence
        WHERE market_analysis_id IN ("""
        + placeholders
        + ") ORDER BY market_analysis_id, ordinal",
        analysis_ids,
    ).fetchall()
    evidence_by_analysis_id: dict[int, list[CommodityDirectionalEvidence]] = {}
    for analysis_id, commodity_key, commodity_label, market_direction in rows:
        evidence_by_analysis_id.setdefault(int(analysis_id), []).append(
            CommodityDirectionalEvidence(
                commodity_key=str(commodity_key),
                commodity_label=str(commodity_label),
                market_direction=str(market_direction),
            )
        )
    return {
        analysis_id: tuple(evidence)
        for analysis_id, evidence in evidence_by_analysis_id.items()
    }
