"""Normalized representation of collected market information."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


VALID_IMPORTANCE = frozenset({"low", "medium", "high", "critical"})


@dataclass
class MarketInformation:
    """A domain-neutral item collected from a market-information source."""

    title: str
    source: str
    source_type: str
    published_time: datetime
    content: str
    category: tuple[str, ...] = ()
    commodities: tuple[str, ...] = ()
    regions: tuple[str, ...] = ()
    importance: str = "medium"
    reliability_score: int = 3
    url: str | None = None

    def __post_init__(self) -> None:
        """Normalize text fields and validate the normalized item."""
        self.title = _normalize_required_text("title", self.title)
        self.source = _normalize_required_text("source", self.source)
        self.source_type = _normalize_required_text("source_type", self.source_type)
        self.content = _normalize_required_text("content", self.content)
        self.category = _normalize_text_tuple("category", self.category)
        self.commodities = _normalize_text_tuple("commodities", self.commodities)
        self.regions = _normalize_text_tuple("regions", self.regions)
        self.importance = _normalize_required_text("importance", self.importance)
        self.url = _normalize_url(self.url)

        if self.published_time.tzinfo is None or (
            self.published_time.utcoffset() is None
        ):
            raise ValueError("published_time must be timezone-aware")
        if self.importance not in VALID_IMPORTANCE:
            raise ValueError(
                f"importance must be one of: {', '.join(sorted(VALID_IMPORTANCE))}"
            )
        if not 1 <= self.reliability_score <= 5:
            raise ValueError("reliability_score must be between 1 and 5")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of this item."""
        return {
            "title": self.title,
            "source": self.source,
            "source_type": self.source_type,
            "published_time": self.published_time.isoformat(),
            "content": self.content,
            "category": list(self.category),
            "commodities": list(self.commodities),
            "regions": list(self.regions),
            "importance": self.importance,
            "reliability_score": self.reliability_score,
            "url": self.url,
        }


def _normalize_required_text(field_name: str, value: str) -> str:
    """Strip and validate a required text value."""
    if not isinstance(value, str) or not (normalized := value.strip()):
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _normalize_text_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    """Strip and validate text values in a tuple field."""
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple of strings")
    return tuple(_normalize_required_text(field_name, value) for value in values)


def _normalize_url(value: str | None) -> str | None:
    """Strip an optional URL, treating an empty value as absent."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("url must be a string or None")
    return value.strip() or None
