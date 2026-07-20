"""Deterministic, cost-controlled selection of production LLM candidates."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from futures_intelligence.models import MarketInformation


@dataclass(frozen=True)
class LLMCandidateSelection:
    """The eligible count and ordered instances selected for one LLM run."""

    eligible_count: int
    selected_items: tuple[MarketInformation, ...]


class LLMCandidateSelector:
    """Select eligible ranked items without invoking any analyst or external service."""

    def __init__(
        self,
        *,
        enabled: bool,
        source_types: Iterable[str],
        min_reliability_score: int,
        max_items_per_run: int,
    ) -> None:
        """Configure a static production candidate policy."""
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a boolean")
        if (
            isinstance(min_reliability_score, bool)
            or not isinstance(min_reliability_score, int)
            or not 1 <= min_reliability_score <= 5
        ):
            raise ValueError("min_reliability_score must be an integer between 1 and 5")
        if (
            isinstance(max_items_per_run, bool)
            or not isinstance(max_items_per_run, int)
            or max_items_per_run < 1
        ):
            raise ValueError("max_items_per_run must be a positive integer")
        self._enabled = enabled
        self._source_types = frozenset(
            source_type.strip()
            for source_type in source_types
            if isinstance(source_type, str) and source_type.strip()
        )
        self._min_reliability_score = min_reliability_score
        self._max_items_per_run = max_items_per_run

    def select(
        self,
        information: list[MarketInformation],
    ) -> LLMCandidateSelection:
        """Return ordered eligible instances, capped once for the entire run."""
        if not self._enabled:
            return LLMCandidateSelection(eligible_count=0, selected_items=())

        eligible_items = tuple(
            item
            for item in information
            if item.source_type in self._source_types
            and item.reliability_score >= self._min_reliability_score
            and isinstance(item.content, str)
            and item.content.strip()
        )
        return LLMCandidateSelection(
            eligible_count=len(eligible_items),
            selected_items=eligible_items[: self._max_items_per_run],
        )
