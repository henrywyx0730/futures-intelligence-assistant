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
        llm_candidates: Iterable[MarketInformation] = (),
        llm_analyst: LLMAnalyst | None = None,
        max_llm_items: int | None = None,
    ) -> None:
        """Configure default analysts and authoritative selected LLM instances."""
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
        self._llm_candidate_ids = {
            id(item) for item in llm_candidates if isinstance(item, MarketInformation)
        }
        if max_llm_items is None and llm_analyst is not None:
            max_llm_items = llm_analyst.max_items_per_run
        if max_llm_items is not None and (
            isinstance(max_llm_items, bool)
            or not isinstance(max_llm_items, int)
            or max_llm_items < 1
        ):
            raise ValueError("max_llm_items must be a positive integer or None")
        self._max_llm_items = max_llm_items or 0

    def select_analyst(self, information: MarketInformation) -> BaseAnalyst:
        """Return the deterministic analyst for one normalized information item."""
        if not isinstance(information, MarketInformation):
            raise TypeError("information must be a MarketInformation instance")
        if self._llm_analyst is not None and id(information) in self._llm_candidate_ids:
            return self._llm_analyst
        return self._analysts_by_source_type.get(information.source_type, self._default_analyst)

    def analyze(self, information: list[MarketInformation]) -> list[MarketAnalysis]:
        """Analyze items in order with only selected instances eligible for LLM calls."""
        analyses: list[MarketAnalysis] = []
        llm_items_processed = 0
        processed_candidate_ids: set[int] = set()
        for item in information:
            analyst = self.select_analyst(item)
            if analyst is self._llm_analyst:
                item_id = id(item)
                if (
                    item_id in processed_candidate_ids
                    or llm_items_processed >= self._max_llm_items
                ):
                    analyst = self._default_analyst
                else:
                    processed_candidate_ids.add(item_id)
                    llm_items_processed += 1
            analyses.extend(analyst.analyze([item]))
        return analyses
