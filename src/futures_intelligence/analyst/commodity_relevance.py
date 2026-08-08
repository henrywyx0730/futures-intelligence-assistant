"""Deterministic lexical commodity relevance assessment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from futures_intelligence.analyst.commodity_matcher import (
    CommodityMatch,
    CommodityMatchEvidence,
    CommodityMatcher,
    CommodityOccurrence,
)
from futures_intelligence.models import MarketInformation


PRIMARY_REASON = "Matched a tracked commodity alias in the report title."
MENTIONED_REASON = "Matched tracked commodity aliases only in report content."


class CommodityRelevanceError(ValueError):
    """Raised when a supplied matcher evidence contract is malformed."""


@dataclass(frozen=True)
class CommodityRelevance:
    """One lexical commodity's deterministic title/content relevance role."""

    commodity_key: str
    commodity_label: str
    role: Literal["primary", "mentioned"]
    title_aliases: tuple[str, ...]
    content_aliases: tuple[str, ...]
    title_occurrence_count: int
    content_occurrence_count: int
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        """Fail closed for malformed local relevance values without coercion."""
        if not _is_nonempty_string(self.commodity_key) or not _is_nonempty_string(
            self.commodity_label
        ):
            raise CommodityRelevanceError("commodity identity must be non-empty")
        if self.role not in {"primary", "mentioned"}:
            raise CommodityRelevanceError("relevance role is invalid")
        _validate_aliases(self.title_aliases, "title aliases")
        _validate_aliases(self.content_aliases, "content aliases")
        _validate_count(self.title_occurrence_count, "title occurrence count")
        _validate_count(self.content_occurrence_count, "content occurrence count")
        if self.title_occurrence_count == 0 and self.title_aliases:
            raise CommodityRelevanceError("title aliases require title evidence")
        if self.content_occurrence_count == 0 and self.content_aliases:
            raise CommodityRelevanceError("content aliases require content evidence")
        if self.title_occurrence_count > 0 and not self.title_aliases:
            raise CommodityRelevanceError("title evidence requires title aliases")
        if self.content_occurrence_count > 0 and not self.content_aliases:
            raise CommodityRelevanceError("content evidence requires content aliases")
        if self.role == "primary" and self.title_occurrence_count == 0:
            raise CommodityRelevanceError("primary relevance requires title evidence")
        if self.role == "mentioned" and (
            self.title_occurrence_count != 0 or self.content_occurrence_count == 0
        ):
            raise CommodityRelevanceError("mentioned relevance requires content-only evidence")
        if type(self.reasons) is not tuple or not self.reasons or any(
            reason not in {PRIMARY_REASON, MENTIONED_REASON} for reason in self.reasons
        ):
            raise CommodityRelevanceError("relevance reasons are invalid")
        expected_reason = PRIMARY_REASON if self.role == "primary" else MENTIONED_REASON
        if self.reasons != (expected_reason,):
            raise CommodityRelevanceError("relevance reason does not match role")


@dataclass(frozen=True)
class CommodityRelevanceAssessment:
    """Immutable lexical matches partitioned into primary and mentioned roles."""

    lexical_matches: tuple[CommodityMatch, ...]
    primary: tuple[CommodityRelevance, ...]
    mentioned: tuple[CommodityRelevance, ...]

    def __post_init__(self) -> None:
        """Protect the deterministic role partition contract."""
        if type(self.lexical_matches) is not tuple or not all(
            isinstance(match, CommodityMatch) for match in self.lexical_matches
        ):
            raise CommodityRelevanceError("lexical matches must be a commodity match tuple")
        if type(self.primary) is not tuple or type(self.mentioned) is not tuple or not all(
            isinstance(item, CommodityRelevance) for item in self.primary + self.mentioned
        ):
            raise CommodityRelevanceError("relevance roles must be commodity relevance tuples")
        lexical_keys = tuple(match.commodity_key for match in self.lexical_matches)
        primary_keys = tuple(item.commodity_key for item in self.primary)
        mentioned_keys = tuple(item.commodity_key for item in self.mentioned)
        if len(lexical_keys) != len(set(lexical_keys)):
            raise CommodityRelevanceError("lexical commodity identities must be unique")
        if any(item.role != "primary" for item in self.primary) or any(
            item.role != "mentioned" for item in self.mentioned
        ):
            raise CommodityRelevanceError("relevance role tuple is inconsistent")
        if len(primary_keys) != len(set(primary_keys)) or len(mentioned_keys) != len(
            set(mentioned_keys)
        ):
            raise CommodityRelevanceError("relevance commodity identities must be unique")
        if set(primary_keys) & set(mentioned_keys) or set(primary_keys) | set(
            mentioned_keys
        ) != set(lexical_keys):
            raise CommodityRelevanceError("relevance roles must partition lexical matches")
        if not _is_subsequence(primary_keys, lexical_keys) or not _is_subsequence(
            mentioned_keys, lexical_keys
        ):
            raise CommodityRelevanceError("relevance roles must preserve lexical order")
        lexical_labels = {
            match.commodity_key: match.commodity_label for match in self.lexical_matches
        }
        for relevance in self.primary + self.mentioned:
            if lexical_labels[relevance.commodity_key] != relevance.commodity_label:
                raise CommodityRelevanceError(
                    "relevance label must match lexical commodity label"
                )


class CommodityRelevanceResolver:
    """Classify title-confirmed lexical commodities as primary, else mentioned."""

    def __init__(self, matcher: CommodityMatcher | None = None) -> None:
        self._matcher = matcher if matcher is not None else CommodityMatcher()

    def assess(self, information: MarketInformation) -> CommodityRelevanceAssessment:
        """Resolve one immutable relevance assessment from one matcher invocation."""
        evidence = self._matcher.match_with_evidence(information)
        _validate_evidence(evidence, information)
        occurrences_by_key: dict[str, list[CommodityOccurrence]] = {}
        for occurrence in evidence.occurrences:
            occurrences_by_key.setdefault(occurrence.commodity_key, []).append(occurrence)

        primary: list[CommodityRelevance] = []
        mentioned: list[CommodityRelevance] = []
        for match in evidence.matches:
            occurrences = occurrences_by_key[match.commodity_key]
            title_occurrences = tuple(
                occurrence for occurrence in occurrences if occurrence.field == "title"
            )
            content_occurrences = tuple(
                occurrence for occurrence in occurrences if occurrence.field == "content"
            )
            relevance = CommodityRelevance(
                commodity_key=match.commodity_key,
                commodity_label=match.commodity_label,
                role="primary" if title_occurrences else "mentioned",
                title_aliases=_aliases_for_field(match, title_occurrences),
                content_aliases=_aliases_for_field(match, content_occurrences),
                title_occurrence_count=len(title_occurrences),
                content_occurrence_count=len(content_occurrences),
                reasons=(PRIMARY_REASON,) if title_occurrences else (MENTIONED_REASON,),
            )
            (primary if relevance.role == "primary" else mentioned).append(relevance)
        return CommodityRelevanceAssessment(evidence.matches, tuple(primary), tuple(mentioned))


def _validate_evidence(evidence: object, information: MarketInformation) -> None:
    """Validate an injected matcher boundary without exposing report contents."""
    if not isinstance(evidence, CommodityMatchEvidence):
        raise CommodityRelevanceError("matcher must return commodity match evidence")
    if type(evidence.matches) is not tuple or type(evidence.occurrences) is not tuple:
        raise CommodityRelevanceError("matcher evidence collections must be tuples")
    if not all(isinstance(match, CommodityMatch) for match in evidence.matches) or not all(
        isinstance(occurrence, CommodityOccurrence) for occurrence in evidence.occurrences
    ):
        raise CommodityRelevanceError("matcher evidence contains invalid values")
    matches_by_key: dict[str, CommodityMatch] = {}
    for match in evidence.matches:
        if not _is_nonempty_string(match.commodity_key) or not _is_nonempty_string(
            match.commodity_label
        ) or type(match.matched_aliases) is not tuple or not match.matched_aliases or any(
            not _is_nonempty_string(alias) for alias in match.matched_aliases
        ):
            raise CommodityRelevanceError("matcher match contract is invalid")
        if match.commodity_key in matches_by_key:
            raise CommodityRelevanceError("matcher match identities must be unique")
        matches_by_key[match.commodity_key] = match

    occurrence_keys: set[tuple[str, str, int, int, str]] = set()
    occurrence_counts: dict[str, int] = {}
    for occurrence in evidence.occurrences:
        match = matches_by_key.get(occurrence.commodity_key)
        if match is None:
            raise CommodityRelevanceError("occurrence commodity must exist in matches")
        if occurrence.commodity_label != match.commodity_label:
            raise CommodityRelevanceError("occurrence label must match commodity match")
        if occurrence.alias not in match.matched_aliases:
            raise CommodityRelevanceError("occurrence alias must exist in commodity match")
        if occurrence.field not in {"title", "content"}:
            raise CommodityRelevanceError("occurrence field is invalid")
        if (
            type(occurrence.start) is not int
            or type(occurrence.end) is not int
            or occurrence.start < 0
            or occurrence.end <= occurrence.start
        ):
            raise CommodityRelevanceError("occurrence span is invalid")
        source_text = information.title if occurrence.field == "title" else information.content
        if occurrence.end > len(source_text) or source_text[
            occurrence.start : occurrence.end
        ].casefold() != occurrence.alias.casefold():
            raise CommodityRelevanceError("occurrence span does not match source field")
        identity = (
            occurrence.commodity_key,
            occurrence.field,
            occurrence.start,
            occurrence.end,
            occurrence.alias,
        )
        if identity in occurrence_keys:
            raise CommodityRelevanceError("occurrence identities must be unique")
        occurrence_keys.add(identity)
        occurrence_counts[occurrence.commodity_key] = occurrence_counts.get(
            occurrence.commodity_key, 0
        ) + 1
    if any(match.commodity_key not in occurrence_counts for match in evidence.matches):
        raise CommodityRelevanceError("each commodity match requires an occurrence")


def _aliases_for_field(
    match: CommodityMatch,
    occurrences: tuple[CommodityOccurrence, ...],
) -> tuple[str, ...]:
    """Preserve public matched-alias order while filtering one field's evidence."""
    aliases = {occurrence.alias for occurrence in occurrences}
    return tuple(alias for alias in match.matched_aliases if alias in aliases)


def _validate_aliases(values: object, label: str) -> None:
    if type(values) is not tuple or any(not _is_nonempty_string(value) for value in values):
        raise CommodityRelevanceError(f"{label} must be a string tuple")
    if len(values) != len(set(values)):
        raise CommodityRelevanceError(f"{label} must be unique")


def _validate_count(value: object, label: str) -> None:
    if type(value) is not int or value < 0:
        raise CommodityRelevanceError(f"{label} is invalid")


def _is_nonempty_string(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _is_subsequence(values: tuple[str, ...], order: tuple[str, ...]) -> bool:
    positions = [order.index(value) for value in values]
    return positions == sorted(positions)
