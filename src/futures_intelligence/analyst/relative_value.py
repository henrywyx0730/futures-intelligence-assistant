"""Deterministic, non-directional relative-value observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from futures_intelligence.analyst.commodity_matcher import (
    CommodityMatch,
    phrase_matches,
)
from futures_intelligence.models import MarketInformation


RelationshipType = Literal[
    "relative_value",
    "calendar_spread",
    "carry",
    "crack_spread",
]
RelationshipState = Literal[
    "identified",
    "widening",
    "narrowing",
    "repair_potential",
    "paired_legs",
    "strengthening",
    "unresolved",
]
RelationshipHorizon = Literal["near_far"]

_VALID_RELATIONSHIP_TYPES = frozenset(
    {"relative_value", "calendar_spread", "carry", "crack_spread"}
)
_VALID_RELATIONSHIP_STATES = frozenset(
    {
        "identified",
        "widening",
        "narrowing",
        "repair_potential",
        "paired_legs",
        "strengthening",
        "unresolved",
    }
)


@dataclass(frozen=True)
class RelativeValueObservation:
    """One immutable structural relationship without an outright direction."""

    relationship_key: str
    relationship_type: RelationshipType
    commodity_keys: tuple[str, ...]
    commodity_labels: tuple[str, ...]
    relationship_state: RelationshipState
    rule_ids: tuple[str, ...]
    reasoning: str
    direction: Literal["not_applicable"] = "not_applicable"
    horizon: RelationshipHorizon | None = None

    def __post_init__(self) -> None:
        """Fail closed for malformed internal structural observations."""
        if not _is_nonempty_text(self.relationship_key):
            raise ValueError("relationship_key must be non-empty")
        if self.relationship_type not in _VALID_RELATIONSHIP_TYPES:
            raise ValueError("relationship_type must be reviewed")
        if self.relationship_state not in _VALID_RELATIONSHIP_STATES:
            raise ValueError("relationship_state must be reviewed")
        if self.direction != "not_applicable":
            raise ValueError("relative-value direction must be not_applicable")
        if self.horizon not in {None, "near_far"}:
            raise ValueError("relative-value horizon must be reviewed or absent")
        _validate_text_tuple(self.commodity_keys, "commodity_keys")
        _validate_text_tuple(self.commodity_labels, "commodity_labels")
        if len(self.commodity_keys) != len(self.commodity_labels):
            raise ValueError("commodity identities and labels must align")
        _validate_text_tuple(self.rule_ids, "rule_ids")
        if not _is_nonempty_text(self.reasoning):
            raise ValueError("reasoning must be non-empty")


@dataclass(frozen=True)
class RelativeValueDetection:
    """Immutable structural observations found in one information item."""

    observations: tuple[RelativeValueObservation, ...] = ()

    @property
    def signal_kind(self) -> str | None:
        """Expose a stable detector kind without changing MarketAnalysis."""
        return "relative_value" if self.observations else None


@dataclass(frozen=True)
class _RelativeValueRule:
    """One reviewed relationship phrase with explicit instrument identities."""

    relationship_key: str
    relationship_type: RelationshipType
    commodity_keys: tuple[str, ...]
    phrase: str
    relationship_state: RelationshipState
    rule_id: str
    reasoning: str
    horizon: RelationshipHorizon | None = None


_RULES = (
    _RelativeValueRule(
        "aluminum_cast_alloy_relative_value",
        "relative_value",
        ("aluminum", "cast_aluminum_alloy"),
        "原铝与铸造铝合金套利机会显现",
        "identified",
        "aluminum_alloy_arbitrage",
        "Detected an Aluminum and Cast Aluminum Alloy relative-value relationship; "
        "no outright market direction was assigned.",
    ),
    _RelativeValueRule(
        "aluminum_cast_alloy_spread",
        "relative_value",
        ("aluminum", "cast_aluminum_alloy"),
        "原铝与铸造铝合金价差扩大",
        "widening",
        "cross_commodity_spread_widening",
        "Detected a widening Aluminum and Cast Aluminum Alloy spread; "
        "no outright market direction was assigned.",
    ),
    _RelativeValueRule(
        "aluminum_cast_alloy_spread",
        "relative_value",
        ("aluminum", "cast_aluminum_alloy"),
        "原铝与铸造铝合金价差收窄",
        "narrowing",
        "cross_commodity_spread_narrowing",
        "Detected a narrowing Aluminum and Cast Aluminum Alloy spread; "
        "no outright market direction was assigned.",
    ),
    _RelativeValueRule(
        "crude_oil_calendar_spread",
        "calendar_spread",
        ("crude_oil",),
        "原油近远月价差存在修复空间",
        "repair_potential",
        "calendar_spread_repair",
        "Detected a Crude Oil calendar-spread repair relationship; "
        "no outright market direction was assigned.",
        "near_far",
    ),
    _RelativeValueRule(
        "aluminum_cast_alloy_paired_legs",
        "relative_value",
        ("aluminum", "cast_aluminum_alloy"),
        "买原铝卖铸造铝合金",
        "paired_legs",
        "paired_legs",
        "Detected paired Aluminum and Cast Aluminum Alloy legs; "
        "no outright market direction was assigned.",
    ),
    _RelativeValueRule(
        "copper_carry",
        "carry",
        ("copper",),
        "铜期货正套机会增强",
        "strengthening",
        "carry_opportunity",
        "Detected a strengthening Copper futures carry relationship; "
        "no outright market direction was assigned.",
    ),
    _RelativeValueRule(
        "crude_fuel_crack_spread",
        "crack_spread",
        ("crude_oil", "fuel_oil"),
        "原油与燃料油裂解价差走强",
        "strengthening",
        "crack_spread_strength",
        "Detected a strengthening Crude Oil and Fuel Oil crack-spread relationship; "
        "no outright market direction was assigned.",
    ),
)


class RelativeValueDetector:
    """Detect only reviewed, explicitly identified research-report relationships."""

    def detect(
        self,
        information: MarketInformation,
        primary_matches: tuple[CommodityMatch, ...],
        lexical_matches: tuple[CommodityMatch, ...],
    ) -> RelativeValueDetection:
        """Return stable G4 observations without deriving market direction."""
        if information.source_type != "research_report" or not primary_matches:
            return RelativeValueDetection()

        primary_keys = frozenset(match.commodity_key for match in primary_matches)
        lexical_by_key = {match.commodity_key: match for match in lexical_matches}
        matched_rules = tuple(
            rule
            for rule in _RULES
            if primary_keys.intersection(rule.commodity_keys)
            and set(rule.commodity_keys) <= lexical_by_key.keys()
            and _matches_authored_field(information, rule.phrase)
        )
        if not matched_rules:
            return RelativeValueDetection()

        rules_by_relationship: dict[str, list[_RelativeValueRule]] = {}
        for rule in matched_rules:
            rules_by_relationship.setdefault(rule.relationship_key, []).append(rule)

        observations = tuple(
            _observation_for(tuple(rules), lexical_by_key)
            for rules in rules_by_relationship.values()
        )
        return RelativeValueDetection(observations)


def _matches_authored_field(information: MarketInformation, phrase: str) -> bool:
    """Require the complete reviewed phrase within one authored source field."""
    return phrase_matches(information.title, phrase) or phrase_matches(
        information.content, phrase
    )


def _observation_for(
    rules: tuple[_RelativeValueRule, ...],
    lexical_by_key: dict[str, CommodityMatch],
) -> RelativeValueObservation:
    """Resolve one stable observation, abstaining on opposing spread states."""
    first = rules[0]
    states = frozenset(rule.relationship_state for rule in rules)
    if {"widening", "narrowing"} <= states:
        state: RelationshipState = "unresolved"
        reasoning = (
            "Detected opposing Aluminum and Cast Aluminum Alloy spread states; "
            "the structural relationship remains unresolved."
        )
    else:
        state = first.relationship_state
        reasoning = first.reasoning
    return RelativeValueObservation(
        relationship_key=first.relationship_key,
        relationship_type=first.relationship_type,
        commodity_keys=first.commodity_keys,
        commodity_labels=tuple(
            lexical_by_key[key].commodity_label for key in first.commodity_keys
        ),
        relationship_state=state,
        rule_ids=tuple(rule.rule_id for rule in rules),
        reasoning=reasoning,
        horizon=first.horizon,
    )


def _validate_text_tuple(value: object, field_name: str) -> None:
    """Require a non-empty tuple of unique, non-empty strings."""
    if (
        type(value) is not tuple
        or not value
        or any(not _is_nonempty_text(item) for item in value)
        or len(value) != len(set(value))
    ):
        raise ValueError(f"{field_name} must be a non-empty unique text tuple")


def _is_nonempty_text(value: object) -> bool:
    """Return whether a value is a non-empty string without coercion."""
    return isinstance(value, str) and bool(value.strip())
