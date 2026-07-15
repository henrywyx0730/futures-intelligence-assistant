"""Deduplicate normalized market information."""

from __future__ import annotations

from futures_intelligence.models import MarketInformation


class InformationDeduplicator:
    """Remove duplicate and empty-content market information items."""

    def deduplicate(
        self, information: list[MarketInformation]
    ) -> list[MarketInformation]:
        """Return the first valid occurrence of each title and source-title key."""
        cleaned: list[MarketInformation] = []
        seen_titles: set[str] = set()
        seen_source_titles: set[tuple[str, str]] = set()

        for item in information:
            if not isinstance(item.content, str) or not item.content.strip():
                continue

            source_title = (item.source, item.title)
            if item.title in seen_titles or source_title in seen_source_titles:
                continue

            seen_titles.add(item.title)
            seen_source_titles.add(source_title)
            cleaned.append(item)

        return cleaned
