"""Collect bounded Huatai Futures PDF research reports without analysis."""

from __future__ import annotations

from datetime import date
import logging
from typing import Protocol
from urllib.parse import urlparse

from futures_intelligence.collectors.base import BaseCollector
from futures_intelligence.collectors.research_report_pdf_adapter import (
    ResearchReportPDFMarketInformationAdapter,
)
from futures_intelligence.fetchers.huatai_futures import (
    HTFC_DOMAINS,
    HuataiListingDiscovery,
    HuataiReportListingItem,
)
from futures_intelligence.fetchers.huatai_pdf import (
    HuataiPdfAttachment,
    HuataiPdfExtractionResult,
)
from futures_intelligence.models import MarketInformation


logger = logging.getLogger(__name__)


class _ListingDiscoverer(Protocol):
    """Provide one already-scoped Huatai report listing."""

    def discover_listing(self) -> HuataiListingDiscovery:
        """Return the current official listing discovery result."""


class _PdfTextExtractor(Protocol):
    """Extract one bounded official Huatai PDF attachment."""

    def extract(self, attachment: HuataiPdfAttachment) -> HuataiPdfExtractionResult:
        """Return the controlled result for one attachment."""


class HuataiFuturesPdfResearchReportCollector(BaseCollector):
    """Collect selected Huatai PDF reports into normalized market information."""

    def __init__(
        self,
        *,
        listing_fetcher: _ListingDiscoverer,
        pdf_extractor: _PdfTextExtractor,
        adapter: ResearchReportPDFMarketInformationAdapter,
        source: str,
        category: tuple[str, ...],
        regions: tuple[str, ...],
        reliability_score: int,
        provider: str,
        max_selected_pdfs: int,
    ) -> None:
        """Configure bounded, source-specific collaborators for one collection run."""
        source = _require_nonempty_text("source", source)
        provider = _require_nonempty_text("provider", provider)
        category = _require_text_tuple("category", category)
        regions = _require_text_tuple("regions", regions)
        reliability_score = _require_reliability_score(reliability_score)
        max_selected_pdfs = _require_positive_limit(
            "max_selected_pdfs", max_selected_pdfs
        )
        self._listing_fetcher = listing_fetcher
        self._pdf_extractor = pdf_extractor
        self._adapter = adapter
        self._source_metadata = {
            "source": source,
            "provider": provider,
            "category": category,
            "regions": regions,
            "reliability_score": reliability_score,
        }
        self._max_selected_pdfs = max_selected_pdfs

    def collect(self) -> list[MarketInformation]:
        """Discover, select, extract, and normalize a bounded PDF report set."""
        discovery = self._listing_fetcher.discover_listing()
        selected, unique_count, duplicate_count = self._selected_pdf_items(discovery)
        logger.info(
            "Huatai Futures PDF collector discovered %d PDF attachments, retained %d "
            "unique candidates, and selected %d.",
            len(discovery.pdf_attachment_links),
            unique_count,
            len(selected),
        )
        if duplicate_count:
            logger.info(
                "Huatai Futures PDF collector skipped %d duplicate canonical PDF URLs.",
                duplicate_count,
            )
        if not selected:
            logger.info("Huatai Futures PDF collector found no accepted PDF attachments.")
            return []

        information: list[MarketInformation] = []
        for item in selected:
            attachment = HuataiPdfAttachment(
                url=item.canonical_url,
                listing_title=item.listing_title,
                publication_date=item.publication_date,
                report_type=item.report_type,
            )
            logger.info(
                "Huatai Futures PDF collector extracting %s.",
                attachment.url,
            )
            result = self._pdf_extractor.extract(attachment)
            if result.extraction_status != "success":
                logger.warning(
                    "Huatai Futures PDF collector skipped %s: %s.",
                    attachment.url,
                    result.failure_category or "extraction_failed",
                )
                continue
            normalized = self._adapter.to_market_information(
                result,
                self._source_metadata,
            )
            if normalized is None:
                logger.warning(
                    "Huatai Futures PDF collector skipped %s: adapter_rejected.",
                    attachment.url,
                )
                continue
            information.append(normalized)

        logger.info(
            "Huatai Futures PDF collector returned %d market information items.",
            len(information),
        )
        return information

    def _selected_pdf_items(
        self,
        discovery: HuataiListingDiscovery,
    ) -> tuple[tuple[HuataiReportListingItem, ...], int, int]:
        """Return unique, newest-first PDF listing items with stable tie-breaking."""
        unique: list[tuple[int, HuataiReportListingItem]] = []
        seen_urls: set[str] = set()
        duplicate_count = 0
        for discovery_position, item in enumerate(discovery.report_items):
            if item.link_kind != "pdf_attachment" or not _is_usable_pdf_url(
                item.canonical_url
            ):
                continue
            if item.canonical_url in seen_urls:
                duplicate_count += 1
                continue
            seen_urls.add(item.canonical_url)
            unique.append((discovery_position, item))

        ordered = sorted(unique, key=_pdf_selection_key)
        return (
            tuple(item for _, item in ordered[: self._max_selected_pdfs]),
            len(unique),
            duplicate_count,
        )


def _pdf_selection_key(
    candidate: tuple[int, HuataiReportListingItem],
) -> tuple[bool, int, int, int, int]:
    """Sort dated reports newest-first, then retain listing-order tie-breakers."""
    discovery_position, item = candidate
    publication_date = item.publication_date
    is_dated = isinstance(publication_date, date)
    return (
        not is_dated,
        -publication_date.toordinal() if is_dated else 0,
        item.section_position,
        item.item_position,
        discovery_position,
    )


def _is_usable_pdf_url(value: object) -> bool:
    """Require the public URL invariants enforced by the PDF extractor."""
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    parsed = urlparse(value)
    return (
        parsed.scheme in {"http", "https"}
        and parsed.hostname in HTFC_DOMAINS
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
        and parsed.path.lower().endswith(".pdf")
    )


def _require_nonempty_text(field_name: str, value: object) -> str:
    """Validate a required source-metadata label before any network discovery."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_text_tuple(field_name: str, value: object) -> tuple[str, ...]:
    """Validate detached tuple-only source metadata for the adapter boundary."""
    if not isinstance(value, tuple) or any(
        not isinstance(member, str) or not member.strip() for member in value
    ):
        raise ValueError(f"{field_name} must be a tuple of non-empty strings")
    return tuple(value)


def _require_reliability_score(value: object) -> int:
    """Require the same bounded reliability scale used by MarketInformation."""
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise ValueError("reliability_score must be an integer between 1 and 5")
    return value


def _require_positive_limit(field_name: str, value: object) -> int:
    """Require a bounded, non-boolean collector selection limit."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return value
