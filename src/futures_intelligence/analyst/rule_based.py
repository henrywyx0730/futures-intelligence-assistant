"""Deterministic rule-based market analyst."""

from __future__ import annotations

from futures_intelligence.analyst.base import BaseAnalyst
from futures_intelligence.analyst.commodity_matcher import (
    CommodityMatch,
    CommodityMatcher,
    phrase_matches,
)
from futures_intelligence.analyst.commodity_relevance import CommodityRelevanceResolver
from futures_intelligence.analyst.fundamental_signal import (
    ChineseFundamentalSignalDetector,
    FundamentalSignal,
)
from futures_intelligence.analyst.market_movement import (
    NUMERICAL_PRIORITY,
    SETTLEMENT_PRIORITY,
    MarketMovementDetector,
    MarketMovementSignal,
)
from futures_intelligence.models import MarketAnalysis, MarketInformation

BULLISH_KEYWORDS = (
    "inventory declined",
    "inventories declined",
    "demand improved",
    "demand resilient",
    "supply risk",
    "supply risks",
    "supply disruption",
)
BEARISH_KEYWORDS = (
    "inventory increased",
    "inventories increased",
    "demand weakened",
    "supply increased",
    "oversupply",
)
COMMODITY_RULES = (
    (
        "Crude oil",
        frozenset({"Crude Oil"}),
        ("opec production cuts", "refinery outage", "inventory draw"),
        ("opec production increase", "refinery restart"),
    ),
    (
        "Gold",
        frozenset({"Gold"}),
        ("central bank buying", "safe haven demand", "weaker dollar"),
        ("higher real yields", "stronger dollar"),
    ),
    (
        "Agriculture",
        frozenset({"Corn", "Soybean Meal", "Wheat"}),
        ("drought", "crop damage", "poor harvest"),
        ("favorable weather", "record harvest", "crop conditions improved"),
    ),
)


class RuleBasedAnalyst(BaseAnalyst):
    """Create basic market interpretations from commodity keywords."""

    def __init__(
        self,
        commodity_matcher: CommodityMatcher | None = None,
        commodity_relevance_resolver: CommodityRelevanceResolver | None = None,
    ) -> None:
        """Load the configured commodity aliases."""
        self._commodity_matcher = (
            commodity_matcher if commodity_matcher is not None else CommodityMatcher()
        )
        self._commodity_relevance_resolver = (
            commodity_relevance_resolver
            if commodity_relevance_resolver is not None
            else CommodityRelevanceResolver(matcher=self._commodity_matcher)
        )
        self._market_movement_detector = MarketMovementDetector()
        self._fundamental_signal_detector = ChineseFundamentalSignalDetector()

    def analyze(self, information: list[MarketInformation]) -> list[MarketAnalysis]:
        """Return one deterministic analysis for each information item."""
        return [self._analysis_for(item) for item in information]

    def _analysis_for(self, item: MarketInformation) -> MarketAnalysis:
        """Build one rich, deterministic analysis without changing its summary."""
        text = f"{item.title} {item.content}".lower()
        if item.source_type == "research_report":
            relevance = self._commodity_relevance_resolver.assess(item)
            commodity_matches = relevance.lexical_matches
            primary_keys = {entry.commodity_key for entry in relevance.primary}
            primary_matches = tuple(
                match for match in commodity_matches if match.commodity_key in primary_keys
            )
            mentioned_keys = {entry.commodity_key for entry in relevance.mentioned}
            mentioned_matches = tuple(
                match for match in commodity_matches if match.commodity_key in mentioned_keys
            )
            commodities = _commodity_labels(primary_matches)
            mentioned_commodities = _commodity_labels(mentioned_matches)
            fundamental_signals = self._fundamental_signal_detector.detect(
                item,
                primary_matches,
                commodity_matches,
            )
            summary = _research_report_summary(commodities)
        else:
            commodity_matches = self._commodity_matcher.match(item)
            commodities = _commodity_labels(commodity_matches)
            mentioned_commodities = ()
            fundamental_signals = ()
            summary = _summary_for_commodities(commodities)
        market_direction, directional_details, directional_confidence = (
            _directional_signals(
                item,
                text,
                commodities,
                self._market_movement_detector.detect(item, commodity_matches),
                fundamental_signals,
            )
        )
        reasoning_details = [
            f"Source type: {item.source_type}; reliability score: {item.reliability_score}/5."
        ]
        if item.source_type == "research_report":
            if commodities:
                reasoning_details.append(
                    f"Primary commodity focus: {', '.join(commodities)}."
                )
            else:
                reasoning_details.append("No primary tracked commodity focus was detected.")
            if mentioned_commodities:
                reasoning_details.append(
                    f"Mentioned tracked commodities: {', '.join(mentioned_commodities)}."
                )
        elif commodities:
            reasoning_details.append(
                f"Detected commodity keywords: {', '.join(commodities)}."
            )
        reasoning_details.extend(directional_details)

        confidence_score = min(
            95,
            20
            + item.reliability_score * 10
            + (10 if commodities else 0)
            + directional_confidence,
        )
        return MarketAnalysis(
            market_information=item,
            summary=summary,
            market_direction=market_direction,
            confidence_score=confidence_score,
            reasoning_details=tuple(reasoning_details),
        )

def _commodity_labels(matches: tuple[CommodityMatch, ...]) -> tuple[str, ...]:
    """Return configured display labels from immutable matcher results."""
    return tuple(match.commodity_label for match in matches)


def _summary_for_commodities(commodities: tuple[str, ...]) -> str:
    """Build the established flat-matcher summary for non-research sources."""
    if commodities:
        return (
            f"Detected commodity focus: {', '.join(commodities)}. "
            "Review potential supply, demand, inventory, and cost implications."
        )
    return (
        "No tracked commodity keywords detected. "
        "Review the information for broader market context."
    )


def _research_report_summary(primary_commodities: tuple[str, ...]) -> str:
    """Describe only title-confirmed research-report commodity focus."""
    if primary_commodities:
        return _summary_for_commodities(primary_commodities)
    return (
        "No primary tracked commodity focus detected. "
        "Review the information for broader market context."
    )


def _directional_signals(
    item: MarketInformation,
    text: str,
    detected_commodities: tuple[str, ...],
    movement_signal: MarketMovementSignal,
    fundamental_signals: tuple[FundamentalSignal, ...],
) -> tuple[str, tuple[str, ...], int]:
    """Determine direction from structured quote data or deterministic text terms."""
    price_change = item.metadata.get("price_change")
    if _is_number(price_change):
        if price_change > 0:
            return (
                "bullish",
                (f"Structured price change is positive ({price_change}).",),
                20,
            )
        if price_change < 0:
            return (
                "bearish",
                (f"Structured price change is negative ({price_change}).",),
                20,
            )
        return (
            "neutral",
            ("Structured price change is unchanged (0).",),
            20,
        )

    if movement_signal.priority > 0:
        return (
            movement_signal.direction,
            (f"Observed market movement: {movement_signal.evidence}.",),
            {SETTLEMENT_PRIORITY: 25, NUMERICAL_PRIORITY: 20}.get(
                movement_signal.priority, 15
            ),
        )

    factual_directions = {signal.direction for signal in fundamental_signals}
    if factual_directions == {"bullish", "bearish"}:
        return (
            "neutral",
            ("Conflicting bullish and bearish direct factual signals were detected.",),
            0,
        )

    bullish_matches = _matched_keywords(text, BULLISH_KEYWORDS)
    bearish_matches = _matched_keywords(text, BEARISH_KEYWORDS)
    commodity_bullish, commodity_bearish, commodity_details = _commodity_signals(
        text,
        detected_commodities,
    )
    factual_bullish_details = tuple(
        signal.reasoning
        for signal in fundamental_signals
        if signal.direction == "bullish"
    )
    factual_bearish_details = tuple(
        signal.reasoning
        for signal in fundamental_signals
        if signal.direction == "bearish"
    )
    bullish_details = (
        _generic_signal_details("Bullish", bullish_matches)
        + commodity_details[0]
        + factual_bullish_details
    )
    bearish_details = (
        _generic_signal_details("Bearish", bearish_matches)
        + commodity_details[1]
        + factual_bearish_details
    )
    bullish_count = (
        len(bullish_matches)
        + len(commodity_bullish)
        + bool(factual_bullish_details)
    )
    bearish_count = (
        len(bearish_matches)
        + len(commodity_bearish)
        + bool(factual_bearish_details)
    )
    confidence = (
        15
        if commodity_bullish or commodity_bearish or fundamental_signals
        else 10
    )
    if bullish_count > bearish_count:
        return (
            "bullish",
            bullish_details,
            confidence,
        )
    if bearish_count > bullish_count:
        return (
            "bearish",
            bearish_details,
            confidence,
        )
    if bullish_count or bearish_count:
        return (
            "neutral",
            ("Conflicting bullish and bearish deterministic signals were detected.",),
            confidence,
        )
    return (
        "neutral",
        ("No deterministic directional signal was detected.",),
        0,
    )


def _matched_keywords(text: str, keywords: tuple[str, ...]) -> tuple[str, ...]:
    """Return matched keywords in their configured deterministic order."""
    return tuple(keyword for keyword in keywords if phrase_matches(text, keyword))


def _generic_signal_details(
    direction: str, matches: tuple[str, ...]
) -> tuple[str, ...]:
    """Return a reasoning detail when generic directional keywords matched."""
    if not matches:
        return ()
    return (f"{direction} text signals: {', '.join(matches)}.",)


def _commodity_signals(
    text: str,
    detected_commodities: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[tuple[str, ...], tuple[str, ...]]]:
    """Return rule signals only for article-level detected commodity groups."""
    detected = frozenset(detected_commodities)
    bullish_matches: list[str] = []
    bearish_matches: list[str] = []
    bullish_details: list[str] = []
    bearish_details: list[str] = []

    for name, labels, bullish_keywords, bearish_keywords in COMMODITY_RULES:
        if not detected & labels:
            continue
        matched_bullish = _matched_keywords(text, bullish_keywords)
        matched_bearish = _matched_keywords(text, bearish_keywords)
        bullish_matches.extend(matched_bullish)
        bearish_matches.extend(matched_bearish)
        if matched_bullish:
            bullish_details.append(
                f"{name} bullish signals: {', '.join(matched_bullish)}."
            )
        if matched_bearish:
            bearish_details.append(
                f"{name} bearish signals: {', '.join(matched_bearish)}."
            )

    return (
        tuple(bullish_matches),
        tuple(bearish_matches),
        (tuple(bullish_details), tuple(bearish_details)),
    )


def _is_number(value: object) -> bool:
    """Return whether metadata contains a numeric, non-boolean value."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)
