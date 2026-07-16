"""RSS feed collector."""

from __future__ import annotations

from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from futures_intelligence.collectors.base import BaseCollector
from futures_intelligence.models import MarketInformation


class RSSCollector(BaseCollector):
    """Collect and normalize items from an RSS feed."""

    def __init__(
        self,
        rss_url: str,
        source: str | None = None,
        timeout: float = 10.0,
        category: tuple[str, ...] = (),
        commodities: tuple[str, ...] = (),
        regions: tuple[str, ...] = (),
        reliability_score: int = 3,
    ) -> None:
        self.rss_url = rss_url
        self.source = source
        self.timeout = timeout
        self.category = category
        self.commodities = commodities
        self.regions = regions
        self.reliability_score = reliability_score

    def collect(self) -> list[MarketInformation]:
        """Fetch an RSS feed and return its valid normalized items."""
        request = Request(
            self.rss_url,
            headers={"User-Agent": "FuturesIntelligenceAssistant/0.1"},
        )
        with urlopen(request, timeout=self.timeout) as response:
            feed_content = response.read()

        try:
            root = ElementTree.fromstring(feed_content)
        except ElementTree.ParseError:
            return []

        channel = root.find("channel")
        if channel is None:
            return []

        source = self.source or _text(channel.find("title")) or self.rss_url
        information: list[MarketInformation] = []
        for item in channel.findall("item"):
            market_information = _parse_item(
                item,
                source,
                self.category,
                self.commodities,
                self.regions,
                self.reliability_score,
            )
            if market_information is not None:
                information.append(market_information)
        return information


def _parse_item(
    item: ElementTree.Element,
    source: str,
    category: tuple[str, ...],
    commodities: tuple[str, ...],
    regions: tuple[str, ...],
    reliability_score: int,
) -> MarketInformation | None:
    """Convert a valid RSS item to normalized market information."""
    title = _text(item.find("title"))
    content = _text(item.find("description"))
    published_text = _text(item.find("pubDate"))
    if not title or not content or not published_text:
        return None

    try:
        published_time = parsedate_to_datetime(published_text)
        return MarketInformation(
            title=title,
            source=source,
            source_type="rss",
            published_time=published_time,
            content=content,
            category=category,
            commodities=commodities,
            regions=regions,
            reliability_score=reliability_score,
            url=_text(item.find("link")),
        )
    except (TypeError, ValueError):
        return None


def _text(element: ElementTree.Element | None) -> str | None:
    """Return stripped element text, or None when no text is present."""
    if element is None or element.text is None:
        return None
    return element.text.strip() or None
