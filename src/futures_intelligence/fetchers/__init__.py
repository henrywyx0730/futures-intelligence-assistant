"""Report-content fetcher abstractions and implementations."""

from futures_intelligence.fetchers.huatai_futures import (
    FetchedResearchReport,
    HuataiFetchResult,
    HuataiFuturesReportFetcher,
    HuataiListingDiscovery,
    HuataiPdfListingEntry,
    HuataiReportListingItem,
    discover_listing_links,
)
from futures_intelligence.fetchers.huatai_pdf import (
    HuataiPdfAttachment,
    HuataiPdfDownloadLimits,
    HuataiPdfExtractionResult,
    HuataiPdfParseLimits,
    HuataiPdfTextExtractor,
)
from futures_intelligence.fetchers.local_file import LocalFileResearchReportFetcher
from futures_intelligence.fetchers.research_report import ResearchReportFetcher

__all__ = [
    "FetchedResearchReport",
    "HuataiFetchResult",
    "HuataiFuturesReportFetcher",
    "HuataiListingDiscovery",
    "HuataiPdfListingEntry",
    "HuataiReportListingItem",
    "HuataiPdfAttachment",
    "HuataiPdfDownloadLimits",
    "HuataiPdfExtractionResult",
    "HuataiPdfParseLimits",
    "HuataiPdfTextExtractor",
    "LocalFileResearchReportFetcher",
    "ResearchReportFetcher",
    "discover_listing_links",
]
