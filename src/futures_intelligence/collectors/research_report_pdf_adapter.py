"""Normalize safe PDF research-report extractions into market information."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time
from math import isfinite
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from futures_intelligence.models import MarketInformation


SHANGHAI_TIME_ZONE = ZoneInfo("Asia/Shanghai")


class ResearchReportPDFExtractionResult(Protocol):
    """Minimum PDF extraction contract required for research-report normalization."""

    canonical_pdf_url: str
    byte_count: int
    page_count: int | None
    document_metadata: tuple[tuple[str, str], ...]
    extracted_text: str
    extracted_character_count: int
    extraction_status: str
    ocr_required: bool
    title: str | None
    publication_date: date | None
    report_type: str | None
    report_author: str | None
    document_metadata_author: str | None
    parser_diagnostics: tuple[str, ...]


class ResearchReportPDFMarketInformationAdapter:
    """Adapt one successful date-only PDF extraction without adding analysis."""

    def to_market_information(
        self,
        extraction_result: ResearchReportPDFExtractionResult,
        source_metadata: Mapping[str, Any],
    ) -> MarketInformation | None:
        """Return normalized information for a usable extraction, otherwise None."""
        if not _is_usable(extraction_result):
            return None
        try:
            provenance = _external_provenance_snapshot(extraction_result)
        except _ExternalMetadataError:
            return None

        publication_date = extraction_result.publication_date
        assert publication_date is not None
        return MarketInformation(
            title=extraction_result.title or "",
            source=_source_name(source_metadata),
            source_type="research_report",
            published_time=datetime.combine(
                publication_date,
                time.min,
                tzinfo=SHANGHAI_TIME_ZONE,
            ),
            content=extraction_result.extracted_text,
            category=_text_tuple(source_metadata, "category"),
            commodities=(),
            regions=_text_tuple(source_metadata, "regions"),
            importance=source_metadata.get("importance", "medium"),
            reliability_score=source_metadata.get("reliability_score", 3),
            url=extraction_result.canonical_pdf_url,
            metadata={"provider": source_metadata.get("provider"), **provenance},
        )


class _ExternalMetadataError(ValueError):
    """Raised only when extractor-derived optional metadata is unsafe to retain."""


def _is_usable(result: ResearchReportPDFExtractionResult) -> bool:
    """Require a successful non-OCR extraction with complete date-only provenance."""
    publication_date = result.publication_date
    return (
        result.extraction_status == "success"
        and not result.ocr_required
        and isinstance(result.title, str)
        and bool(result.title.strip())
        and isinstance(publication_date, date)
        and not isinstance(publication_date, datetime)
        and isinstance(result.canonical_pdf_url, str)
        and bool(result.canonical_pdf_url.strip())
        and isinstance(result.extracted_text, str)
        and bool(result.extracted_text.strip())
    )


def _external_provenance_snapshot(
    result: ResearchReportPDFExtractionResult,
) -> dict[str, Any]:
    """Create a detached JSON-safe snapshot of bounded extractor provenance."""
    publication_date = result.publication_date
    assert publication_date is not None
    return _json_safe_snapshot(
        {
            "report_type": result.report_type,
            "report_author": result.report_author,
            "document_metadata_author": result.document_metadata_author,
            "document_metadata": _document_metadata_snapshot(result.document_metadata),
            "page_count": result.page_count,
            "byte_count": result.byte_count,
            "extracted_character_count": result.extracted_character_count,
            "parser_diagnostics": _diagnostics_snapshot(result.parser_diagnostics),
            "publication_date": publication_date.isoformat(),
            "published_time_precision": "date",
        }
    )


def _document_metadata_snapshot(value: object) -> dict[str, Any]:
    """Convert bounded PDF metadata pairs or a mapping into a safe detached mapping."""
    if isinstance(value, Mapping):
        return _json_safe_snapshot(value)
    if not isinstance(value, (list, tuple)):
        raise _ExternalMetadataError("document metadata must be a mapping or pairs")

    pairs: dict[str, Any] = {}
    for pair in value:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise _ExternalMetadataError("document metadata entries must be key-value pairs")
        key, metadata_value = pair
        if not isinstance(key, str):
            raise _ExternalMetadataError("document metadata keys must be strings")
        pairs[key] = metadata_value
    return _json_safe_snapshot(pairs)


def _diagnostics_snapshot(value: object) -> list[str]:
    """Copy only an ordered sequence of bounded diagnostic category strings."""
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, str) for item in value
    ):
        raise _ExternalMetadataError("parser diagnostics must be strings")
    return list(value)


def _json_safe_snapshot(value: Any) -> Any:
    """Recursively copy only standard JSON-compatible external metadata values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise _ExternalMetadataError("metadata floats must be finite")
        return value
    if isinstance(value, Mapping):
        snapshot: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise _ExternalMetadataError("metadata keys must be strings")
            snapshot[key] = _json_safe_snapshot(item)
        return snapshot
    if isinstance(value, (list, tuple)):
        return [_json_safe_snapshot(item) for item in value]
    raise _ExternalMetadataError("metadata must be JSON-compatible")


def _source_name(source_metadata: Mapping[str, Any]) -> Any:
    """Use the explicit source value, or the source registry's conventional name."""
    return source_metadata.get("source", source_metadata.get("name"))


def _text_tuple(source_metadata: Mapping[str, Any], field_name: str) -> tuple[str, ...]:
    """Normalize YAML-style source metadata lists to model tuple fields."""
    value = source_metadata.get(field_name, ())
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a list or tuple of strings")
    return tuple(value)
