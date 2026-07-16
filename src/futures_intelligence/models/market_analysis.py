"""Normalized output from a market-information analyst."""

from __future__ import annotations

from dataclasses import dataclass

from futures_intelligence.models.market_information import MarketInformation


@dataclass
class MarketAnalysis:
    """A concise analysis associated with one normalized market-information item."""

    market_information: MarketInformation
    summary: str

    def __post_init__(self) -> None:
        """Validate the analysis source and normalize its summary."""
        if not isinstance(self.market_information, MarketInformation):
            raise TypeError("market_information must be a MarketInformation instance")
        if not isinstance(self.summary, str) or not (summary := self.summary.strip()):
            raise ValueError("summary must be a non-empty string")
        self.summary = summary
