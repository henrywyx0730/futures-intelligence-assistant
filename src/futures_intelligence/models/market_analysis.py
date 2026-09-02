"""Normalized output from a market-information analyst."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from futures_intelligence.models.market_information import MarketInformation


VALID_MARKET_DIRECTIONS = frozenset({"bullish", "bearish", "neutral"})
DirectionalProvenance = Literal[
    "metadata_direction",
    "observed_market_movement",
    "direct_fundamental",
    "deterministic_text_signal",
    "no_directional_signal",
    "qualified_only",
    "same_market_conflict",
    "horizon_conflict",
    "cross_commodity_abstention",
    "structural_only",
    "external_analyst",
    "unspecified",
]
VALID_DIRECTIONAL_PROVENANCES = frozenset(
    {
        "metadata_direction",
        "observed_market_movement",
        "direct_fundamental",
        "deterministic_text_signal",
        "no_directional_signal",
        "qualified_only",
        "same_market_conflict",
        "horizon_conflict",
        "cross_commodity_abstention",
        "structural_only",
        "external_analyst",
        "unspecified",
    }
)
_NEUTRAL_ONLY_PROVENANCES = frozenset(
    {
        "no_directional_signal",
        "qualified_only",
        "same_market_conflict",
        "horizon_conflict",
        "cross_commodity_abstention",
        "structural_only",
    }
)


@dataclass
class MarketAnalysis:
    """A concise analysis associated with one normalized market-information item."""

    market_information: MarketInformation
    summary: str
    market_direction: str = "neutral"
    confidence_score: int = 0
    reasoning_details: tuple[str, ...] = ()
    directional_provenance: DirectionalProvenance = "unspecified"

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
        self.directional_provenance = _normalize_directional_provenance(
            self.directional_provenance
        )
        if (
            self.directional_provenance in _NEUTRAL_ONLY_PROVENANCES
            and self.market_direction != "neutral"
        ):
            raise ValueError(
                f"{self.directional_provenance} provenance requires neutral direction"
            )
        if (
            self.directional_provenance == "direct_fundamental"
            and self.market_direction == "neutral"
        ):
            raise ValueError(
                "direct_fundamental provenance requires bullish or bearish direction"
            )


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


def _normalize_directional_provenance(value: object) -> DirectionalProvenance:
    """Normalize and validate one bounded final-decision provenance value."""
    if not isinstance(value, str) or not (normalized := value.strip().lower()):
        raise ValueError("directional_provenance must be a non-empty string")
    if normalized not in VALID_DIRECTIONAL_PROVENANCES:
        raise ValueError(
            "directional_provenance must be one of: "
            f"{', '.join(sorted(VALID_DIRECTIONAL_PROVENANCES))}"
        )
    return cast(DirectionalProvenance, normalized)
