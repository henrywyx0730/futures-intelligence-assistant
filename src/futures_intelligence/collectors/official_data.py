"""Local JSON collector for official market data."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from futures_intelligence.collectors.base import BaseCollector
from futures_intelligence.models import MarketInformation


class OfficialDataCollector(BaseCollector):
    """Load configured local official-data records from a JSON file."""

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
        """Return normalized records from a local JSON data file."""
        records = _load_records(self.content_path)
        return [
            information
            for record in records
            if (information := self._normalize_record(record)) is not None
        ]

    def _normalize_record(
        self, record: Mapping[str, Any]
    ) -> MarketInformation | None:
        """Convert one valid official-data record into market information."""
        published_time = _parse_published_time(record.get("published_time"))
        if published_time is None:
            return None

        try:
            return MarketInformation(
                title=record["title"],
                source=self.source,
                source_type="official_data",
                published_time=published_time,
                content=record["content"],
                category=_record_tuple(record, "category", self.category),
                commodities=_record_tuple(record, "commodities", self.commodities),
                regions=_record_tuple(record, "regions", self.regions),
                importance=record.get("importance", "medium"),
                reliability_score=record.get(
                    "reliability_score", self.reliability_score
                ),
                url=record.get("url"),
                metadata=record.get("metadata", {}),
            )
        except (KeyError, TypeError, ValueError):
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


def _parse_published_time(value: Any) -> datetime | None:
    """Parse an ISO-8601 timezone-aware publication timestamp."""
    if not isinstance(value, str):
        return None
    try:
        published_time = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if published_time.tzinfo is None or published_time.utcoffset() is None:
        return None
    return published_time


def _record_tuple(
    record: Mapping[str, Any], field_name: str, default: tuple[str, ...]
) -> tuple[str, ...]:
    """Return a record metadata tuple, falling back to configured metadata."""
    value = record.get(field_name, default)
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a list or tuple of strings")
    return tuple(value)
