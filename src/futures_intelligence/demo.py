"""Bounded presentation for the manual Huatai research demo."""

from __future__ import annotations

from datetime import datetime, timezone

from futures_intelligence.analyst import (
    AggregatedMarketView,
    CommodityMarketView,
    MarketAnalysisAggregator,
)
from futures_intelligence.analyst.commodity_matcher import CommodityMatcher
from futures_intelligence.analyst.commodity_relevance import (
    CommodityRelevanceAssessment,
)
from futures_intelligence.fetchers import HuataiReportListingItem
from futures_intelligence.models import MarketAnalysis, MarketInformation


HTFC_DEMO_REPORT_LIMIT = 3
MAX_TITLE_CHARACTERS = 300
MAX_PRESENTATION_CHARACTERS = 240
MAX_REASONING_DETAILS = 3
_MAJOR_SEPARATOR = "=" * 60
_SECTION_SEPARATOR = "-" * 60
_TITLE_MATCH_TIMESTAMP = datetime(1970, 1, 1, tzinfo=timezone.utc)
_DIRECTION_LABELS = {
    "bullish": "偏多 (bullish)",
    "bearish": "偏空 (bearish)",
    "neutral": "中性 (neutral)",
}
DEMO_SAMPLING_DESCRIPTION = (
    "选样规则：优先选择标题明确命中已跟踪品种的华泰报告，"
    "不足 3 篇时按最新报告补足。"
)


class HuataiDemoError(ValueError):
    """Raised when bounded evaluated inputs cannot form a truthful demo."""


def select_htfc_demo_pdf_items(
    items: tuple[HuataiReportListingItem, ...],
    *,
    matcher: CommodityMatcher | None = None,
    maximum_items: int = HTFC_DEMO_REPORT_LIMIT,
) -> tuple[HuataiReportListingItem, ...]:
    """Prioritize title-matched PDFs before stable broader-report fallback."""
    if type(items) is not tuple or not all(
        isinstance(item, HuataiReportListingItem) for item in items
    ):
        raise HuataiDemoError("demo PDF candidates must be a Huatai listing item tuple")
    if (
        isinstance(maximum_items, bool)
        or not isinstance(maximum_items, int)
        or maximum_items < 1
        or maximum_items > HTFC_DEMO_REPORT_LIMIT
    ):
        raise HuataiDemoError("demo PDF selection limit must be between 1 and 3")

    resolved_matcher = matcher if matcher is not None else CommodityMatcher()
    relevant: list[HuataiReportListingItem] = []
    broader: list[HuataiReportListingItem] = []
    seen_urls: set[str] = set()
    for item in items:
        if item.canonical_url in seen_urls:
            continue
        seen_urls.add(item.canonical_url)
        target = (
            relevant
            if _listing_title_has_commodity(item, resolved_matcher)
            else broader
        )
        target.append(item)
    return tuple((relevant + broader)[:maximum_items])


def _listing_title_has_commodity(
    item: HuataiReportListingItem,
    matcher: CommodityMatcher,
) -> bool:
    """Use the canonical article matcher with title-only listing metadata."""
    probe = MarketInformation(
        title=item.listing_title,
        source="Huatai Futures listing",
        source_type="research_report",
        published_time=_TITLE_MATCH_TIMESTAMP,
        content=".",
        reliability_score=1,
    )
    evidence = matcher.match_with_evidence(probe)
    return any(occurrence.field == "title" for occurrence in evidence.occurrences)


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
        "期货情报 DEMO",
        _MAJOR_SEPARATOR,
        "",
        f"已选华泰报告：{len(information)}",
        DEMO_SAMPLING_DESCRIPTION,
    ]
    for index, (item, analysis, assessment) in enumerate(
        zip(information, analyses, relevance),
        start=1,
    ):
        lines.extend(_format_report(index, item, analysis, assessment))

    lines.extend(["", _SECTION_SEPARATOR, "品种视图", _SECTION_SEPARATOR])
    if commodity_views:
        for view in commodity_views:
            lines.extend(_format_commodity_view(view))
    else:
        lines.append("本次所选报告未形成明确的 Primary 品种视图。")

    lines.extend(_format_global_view(global_view))
    lines.extend(_format_demo_brief(commodity_views, global_view))
    lines.extend(
        [
            "",
            (
                f"Demo 完成：已分析 {len(analyses)} 篇报告，"
                f"生成 {len(commodity_views)} 个品种视图。"
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
        f"报告 {index}",
        f"标题：{_bounded_text(item.title, MAX_TITLE_CHARACTERS)}",
        f"发布日期：{item.published_time.isoformat()}",
        f"来源：{_bounded_text(item.source, MAX_PRESENTATION_CHARACTERS)}",
        f"主要品种：{', '.join(primary_labels) or '未识别到明确 Primary 品种'}",
        f"摘要：{_bounded_text(analysis.summary, MAX_PRESENTATION_CHARACTERS)}",
        f"报告方向：{_direction_label(analysis.market_direction)}",
        f"方向置信度：{analysis.confidence_score}/100",
        f"判定依据：{analysis.directional_provenance}",
        "品种级方向：",
    ]
    if analysis.commodity_directional_evidence:
        lines.extend(
            f"- {evidence.commodity_label}：{_direction_label(evidence.market_direction)}"
            for evidence in analysis.commodity_directional_evidence
        )
    else:
        lines.append("- 未解析出品种级方向")
    lines.append("核心依据：")
    lines.extend(_bounded_reasoning(analysis.reasoning_details))
    return lines


def _format_commodity_view(view: CommodityMarketView) -> list[str]:
    """Format one existing commodity aggregate with bounded support."""
    return [
        "",
        view.commodity_label,
        f"方向：{_direction_label(view.overall_direction)}",
        f"聚合方向置信度：{view.confidence_score}/100",
        f"报告数：{view.analysis_count}",
        "核心依据：",
        *_bounded_reasoning(view.reasoning_details),
    ]


def _format_global_view(view: AggregatedMarketView) -> list[str]:
    """Format the existing global aggregate without changing its semantics."""
    return [
        "",
        _SECTION_SEPARATOR,
        "市场概览",
        _SECTION_SEPARATOR,
        f"市场整体方向：{_direction_label(view.overall_market_direction)}",
        f"聚合方向置信度：{view.aggregated_confidence_score}/100",
        f"分析报告数：{view.analysis_count}",
        "核心背景：",
        *_bounded_reasoning(view.reasoning_details),
    ]


def _format_demo_brief(
    commodity_views: tuple[CommodityMarketView, ...],
    global_view: AggregatedMarketView,
) -> list[str]:
    """Format a compact deterministic commodity-first demo summary."""
    lines = ["", _SECTION_SEPARATOR, "早间视图 / DEMO BRIEF", _SECTION_SEPARATOR]
    if commodity_views:
        lines.extend(
            _bounded_bullet(
                f"{view.commodity_label} — {_direction_label(view.overall_direction)}，"
                f"聚合方向置信度 {view.confidence_score}/100，"
                f"{view.analysis_count} 篇报告"
            )
            for view in commodity_views
        )
    else:
        lines.append("- 本次所选报告未形成明确的 Primary 品种视图。")
    lines.append(
        _bounded_text(
            "市场整体："
            f"{_direction_label(global_view.overall_market_direction)}，"
            f"聚合方向置信度 {global_view.aggregated_confidence_score}/100",
            MAX_PRESENTATION_CHARACTERS,
        )
    )
    return lines


def _direction_label(direction: str) -> str:
    """Return one presentation-only bilingual direction label."""
    try:
        return _DIRECTION_LABELS[direction]
    except KeyError as error:
        raise HuataiDemoError("demo received an unsupported market direction") from error


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
