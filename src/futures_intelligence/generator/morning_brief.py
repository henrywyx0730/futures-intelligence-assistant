"""Deterministic text generation for a morning market brief."""

from futures_intelligence.analyst import (
    AggregatedMarketView,
    CommodityMarketView,
    MarketAnalysisAggregator,
)
from futures_intelligence.models import MarketAnalysis
from futures_intelligence.processing import MarketTrendChange


class MorningBriefGenerator:
    """Generate a concise morning brief from analyses ordered by relevance."""

    MAX_ANALYSES = 5

    def generate(
        self,
        analyses: list[MarketAnalysis],
        market_view: AggregatedMarketView | None = None,
        trend_change: MarketTrendChange | None = None,
        *,
        commodity_market_views: tuple[CommodityMarketView, ...] = (),
    ) -> str:
        """Return a deterministic report containing the most relevant analyses."""
        selected_analyses = analyses[: self.MAX_ANALYSES]
        market_view = market_view or MarketAnalysisAggregator().aggregate(analyses)
        lines = ["Morning Futures Brief", "", "Market Overview"]
        if commodity_market_views:
            for view in commodity_market_views:
                lines.extend(
                    [
                        "",
                        view.commodity_label,
                        f"Direction: {view.overall_direction.title()}",
                        f"Confidence: {view.confidence_score}/100",
                        f"Signals: {view.analysis_count}",
                        "Reasoning:",
                    ]
                )
                if view.reasoning_details:
                    lines.extend(f"- {detail}" for detail in view.reasoning_details)
                else:
                    lines.append("- No reasoning details available.")
        else:
            lines.extend(
                [
                    f"Direction: {market_view.overall_market_direction.title()}",
                    f"Confidence: {market_view.aggregated_confidence_score}/100",
                    "Reasoning:",
                ]
            )
            if market_view.reasoning_details:
                lines.extend(f"- {detail}" for detail in market_view.reasoning_details)
            else:
                lines.append("- No reasoning details available.")
        if _has_comparable_trend_change(trend_change):
            assert trend_change is not None
            assert trend_change.previous_direction is not None
            assert trend_change.latest_direction is not None
            lines.extend(
                [
                    "",
                    "Trend Change",
                    f"Previous Direction: {trend_change.previous_direction.title()}",
                    f"Current Direction: {trend_change.latest_direction.title()}",
                    f"Confidence Change: {trend_change.confidence_change:+d} points",
                ]
            )
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


def _has_comparable_trend_change(trend_change: MarketTrendChange | None) -> bool:
    """Return whether a trend change contains both historical directions."""
    return (
        trend_change is not None
        and trend_change.previous_direction is not None
        and trend_change.latest_direction is not None
    )
