"""RSS feed collector."""

from __future__ import annotations

from email.utils import parsedate_to_datetime
from urllib.request import urlopen
from xml.etree import ElementTree

from futures_intelligence.collectors.base import BaseCollector
from futures_intelligence.models import MarketInformation


class RSSCollector(BaseCollector):
    """Collect and normalize items from an RSS feed."""

    def __init__(
        self, rss_url: str, source: str | None = None, timeout: float = 10.0
    ) -> None:
        self.rss_url = rss_url
        self.source = source
        self.timeout = timeout

    def collect(self) -> list[MarketInformation]:
        """Fetch an RSS feed and return its valid normalized items."""
        with urlopen(self.rss_url, timeout=self.timeout) as response:
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
            market_information = _parse_item(item, source)
            if market_information is not None:
                information.append(market_information)
        return information


def _parse_item(
    item: ElementTree.Element, source: str
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
            url=_text(item.find("link")),
        )
    except (TypeError, ValueError):
        return None


def _text(element: ElementTree.Element | None) -> str | None:
    """Return stripped element text, or None when no text is present."""
    if element is None or element.text is None:
        return None
    return element.text.strip() or None
