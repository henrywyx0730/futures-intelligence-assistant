"""Local research-report collector foundation."""

from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from futures_intelligence.collectors.base import BaseCollector
from futures_intelligence.fetchers import (
    HuataiFetchResult,
    LocalFileResearchReportFetcher,
    ResearchReportFetcher,
)
from futures_intelligence.models import MarketInformation


class ResearchReportCollector(BaseCollector):
    """Load and normalize one configured local research report."""

    def __init__(
        self,
        content_path: str | Path | None,
        source: str,
        title: str | None = None,
        published_time: datetime | None = None,
        category: tuple[str, ...] = (),
        commodities: tuple[str, ...] = (),
        regions: tuple[str, ...] = (),
        reliability_score: int = 3,
        fetcher: ResearchReportFetcher | None = None,
        structured_fetcher: object | None = None,
    ) -> None:
        self.content_path = Path(content_path) if content_path is not None else None
        self.source = source
        self.title = title
        self.published_time = published_time
        self.category = category
        self.commodities = commodities
        self.regions = regions
        self.reliability_score = reliability_score
        self.fetcher = fetcher or (
            LocalFileResearchReportFetcher(self.content_path)
            if self.content_path is not None
            else None
        )
        self.structured_fetcher = structured_fetcher
        self.last_fetch_result: HuataiFetchResult | None = None

    def collect(self) -> list[MarketInformation]:
        """Load a local text or HTML report into one normalized item."""
        if self.structured_fetcher is not None:
            return self._collect_structured_reports()
        if self.fetcher is None or self.content_path is None:
            return []
        raw_content = self.fetcher.fetch()
        if raw_content is None:
            return []

        try:
            published_time = self.published_time or datetime.fromtimestamp(
                self.content_path.stat().st_mtime,
                tz=timezone.utc,
            )
        except OSError:
            return []

        content = _normalize_content(raw_content, self.content_path.suffix)
        if not content:
            return []

        return [
            MarketInformation(
                title=self.title or _title_from_path(self.content_path),
                source=self.source,
                source_type="research_report",
                published_time=published_time,
                content=content,
                category=self.category,
                commodities=self.commodities,
                regions=self.regions,
                reliability_score=self.reliability_score,
                url=self.content_path.resolve().as_uri(),
            )
        ]

    def _collect_structured_reports(self) -> list[MarketInformation]:
        """Normalize source-specific HTML report records without changing local behavior."""
        fetch_reports = getattr(self.structured_fetcher, "fetch_reports", None)
        if not callable(fetch_reports):
            return []
        result = fetch_reports()
        if not isinstance(result, HuataiFetchResult):
            return []
        self.last_fetch_result = result
        return [
            MarketInformation(
                title=report.title,
                source=self.source,
                source_type="research_report",
                published_time=report.published_time,
                content=report.content,
                category=self.category,
                commodities=(),
                regions=self.regions,
                reliability_score=self.reliability_score,
                url=report.url,
                metadata={
                    key: value
                    for key, value in (
                        ("report_type", report.report_type),
                        ("author", report.author),
                    )
                    if value is not None
                },
            )
            for report in result.reports
            if report.content.strip()
        ]


def _normalize_content(content: str, suffix: str) -> str:
    """Return plain text from a local text or HTML report."""
    if suffix.lower() in {".html", ".htm"}:
        parser = _HTMLTextExtractor()
        parser.feed(content)
        content = parser.text
    return " ".join(content.split())


def _title_from_path(path: Path) -> str:
    """Create a readable fallback title from a local report filename."""
    return path.stem.replace("_", " ").replace("-", " ").title()


class _HTMLTextExtractor(HTMLParser):
    """Extract visible text from a small local HTML report."""

    def __init__(self) -> None:
        super().__init__()
        self._text: list[str] = []
        self._ignored_depth = 0

    @property
    def text(self) -> str:
        """Return the accumulated visible text."""
        return " ".join(self._text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Ignore script and style content."""
        del attrs
        if tag in {"script", "style"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        """Resume text collection after ignored content ends."""
        if tag in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        """Collect visible non-empty text fragments."""
        if not self._ignored_depth and data.strip():
            self._text.append(data)
