"""Deterministic routing of normalized information to analyst implementations."""

from __future__ import annotations

from collections.abc import Mapping

from futures_intelligence.analyst.base import BaseAnalyst
from futures_intelligence.analyst.rule_based import RuleBasedAnalyst
from futures_intelligence.models import MarketInformation


ROUTED_SOURCE_TYPES = frozenset(
    {"market_data", "official_data", "research_report", "rss"}
)


class AnalystRouter:
    """Select an analyst implementation from a normalized item's source type."""

    def __init__(
        self, analyst_overrides: Mapping[str, BaseAnalyst] | None = None
    ) -> None:
        """Configure the initial deterministic source-type routing table."""
        self._default_analyst = RuleBasedAnalyst()
        self._analysts_by_source_type = {
            source_type: self._default_analyst for source_type in ROUTED_SOURCE_TYPES
        }
        if analyst_overrides is not None:
            self._analysts_by_source_type.update(analyst_overrides)

    def select_analyst(self, information: MarketInformation) -> BaseAnalyst:
        """Return the deterministic analyst for one normalized information item."""
        if not isinstance(information, MarketInformation):
            raise TypeError("information must be a MarketInformation instance")
        return self._analysts_by_source_type.get(
            information.source_type,
            self._default_analyst,
        )
