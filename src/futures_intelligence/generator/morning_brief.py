"""Deterministic text generation for a morning market brief."""

from futures_intelligence.analyst import (
    AggregatedMarketView,
    MarketAnalysisAggregator,
)
from futures_intelligence.models import MarketAnalysis


class MorningBriefGenerator:
    """Generate a concise morning brief from analyses ordered by relevance."""

    MAX_ANALYSES = 5

    def generate(
        self,
        analyses: list[MarketAnalysis],
        market_view: AggregatedMarketView | None = None,
    ) -> str:
        """Return a deterministic report containing the most relevant analyses."""
        selected_analyses = analyses[: self.MAX_ANALYSES]
        market_view = market_view or MarketAnalysisAggregator().aggregate(analyses)
        lines = [
            "Morning Futures Brief",
            "",
            "Market Overview",
            f"Direction: {market_view.overall_market_direction.title()}",
            f"Confidence: {market_view.aggregated_confidence_score}/100",
            "Reasoning:",
        ]
        if market_view.reasoning_details:
            lines.extend(f"- {detail}" for detail in market_view.reasoning_details)
        else:
            lines.append("- No reasoning details available.")
        lines.extend(
            [
                "",
                f"Top analyses: {len(selected_analyses)} of {len(analyses)}",
            ]
        )

        for index, analysis in enumerate(selected_analyses, start=1):
            information = analysis.market_information
            lines.extend(
                [
                    "",
                    f"{index}. {information.title} ({information.source})",
                    f"   {analysis.summary}",
                ]
            )

        return "\n".join(lines)
