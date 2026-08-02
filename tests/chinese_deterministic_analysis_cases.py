"""Immutable test-only loader for synthetic Chinese analysis cases."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "chinese_deterministic_analysis_cases.json"
)

VALID_DIRECTIONS = frozenset({"bullish", "bearish", "neutral"})
ALLOWED_ENFORCEMENT_PHASES = frozenset(
    {"g2", "g3a", "g3b", "g4", "not_applicable"}
)
ALLOWED_SCENARIO_TAGS = frozenset(
    {
        "commodity_identity",
        "supply",
        "inventory",
        "demand",
        "cost",
        "observed_fact",
        "explicit_price_movement",
        "bullish",
        "bearish",
        "neutral",
        "negation",
        "uncertainty",
        "conditional",
        "forecast",
        "conflict",
        "horizon",
        "relative_value",
        "arbitrage",
        "spread",
        "false_positive_guard",
        "petroleum",
        "live_hog",
        "aluminum",
        "agriculture",
        "metals",
        "energy",
    }
)
ALLOWED_SIGNAL_KINDS = frozenset(
    {
        "commodity_identity_only",
        "fundamental_fact",
        "explicit_price_movement",
        "negated_signal",
        "uncertain_signal",
        "conditional_signal",
        "conflicting_signals",
        "horizon_conflict",
        "relative_value",
        "false_positive_guard",
    }
)
ALLOWED_COMMODITY_KEYS = frozenset(
    {
        "crude_oil",
        "butadiene_rubber",
        "styrene",
        "copper",
        "aluminum",
        "silver",
        "gold",
        "iron_ore",
        "coal",
        "soybean_meal",
        "corn",
        "wheat",
        "live_hog",
        "fuel_oil",
        "low_sulfur_fuel_oil",
        "cast_aluminum_alloy",
    }
)

_TOP_LEVEL_FIELDS = frozenset({"schema_version", "active_enforcement_phases", "cases"})
_CASE_FIELDS = frozenset(
    {
        "id",
        "title",
        "content",
        "provenance",
        "scenario_tags",
        "expected",
        "enforcement",
        "notes",
    }
)
_EXPECTED_FIELDS = frozenset(
    {
        "commodity_keys",
        "no_commodity_keys",
        "market_direction",
        "reasoning_tags",
        "signal_kind",
    }
)
_ENFORCEMENT_FIELDS = frozenset({"commodity", "direction", "relative_value"})
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_REASONING_TAG_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_URL_PATTERN = re.compile(r"https?://|www\\.", re.IGNORECASE)
_FORBIDDEN_SOURCE_MARKERS = ("华泰期货", "免责声明", "请仔细阅读本报告")
_EXPECTED_CATEGORY_COUNTS = {
    "commodity_identity": 16,
    "simple_factual_direction": 12,
    "negation_or_uncertainty": 8,
    "qualified_or_conflicting": 8,
    "relative_value": 6,
    "false_positive_guard": 8,
}


@dataclass(frozen=True)
class ExpectedOutcome:
    """One future deterministic expectation without production-rule coupling."""

    commodity_keys: tuple[str, ...]
    no_commodity_keys: tuple[str, ...]
    market_direction: str
    reasoning_tags: tuple[str, ...]
    signal_kind: str


@dataclass(frozen=True)
class EnforcementPlan:
    """The first phase permitted to activate each expectation axis."""

    commodity: str
    direction: str
    relative_value: str

    def as_tuple(self) -> tuple[str, str, str]:
        """Return phase values in stable fixture-field order."""
        return (self.commodity, self.direction, self.relative_value)


@dataclass(frozen=True)
class ChineseDeterministicAnalysisCase:
    """One concise original Chinese scenario for a future rule phase."""

    id: str
    title: str
    content: str
    provenance: str
    scenario_tags: tuple[str, ...]
    expected: ExpectedOutcome
    enforcement: EnforcementPlan
    notes: str
    primary_category: str


@dataclass(frozen=True)
class ChineseDeterministicCorpus:
    """The validated immutable corpus, preserving fixture order."""

    schema_version: int
    active_enforcement_phases: tuple[str, ...]
    cases: tuple[ChineseDeterministicAnalysisCase, ...]


def load_chinese_deterministic_corpus() -> ChineseDeterministicCorpus:
    """Load the reviewed UTF-8 fixture without importing production analysis code."""
    try:
        raw_fixture = FIXTURE_PATH.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError("Chinese deterministic-analysis corpus could not be loaded") from error
    payload = _decode_corpus_json(raw_fixture)
    return _parse_corpus_payload(payload)


def cases_for_phase(
    corpus: ChineseDeterministicCorpus, phase: str
) -> tuple[ChineseDeterministicAnalysisCase, ...]:
    """Return fixture-ordered cases targeted by one future implementation phase."""
    if phase not in ALLOWED_ENFORCEMENT_PHASES - {"not_applicable"}:
        raise ValueError("phase must be a named behavioral enforcement phase")
    return tuple(case for case in corpus.cases if phase in case.enforcement.as_tuple())


def cases_with_tag(
    corpus: ChineseDeterministicCorpus, tag: str
) -> tuple[ChineseDeterministicAnalysisCase, ...]:
    """Return fixture-ordered cases carrying one reviewed scenario tag."""
    if tag not in ALLOWED_SCENARIO_TAGS:
        raise ValueError("tag must be an approved scenario tag")
    return tuple(case for case in corpus.cases if tag in case.scenario_tags)


def _parse_corpus_payload(payload: object) -> ChineseDeterministicCorpus:
    """Strictly validate JSON-decoded data and return immutable test-only values."""
    top_level = _require_object(payload, "corpus")
    _require_exact_fields(top_level, _TOP_LEVEL_FIELDS, "corpus")
    schema_version = top_level["schema_version"]
    if type(schema_version) is not int or schema_version != 1:
        raise ValueError("corpus.schema_version must be exactly integer 1")
    active_phases = _validate_phase_list(
        top_level["active_enforcement_phases"], "corpus.active_enforcement_phases"
    )
    raw_cases = top_level["cases"]
    if type(raw_cases) is not list:
        raise ValueError("corpus.cases must be a list")
    if len(raw_cases) != 58:
        raise ValueError("corpus.cases must contain exactly 58 cases")

    cases = tuple(_parse_case(raw_case, index) for index, raw_case in enumerate(raw_cases))
    _validate_case_ids(cases)
    _validate_category_counts(cases)
    return ChineseDeterministicCorpus(schema_version, active_phases, cases)


def _parse_case(raw_case: object, index: int) -> ChineseDeterministicAnalysisCase:
    """Validate one exact case object without coercing any fixture value."""
    location = f"corpus.cases[{index}]"
    case = _require_object(raw_case, location)
    _require_exact_fields(case, _CASE_FIELDS, location)
    case_id = _validate_text(case["id"], f"{location}.id", maximum=80)
    if _ID_PATTERN.fullmatch(case_id) is None:
        raise ValueError(f"{location}.id must be lowercase kebab-case")
    title = _validate_text(case["title"], f"{location}.title", maximum=180)
    content = _validate_text(
        case["content"], f"{location}.content", maximum=180, allow_empty=True
    )
    provenance = _validate_text(case["provenance"], f"{location}.provenance", maximum=64)
    if provenance != "synthetic_original":
        raise ValueError(f"{location}.provenance must be synthetic_original")
    scenario_tags = _validate_string_list(
        case["scenario_tags"], f"{location}.scenario_tags", allow_empty=False
    )
    if not set(scenario_tags) <= ALLOWED_SCENARIO_TAGS:
        raise ValueError(f"{location}.scenario_tags contains an unsupported tag")

    expected = _parse_expected(case["expected"], f"{location}.expected")
    enforcement = _parse_enforcement(case["enforcement"], f"{location}.enforcement")
    notes = _validate_text(case["notes"], f"{location}.notes", maximum=240)
    _validate_no_source_text((title, content, notes), location)
    primary_category = _primary_category(scenario_tags, location)
    _validate_phase_assignment(
        primary_category, expected, enforcement, location, case_id
    )
    return ChineseDeterministicAnalysisCase(
        case_id,
        title,
        content,
        provenance,
        scenario_tags,
        expected,
        enforcement,
        notes,
        primary_category,
    )


def _parse_expected(value: object, location: str) -> ExpectedOutcome:
    """Validate future expectations as schema data, not current behavior."""
    expected = _require_object(value, location)
    _require_exact_fields(expected, _EXPECTED_FIELDS, location)
    commodity_keys = _validate_commodity_list(expected["commodity_keys"], f"{location}.commodity_keys")
    no_commodity_keys = _validate_commodity_list(
        expected["no_commodity_keys"], f"{location}.no_commodity_keys"
    )
    if set(commodity_keys) & set(no_commodity_keys):
        raise ValueError(f"{location} commodity expectations must be disjoint")
    direction = _validate_text(expected["market_direction"], f"{location}.market_direction", maximum=16)
    if direction not in VALID_DIRECTIONS:
        raise ValueError(f"{location}.market_direction is invalid")
    reasoning_tags = _validate_string_list(
        expected["reasoning_tags"], f"{location}.reasoning_tags", allow_empty=True
    )
    if not all(_REASONING_TAG_PATTERN.fullmatch(tag) for tag in reasoning_tags):
        raise ValueError(f"{location}.reasoning_tags must be stable identifiers")
    signal_kind = _validate_text(expected["signal_kind"], f"{location}.signal_kind", maximum=64)
    if signal_kind not in ALLOWED_SIGNAL_KINDS:
        raise ValueError(f"{location}.signal_kind is invalid")
    return ExpectedOutcome(
        commodity_keys, no_commodity_keys, direction, reasoning_tags, signal_kind
    )


def _parse_enforcement(value: object, location: str) -> EnforcementPlan:
    """Validate the three independent future activation axes."""
    enforcement = _require_object(value, location)
    _require_exact_fields(enforcement, _ENFORCEMENT_FIELDS, location)
    phases = tuple(
        _validate_text(enforcement[name], f"{location}.{name}", maximum=32)
        for name in ("commodity", "direction", "relative_value")
    )
    if not set(phases) <= ALLOWED_ENFORCEMENT_PHASES:
        raise ValueError(f"{location} contains an invalid enforcement phase")
    return EnforcementPlan(*phases)


def _decode_corpus_json(raw_fixture: str) -> object:
    """Decode fixture JSON while rejecting duplicate object keys at every level."""
    try:
        return json.loads(raw_fixture, object_pairs_hook=_reject_duplicate_json_keys)
    except json.JSONDecodeError as error:
        raise ValueError("Chinese deterministic-analysis corpus could not be loaded") from error


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build a JSON object without silently overwriting repeated member names."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _require_object(value: object, location: str) -> dict[str, Any]:
    """Require a plain JSON object without accepting unrelated mappings."""
    if type(value) is not dict:
        raise ValueError(f"{location} must be an object")
    return value


def _require_exact_fields(
    value: dict[str, Any], expected_fields: frozenset[str], location: str
) -> None:
    """Reject both missing and unexpected schema fields."""
    if set(value) != expected_fields:
        raise ValueError(f"{location} fields do not match the required schema")


def _validate_text(value: object, location: str, *, maximum: int, allow_empty: bool = False) -> str:
    """Reject non-string, empty, overlong, or silently normalizable fixture text."""
    if not isinstance(value, str):
        raise ValueError(f"{location} must be a string")
    if not allow_empty and not value.strip():
        raise ValueError(f"{location} must be non-empty")
    if allow_empty and value and not value.strip():
        raise ValueError(f"{location} must be empty or contain non-whitespace text")
    if len(value) > maximum:
        raise ValueError(f"{location} exceeds its maximum length")
    return value


def _validate_string_list(
    value: object, location: str, *, allow_empty: bool
) -> tuple[str, ...]:
    """Require a unique JSON list of non-empty strings without normalization."""
    if type(value) is not list:
        raise ValueError(f"{location} must be a list")
    if not allow_empty and not value:
        raise ValueError(f"{location} must be non-empty")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{location} must contain non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{location} must not contain duplicates")
    return tuple(value)


def _validate_commodity_list(value: object, location: str) -> tuple[str, ...]:
    """Require reviewed canonical current or future commodity keys."""
    keys = _validate_string_list(value, location, allow_empty=True)
    if not set(keys) <= ALLOWED_COMMODITY_KEYS:
        raise ValueError(f"{location} contains an unsupported commodity key")
    return keys


def _validate_phase_list(value: object, location: str) -> tuple[str, ...]:
    """Require unique named future phases without silently activating behavior."""
    phases = _validate_string_list(value, location, allow_empty=True)
    if not set(phases) <= ALLOWED_ENFORCEMENT_PHASES - {"not_applicable"}:
        raise ValueError(f"{location} contains an invalid active phase")
    return phases


def _validate_no_source_text(values: tuple[str, str, str], location: str) -> None:
    """Keep fixture prose original, concise, and free of source-specific material."""
    rendered = "\n".join(values)
    if _URL_PATTERN.search(rendered):
        raise ValueError(f"{location} must not contain a URL")
    if any(marker in rendered for marker in _FORBIDDEN_SOURCE_MARKERS):
        raise ValueError(f"{location} contains a prohibited source marker")


def _primary_category(tags: tuple[str, ...], location: str) -> str:
    """Classify each case once using the reviewed phase-G1 precedence."""
    tag_set = set(tags)
    if "false_positive_guard" in tag_set:
        return "false_positive_guard"
    if "relative_value" in tag_set:
        return "relative_value"
    if tag_set & {"negation", "uncertainty"}:
        return "negation_or_uncertainty"
    if tag_set & {"conditional", "forecast", "conflict", "horizon"}:
        return "qualified_or_conflicting"
    if "observed_fact" in tag_set:
        return "simple_factual_direction"
    if "commodity_identity" in tag_set:
        return "commodity_identity"
    raise ValueError(f"{location}.scenario_tags has no primary category")


def _validate_phase_assignment(
    primary_category: str,
    expected: ExpectedOutcome,
    enforcement: EnforcementPlan,
    location: str,
    case_id: str,
) -> None:
    """Keep expected behavior and its planned activation phase internally consistent."""
    if primary_category == "relative_value":
        if (
            expected.market_direction != "neutral"
            or expected.signal_kind != "relative_value"
            or enforcement.commodity not in {"g2", "not_applicable"}
            or enforcement.direction != "not_applicable"
            or enforcement.relative_value != "g4"
        ):
            raise ValueError(f"case {case_id}: violates the relative-value deferral policy")
        return
    if primary_category == "simple_factual_direction":
        if expected.market_direction not in {"bullish", "bearish"}:
            raise ValueError(f"case {case_id}: factual case must have bullish or bearish direction")
        if expected.signal_kind != "fundamental_fact":
            raise ValueError(f"case {case_id}: factual case must use fundamental_fact")
        if not expected.commodity_keys:
            raise ValueError(f"case {case_id}: factual case must positively identify a commodity")
        if (
            enforcement.commodity != "g2"
            or enforcement.direction != "g3a"
            or enforcement.relative_value != "not_applicable"
        ):
            raise ValueError(f"case {case_id}: factual case must target G2 and G3a")
        return
    if primary_category == "negation_or_uncertainty":
        if expected.signal_kind not in {"negated_signal", "uncertain_signal"}:
            raise ValueError(f"case {case_id}: qualified case has an invalid signal kind")
        if (
            enforcement.commodity != "g2"
            or enforcement.direction != "g3b"
            or enforcement.relative_value != "not_applicable"
        ):
            raise ValueError(f"case {case_id}: qualified case must target G2 and G3b")
        return
    if primary_category == "qualified_or_conflicting":
        if expected.signal_kind not in {
            "conditional_signal",
            "conflicting_signals",
            "horizon_conflict",
        }:
            raise ValueError(f"case {case_id}: qualified case has an invalid signal kind")
        if (
            enforcement.commodity != "g2"
            or enforcement.direction != "g3b"
            or enforcement.relative_value != "not_applicable"
        ):
            raise ValueError(f"case {case_id}: qualified case must target G2 and G3b")
        return
    if primary_category == "commodity_identity":
        if expected.market_direction != "neutral":
            raise ValueError(f"case {case_id}: identity case must remain neutral")
        if expected.signal_kind != "commodity_identity_only":
            raise ValueError(f"case {case_id}: identity case must use commodity_identity_only")
        if not (expected.commodity_keys or expected.no_commodity_keys):
            raise ValueError(f"case {case_id}: identity case requires a commodity assertion")
        if (
            enforcement.commodity != "g2"
            or enforcement.direction != "not_applicable"
            or enforcement.relative_value != "not_applicable"
        ):
            raise ValueError(f"case {case_id}: identity case has an inconsistent enforcement plan")
        return
    if primary_category == "false_positive_guard":
        if expected.market_direction != "neutral":
            raise ValueError(f"case {case_id}: false-positive guard must remain neutral")
        if expected.signal_kind != "false_positive_guard":
            raise ValueError(f"case {case_id}: false-positive guard must use false_positive_guard")
        if expected.commodity_keys:
            raise ValueError(f"case {case_id}: false-positive guard cannot positively expect commodities")
        if not expected.no_commodity_keys:
            raise ValueError(f"case {case_id}: false-positive guard requires a forbidden commodity")
        if (
            enforcement.commodity != "g2"
            or enforcement.direction != "not_applicable"
            or enforcement.relative_value != "not_applicable"
        ):
            raise ValueError(f"case {case_id}: false-positive guard has an inconsistent enforcement plan")


def _validate_case_ids(cases: tuple[ChineseDeterministicAnalysisCase, ...]) -> None:
    """Reject duplicate IDs before future tests use them as stable references."""
    ids = tuple(case.id for case in cases)
    if len(ids) != len(set(ids)):
        raise ValueError("corpus case IDs must be unique")


def _validate_category_counts(cases: tuple[ChineseDeterministicAnalysisCase, ...]) -> None:
    """Keep the first corpus balanced across its six reviewed scenario groups."""
    counts = Counter(case.primary_category for case in cases)
    if counts != _EXPECTED_CATEGORY_COUNTS:
        raise ValueError("corpus primary category counts do not match the G1 plan")
