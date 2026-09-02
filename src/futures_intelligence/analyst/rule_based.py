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
    FundamentalConflict,
    FundamentalQualification,
    FundamentalSignal,
)
from futures_intelligence.analyst.market_movement import (
    NUMERICAL_PRIORITY,
    SETTLEMENT_PRIORITY,
    MarketMovementDetector,
    MarketMovementSignal,
)
from futures_intelligence.analyst.relative_value import RelativeValueDetector
from futures_intelligence.models import (
    DirectionalProvenance,
    MarketAnalysis,
    MarketInformation,
)

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
        self._relative_value_detector = RelativeValueDetector()

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
            fundamental_detection = self._fundamental_signal_detector.detect(
                item,
                primary_matches,
                commodity_matches,
            )
            fundamental_signals = fundamental_detection.signals
            fundamental_qualifications = fundamental_detection.qualifications
            fundamental_conflicts = fundamental_detection.conflicts
            relative_value_observations = self._relative_value_detector.detect(
                item,
                primary_matches,
                commodity_matches,
            ).observations
            summary = _research_report_summary(commodities)
        else:
            commodity_matches = self._commodity_matcher.match(item)
            commodities = _commodity_labels(commodity_matches)
            mentioned_commodities = ()
            fundamental_signals = ()
            fundamental_qualifications = ()
            fundamental_conflicts = ()
            relative_value_observations = ()
            summary = _summary_for_commodities(commodities)
        (
            market_direction,
            directional_details,
            directional_confidence,
            directional_provenance,
        ) = (
            _directional_signals(
                item,
                text,
                commodities,
                self._market_movement_detector.detect(item, commodity_matches),
                fundamental_signals,
                fundamental_qualifications,
                fundamental_conflicts,
            )
        )
        if (
            directional_provenance == "no_directional_signal"
            and relative_value_observations
        ):
            directional_provenance = "structural_only"
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
        reasoning_details.extend(
            observation.reasoning for observation in relative_value_observations
        )

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
            directional_provenance=directional_provenance,
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
    fundamental_qualifications: tuple[FundamentalQualification, ...],
    fundamental_conflicts: tuple[FundamentalConflict, ...],
) -> tuple[str, tuple[str, ...], int, DirectionalProvenance]:
    """Determine direction from structured quote data or deterministic text terms."""
    price_change = item.metadata.get("price_change")
    if _is_number(price_change):
        if price_change > 0:
            return (
                "bullish",
                (f"Structured price change is positive ({price_change}).",),
                20,
                "metadata_direction",
            )
        if price_change < 0:
            return (
                "bearish",
                (f"Structured price change is negative ({price_change}).",),
                20,
                "metadata_direction",
            )
        return (
            "neutral",
            ("Structured price change is unchanged (0).",),
            20,
            "metadata_direction",
        )

    if movement_signal.priority > 0:
        return (
            movement_signal.direction,
            (f"Observed market movement: {movement_signal.evidence}.",),
            {SETTLEMENT_PRIORITY: 25, NUMERICAL_PRIORITY: 20}.get(
                movement_signal.priority, 15
            ),
            "observed_market_movement",
        )

    if fundamental_conflicts:
        conflict_provenance: DirectionalProvenance = (
            "horizon_conflict"
            if all(
                conflict.conflict_kind == "horizon_conflict"
                for conflict in fundamental_conflicts
            )
            else "same_market_conflict"
        )
        if len(fundamental_conflicts) == 1:
            return (
                "neutral",
                (fundamental_conflicts[0].reasoning,),
                0,
                conflict_provenance,
            )
        return (
            "neutral",
            ("Conflicting direct fundamentals span multiple primary commodities.",),
            0,
            conflict_provenance,
        )

    directions_by_commodity = {
        commodity_key: {
            signal.direction
            for signal in fundamental_signals
            if signal.commodity_key == commodity_key
        }
        for commodity_key in dict.fromkeys(
            signal.commodity_key for signal in fundamental_signals
        )
    }
    if any(
        directions == {"bullish", "bearish"}
        for directions in directions_by_commodity.values()
    ):
        return (
            "neutral",
            ("Conflicting bullish and bearish direct factual signals were detected.",),
            0,
            "same_market_conflict",
        )
    factual_directions = {
        direction
        for directions in directions_by_commodity.values()
        for direction in directions
    }
    if factual_directions == {"bullish", "bearish"}:
        return (
            "neutral",
            (
                "Opposing direct fundamentals concern different primary commodities; "
                "no single report-level direction was assigned.",
            ),
            0,
            "cross_commodity_abstention",
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
    qualification_details = (
        tuple(
            dict.fromkeys(
                qualification.reasoning
                for qualification in fundamental_qualifications
            )
        )
        if fundamental_signals
        else ()
    )
    bullish_details = (
        _generic_signal_details("Bullish", bullish_matches)
        + commodity_details[0]
        + factual_bullish_details
        + qualification_details
    )
    bearish_details = (
        _generic_signal_details("Bearish", bearish_matches)
        + commodity_details[1]
        + factual_bearish_details
        + qualification_details
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
            (
                "direct_fundamental"
                if factual_directions == {"bullish"}
                else "deterministic_text_signal"
            ),
        )
    if bearish_count > bullish_count:
        return (
            "bearish",
            bearish_details,
            confidence,
            (
                "direct_fundamental"
                if factual_directions == {"bearish"}
                else "deterministic_text_signal"
            ),
        )
    if bullish_count or bearish_count:
        return (
            "neutral",
            ("Conflicting bullish and bearish deterministic signals were detected.",),
            confidence,
            "deterministic_text_signal",
        )
    if fundamental_qualifications:
        return (
            "neutral",
            tuple(
                dict.fromkeys(
                    qualification.reasoning
                    for qualification in fundamental_qualifications
                )
            ),
            0,
            "qualified_only",
        )
    return (
        "neutral",
        ("No deterministic directional signal was detected.",),
        0,
        "no_directional_signal",
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
