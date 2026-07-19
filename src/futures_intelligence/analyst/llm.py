"""API-free placeholder for a future large-language-model analyst."""

from __future__ import annotations

from futures_intelligence.analyst.base import BaseAnalyst
from futures_intelligence.models import MarketAnalysis, MarketInformation


class LLMAnalyst(BaseAnalyst):
    """Return deterministic unavailable analyses until LLM integration is added."""

    def analyze(self, information: list[MarketInformation]) -> list[MarketAnalysis]:
        """Return one neutral placeholder analysis for each information item."""
        return [
            MarketAnalysis(
                market_information=item,
                summary="LLM analysis is unavailable in the current application configuration.",
                market_direction="neutral",
                confidence_score=0,
                reasoning_details=(
                    "LLM analyst placeholder: external model integration is unavailable.",
                ),
            )
            for item in information
        ]
