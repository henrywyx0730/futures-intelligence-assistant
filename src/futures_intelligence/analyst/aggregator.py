"""Deterministic aggregation of individual market analyses."""

from __future__ import annotations

from dataclasses import dataclass

from futures_intelligence.models import MarketAnalysis


SOURCE_TYPE_WEIGHTS = {
    "official_data": 120,
    "research_report": 110,
    "market_data": 100,
    "rss": 80,
}


@dataclass(frozen=True)
class AggregatedMarketView:
    """A combined directional view derived from individual analyses."""

    overall_market_direction: str
    aggregated_confidence_score: int
    reasoning_details: tuple[str, ...]
    analysis_count: int


class MarketAnalysisAggregator:
    """Combine deterministic MarketAnalysis outputs into one market view."""

    def aggregate(self, analyses: list[MarketAnalysis]) -> AggregatedMarketView:
        """Return a confidence-weighted direction and combined reasoning details."""
        _validate_analyses(analyses)
        if not analyses:
            return AggregatedMarketView(
                overall_market_direction="neutral",
                aggregated_confidence_score=0,
                reasoning_details=("No analyses available for aggregation.",),
                analysis_count=0,
            )

        bullish_weight = sum(
            _signal_weight(analysis)
            for analysis in analyses
            if analysis.market_direction == "bullish"
        )
        bearish_weight = sum(
            _signal_weight(analysis)
            for analysis in analyses
            if analysis.market_direction == "bearish"
        )
        source_weights = [_source_weight(analysis) for analysis in analyses]
        return AggregatedMarketView(
            overall_market_direction=_overall_direction(
                bullish_weight, bearish_weight
            ),
            aggregated_confidence_score=sum(
                analysis.confidence_score * source_weight
                for analysis, source_weight in zip(analyses, source_weights)
            )
            // sum(source_weights),
            reasoning_details=_combined_reasoning_details(analyses),
            analysis_count=len(analyses),
        )


def _validate_analyses(analyses: list[MarketAnalysis]) -> None:
    """Reject non-analysis values before computing an aggregate."""
    if not all(isinstance(analysis, MarketAnalysis) for analysis in analyses):
        raise TypeError("analyses must contain only MarketAnalysis instances")


def _overall_direction(bullish_weight: int, bearish_weight: int) -> str:
    """Resolve weighted directional support, treating ties as neutral."""
    if bullish_weight > bearish_weight:
        return "bullish"
    if bearish_weight > bullish_weight:
        return "bearish"
    return "neutral"


def _signal_weight(analysis: MarketAnalysis) -> int:
    """Return confidence weighted by the underlying source's reliability and type."""
    return analysis.confidence_score * _source_weight(analysis)


def _source_weight(analysis: MarketAnalysis) -> int:
    """Return an integer source weight using reliability and source-type metadata."""
    information = analysis.market_information
    source_type_weight = SOURCE_TYPE_WEIGHTS.get(
        information.source_type.lower(), 100
    )
    return information.reliability_score * source_type_weight


def _combined_reasoning_details(
    analyses: list[MarketAnalysis],
) -> tuple[str, ...]:
    """Combine reasoning in input order while omitting duplicate details."""
    combined: list[str] = []
    for analysis in analyses:
        for detail in analysis.reasoning_details:
            if detail not in combined:
                combined.append(detail)
    return tuple(combined)
