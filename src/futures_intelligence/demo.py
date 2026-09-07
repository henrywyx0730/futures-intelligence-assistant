"""Bounded presentation for the manual Huatai research demo."""

from __future__ import annotations

from futures_intelligence.analyst import (
    AggregatedMarketView,
    CommodityMarketView,
    MarketAnalysisAggregator,
)
from futures_intelligence.analyst.commodity_relevance import (
    CommodityRelevanceAssessment,
)
from futures_intelligence.models import MarketAnalysis, MarketInformation


HTFC_DEMO_REPORT_LIMIT = 3
MAX_TITLE_CHARACTERS = 300
MAX_PRESENTATION_CHARACTERS = 240
MAX_REASONING_DETAILS = 3
_MAJOR_SEPARATOR = "=" * 60
_SECTION_SEPARATOR = "-" * 60


class HuataiDemoError(ValueError):
    """Raised when bounded evaluated inputs cannot form a truthful demo."""


def format_htfc_demo(
    information: list[MarketInformation],
    analyses: list[MarketAnalysis],
    relevance: tuple[CommodityRelevanceAssessment, ...],
) -> str:
    """Aggregate and format an already-evaluated bounded Huatai report batch."""
    _validate_demo_inputs(information, analyses, relevance)
    aggregator = MarketAnalysisAggregator()
    commodity_views = aggregator.aggregate_by_commodity(analyses)
    global_view = aggregator.aggregate(analyses)

    lines = [
        _MAJOR_SEPARATOR,
        "FUTURES INTELLIGENCE DEMO",
        _MAJOR_SEPARATOR,
        "",
        f"Huatai reports collected: {len(information)}",
    ]
    for index, (item, analysis, assessment) in enumerate(
        zip(information, analyses, relevance),
        start=1,
    ):
        lines.extend(_format_report(index, item, analysis, assessment))

    lines.extend(["", _SECTION_SEPARATOR, "COMMODITY VIEW", _SECTION_SEPARATOR])
    if commodity_views:
        for view in commodity_views:
            lines.extend(_format_commodity_view(view))
    else:
        lines.append("No Primary commodity views were resolved.")

    lines.extend(_format_global_view(global_view))
    lines.extend(_format_demo_brief(commodity_views, global_view))
    lines.extend(
        [
            "",
            (
                f"Demo complete: {len(analyses)} reports analyzed, "
                f"{len(commodity_views)} commodity views generated."
            ),
        ]
    )
    return "\n".join(lines)


def _validate_demo_inputs(
    information: list[MarketInformation],
    analyses: list[MarketAnalysis],
    relevance: tuple[CommodityRelevanceAssessment, ...],
) -> None:
    """Require aligned, bounded, identity-preserving evaluated inputs."""
    if not isinstance(information, list) or not all(
        isinstance(item, MarketInformation) for item in information
    ):
        raise HuataiDemoError(
            "Huatai demo information must be a MarketInformation list."
        )
    if not information:
        raise HuataiDemoError("no Huatai research reports were available for the demo.")
    if len(information) > HTFC_DEMO_REPORT_LIMIT:
        raise HuataiDemoError("the demo received more than 3 Huatai research reports.")
    if len({id(item) for item in information}) != len(information):
        raise HuataiDemoError("the demo received duplicate report object identities.")
    if not isinstance(analyses, list) or not all(
        isinstance(analysis, MarketAnalysis) for analysis in analyses
    ):
        raise HuataiDemoError("Huatai demo analyses must be a MarketAnalysis list.")
    if type(relevance) is not tuple or not all(
        isinstance(assessment, CommodityRelevanceAssessment)
        for assessment in relevance
    ):
        raise HuataiDemoError(
            "Huatai demo relevance must be a CommodityRelevanceAssessment tuple."
        )
    if len(analyses) != len(information) or len(relevance) != len(information):
        raise HuataiDemoError("Huatai demo evaluation results are not aligned.")
    if any(
        analysis.market_information is not item
        for item, analysis in zip(information, analyses)
    ):
        raise HuataiDemoError("Huatai demo analysis identity was not preserved.")


def _format_report(
    index: int,
    item: MarketInformation,
    analysis: MarketAnalysis,
    relevance: CommodityRelevanceAssessment,
) -> list[str]:
    """Format one report without exposing body text or arbitrary metadata."""
    primary_labels = tuple(entry.commodity_label for entry in relevance.primary)
    lines = [
        "",
        f"REPORT {index}",
        f"Title: {_bounded_text(item.title, MAX_TITLE_CHARACTERS)}",
        f"Published: {item.published_time.isoformat()}",
        f"Source: {_bounded_text(item.source, MAX_PRESENTATION_CHARACTERS)}",
        f"Primary commodities: {', '.join(primary_labels) or 'none'}",
        f"Summary: {_bounded_text(analysis.summary, MAX_PRESENTATION_CHARACTERS)}",
        f"Report direction: {analysis.market_direction}",
        f"Confidence: {analysis.confidence_score}/100",
        f"Directional provenance: {analysis.directional_provenance}",
        "Commodity-scoped direction:",
    ]
    if analysis.commodity_directional_evidence:
        lines.extend(
            f"- {evidence.commodity_label}: {evidence.market_direction}"
            for evidence in analysis.commodity_directional_evidence
        )
    else:
        lines.append("- none resolved")
    lines.append("Reasoning:")
    lines.extend(_bounded_reasoning(analysis.reasoning_details))
    return lines


def _format_commodity_view(view: CommodityMarketView) -> list[str]:
    """Format one existing commodity aggregate with bounded support."""
    return [
        "",
        view.commodity_label,
        f"Direction: {view.overall_direction}",
        f"Confidence: {view.confidence_score}/100",
        f"Reports: {view.analysis_count}",
        "Key reasoning:",
        *_bounded_reasoning(view.reasoning_details),
    ]


def _format_global_view(view: AggregatedMarketView) -> list[str]:
    """Format the existing global aggregate without changing its semantics."""
    return [
        "",
        _SECTION_SEPARATOR,
        "MARKET OVERVIEW",
        _SECTION_SEPARATOR,
        f"Global direction: {view.overall_market_direction}",
        f"Global confidence: {view.aggregated_confidence_score}/100",
        f"Reports analyzed: {view.analysis_count}",
        "Key context:",
        *_bounded_reasoning(view.reasoning_details),
    ]


def _format_demo_brief(
    commodity_views: tuple[CommodityMarketView, ...],
    global_view: AggregatedMarketView,
) -> list[str]:
    """Format a compact deterministic commodity-first demo summary."""
    lines = ["", _SECTION_SEPARATOR, "DEMO BRIEF", _SECTION_SEPARATOR]
    if commodity_views:
        lines.extend(
            _bounded_bullet(
                f"{view.commodity_label} — {view.overall_direction} "
                f"({view.confidence_score}/100, {view.analysis_count} "
                f"{'report' if view.analysis_count == 1 else 'reports'})"
            )
            for view in commodity_views
        )
    else:
        lines.append("- No Primary commodity views were resolved.")
    lines.append(
        _bounded_text(
            "Market-wide view: "
            f"{global_view.overall_market_direction} "
            f"({global_view.aggregated_confidence_score}/100)",
            MAX_PRESENTATION_CHARACTERS,
        )
    )
    return lines


def _bounded_reasoning(details: tuple[str, ...]) -> list[str]:
    """Render at most three normalized reasoning details."""
    if not details:
        return ["- none"]
    lines = [_bounded_bullet(detail) for detail in details[:MAX_REASONING_DETAILS]]
    omitted_count = len(details) - MAX_REASONING_DETAILS
    if omitted_count > 0:
        lines.append(_bounded_bullet(f"{omitted_count} additional details omitted."))
    return lines


def _bounded_bullet(value: str) -> str:
    """Format one bounded bullet value."""
    return f"- {_bounded_text(value, MAX_PRESENTATION_CHARACTERS)}"


def _bounded_text(value: str, maximum_characters: int) -> str:
    """Normalize terminal whitespace and truncate one display-only value."""
    normalized = " ".join(value.split())
    if len(normalized) <= maximum_characters:
        return normalized
    return f"{normalized[: maximum_characters - 3]}..."
