"""Safe HTML-only Huatai Futures research-report retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
import re
from typing import Callable, Protocol
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


HTFC_DOMAINS = frozenset({"htfc.com", "www.htfc.com"})
DEFAULT_USER_AGENT = "FuturesIntelligenceAssistant/0.1"


@dataclass(frozen=True)
class FetchedResearchReport:
    """Structured report material ready for collector normalization."""

    title: str
    published_time: datetime
    content: str
    url: str
    report_type: str | None = None
    author: str | None = None


@dataclass(frozen=True)
class HuataiListingDiscovery:
    """Immutable classification of links exposed by an official listing."""

    html_detail_links: tuple[str, ...] = ()
    pdf_attachment_links: tuple[str, ...] = ()
    unsupported_links: tuple[str, ...] = ()


@dataclass(frozen=True)
class HuataiFetchResult:
    """Bounded listing discovery and parsed report results."""

    discovered_link_count: int
    selected_urls: tuple[str, ...]
    reports: tuple[FetchedResearchReport, ...]
    discovery: HuataiListingDiscovery | None = None


class _Response(Protocol):
    headers: object

    def read(self, size: int = -1) -> bytes: ...
    def geturl(self) -> str: ...
    def __enter__(self) -> "_Response": ...
    def __exit__(self, *args: object) -> None: ...


class HuataiFuturesReportFetcher:
    """Fetch a small, allowlisted set of HTML reports from Huatai Futures."""

    def __init__(
        self,
        listing_url: str,
        max_reports: int = 3,
        timeout_seconds: float = 10.0,
        max_response_bytes: int = 1_000_000,
        opener: Callable[..., _Response] = urlopen,
    ) -> None:
        if max_reports < 1:
            raise ValueError("max_reports must be at least 1")
        if timeout_seconds <= 0 or max_response_bytes < 1:
            raise ValueError("timeout and response size must be positive")
        _validate_htfc_url(listing_url)
        self.listing_url = listing_url
        self.max_reports = max_reports
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self._opener = opener

    def fetch_reports(self) -> HuataiFetchResult:
        """Discover, bound, and parse official HTML detail pages in listing order."""
        listing_html, listing_url = self._fetch_html(self.listing_url)
        discovery = discover_listing_links(listing_html, listing_url)
        selected = discovery.html_detail_links[: self.max_reports]
        reports: list[FetchedResearchReport] = []
        for detail_url in selected:
            detail_html, canonical_url = self._fetch_html(detail_url)
            report = _parse_detail_page(detail_html, canonical_url)
            if report is not None:
                reports.append(report)
        return HuataiFetchResult(
            len(discovery.html_detail_links), selected, tuple(reports), discovery
        )

    def _fetch_html(self, url: str) -> tuple[str, str]:
        _validate_htfc_url(url)
        request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
        try:
            with self._opener(request, timeout=self.timeout_seconds) as response:
                canonical_url = response.geturl()
                _validate_htfc_url(canonical_url)
                payload = response.read(self.max_response_bytes + 1)
                if len(payload) > self.max_response_bytes:
                    raise ValueError("response exceeds configured size limit")
                charset = _response_charset(response.headers)
        except (OSError, ValueError):
            raise
        except Exception as error:
            raise RuntimeError("unable to fetch Huatai Futures HTML") from error
        return payload.decode(charset or "utf-8", errors="replace"), canonical_url


def _validate_htfc_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in HTFC_DOMAINS:
        raise ValueError("Huatai Futures URLs must use http(s) and an official htfc.com domain")


def _response_charset(headers: object) -> str | None:
    getter = getattr(headers, "get_content_charset", None)
    if callable(getter):
        return getter()
    content_type = getattr(headers, "get", lambda *_: "")("Content-Type", "")
    match = re.search(r"charset=([^;\s]+)", str(content_type), re.IGNORECASE)
    return match.group(1) if match else None


class _ListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


_HTML_DETAIL_PATTERN = re.compile(r"^/main/a/\d{8}/\d+\.shtml$", re.IGNORECASE)


def discover_listing_links(html: str, base_url: str) -> HuataiListingDiscovery:
    """Classify official listing anchors without fetching any discovered link."""
    parser = _ListingParser()
    parser.feed(html)
    html_links: list[str] = []
    pdf_links: list[str] = []
    unsupported_links: list[str] = []
    for href in parser.hrefs:
        url = urljoin(base_url, href)
        parsed = urlparse(url)
        is_official = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname in HTFC_DOMAINS
        )
        if not is_official:
            if url not in unsupported_links:
                unsupported_links.append(url)
            continue
        path = parsed.path or ""
        if _HTML_DETAIL_PATTERN.fullmatch(path):
            if url not in html_links:
                html_links.append(url)
            continue
        if path.lower().endswith(".pdf"):
            if url not in pdf_links:
                pdf_links.append(url)
            continue
        if url not in unsupported_links:
            unsupported_links.append(url)
    return HuataiListingDiscovery(
        html_detail_links=tuple(html_links),
        pdf_attachment_links=tuple(pdf_links),
        unsupported_links=tuple(unsupported_links),
    )


class _DetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._page_title = ""
        self._in_title = False
        self._in_h1 = False
        self._ignored = 0
        self._content_depth = 0
        self._content: list[str] = []
        self._all: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"script", "style", "nav", "footer", "header"}:
            self._ignored += 1
        if tag in {"h1", "title"}:
            self._in_title = True
        if tag == "h1":
            self._in_h1 = True
        marker = f"{attributes.get('id', '')} {attributes.get('class', '')}".lower()
        if tag in {"article", "main"} or any(key in marker for key in ("content", "detail", "article", "report")):
            self._content_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "nav", "footer", "header"} and self._ignored:
            self._ignored -= 1
        if tag in {"h1", "title"}:
            self._in_title = False
        if tag == "h1":
            self._in_h1 = False
        if tag in {"article", "main", "div", "section"} and self._content_depth:
            self._content_depth -= 1

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text or self._ignored:
            return
        if self._in_h1:
            self.title = text
        elif self._in_title and not self._page_title:
            self._page_title = text
        self._all.append(text)
        if self._content_depth:
            self._content.append(text)

    @property
    def text(self) -> str:
        return " ".join(self._content or self._all)


def _parse_detail_page(html: str, url: str) -> FetchedResearchReport | None:
    parser = _DetailParser()
    parser.feed(html)
    text = " ".join(parser.text.split())
    title = parser.title or parser._page_title or _label_value(text, "标题") or _label_value(text, "Title")
    published_time = _published_time(text)
    if not title or not text or published_time is None:
        return None
    return FetchedResearchReport(
        title=title,
        published_time=published_time,
        content=text,
        url=url,
        report_type=_label_value(text, "报告类型") or _label_value(text, "报告类型"),
        author=_label_value(text, "作者") or _label_value(text, "Author"),
    )


def _label_value(text: str, label: str) -> str | None:
    match = re.search(rf"{re.escape(label)}\s*[:：]\s*([^\s|；;]+)", text, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _published_time(text: str) -> datetime | None:
    match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日)?(?:\s+(\d{1,2}):(\d{2}))?", text)
    if not match:
        return None
    year, month, day, hour, minute = match.groups()
    return datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0), tzinfo=timezone(timedelta(hours=8)))
