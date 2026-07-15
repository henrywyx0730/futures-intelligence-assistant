"""Create collectors from individual source configuration dictionaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from futures_intelligence.collectors.base import BaseCollector
from futures_intelligence.collectors.rss import RSSCollector


class CollectorFactory:
    """Create supported collectors from source configuration."""

    @staticmethod
    def create(source_config: Mapping[str, Any]) -> BaseCollector | None:
        """Create an enabled collector, or return None for a disabled source."""
        if not source_config.get("enabled", True):
            return None

        source_type = source_config.get("source_type")
        if source_type == "rss":
            return RSSCollector(
                rss_url=_required_url(source_config),
                source=_optional_name(source_config),
                category=_metadata_tuple(source_config, "category"),
                commodities=_metadata_tuple(source_config, "commodities"),
                regions=_metadata_tuple(source_config, "regions"),
                reliability_score=source_config.get("reliability_score", 3),
            )
        raise ValueError(f"Unsupported source type: {source_type!r}")


def _required_url(source_config: Mapping[str, Any]) -> str:
    """Return the configured RSS URL or raise an actionable error."""
    url = source_config.get("url")
    if not isinstance(url, str) or not (normalized_url := url.strip()):
        raise ValueError("RSS source configuration requires a non-empty url")
    return normalized_url


def _optional_name(source_config: Mapping[str, Any]) -> str | None:
    """Return a configured source name when it is a non-empty string."""
    name = source_config.get("name")
    if not isinstance(name, str):
        return None
    return name.strip() or None


def _metadata_tuple(
    source_config: Mapping[str, Any], field_name: str
) -> tuple[str, ...]:
    """Convert optional YAML metadata lists to tuples."""
    value = source_config.get(field_name)
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list or tuple of strings")
    return tuple(value)
