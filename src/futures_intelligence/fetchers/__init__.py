"""Report-content fetcher abstractions and implementations."""

from futures_intelligence.fetchers.local_file import LocalFileResearchReportFetcher
from futures_intelligence.fetchers.research_report import ResearchReportFetcher

__all__ = ["LocalFileResearchReportFetcher", "ResearchReportFetcher"]
