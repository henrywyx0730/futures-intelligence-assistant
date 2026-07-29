"""Create collectors from individual source configuration dictionaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from futures_intelligence.collectors.base import BaseCollector
from futures_intelligence.collectors.huatai_futures_pdf import (
    HuataiFuturesPdfResearchReportCollector,
)
from futures_intelligence.collectors.market_data import MarketDataCollector
from futures_intelligence.collectors.official_data import OfficialDataCollector
from futures_intelligence.collectors.research_report import ResearchReportCollector
from futures_intelligence.collectors.research_report_pdf_adapter import (
    ResearchReportPDFMarketInformationAdapter,
)
from futures_intelligence.collectors.rss import RSSCollector
from futures_intelligence.fetchers import HuataiFuturesReportFetcher
from futures_intelligence.fetchers.huatai_pdf import (
    HuataiPdfDownloadLimits,
    HuataiPdfParseLimits,
    HuataiPdfTextExtractor,
)


HUATAI_PDF_LISTING_MODE = "huatai_pdf_listing"


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
            if source_config.get("provider") == "huatai_futures":
                return _create_huatai_pdf_collector(source_config)
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


def _required_research_listing_url(source_config: Mapping[str, Any]) -> str:
    """Return an explicit HTTPS listing URL for a source-specific report fetcher."""
    url = source_config.get("url")
    if not isinstance(url, str) or not url.strip().startswith(("https://", "http://")):
        raise ValueError("Research report source configuration requires an http(s) url")
    return url.strip()


def _max_reports(source_config: Mapping[str, Any]) -> int:
    """Return a small positive per-source fetch bound."""
    value = source_config.get("max_reports", 3)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError("max_reports must be a positive integer")
    return value


def _create_huatai_pdf_collector(
    source_config: Mapping[str, Any],
) -> HuataiFuturesPdfResearchReportCollector:
    """Construct the explicitly configured Huatai PDF collector without I/O."""
    collection_mode = source_config.get("collection_mode")
    if collection_mode != HUATAI_PDF_LISTING_MODE:
        if collection_mode is None:
            raise ValueError(
                "Huatai Futures research report configuration requires "
                "collection_mode='huatai_pdf_listing'"
            )
        raise ValueError(
            "Unsupported Huatai Futures collection_mode: "
            f"{collection_mode!r}"
        )

    pdf_extraction = _required_pdf_extraction_settings(source_config)
    max_selected_pdfs = _required_positive_pdf_selection_limit(
        _required_pdf_setting(pdf_extraction, "max_selected_pdfs")
    )
    download_limits = HuataiPdfDownloadLimits(
        socket_timeout_seconds=_required_pdf_setting(
            pdf_extraction, "socket_timeout_seconds"
        ),
        download_deadline_seconds=_required_pdf_setting(
            pdf_extraction, "download_deadline_seconds"
        ),
        max_response_bytes=_required_pdf_setting(pdf_extraction, "max_response_bytes"),
        max_redirects=_required_pdf_setting(pdf_extraction, "max_redirects"),
    )
    parse_limits = HuataiPdfParseLimits(
        max_pages=_required_pdf_setting(pdf_extraction, "max_pages"),
        max_content_stream_bytes_per_page=_required_pdf_setting(
            pdf_extraction, "max_content_stream_bytes_per_page"
        ),
        max_content_stream_bytes=_required_pdf_setting(
            pdf_extraction, "max_content_stream_bytes"
        ),
        max_extracted_characters_per_page=_required_pdf_setting(
            pdf_extraction, "max_extracted_characters_per_page"
        ),
        max_extracted_characters=_required_pdf_setting(
            pdf_extraction, "max_extracted_characters"
        ),
        parser_deadline_seconds=_required_pdf_setting(
            pdf_extraction, "parser_deadline_seconds"
        ),
        minimum_meaningful_characters=_required_pdf_setting(
            pdf_extraction, "minimum_meaningful_characters"
        ),
    )
    return HuataiFuturesPdfResearchReportCollector(
        listing_fetcher=HuataiFuturesReportFetcher(
            _required_research_listing_url(source_config)
        ),
        pdf_extractor=HuataiPdfTextExtractor(
            download_limits=download_limits,
            parse_limits=parse_limits,
        ),
        adapter=ResearchReportPDFMarketInformationAdapter(),
        source=_required_source_name(source_config),
        category=_metadata_tuple(source_config, "category"),
        regions=_metadata_tuple(source_config, "regions"),
        reliability_score=source_config.get("reliability_score", 3),
        provider=source_config.get("provider"),
        max_selected_pdfs=max_selected_pdfs,
    )


def _required_source_name(source_config: Mapping[str, Any]) -> str:
    """Return a required source display name for the dedicated collector."""
    name = _optional_name(source_config)
    if name is None:
        raise ValueError("Huatai Futures source configuration requires a non-empty name")
    return name


def _required_pdf_extraction_settings(
    source_config: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Return the explicit bounded PDF configuration mapping."""
    value = source_config.get("pdf_extraction")
    if not isinstance(value, Mapping):
        raise ValueError("Huatai Futures source configuration requires pdf_extraction")
    return value


def _required_pdf_setting(
    pdf_extraction: Mapping[str, Any],
    field_name: str,
) -> Any:
    """Return one required setting without supplying a competing default."""
    if field_name not in pdf_extraction:
        raise ValueError(
            "Huatai Futures source configuration requires "
            f"pdf_extraction.{field_name}"
        )
    return pdf_extraction[field_name]


def _required_positive_pdf_selection_limit(value: object) -> int:
    """Validate the one PDF setting shared by selection and download limits."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            "pdf_extraction.max_selected_pdfs must be a positive integer"
        )
    return value


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
