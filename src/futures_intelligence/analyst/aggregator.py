"""Deterministic aggregation of individual market analyses."""

from __future__ import annotations

from dataclasses import dataclass

from futures_intelligence.analyst.commodity_matcher import CommodityMatch, CommodityMatcher
from futures_intelligence.analyst.market_movement import MarketMovementDetector
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


@dataclass(frozen=True)
class CommodityMarketView:
    """One directionally weighted market view for an article-level commodity."""

    commodity_key: str
    commodity_label: str
    analysis_count: int
    overall_direction: str
    confidence_score: int
    reasoning_details: tuple[str, ...]


@dataclass(frozen=True)
class _CommodityContribution:
    """One immutable commodity-scoped interpretation of an existing analysis."""

    analysis: MarketAnalysis
    direction: str
    reasoning_details: tuple[str, ...]


class MarketAnalysisAggregator:
    """Combine deterministic MarketAnalysis outputs into one market view."""

    def __init__(self, commodity_matcher: CommodityMatcher | None = None) -> None:
        """Use the shared article-level matcher for optional commodity grouping."""
        self._commodity_matcher = commodity_matcher or CommodityMatcher()
        self._market_movement_detector = MarketMovementDetector()

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
        overall_direction = _overall_direction(bullish_weight, bearish_weight)
        return AggregatedMarketView(
            overall_market_direction=overall_direction,
            aggregated_confidence_score=sum(
                analysis.confidence_score * source_weight
                for analysis, source_weight in zip(analyses, source_weights)
            )
            // sum(source_weights),
            reasoning_details=_combined_reasoning_details(analyses, overall_direction),
            analysis_count=len(analyses),
        )

    def aggregate_by_commodity(
        self, analyses: list[MarketAnalysis]
    ) -> tuple[CommodityMarketView, ...]:
        """Return stable commodity views without creating analyses or API calls."""
        _validate_analyses(analyses)
        grouped: dict[str, tuple[CommodityMatch, list[MarketAnalysis], set[int], int]] = {}
        for index, analysis in enumerate(analyses):
            for match in self._commodity_matcher.match(analysis.market_information):
                group = grouped.get(match.commodity_key)
                if group is None:
                    group = (match, [], set(), index)
                    grouped[match.commodity_key] = group
                _, group_analyses, seen_analysis_ids, _ = group
                if id(analysis) not in seen_analysis_ids:
                    group_analyses.append(analysis)
                    seen_analysis_ids.add(id(analysis))

        configured_order = {
            key: index
            for index, key in enumerate(self._commodity_matcher.commodity_order)
        }
        ordered_groups = sorted(
            grouped.values(),
            key=lambda group: (
                configured_order.get(
                    group[0].commodity_key,
                    len(configured_order) + group[3],
                ),
                group[3],
            ),
        )
        configured_labels = tuple(
            definition.commodity_label
            for definition in self._commodity_matcher.commodity_ordered_matches
        )
        return tuple(
            _commodity_market_view(
                match,
                group_analyses,
                configured_labels,
                self._market_movement_detector,
                self._commodity_matcher,
            )
            for match, group_analyses, _, _ in ordered_groups
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
    overall_direction: str,
) -> tuple[str, ...]:
    """Combine only direction-consistent, non-boilerplate reasoning in input order."""
    if overall_direction in {"bullish", "bearish"}:
        supporting_analyses = [
            analysis
            for analysis in analyses
            if analysis.market_direction == overall_direction
        ]
    elif any(analysis.market_direction == "bullish" for analysis in analyses) and any(
        analysis.market_direction == "bearish" for analysis in analyses
    ):
        return ("Conflicting bullish and bearish directional signals were detected.",)
    else:
        supporting_analyses = [
            analysis for analysis in analyses if analysis.market_direction == "neutral"
        ]

    combined: list[str] = []
    for analysis in supporting_analyses:
        for detail in analysis.reasoning_details:
            if _is_source_scope_detail(detail):
                continue
            if detail not in combined:
                combined.append(detail)
    return tuple(combined)


def _is_source_scope_detail(detail: str) -> bool:
    """Exclude legacy source-scope commodity boilerplate from market reasoning."""
    return detail.lower().startswith("configured source commodities:")


def _commodity_market_view(
    match: CommodityMatch,
    analyses: list[MarketAnalysis],
    configured_labels: tuple[str, ...],
    movement_detector: MarketMovementDetector,
    commodity_matcher: CommodityMatcher,
) -> CommodityMarketView:
    """Build one scoped view using the existing aggregate calculations unchanged."""
    contributions = tuple(
        _commodity_contribution(analysis, match, movement_detector, commodity_matcher)
        for analysis in analyses
    )
    overall_direction, confidence_score, reasoning_details = _aggregate_contributions(
        contributions
    )
    return CommodityMarketView(
        commodity_key=match.commodity_key,
        commodity_label=match.commodity_label,
        analysis_count=len(analyses),
        overall_direction=overall_direction,
        confidence_score=confidence_score,
        reasoning_details=_commodity_reasoning_details(
            reasoning_details,
            match.commodity_label,
            configured_labels,
        ),
    )


def _commodity_contribution(
    analysis: MarketAnalysis,
    match: CommodityMatch,
    movement_detector: MarketMovementDetector,
    commodity_matcher: CommodityMatcher,
) -> _CommodityContribution:
    """Apply a resolved commodity movement without changing the analysis object."""
    signals = movement_detector.detect_by_commodity(
        analysis.market_information,
        commodity_matcher.match(analysis.market_information),
    )
    signal = next(
        (signal for signal in signals if signal.commodity_key == match.commodity_key),
        None,
    )
    if signal is None or signal.priority == 0:
        return _CommodityContribution(
            analysis=analysis,
            direction=analysis.market_direction,
            reasoning_details=analysis.reasoning_details,
        )
    return _CommodityContribution(
        analysis=analysis,
        direction=signal.direction,
        reasoning_details=tuple(
            detail
            for detail in analysis.reasoning_details
            if not detail.startswith("Observed market movement:")
        )
        + (f"Observed market movement: {signal.evidence}.",),
    )


def _aggregate_contributions(
    contributions: tuple[_CommodityContribution, ...],
) -> tuple[str, int, tuple[str, ...]]:
    """Reuse global source-aware weighting for immutable commodity contributions."""
    bullish_weight = sum(
        _signal_weight(contribution.analysis)
        for contribution in contributions
        if contribution.direction == "bullish"
    )
    bearish_weight = sum(
        _signal_weight(contribution.analysis)
        for contribution in contributions
        if contribution.direction == "bearish"
    )
    source_weights = [_source_weight(contribution.analysis) for contribution in contributions]
    overall_direction = _overall_direction(bullish_weight, bearish_weight)
    return (
        overall_direction,
        sum(
            contribution.analysis.confidence_score * source_weight
            for contribution, source_weight in zip(contributions, source_weights)
        )
        // sum(source_weights),
        _combined_contribution_reasoning(contributions, overall_direction),
    )


def _combined_contribution_reasoning(
    contributions: tuple[_CommodityContribution, ...],
    overall_direction: str,
) -> tuple[str, ...]:
    """Combine only final-direction commodity contribution reasoning in input order."""
    if overall_direction in {"bullish", "bearish"}:
        supporting = tuple(
            contribution
            for contribution in contributions
            if contribution.direction == overall_direction
        )
    elif any(contribution.direction == "bullish" for contribution in contributions) and any(
        contribution.direction == "bearish" for contribution in contributions
    ):
        return ("Conflicting bullish and bearish directional signals were detected.",)
    else:
        supporting = tuple(
            contribution
            for contribution in contributions
            if contribution.direction == "neutral"
        )

    combined: list[str] = []
    for contribution in supporting:
        for detail in contribution.reasoning_details:
            if _is_source_scope_detail(detail):
                continue
            if detail not in combined:
                combined.append(detail)
    return tuple(combined)


def _commodity_reasoning_details(
    details: tuple[str, ...],
    commodity_label: str,
    configured_labels: tuple[str, ...],
) -> tuple[str, ...]:
    """Retain support while replacing combined detection boilerplate per commodity."""
    combined: list[str] = []
    for detail in details:
        if detail.lower().startswith("detected commodity keywords:"):
            scoped_detail = f"Detected commodity keywords: {commodity_label}."
        elif any(
            label != commodity_label and label.casefold() in detail.casefold()
            for label in configured_labels
        ):
            continue
        else:
            scoped_detail = detail
        if scoped_detail not in combined:
            combined.append(scoped_detail)
    return tuple(combined)
