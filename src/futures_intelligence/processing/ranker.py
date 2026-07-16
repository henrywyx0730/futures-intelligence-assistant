"""Deterministic ranking for normalized market information."""

from __future__ import annotations

from datetime import datetime, timezone

from futures_intelligence.models import MarketInformation


DEFAULT_CATEGORIES = frozenset(
    {
        "macro",
        "energy",
        "metals",
        "black",
        "chemical",
        "agriculture",
        "financial",
        "financial_futures",
        "commodities",
        "futures",
    }
)
DEFAULT_COMMODITIES = frozenset(
    {
        "crude_oil",
        "BR",
        "styrene",
        "PTA",
        "copper",
        "aluminum",
        "silver",
        "iron_ore",
        "rebar",
        "coal",
        "soybean_meal",
        "corn",
        "hog",
        "IF",
        "IC",
        "IM",
        "T",
        "TL",
        "gold",
    }
)


class InformationRanker:
    """Rank information by reliability, relevance, and publication freshness."""

    def __init__(
        self,
        relevant_categories: tuple[str, ...] = tuple(DEFAULT_CATEGORIES),
        relevant_commodities: tuple[str, ...] = tuple(DEFAULT_COMMODITIES),
        reference_time: datetime | None = None,
    ) -> None:
        self.relevant_categories = frozenset(relevant_categories)
        self.relevant_commodities = frozenset(relevant_commodities)
        self.reference_time = reference_time

    def rank(self, information: list[MarketInformation]) -> list[MarketInformation]:
        """Return the same information objects ordered from highest to lowest score."""
        reference_time = self.reference_time or datetime.now(timezone.utc)
        return sorted(
            information,
            key=lambda item: self._score(item, reference_time),
            reverse=True,
        )

    def _score(self, item: MarketInformation, reference_time: datetime) -> float:
        """Calculate a simple deterministic score for one information item."""
        category_matches = len(set(item.category) & self.relevant_categories)
        commodity_matches = len(set(item.commodities) & self.relevant_commodities)
        age_hours = max(
            0.0,
            (reference_time - item.published_time).total_seconds() / 3600,
        )
        freshness_score = max(0.0, 48.0 - age_hours) / 24.0

        return (
            item.reliability_score * 10
            + category_matches * 3
            + commodity_matches * 5
            + freshness_score
        )
