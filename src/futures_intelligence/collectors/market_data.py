"""Local JSON collector for normalized market-data snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from futures_intelligence.collectors.base import BaseCollector
from futures_intelligence.models import MarketInformation


class MarketDataCollector(BaseCollector):
    """Load configured local market-data records from a JSON file."""

    def __init__(
        self,
        content_path: str | Path,
        source: str,
        category: tuple[str, ...] = (),
        commodities: tuple[str, ...] = (),
        regions: tuple[str, ...] = (),
        reliability_score: int = 3,
    ) -> None:
        self.content_path = Path(content_path)
        self.source = source
        self.category = category
        self.commodities = commodities
        self.regions = regions
        self.reliability_score = reliability_score

    def collect(self) -> list[MarketInformation]:
        """Return normalized local market-data records."""
        records = _load_records(self.content_path)
        fallback_time = _file_modified_time(self.content_path)
        if fallback_time is None:
            return []
        return [
            information
            for record in records
            if (
                information := self._normalize_record(record, fallback_time)
            ) is not None
        ]

    def _normalize_record(
        self, record: Mapping[str, Any], fallback_time: datetime
    ) -> MarketInformation | None:
        """Convert a local quote record into normalized market information."""
        symbol = record.get("symbol")
        price = record.get("price")
        if not isinstance(symbol, str) or not symbol.strip() or not _is_number(price):
            return None

        timestamp = record.get("timestamp")
        published_time = _parse_timestamp(timestamp) if timestamp is not None else fallback_time
        if published_time is None:
            return None

        try:
            metadata = {"symbol": symbol.strip(), "price": price}
            for field_name in ("price_change", "volume", "open_interest"):
                if field_name in record:
                    value = record[field_name]
                    if not _is_number(value):
                        return None
                    metadata[field_name] = value
            if timestamp is not None:
                metadata["timestamp"] = published_time.isoformat()

            return MarketInformation(
                title=f"Market data: {symbol.strip()}",
                source=self.source,
                source_type="market_data",
                published_time=published_time,
                content=f"Local market-data snapshot for {symbol.strip()} at price {price}.",
                category=self.category,
                commodities=self.commodities,
                regions=self.regions,
                reliability_score=self.reliability_score,
                metadata=metadata,
            )
        except (TypeError, ValueError):
            return None


def _load_records(content_path: Path) -> list[Mapping[str, Any]]:
    """Load a JSON list or an object containing an ``items`` list."""
    try:
        with content_path.open(encoding="utf-8") as data_file:
            payload = json.load(data_file)
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(payload, Mapping):
        payload = payload.get("items", [])
    if not isinstance(payload, list):
        return []
    return [record for record in payload if isinstance(record, Mapping)]


def _file_modified_time(content_path: Path) -> datetime | None:
    """Return the local JSON file modification time as an aware timestamp."""
    try:
        return datetime.fromtimestamp(content_path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def _parse_timestamp(value: object) -> datetime | None:
    """Parse an ISO-8601 timezone-aware market-data timestamp."""
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return None
    return timestamp


def _is_number(value: object) -> bool:
    """Return whether a field contains a numeric market-data value."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)
