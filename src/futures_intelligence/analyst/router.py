"""Deterministic routing of normalized information to analyst implementations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from futures_intelligence.analyst.base import BaseAnalyst
from futures_intelligence.analyst.llm import LLMAnalyst
from futures_intelligence.analyst.rule_based import RuleBasedAnalyst
from futures_intelligence.models import MarketAnalysis, MarketInformation


ROUTED_SOURCE_TYPES = frozenset(
    {"market_data", "official_data", "research_report", "rss"}
)


class AnalystRouter:
    """Select an analyst implementation from a normalized item's source type."""

    def __init__(
        self,
        analyst_overrides: Mapping[str, BaseAnalyst] | None = None,
        *,
        llm_enabled: bool = False,
        llm_source_types: Iterable[str] = (),
        llm_analyst: LLMAnalyst | None = None,
    ) -> None:
        """Configure the initial deterministic source-type routing table."""
        self._default_analyst = RuleBasedAnalyst()
        self._analysts_by_source_type = {
            source_type: self._default_analyst for source_type in ROUTED_SOURCE_TYPES
        }
        if analyst_overrides is not None:
            self._analysts_by_source_type.update(
                {
                    source_type: analyst
                    for source_type, analyst in analyst_overrides.items()
                    if not isinstance(analyst, LLMAnalyst)
                }
            )
        self._llm_analyst = llm_analyst
        if llm_enabled and llm_analyst is not None:
            for source_type in llm_source_types:
                if isinstance(source_type, str):
                    self._analysts_by_source_type[source_type] = llm_analyst

    def select_analyst(self, information: MarketInformation) -> BaseAnalyst:
        """Return the deterministic analyst for one normalized information item."""
        if not isinstance(information, MarketInformation):
            raise TypeError("information must be a MarketInformation instance")
        return self._analysts_by_source_type.get(
            information.source_type,
            self._default_analyst,
        )

    def analyze(self, information: list[MarketInformation]) -> list[MarketAnalysis]:
        """Analyze items in order while enforcing the configured LLM run limit."""
        analyses: list[MarketAnalysis] = []
        llm_items_processed = 0
        for item in information:
            analyst = self.select_analyst(item)
            if analyst is self._llm_analyst:
                if llm_items_processed >= self._llm_analyst.max_items_per_run:
                    analyst = self._default_analyst
                else:
                    llm_items_processed += 1
            analyses.extend(analyst.analyze([item]))
        return analyses
