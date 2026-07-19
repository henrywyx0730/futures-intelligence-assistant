"""Normalized output from a market-information analyst."""

from __future__ import annotations

from dataclasses import dataclass

from futures_intelligence.models.market_information import MarketInformation


VALID_MARKET_DIRECTIONS = frozenset({"bullish", "bearish", "neutral"})


@dataclass
class MarketAnalysis:
    """A concise analysis associated with one normalized market-information item."""

    market_information: MarketInformation
    summary: str
    market_direction: str = "neutral"
    confidence_score: int = 0
    reasoning_details: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate the analysis source and normalize its summary."""
        if not isinstance(self.market_information, MarketInformation):
            raise TypeError("market_information must be a MarketInformation instance")
        if not isinstance(self.summary, str) or not (summary := self.summary.strip()):
            raise ValueError("summary must be a non-empty string")
        self.summary = summary
        if not isinstance(self.market_direction, str) or not (
            market_direction := self.market_direction.strip().lower()
        ):
            raise ValueError("market_direction must be a non-empty string")
        if market_direction not in VALID_MARKET_DIRECTIONS:
            raise ValueError(
                "market_direction must be one of: "
                f"{', '.join(sorted(VALID_MARKET_DIRECTIONS))}"
            )
        self.market_direction = market_direction
        if (
            isinstance(self.confidence_score, bool)
            or not isinstance(self.confidence_score, int)
            or not 0 <= self.confidence_score <= 100
        ):
            raise ValueError("confidence_score must be an integer between 0 and 100")
        self.reasoning_details = _normalize_reasoning_details(self.reasoning_details)


def _normalize_reasoning_details(values: tuple[str, ...]) -> tuple[str, ...]:
    """Strip and validate optional supporting reasoning details."""
    if not isinstance(values, tuple):
        raise TypeError("reasoning_details must be a tuple of strings")
    normalized_details: list[str] = []
    for value in values:
        if not isinstance(value, str) or not (normalized := value.strip()):
            raise ValueError("reasoning_details must contain non-empty strings")
        normalized_details.append(normalized)
    return tuple(normalized_details)
