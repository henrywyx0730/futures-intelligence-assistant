"""Narrow deterministic signals for reviewed Chinese fundamental facts."""

from __future__ import annotations

from dataclasses import dataclass
import re

from futures_intelligence.analyst.commodity_matcher import (
    CommodityMatch,
    phrase_matches,
)
from futures_intelligence.models import MarketInformation


@dataclass(frozen=True)
class FundamentalSignal:
    """One immutable, commodity-attributed direct factual signal."""

    commodity_key: str
    commodity_label: str
    direction: str
    signal_family: str
    rule_id: str
    reasoning: str


@dataclass(frozen=True)
class FundamentalQualification:
    """One immutable qualification observation without directional force."""

    commodity_key: str
    commodity_label: str
    qualification_kind: str
    reasoning: str


@dataclass(frozen=True)
class FundamentalDetection:
    """Direct signals and non-directional qualifications from one item."""

    signals: tuple[FundamentalSignal, ...] = ()
    qualifications: tuple[FundamentalQualification, ...] = ()


@dataclass(frozen=True)
class _FundamentalRule:
    """One reviewed commodity-specific Chinese factual relationship."""

    commodity_key: str
    phrase: str
    direction: str
    signal_family: str
    rule_id: str
    reasoning: str


_RULES = (
    _FundamentalRule(
        "crude_oil",
        "供应收紧",
        "bullish",
        "supply",
        "supply_tightening",
        "Detected direct supply tightening for Crude Oil.",
    ),
    _FundamentalRule(
        "fuel_oil",
        "供给减少",
        "bullish",
        "supply",
        "supply_reduction",
        "Detected direct supply reduction for Fuel Oil.",
    ),
    _FundamentalRule(
        "live_hog",
        "库存下降",
        "bullish",
        "inventory",
        "inventory_decline",
        "Detected direct inventory decline for Live Hog.",
    ),
    _FundamentalRule(
        "aluminum",
        "库存去化",
        "bullish",
        "inventory",
        "inventory_destock",
        "Detected direct inventory destocking for Aluminum.",
    ),
    _FundamentalRule(
        "wheat",
        "需求改善",
        "bullish",
        "demand",
        "demand_improvement",
        "Detected direct demand improvement for Wheat.",
    ),
    _FundamentalRule(
        "corn",
        "成本支撑增强",
        "bullish",
        "cost",
        "cost_support",
        "Detected direct cost support strengthening for Corn.",
    ),
    _FundamentalRule(
        "crude_oil",
        "供应增加",
        "bearish",
        "supply",
        "supply_increase",
        "Detected direct supply increase for Crude Oil.",
    ),
    _FundamentalRule(
        "fuel_oil",
        "供应宽松",
        "bearish",
        "supply",
        "supply_loose",
        "Detected direct loose supply for Fuel Oil.",
    ),
    _FundamentalRule(
        "live_hog",
        "库存累积",
        "bearish",
        "inventory",
        "inventory_accumulation",
        "Detected direct inventory accumulation for Live Hog.",
    ),
    _FundamentalRule(
        "aluminum",
        "库存增加",
        "bearish",
        "inventory",
        "inventory_increase",
        "Detected direct inventory increase for Aluminum.",
    ),
    _FundamentalRule(
        "soybean_meal",
        "需求疲弱",
        "bearish",
        "demand",
        "demand_weakness",
        "Detected direct demand weakness for Soybean Meal.",
    ),
    _FundamentalRule(
        "corn",
        "成本下移",
        "bearish",
        "cost",
        "cost_decline",
        "Detected direct cost decline for Corn.",
    ),
)

_CLAUSE_SEPARATOR = re.compile(r"[。！？!?；;\n]+")
_NEGATION_MARKERS = (
    "并未",
    "没有",
    "尚未",
)
_UNCERTAINTY_MARKERS = (
    "不明确",
    "不排除",
    "可能",
)
_CONDITIONAL_MARKERS = (
    "若",
    "如果",
    "一旦",
)
_FORECAST_MARKERS = (
    "有望",
    "预计",
    "预期",
)
_DEFERRED_DISCOURSE_MARKERS = (
    "但",
    "不过",
    "然而",
)
_QUALIFIED_PROPOSITIONS = (
    ("供应", "收紧"),
    ("库存", "下降"),
    ("需求", "改善"),
    ("减产", "兑现"),
    ("成本", "支撑"),
    ("需求", "走弱"),
    ("进口", "下降"),
    ("需求", "恢复"),
    ("库存", "去化"),
)
_MAX_PROPOSITION_GAP = 8
_QUALIFICATION_REASONING = {
    "negated": (
        "Detected a negated fundamental statement; "
        "no realized factual direction was assigned."
    ),
    "uncertain": (
        "Detected an uncertain fundamental statement; "
        "no realized factual direction was assigned."
    ),
    "conditional": (
        "Detected a conditional fundamental statement; "
        "no realized factual direction was assigned."
    ),
    "forecast": (
        "Detected a forecast fundamental statement; "
        "no realized factual direction was assigned."
    ),
}


class ChineseFundamentalSignalDetector:
    """Detect only reviewed direct Chinese facts for eligible research subjects."""

    def detect(
        self,
        information: MarketInformation,
        eligible_primary_matches: tuple[CommodityMatch, ...],
        lexical_matches: tuple[CommodityMatch, ...],
    ) -> FundamentalDetection:
        """Return stable direct signals and non-directional qualifications."""
        if information.source_type != "research_report" or not eligible_primary_matches:
            return FundamentalDetection()

        signals: list[FundamentalSignal] = []
        qualifications: list[FundamentalQualification] = []
        seen_rule_ids: set[str] = set()
        seen_qualifications: set[tuple[str, str]] = set()
        for field_text in (information.title, information.content):
            for clause in _CLAUSE_SEPARATOR.split(field_text):
                if not clause:
                    continue
                attributed_matches = _attributed_matches(
                    clause,
                    eligible_primary_matches,
                    lexical_matches,
                )
                if not attributed_matches:
                    continue
                qualification_kind = _qualification_kind(clause)
                if qualification_kind is not None and _contains_qualified_proposition(
                    clause
                ):
                    for match in attributed_matches:
                        qualification_key = (
                            match.commodity_key,
                            qualification_kind,
                        )
                        if qualification_key in seen_qualifications:
                            continue
                        qualifications.append(
                            FundamentalQualification(
                                commodity_key=match.commodity_key,
                                commodity_label=match.commodity_label,
                                qualification_kind=qualification_kind,
                                reasoning=_QUALIFICATION_REASONING[
                                    qualification_kind
                                ],
                            )
                        )
                        seen_qualifications.add(qualification_key)
                    continue
                if _contains_deferred_discourse(clause):
                    continue
                for match in attributed_matches:
                    for rule in _RULES:
                        if (
                            rule.commodity_key != match.commodity_key
                            or rule.rule_id in seen_rule_ids
                            or not phrase_matches(clause, rule.phrase)
                        ):
                            continue
                        signals.append(
                            FundamentalSignal(
                                commodity_key=match.commodity_key,
                                commodity_label=match.commodity_label,
                                direction=rule.direction,
                                signal_family=rule.signal_family,
                                rule_id=rule.rule_id,
                                reasoning=rule.reasoning,
                            )
                        )
                        seen_rule_ids.add(rule.rule_id)
        return FundamentalDetection(
            signals=tuple(signals),
            qualifications=tuple(qualifications),
        )


def _qualification_kind(clause: str) -> str | None:
    """Classify only reviewed qualification markers in stable precedence."""
    if any(marker in clause for marker in _CONDITIONAL_MARKERS):
        return "conditional"
    if "预期未兑现" in clause:
        return "uncertain"
    if any(marker in clause for marker in _NEGATION_MARKERS):
        return "negated"
    if any(marker in clause for marker in _UNCERTAINTY_MARKERS):
        return "uncertain"
    if any(marker in clause for marker in _FORECAST_MARKERS):
        return "forecast"
    return None


def _contains_deferred_discourse(clause: str) -> bool:
    """Keep mixed-clause discourse semantics deferred to G3B2."""
    return any(marker in clause for marker in _DEFERRED_DISCOURSE_MARKERS)


def _contains_qualified_proposition(clause: str) -> bool:
    """Recognize only reviewed subject-predicate shapes with a bounded gap."""
    for subject, predicate in _QUALIFIED_PROPOSITIONS:
        subject_start = clause.find(subject)
        while subject_start >= 0:
            predicate_start = clause.find(
                predicate,
                subject_start + len(subject),
            )
            if (
                predicate_start >= 0
                and predicate_start - (subject_start + len(subject))
                <= _MAX_PROPOSITION_GAP
            ):
                return True
            subject_start = clause.find(subject, subject_start + 1)
    return False


def _attributed_matches(
    clause: str,
    eligible_primary_matches: tuple[CommodityMatch, ...],
    lexical_matches: tuple[CommodityMatch, ...],
) -> tuple[CommodityMatch, ...]:
    """Attribute a clause conservatively without spreading facts across subjects."""
    explicit_matches = tuple(
        match
        for match in eligible_primary_matches
        if any(phrase_matches(clause, alias) for alias in match.matched_aliases)
    )
    if len(explicit_matches) == 1:
        return explicit_matches
    if (
        not explicit_matches
        and len(eligible_primary_matches) == 1
        and not _contains_another_lexical_commodity(
            clause,
            eligible_primary_matches[0],
            lexical_matches,
        )
    ):
        return eligible_primary_matches
    return ()


def _contains_another_lexical_commodity(
    clause: str,
    primary_match: CommodityMatch,
    lexical_matches: tuple[CommodityMatch, ...],
) -> bool:
    """Prevent implicit attribution across an explicitly named other commodity."""
    return any(
        match.commodity_key != primary_match.commodity_key
        and any(phrase_matches(clause, alias) for alias in match.matched_aliases)
        for match in lexical_matches
    )
