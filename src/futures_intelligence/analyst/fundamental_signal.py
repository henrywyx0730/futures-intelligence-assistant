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
_QUALIFIED_MARKERS = (
    "并未",
    "没有",
    "尚未",
    "未兑现",
    "不明确",
    "不排除",
    "若",
    "如果",
    "一旦",
    "可能",
    "有望",
    "预计",
    "预期",
    "将",
    "但",
    "不过",
    "然而",
)


class ChineseFundamentalSignalDetector:
    """Detect only reviewed direct Chinese facts for eligible research subjects."""

    def detect(
        self,
        information: MarketInformation,
        eligible_primary_matches: tuple[CommodityMatch, ...],
        lexical_matches: tuple[CommodityMatch, ...],
    ) -> tuple[FundamentalSignal, ...]:
        """Return stable, deduplicated signals attributed to primary commodities."""
        if information.source_type != "research_report" or not eligible_primary_matches:
            return ()

        signals: list[FundamentalSignal] = []
        seen_rule_ids: set[str] = set()
        for field_text in (information.title, information.content):
            for clause in _CLAUSE_SEPARATOR.split(field_text):
                if not clause or _is_qualified(clause):
                    continue
                attributed_matches = _attributed_matches(
                    clause,
                    eligible_primary_matches,
                    lexical_matches,
                )
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
        return tuple(signals)


def _is_qualified(clause: str) -> bool:
    """Reject clauses that visibly require later G3B semantics."""
    return any(marker in clause for marker in _QUALIFIED_MARKERS)


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
