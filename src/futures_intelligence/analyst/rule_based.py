"""Deterministic rule-based market analyst."""

from __future__ import annotations

from futures_intelligence.analyst.base import BaseAnalyst
from futures_intelligence.models import MarketAnalysis, MarketInformation


COMMODITY_KEYWORDS = (
    ("crude oil", "Crude Oil"),
    ("oil", "Crude Oil"),
    ("butadiene rubber", "Butadiene Rubber"),
    ("styrene", "Styrene"),
    ("copper", "Copper"),
    ("aluminum", "Aluminum"),
    ("silver", "Silver"),
    ("gold", "Gold"),
    ("iron ore", "Iron Ore"),
    ("coal", "Coal"),
    ("soybean meal", "Soybean Meal"),
    ("corn", "Corn"),
)


class RuleBasedAnalyst(BaseAnalyst):
    """Create basic market interpretations from commodity keywords."""

    def analyze(self, information: list[MarketInformation]) -> list[MarketAnalysis]:
        """Return one deterministic analysis for each information item."""
        return [
            MarketAnalysis(item, self._summary_for(item)) for item in information
        ]

    def _summary_for(self, item: MarketInformation) -> str:
        """Build a concise interpretation from title and content keywords."""
        text = f"{item.title} {item.content}".lower()
        commodities = _detected_commodities(text)
        if commodities:
            return (
                f"Detected commodity focus: {', '.join(commodities)}. "
                "Review potential supply, demand, inventory, and cost implications."
            )
        return (
            "No tracked commodity keywords detected. "
            "Review the information for broader market context."
        )


def _detected_commodities(text: str) -> tuple[str, ...]:
    """Return unique commodity labels in a stable configured order."""
    detected: list[str] = []
    for keyword, commodity in COMMODITY_KEYWORDS:
        if keyword in text and commodity not in detected:
            detected.append(commodity)
    return tuple(detected)
