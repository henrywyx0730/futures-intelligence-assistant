"""Safe HTML-only Huatai Futures research-report retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
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
    """Immutable, section-scoped classification of official report entries."""

    report_items: tuple["HuataiReportListingItem", ...] = ()
    ignored_non_report_links: tuple[str, ...] = ()

    @property
    def html_detail_links(self) -> tuple[str, ...]:
        """Backward-compatible URLs derived only from report listing items."""
        return tuple(
            item.canonical_url
            for item in self.report_items
            if item.link_kind == "html_detail"
        )

    @property
    def pdf_attachment_links(self) -> tuple[str, ...]:
        """Backward-compatible URLs derived only from report listing items."""
        return tuple(
            item.canonical_url
            for item in self.report_items
            if item.link_kind == "pdf_attachment"
        )

    @property
    def unsupported_links(self) -> tuple[str, ...]:
        """Compatibility name for links excluded from report discovery."""
        return self.ignored_non_report_links

    @property
    def pdf_attachments(self) -> tuple["HuataiPdfListingEntry", ...]:
        """Legacy PDF context derived only from report listing items."""
        return tuple(
            HuataiPdfListingEntry(
                url=item.canonical_url,
                title=item.listing_title,
                publication_date=item.publication_date,
                report_type=item.report_type,
            )
            for item in self.report_items
            if item.link_kind == "pdf_attachment"
        )


@dataclass(frozen=True)
class HuataiReportListingItem:
    """One validated report link and its metadata from the same list record."""

    canonical_url: str
    link_kind: str
    listing_title: str
    publication_date: date | None
    report_type: str
    section_position: int
    item_position: int


@dataclass(frozen=True)
class HuataiPdfListingEntry:
    """Explicit title and date context attached to one classified PDF link."""

    url: str
    title: str | None = None
    publication_date: date | None = None
    report_type: str | None = None


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


_REPORT_TYPES = frozenset({"专题报告", "周期报告", "策略报告"})


@dataclass
class _OpenElement:
    tag: str
    attributes: dict[str, str | None]
    hidden: bool
    is_report_box: bool = False
    report_type: str | None = None
    section_position: int | None = None
    report_list: bool = False
    record: "_PendingListingRecord | None" = None
    captures_label: bool = False
    captures_date: bool = False
    captures_title: bool = False
    text: list[str] | None = None


@dataclass
class _PendingListingRecord:
    report_type: str
    section_position: int
    item_position: int
    date_text: list[str]
    href: str | None = None
    title_text: list[str] | None = None


class _ListingParser(HTMLParser):
    """Collect only direct records from official Huatai report boxes."""

    def __init__(self) -> None:
        super().__init__()
        self.report_records: list[_PendingListingRecord] = []
        self.ignored_hrefs: list[str] = []
        self._stack: list[_OpenElement] = []
        self._next_section_position = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        parent = self._stack[-1] if self._stack else None
        enclosing_report_box = self._current_report_box()
        hidden = _is_hidden(attributes) or (
            parent.hidden if enclosing_report_box is not None and parent is not None else False
        )
        element = _OpenElement(tag, attributes, hidden)
        element.is_report_box = tag == "div" and _has_class(attributes, "ztreport_box")
        self._stack.append(element)
        report_box = self._current_report_box()

        if tag == "span" and self._is_box_label(report_box, hidden):
            element.captures_label = True
            element.text = []
        elif tag == "ul" and self._is_report_list(parent, report_box, hidden):
            element.report_list = True
            element.report_type = report_box.report_type if report_box is not None else None
            element.section_position = report_box.section_position if report_box is not None else None
        elif tag == "li" and parent is not None and parent.report_list and not hidden:
            assert parent.report_type is not None and parent.section_position is not None
            item_position = sum(
                1
                for record in self.report_records
                if record.section_position == parent.section_position
            )
            element.record = _PendingListingRecord(
                parent.report_type,
                parent.section_position,
                item_position,
                [],
            )
        elif tag == "span" and parent is not None and parent.record is not None and not hidden:
            element.captures_date = True
            element.text = parent.record.date_text
        elif tag == "a":
            href = attributes.get("href")
            if href:
                if parent is not None and parent.record is not None and not hidden:
                    parent.record.href = href
                    parent.record.title_text = []
                    element.captures_title = True
                    element.text = parent.record.title_text
                else:
                    self.ignored_hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        if not self._stack or self._stack[-1].tag != tag:
            return
        element = self._stack.pop()
        if element.captures_label:
            report_type = " ".join(element.text or ()).strip()
            report_box = self._current_report_box()
            if report_box is not None and report_type in _REPORT_TYPES:
                report_box.report_type = report_type
                report_box.section_position = self._next_section_position
                self._next_section_position += 1
        if element.record is not None and element.record.href and element.record.title_text:
            self.report_records.append(element.record)

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        for element in reversed(self._stack):
            if element.text is not None:
                element.text.append(text)
                return

    def _current_report_box(self) -> _OpenElement | None:
        return next(
            (element for element in reversed(self._stack) if element.is_report_box),
            None,
        )

    def _is_box_label(self, report_box: _OpenElement | None, hidden: bool) -> bool:
        if report_box is None or hidden or len(self._stack) < 4:
            return False
        span, paragraph, heading, box = self._stack[-1], self._stack[-2], self._stack[-3], self._stack[-4]
        return (
            span.tag == "span"
            and paragraph.tag == "p"
            and heading.tag == "div"
            and _has_class(heading.attributes, "compre_top")
            and box is report_box
        )

    def _is_report_list(
        self,
        parent: _OpenElement | None,
        report_box: _OpenElement | None,
        hidden: bool,
    ) -> bool:
        return (
            parent is report_box
            and report_box is not None
            and not hidden
            and report_box.report_type in _REPORT_TYPES
            and _has_class(self._stack[-1].attributes, "clranking")
        )


_HTML_DETAIL_PATTERN = re.compile(r"^/main/a/\d{8}/\d+\.shtml$", re.IGNORECASE)


def discover_listing_links(html: str, base_url: str) -> HuataiListingDiscovery:
    """Classify only report-list anchors without fetching discovered links."""
    parser = _ListingParser()
    parser.feed(html)
    items: list[HuataiReportListingItem] = []
    ignored_links: list[str] = []
    seen_urls: set[str] = set()
    for record in parser.report_records:
        url = urljoin(base_url, record.href or "")
        parsed = urlparse(url)
        is_official = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname in HTFC_DOMAINS
        )
        if not is_official:
            ignored_links.append(url)
            continue
        path = parsed.path or ""
        if _HTML_DETAIL_PATTERN.fullmatch(path):
            link_kind = "html_detail"
        elif path.lower().endswith(".pdf"):
            link_kind = "pdf_attachment"
        else:
            ignored_links.append(url)
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        items.append(
            HuataiReportListingItem(
                canonical_url=url,
                link_kind=link_kind,
                listing_title=" ".join(record.title_text or ()).strip(),
                publication_date=_listing_date(" ".join(record.date_text)),
                report_type=record.report_type,
                section_position=record.section_position,
                item_position=record.item_position,
            )
    )
    for href in parser.ignored_hrefs:
        ignored_links.append(urljoin(base_url, href))
    return HuataiListingDiscovery(
        report_items=tuple(items),
        ignored_non_report_links=tuple(ignored_links),
    )


def _has_class(attributes: dict[str, str | None], expected: str) -> bool:
    return expected in (attributes.get("class") or "").split()


def _is_hidden(attributes: dict[str, str | None]) -> bool:
    style = (attributes.get("style") or "").replace(" ", "").lower()
    return (
        "hidden" in attributes
        or attributes.get("aria-hidden", "").lower() == "true"
        or "display:none" in style
    )


def _listing_date(value: str) -> date | None:
    match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日)?", value)
    if match is None:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


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
