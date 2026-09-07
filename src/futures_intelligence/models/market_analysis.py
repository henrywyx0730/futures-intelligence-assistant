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
_COMMODITY_EVIDENCE_PROVENANCES = frozenset(
    {"direct_fundamental", "cross_commodity_abstention"}
)


@dataclass(frozen=True)
class CommodityDirectionalEvidence:
    """One resolved direct-fundamental direction for a canonical commodity."""

    commodity_key: str
    commodity_label: str
    market_direction: Literal["bullish", "bearish"]

    def __post_init__(self) -> None:
        """Fail closed for non-canonical or non-directional evidence values."""
        if (
            not isinstance(self.commodity_key, str)
            or not self.commodity_key
            or self.commodity_key != self.commodity_key.strip()
            or self.commodity_key != self.commodity_key.lower()
        ):
            raise ValueError("commodity_key must be a canonical non-empty string")
        if (
            not isinstance(self.commodity_label, str)
            or not self.commodity_label
            or self.commodity_label != self.commodity_label.strip()
        ):
            raise ValueError("commodity_label must be a normalized non-empty string")
        if (
            not isinstance(self.market_direction, str)
            or self.market_direction not in {"bullish", "bearish"}
        ):
            raise ValueError("commodity evidence direction must be bullish or bearish")


@dataclass
class MarketAnalysis:
    """A concise analysis associated with one normalized market-information item."""

    market_information: MarketInformation
    summary: str
    market_direction: str = "neutral"
    confidence_score: int = 0
    reasoning_details: tuple[str, ...] = ()
    directional_provenance: DirectionalProvenance = "unspecified"
    commodity_directional_evidence: tuple[CommodityDirectionalEvidence, ...] = ()

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
        _validate_commodity_directional_evidence(
            self.commodity_directional_evidence,
            self.directional_provenance,
            self.market_direction,
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


def _validate_commodity_directional_evidence(
    values: tuple[CommodityDirectionalEvidence, ...],
    provenance: DirectionalProvenance,
    report_direction: str,
) -> None:
    """Validate immutable scoped evidence and its report-level compatibility."""
    if type(values) is not tuple:
        raise TypeError(
            "commodity_directional_evidence must be a tuple of "
            "CommodityDirectionalEvidence objects"
        )
    if not all(isinstance(value, CommodityDirectionalEvidence) for value in values):
        raise TypeError(
            "commodity_directional_evidence must be a tuple of "
            "CommodityDirectionalEvidence objects"
        )
    commodity_keys = tuple(value.commodity_key for value in values)
    if len(commodity_keys) != len(set(commodity_keys)):
        raise ValueError("commodity directional evidence keys must be unique")
    if not values:
        return
    if provenance not in _COMMODITY_EVIDENCE_PROVENANCES:
        raise ValueError(
            "commodity directional evidence requires direct_fundamental or "
            "cross_commodity_abstention provenance"
        )
    directions = {value.market_direction for value in values}
    if provenance == "direct_fundamental" and directions != {report_direction}:
        raise ValueError(
            "direct_fundamental commodity evidence must match report direction"
        )
    if provenance == "cross_commodity_abstention" and (
        len(values) < 2 or directions != {"bullish", "bearish"}
    ):
        raise ValueError(
            "cross_commodity_abstention evidence requires opposing commodity directions"
        )
