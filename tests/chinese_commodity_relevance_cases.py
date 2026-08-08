"""Immutable test-only loader for synthetic commodity-relevance cases."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re


FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "chinese_commodity_relevance_cases.json"
)
ALLOWED_TAGS = frozenset(
    {
        "propylene",
        "ethylene_glycol",
        "live_hog",
        "crude_oil",
        "aluminum",
        "cast_aluminum_alloy",
        "title_primary",
        "content_mentioned",
        "co_primary",
        "zero_primary",
        "false_positive_guard",
        "excluded_compound",
        "repeated_occurrence",
        "deterministic_order",
    }
)
ALLOWED_COMMODITY_KEYS = frozenset(
    {
        "crude_oil",
        "live_hog",
        "aluminum",
        "cast_aluminum_alloy",
        "propylene",
        "ethylene_glycol",
    }
)
_TOP_LEVEL_FIELDS = frozenset({"schema_version", "active_enforcement_phases", "cases"})
_CASE_FIELDS = frozenset(
    {"id", "title", "content", "provenance", "scenario_tags", "expected", "notes"}
)
_EXPECTED_FIELDS = frozenset({"lexical_keys", "primary_keys", "mentioned_keys"})
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_URL_PATTERN = re.compile(r"https?://|www\\.", re.IGNORECASE)
_FORBIDDEN_SOURCE_MARKERS = ("华泰期货", "免责声明", "请仔细阅读本报告")


@dataclass(frozen=True)
class ExpectedCommodityRelevance:
    """Reviewed lexical and relevance keys for one synthetic case."""

    lexical_keys: tuple[str, ...]
    primary_keys: tuple[str, ...]
    mentioned_keys: tuple[str, ...]


@dataclass(frozen=True)
class ChineseCommodityRelevanceCase:
    """One concise synthetic commodity-relevance scenario."""

    id: str
    title: str
    content: str
    provenance: str
    scenario_tags: tuple[str, ...]
    expected: ExpectedCommodityRelevance
    notes: str


@dataclass(frozen=True)
class ChineseCommodityRelevanceCorpus:
    """Validated immutable relevance corpus in fixture order."""

    schema_version: int
    active_enforcement_phases: tuple[str, ...]
    cases: tuple[ChineseCommodityRelevanceCase, ...]


def load_chinese_commodity_relevance_corpus() -> ChineseCommodityRelevanceCorpus:
    """Load the reviewed UTF-8 relevance fixture without production imports."""
    try:
        raw_fixture = FIXTURE_PATH.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError("Chinese commodity-relevance corpus could not be loaded") from error
    try:
        payload = json.loads(raw_fixture, object_pairs_hook=_reject_duplicate_json_keys)
    except json.JSONDecodeError as error:
        raise ValueError("Chinese commodity-relevance corpus could not be loaded") from error
    return _parse_corpus_payload(payload)


def cases_with_tag(
    corpus: ChineseCommodityRelevanceCorpus, tag: str
) -> tuple[ChineseCommodityRelevanceCase, ...]:
    """Return fixture-ordered cases with one approved scenario tag."""
    if tag not in ALLOWED_TAGS:
        raise ValueError("tag must be an approved relevance scenario tag")
    return tuple(case for case in corpus.cases if tag in case.scenario_tags)


def cases_for_phase(
    corpus: ChineseCommodityRelevanceCorpus, phase: str
) -> tuple[ChineseCommodityRelevanceCase, ...]:
    """Return all fixture cases when the sole active relevance phase is requested."""
    if phase != "g2_5b":
        raise ValueError("phase must be g2_5b")
    return corpus.cases if phase in corpus.active_enforcement_phases else ()


def _parse_corpus_payload(payload: object) -> ChineseCommodityRelevanceCorpus:
    """Validate exact fixture shape without normalizing malformed values."""
    corpus = _require_object(payload, "corpus")
    _require_exact_fields(corpus, _TOP_LEVEL_FIELDS, "corpus")
    if type(corpus["schema_version"]) is not int or corpus["schema_version"] != 1:
        raise ValueError("corpus.schema_version must be exactly integer 1")
    phases = _validate_string_list(
        corpus["active_enforcement_phases"], "corpus.active_enforcement_phases", False
    )
    if phases != ("g2_5b",):
        raise ValueError("corpus.active_enforcement_phases must be exactly g2_5b")
    raw_cases = corpus["cases"]
    if type(raw_cases) is not list or len(raw_cases) != 18:
        raise ValueError("corpus.cases must contain exactly 18 cases")
    cases = tuple(_parse_case(value, index) for index, value in enumerate(raw_cases))
    ids = tuple(case.id for case in cases)
    if len(ids) != len(set(ids)):
        raise ValueError("corpus case ids must be unique")
    return ChineseCommodityRelevanceCorpus(corpus["schema_version"], phases, cases)


def _parse_case(value: object, index: int) -> ChineseCommodityRelevanceCase:
    """Validate one relevance case and its deterministic role relationship."""
    location = f"corpus.cases[{index}]"
    case = _require_object(value, location)
    _require_exact_fields(case, _CASE_FIELDS, location)
    case_id = _validate_text(case["id"], f"{location}.id", 80)
    if _ID_PATTERN.fullmatch(case_id) is None:
        raise ValueError(f"{location}.id must be lowercase kebab-case")
    title = _validate_text(case["title"], f"{location}.title", 180)
    content = _validate_text(case["content"], f"{location}.content", 180, allow_empty=True)
    provenance = _validate_text(case["provenance"], f"{location}.provenance", 64)
    if provenance != "synthetic_original":
        raise ValueError(f"{location}.provenance must be synthetic_original")
    tags = _validate_string_list(case["scenario_tags"], f"{location}.scenario_tags", False)
    if len(tags) != len(set(tags)) or not set(tags) <= ALLOWED_TAGS:
        raise ValueError(f"{location}.scenario_tags is invalid")
    expected = _parse_expected(case["expected"], f"{location}.expected")
    notes = _validate_text(case["notes"], f"{location}.notes", 240)
    _validate_no_source_text((title, content, notes), location)
    return ChineseCommodityRelevanceCase(case_id, title, content, provenance, tags, expected, notes)


def _parse_expected(value: object, location: str) -> ExpectedCommodityRelevance:
    """Validate lexical identities and their exact role partition."""
    expected = _require_object(value, location)
    _require_exact_fields(expected, _EXPECTED_FIELDS, location)
    lexical = _validate_commodity_key_list(
        expected["lexical_keys"], f"{location}.lexical_keys"
    )
    primary = _validate_commodity_key_list(
        expected["primary_keys"], f"{location}.primary_keys"
    )
    mentioned = _validate_commodity_key_list(
        expected["mentioned_keys"], f"{location}.mentioned_keys"
    )
    if any(len(values) != len(set(values)) for values in (lexical, primary, mentioned)):
        raise ValueError(f"{location} keys must be unique")
    if set(primary) & set(mentioned) or set(primary) | set(mentioned) != set(lexical):
        raise ValueError(f"{location} roles must partition lexical keys")
    if not _is_subsequence(primary, lexical) or not _is_subsequence(mentioned, lexical):
        raise ValueError(f"{location} role keys must preserve lexical order")
    return ExpectedCommodityRelevance(lexical, primary, mentioned)


def _require_object(value: object, location: str) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError(f"{location} must be an object")
    return value


def _require_exact_fields(value: dict[str, object], expected: frozenset[str], location: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{location} has an invalid field shape")


def _validate_text(value: object, location: str, maximum: int, *, allow_empty: bool = False) -> str:
    if type(value) is not str or len(value) > maximum:
        raise ValueError(f"{location} must be valid text")
    if value == "" and allow_empty:
        return value
    if not value.strip():
        raise ValueError(f"{location} must be valid text")
    return value


def _validate_string_list(value: object, location: str, allow_empty: bool) -> tuple[str, ...]:
    if type(value) is not list or (not allow_empty and not value):
        raise ValueError(f"{location} must be a list")
    if any(type(item) is not str or not item.strip() for item in value):
        raise ValueError(f"{location} must contain non-empty strings")
    return tuple(value)


def _validate_commodity_key_list(value: object, location: str) -> tuple[str, ...]:
    keys = _validate_string_list(value, location, True)
    if not set(keys) <= ALLOWED_COMMODITY_KEYS:
        raise ValueError(f"{location} must contain approved commodity keys")
    return keys


def _validate_no_source_text(values: tuple[str, ...], location: str) -> None:
    rendered = "\n".join(values)
    if _URL_PATTERN.search(rendered) or any(marker in rendered for marker in _FORBIDDEN_SOURCE_MARKERS):
        raise ValueError(f"{location} must contain only synthetic text")


def _is_subsequence(values: tuple[str, ...], order: tuple[str, ...]) -> bool:
    positions = [order.index(value) for value in values]
    return positions == sorted(positions)


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
