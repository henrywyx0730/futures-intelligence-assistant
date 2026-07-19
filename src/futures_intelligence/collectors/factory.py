"""Create collectors from individual source configuration dictionaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from futures_intelligence.collectors.base import BaseCollector
from futures_intelligence.collectors.market_data import MarketDataCollector
from futures_intelligence.collectors.official_data import OfficialDataCollector
from futures_intelligence.collectors.research_report import ResearchReportCollector
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
        if source_type == "research_report":
            content_path = _required_local_content_path(source_config)
            return ResearchReportCollector(
                content_path=content_path,
                source=_optional_name(source_config) or content_path,
                title=_optional_title(source_config),
                category=_metadata_tuple(source_config, "category"),
                commodities=_metadata_tuple(source_config, "commodities"),
                regions=_metadata_tuple(source_config, "regions"),
                reliability_score=source_config.get("reliability_score", 3),
            )
        if source_type == "official_data":
            content_path = _required_local_official_data_path(source_config)
            return OfficialDataCollector(
                content_path=content_path,
                source=_optional_name(source_config) or content_path,
                category=_metadata_tuple(source_config, "category"),
                commodities=_metadata_tuple(source_config, "commodities"),
                regions=_metadata_tuple(source_config, "regions"),
                reliability_score=source_config.get("reliability_score", 3),
            )
        if source_type == "market_data":
            content_path = _required_local_market_data_path(source_config)
            return MarketDataCollector(
                content_path=content_path,
                source=_optional_name(source_config) or content_path,
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


def _optional_title(source_config: Mapping[str, Any]) -> str | None:
    """Return a configured report title when it is a non-empty string."""
    title = source_config.get("title")
    if not isinstance(title, str):
        return None
    return title.strip() or None


def _required_local_content_path(source_config: Mapping[str, Any]) -> str:
    """Return a configured local report path without permitting remote loading."""
    value = source_config.get("content_path") or source_config.get("url")
    if not isinstance(value, str) or not (path := value.strip()):
        raise ValueError(
            "Research report source configuration requires a local content_path"
        )
    if "://" in path:
        raise ValueError(
            "Research report source configuration requires a local content_path"
        )
    return path


def _required_local_official_data_path(source_config: Mapping[str, Any]) -> str:
    """Return a configured local JSON path without permitting remote loading."""
    value = source_config.get("content_path")
    if not isinstance(value, str) or not (path := value.strip()) or "://" in value:
        raise ValueError(
            "Official data source configuration requires a local content_path"
        )
    if not path.lower().endswith(".json"):
        raise ValueError("Official data source configuration requires a JSON content_path")
    return path


def _required_local_market_data_path(source_config: Mapping[str, Any]) -> str:
    """Return a configured local JSON path without permitting remote loading."""
    value = source_config.get("content_path")
    if not isinstance(value, str) or not (path := value.strip()) or "://" in value:
        raise ValueError(
            "Market data source configuration requires a local content_path"
        )
    if not path.lower().endswith(".json"):
        raise ValueError("Market data source configuration requires a JSON content_path")
    return path


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
