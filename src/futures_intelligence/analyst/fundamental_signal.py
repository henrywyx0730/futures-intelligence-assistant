"""Narrow deterministic signals for reviewed Chinese fundamental facts."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from futures_intelligence.analyst.commodity_matcher import (
    CommodityMatch,
    phrase_matches,
)
from futures_intelligence.models import MarketInformation


_Horizon = Literal["short_term", "medium_long_term", "current", "future"]
_VALID_HORIZONS = frozenset({"short_term", "medium_long_term", "current", "future"})


@dataclass(frozen=True)
class FundamentalSignal:
    """One immutable, commodity-attributed direct factual signal."""

    commodity_key: str
    commodity_label: str
    direction: str
    signal_family: str
    rule_id: str
    reasoning: str
    horizon: _Horizon | None = None

    def __post_init__(self) -> None:
        """Reject non-canonical horizon values at the immutable record boundary."""
        if self.horizon is not None and self.horizon not in _VALID_HORIZONS:
            raise ValueError("horizon must be a reviewed canonical value or None")


@dataclass(frozen=True)
class FundamentalQualification:
    """One immutable qualification observation without directional force."""

    commodity_key: str
    commodity_label: str
    qualification_kind: str
    reasoning: str
    rule_id: str | None = None


@dataclass(frozen=True)
class FundamentalConflict:
    """One immutable same-commodity conflict between direct factual signals."""

    commodity_key: str
    commodity_label: str
    conflict_kind: str
    signal_rule_ids: tuple[str, ...]
    reasoning: str


@dataclass(frozen=True)
class FundamentalDetection:
    """Direct signals and non-directional qualifications from one item."""

    signals: tuple[FundamentalSignal, ...] = ()
    qualifications: tuple[FundamentalQualification, ...] = ()
    conflicts: tuple[FundamentalConflict, ...] = ()

    @property
    def signal_kind(self) -> str | None:
        """Expose one stable detector-level kind without changing MarketAnalysis."""
        if self.conflicts:
            return self.conflicts[0].conflict_kind
        if self.qualifications:
            return {
                "negated": "negated_signal",
                "uncertain": "uncertain_signal",
                "conditional": "conditional_signal",
                "forecast": "forecast_signal",
            }[self.qualifications[0].qualification_kind]
        if self.signals:
            return "fundamental_fact"
        return None


@dataclass(frozen=True)
class _FundamentalRule:
    """One reviewed commodity-specific Chinese factual relationship."""

    commodity_key: str
    phrase: str
    direction: str
    signal_family: str
    rule_id: str
    reasoning: str
    horizon: _Horizon | None = None


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

_G3B2_RULES = (
    _FundamentalRule(
        "crude_oil",
        "需求明显改善",
        "bullish",
        "demand",
        "demand_improvement",
        "Detected direct demand improvement for Crude Oil.",
    ),
    _FundamentalRule(
        "crude_oil",
        "需求疲弱",
        "bearish",
        "demand",
        "demand_weakness",
        "Detected direct demand weakness for Crude Oil.",
    ),
    _FundamentalRule(
        "aluminum",
        "高库存仍限制上涨空间",
        "bearish",
        "inventory",
        "high_inventory_constraint",
        "Detected a direct high-inventory constraint for Aluminum.",
    ),
    _FundamentalRule(
        "fuel_oil",
        "短期偏强",
        "bullish",
        "horizon",
        "short_term_strength",
        "Detected short-term strength for Fuel Oil.",
        "short_term",
    ),
    _FundamentalRule(
        "fuel_oil",
        "中长期承压",
        "bearish",
        "horizon",
        "medium_long_term_pressure",
        "Detected medium-to-long-term pressure for Fuel Oil.",
        "medium_long_term",
    ),
    _FundamentalRule(
        "aluminum",
        "当前电解铝供应偏紧",
        "bullish",
        "horizon",
        "current_supply_tightness",
        "Detected current supply tightness for Aluminum.",
        "current",
    ),
    _FundamentalRule(
        "aluminum",
        "后期产能将恢复",
        "bearish",
        "horizon",
        "future_capacity_recovery",
        "Detected future capacity recovery for Aluminum.",
        "future",
    ),
)

_G3B2_RULE_IDS = frozenset(rule.rule_id for rule in _G3B2_RULES)

_CLAUSE_SEPARATOR = re.compile(r"[。！？!?；;\n]+")
_CONTRAST_PROPOSITION_SEPARATOR = re.compile(
    r"(?:[，,][ \t]*)?(?:但|不过|然而)"
)
_REVIEWED_HORIZON_BOUNDARIES = (
    ("短期偏强", "中长期承压"),
    ("当前电解铝供应偏紧", "后期产能将恢复"),
)
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
                for proposition in _split_propositions(clause):
                    if not proposition:
                        continue
                    attributed_matches = _attributed_matches(
                        proposition,
                        eligible_primary_matches,
                        lexical_matches,
                    )
                    if not attributed_matches:
                        continue
                    qualification_kind = _qualification_kind(proposition)
                    if (
                        qualification_kind is not None
                        and _contains_qualified_proposition(proposition)
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
                                    rule_id=_qualification_rule_id(
                                        proposition,
                                        match,
                                        qualification_kind,
                                    ),
                                )
                            )
                            seen_qualifications.add(qualification_key)
                        continue
                    if _contains_deferred_discourse(proposition):
                        continue
                    for match in attributed_matches:
                        for rule in _RULES + _G3B2_RULES:
                            if (
                                rule.commodity_key != match.commodity_key
                                or rule.rule_id in seen_rule_ids
                                or not phrase_matches(proposition, rule.phrase)
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
                                    horizon=rule.horizon,
                                )
                            )
                            seen_rule_ids.add(rule.rule_id)
        return FundamentalDetection(
            signals=tuple(signals),
            qualifications=tuple(qualifications),
            conflicts=_resolve_conflicts(tuple(signals)),
        )


def _split_propositions(clause: str) -> tuple[str, ...]:
    """Split reviewed contrasts and exact horizon pairs, not ordinary commas."""
    propositions: list[str] = []
    for contrast_part in _CONTRAST_PROPOSITION_SEPARATOR.split(clause):
        parts = (contrast_part,)
        for left_phrase, right_phrase in _REVIEWED_HORIZON_BOUNDARIES:
            expanded: list[str] = []
            for part in parts:
                expanded.extend(
                    _split_reviewed_horizon_boundary(
                        part,
                        left_phrase,
                        right_phrase,
                    )
                )
            parts = tuple(expanded)
        propositions.extend(part for part in parts if part)
    return tuple(propositions)


def _split_reviewed_horizon_boundary(
    proposition: str,
    left_phrase: str,
    right_phrase: str,
) -> tuple[str, ...]:
    """Split one exact reviewed horizon pair at its Chinese or ASCII comma."""
    for comma in ("，", ","):
        boundary = f"{left_phrase}{comma}{right_phrase}"
        boundary_start = proposition.find(boundary)
        if boundary_start < 0:
            continue
        comma_index = boundary_start + len(left_phrase)
        return (
            proposition[:comma_index],
            proposition[comma_index + len(comma) :],
        )
    return (proposition,)


def _qualification_rule_id(
    proposition: str,
    match: CommodityMatch,
    qualification_kind: str,
) -> str | None:
    """Identify only the reviewed qualified proposition needed by G3B2."""
    if (
        match.commodity_key == "crude_oil"
        and qualification_kind == "negated"
        and _contains_subject_predicate(proposition, "供应", "收紧")
    ):
        return "supply_tightening_negated"
    return None


def _resolve_conflicts(
    signals: tuple[FundamentalSignal, ...],
) -> tuple[FundamentalConflict, ...]:
    """Resolve reviewed same-commodity opposing facts without vote weighting."""
    conflicts: list[FundamentalConflict] = []
    commodity_keys = tuple(dict.fromkeys(signal.commodity_key for signal in signals))
    for commodity_key in commodity_keys:
        commodity_signals = tuple(
            signal for signal in signals if signal.commodity_key == commodity_key
        )
        if {signal.direction for signal in commodity_signals} != {
            "bullish",
            "bearish",
        }:
            continue
        horizons = tuple(
            dict.fromkeys(
                signal.horizon
                for signal in commodity_signals
                if signal.horizon is not None
            )
        )
        if len(horizons) > 1 and all(
            signal.horizon is not None for signal in commodity_signals
        ):
            conflict_kind = "horizon_conflict"
            reasoning = (
                "Detected opposing fundamental signals across different time "
                "horizons; no single horizon-independent direction was assigned."
            )
        elif any(
            signal.rule_id in _G3B2_RULE_IDS for signal in commodity_signals
        ):
            conflict_kind = "conflicting_signals"
            reasoning = (
                "Detected conflicting direct fundamental signals; "
                "no deterministic directional conclusion was assigned."
            )
        else:
            continue
        conflicts.append(
            FundamentalConflict(
                commodity_key=commodity_key,
                commodity_label=commodity_signals[0].commodity_label,
                conflict_kind=conflict_kind,
                signal_rule_ids=tuple(signal.rule_id for signal in commodity_signals),
                reasoning=reasoning,
            )
        )
    return tuple(conflicts)


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
    return any(
        _contains_subject_predicate(clause, subject, predicate)
        for subject, predicate in _QUALIFIED_PROPOSITIONS
    )


def _contains_subject_predicate(clause: str, subject: str, predicate: str) -> bool:
    """Match one reviewed subject-predicate pair with the established bounded gap."""
    subject_start = clause.find(subject)
    while subject_start >= 0:
        predicate_start = clause.find(predicate, subject_start + len(subject))
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
