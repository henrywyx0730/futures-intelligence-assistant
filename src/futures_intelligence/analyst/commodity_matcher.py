"""Knowledge-backed, article-level commodity matching."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Literal

from futures_intelligence.models import MarketInformation


COMMODITY_KEYWORDS_FILE = (
    Path(__file__).resolve().parents[3] / "knowledge" / "commodity_keywords.yaml"
)


@dataclass(frozen=True)
class CommodityDefinition:
    """One configured commodity and its title/content aliases."""

    commodity_key: str
    commodity_label: str
    aliases: tuple[str, ...]
    title_topic_aliases: tuple[str, ...] = ()

    @property
    def all_aliases(self) -> tuple[str, ...]:
        """Return ordinary aliases followed by title-only topic aliases."""
        return self.aliases + self.title_topic_aliases


@dataclass(frozen=True)
class CommodityMatch:
    """One immutable article-level commodity match with supporting aliases."""

    commodity_key: str
    commodity_label: str
    matched_aliases: tuple[str, ...]


@dataclass(frozen=True)
class CommodityOccurrence:
    """One selected lexical occurrence with field-local source provenance."""

    commodity_key: str
    commodity_label: str
    alias: str
    field: Literal["title", "content"]
    start: int
    end: int


@dataclass(frozen=True)
class CommodityMatchEvidence:
    """Immutable flat matches and their selected lexical occurrences."""

    matches: tuple[CommodityMatch, ...]
    occurrences: tuple[CommodityOccurrence, ...]


@dataclass(frozen=True)
class _AliasCandidate:
    """One private alias occurrence used for deterministic overlap resolution."""

    field_index: int
    commodity_index: int
    alias_index: int
    alias: str
    start: int
    end: int

    @property
    def span_length(self) -> int:
        """Return the complete matched span length for global priority sorting."""
        return self.end - self.start


class CommodityMatcher:
    """Match configured commodities against original information title and content."""

    def __init__(
        self,
        definitions: tuple[CommodityDefinition, ...] | None = None,
        ambiguous_alias_exclusions: tuple[tuple[str, tuple[str, ...]], ...] | None = None,
    ) -> None:
        """Load the stable registry unless explicit test definitions are supplied."""
        if definitions is None or ambiguous_alias_exclusions is None:
            definitions, ambiguous_alias_exclusions = _load_commodity_registry()
        self._definitions = definitions
        self._ambiguous_alias_exclusions = dict(ambiguous_alias_exclusions)

    @property
    def commodity_order(self) -> tuple[str, ...]:
        """Return immutable configured commodity keys in their YAML order."""
        return tuple(definition.commodity_key for definition in self._definitions)

    @property
    def commodity_ordered_matches(self) -> tuple[CommodityDefinition, ...]:
        """Expose immutable configured definitions for ordered downstream grouping."""
        return self._definitions

    def match(self, information: MarketInformation) -> tuple[CommodityMatch, ...]:
        """Return title/content-supported commodity matches in configured order."""
        return self.match_with_evidence(information).matches

    def match_with_evidence(
        self,
        information: MarketInformation,
    ) -> CommodityMatchEvidence:
        """Return flat matches plus selected field-local lexical provenance."""
        selected_candidates = self._resolve_overlaps(
            self._collect_candidates(information.title, field_index=0)
            + self._collect_title_topic_candidates(information.title)
            + self._collect_candidates(information.content, field_index=1)
        )
        matches = self._build_matches(selected_candidates)
        occurrences = tuple(
            CommodityOccurrence(
                commodity_key=self._definitions[candidate.commodity_index].commodity_key,
                commodity_label=self._definitions[candidate.commodity_index].commodity_label,
                alias=candidate.alias,
                field="title" if candidate.field_index == 0 else "content",
                start=candidate.start,
                end=candidate.end,
            )
            for candidate in sorted(
                selected_candidates,
                key=lambda item: (
                    item.commodity_index,
                    item.field_index,
                    item.start,
                    -item.span_length,
                    item.alias_index,
                ),
            )
        )
        return CommodityMatchEvidence(matches, occurrences)

    def _build_matches(
        self,
        selected_candidates: tuple[_AliasCandidate, ...],
    ) -> tuple[CommodityMatch, ...]:
        """Build established flat public matches from selected candidates once."""
        selected_aliases: dict[int, set[int]] = {}
        for candidate in selected_candidates:
            selected_aliases.setdefault(candidate.commodity_index, set()).add(
                candidate.alias_index
            )

        return tuple(
            CommodityMatch(
                commodity_key=definition.commodity_key,
                commodity_label=definition.commodity_label,
                matched_aliases=tuple(
                    alias
                    for _, alias in sorted(
                        (
                            (alias_index, alias)
                            for alias_index, alias in enumerate(definition.all_aliases)
                            if alias_index
                            in selected_aliases.get(commodity_index, set())
                        ),
                        key=lambda item: (-len(item[1]), item[0]),
                    )
                ),
            )
            for commodity_index, definition in enumerate(self._definitions)
            if commodity_index in selected_aliases
        )

    def _collect_candidates(
        self,
        text: str,
        *,
        field_index: int,
    ) -> tuple[_AliasCandidate, ...]:
        """Collect every non-excluded configured alias occurrence in stable order."""
        normalized_text = text.casefold()
        candidates: list[_AliasCandidate] = []
        for commodity_index, definition in enumerate(self._definitions):
            for alias_index, alias in enumerate(definition.aliases):
                exclusion_spans = self._exclusion_spans(normalized_text, alias)
                for match in re.finditer(_alias_pattern(alias), normalized_text):
                    if any(
                        _spans_overlap(match.start(), match.end(), start, end)
                        for start, end in exclusion_spans
                    ):
                        continue
                    candidates.append(
                        _AliasCandidate(
                            field_index,
                            commodity_index,
                            alias_index,
                            alias,
                            match.start(),
                            match.end(),
                        )
                    )
        return tuple(candidates)

    def _collect_title_topic_candidates(self, title: str) -> tuple[_AliasCandidate, ...]:
        """Collect one-character CJK aliases only from strong report-title structures."""
        normalized_title = title.casefold()
        candidates: list[_AliasCandidate] = []
        for commodity_index, definition in enumerate(self._definitions):
            for topic_alias_index, alias in enumerate(definition.title_topic_aliases):
                alias_index = len(definition.aliases) + topic_alias_index
                exclusion_spans = self._exclusion_spans(normalized_title, alias)
                for match in re.finditer(_title_topic_alias_pattern(alias), normalized_title):
                    start, end = match.span("alias")
                    if any(
                        _spans_overlap(start, end, exclusion_start, exclusion_end)
                        for exclusion_start, exclusion_end in exclusion_spans
                    ):
                        continue
                    candidates.append(
                        _AliasCandidate(
                            0,
                            commodity_index,
                            alias_index,
                            alias,
                            start,
                            end,
                        )
                    )
        return tuple(candidates)

    def _exclusion_spans(self, text: str, alias: str) -> tuple[tuple[int, int], ...]:
        """Return local spans where an ambiguous alias is not article evidence."""
        exclusions = self._ambiguous_alias_exclusions.get(alias.casefold(), ())
        return tuple(
            (match.start(), match.end())
            for phrase in exclusions
            for match in re.finditer(_alias_pattern(phrase), text)
        )

    @staticmethod
    def _resolve_overlaps(
        candidates: tuple[_AliasCandidate, ...],
    ) -> tuple[_AliasCandidate, ...]:
        """Prefer longest global spans, then stable registry and alias order."""
        selected: list[_AliasCandidate] = []
        for candidate in sorted(
            candidates,
            key=lambda item: (
                -item.span_length,
                item.commodity_index,
                item.alias_index,
                item.field_index,
                item.start,
            ),
        ):
            if any(
                candidate.field_index == prior.field_index
                and _spans_overlap(
                    candidate.start,
                    candidate.end,
                    prior.start,
                    prior.end,
                )
                for prior in selected
            ):
                continue
            selected.append(candidate)
        return tuple(selected)


def phrase_matches(text: str, phrase: str) -> bool:
    """Match a configured phrase outside larger tokens, allowing punctuation separators."""
    return re.search(_alias_pattern(phrase), text.casefold()) is not None


def _alias_pattern(alias: str) -> str:
    """Build escaped phrase matching with ASCII-only word-edge protection."""
    normalized_alias = alias.casefold()
    parts = normalized_alias.split()
    pattern = r"(?:[\W_]+)".join(re.escape(part) for part in parts)
    prefix = r"(?<![A-Za-z0-9_])" if _is_ascii_word_character(normalized_alias[0]) else ""
    suffix = r"(?![A-Za-z0-9_])" if _is_ascii_word_character(normalized_alias[-1]) else ""
    return f"{prefix}{pattern}{suffix}"


def _title_topic_alias_pattern(alias: str) -> str:
    """Build one escaped title-only topic alias pattern with a safe context gate."""
    return (
        r"(?:^|期货|[\s:：\-—/·])"
        rf"(?P<alias>{re.escape(alias.casefold())})"
        r"(?:专题|期货|周报|月报|季报|年报|策略|调研|报告)"
    )


def _is_ascii_word_character(character: str) -> bool:
    """Return whether one character needs an ASCII token boundary."""
    return character.isascii() and (character.isalnum() or character == "_")


def _spans_overlap(first_start: int, first_end: int, second_start: int, second_end: int) -> bool:
    """Return whether two non-empty string spans share any characters."""
    return first_start < second_end and second_start < first_end


def _load_commodity_registry() -> tuple[
    tuple[CommodityDefinition, ...], tuple[tuple[str, tuple[str, ...]], ...]
]:
    """Parse the small project registry without adding a YAML dependency."""
    definitions: list[CommodityDefinition] = []
    exclusions: list[tuple[str, tuple[str, ...]]] = []
    key: str | None = None
    label: str | None = None
    aliases: list[str] = []
    title_topic_aliases: list[str] = []
    alias_field: str | None = None
    excluded_alias: str | None = None
    excluded_phrases: list[str] = []
    section = "commodities"

    def add_definition() -> None:
        if key is None and label is None and not aliases and not title_topic_aliases:
            return
        if not key or not label or not aliases:
            raise ValueError("Each commodity entry must define a key, label, and aliases")
        _validate_aliases(key, aliases)
        _validate_title_topic_aliases(key, aliases, title_topic_aliases)
        definitions.append(
            CommodityDefinition(
                key,
                label,
                tuple(alias.casefold() for alias in aliases),
                tuple(alias.casefold() for alias in title_topic_aliases),
            )
        )

    def add_exclusions() -> None:
        if excluded_alias is None:
            return
        if not excluded_phrases:
            raise ValueError("Ambiguous aliases must define exclusion phrases")
        exclusions.append(
            (
                excluded_alias.casefold(),
                tuple(phrase.casefold() for phrase in excluded_phrases),
            )
        )

    lines = COMMODITY_KEYWORDS_FILE.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "commodities:":
        raise ValueError("Commodity keyword file must start with a commodities mapping")

    for line in lines[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indentation = len(line) - len(line.lstrip())
        if indentation == 0 and stripped == "ambiguous_alias_exclusions:":
            add_definition()
            key = None
            label = None
            aliases = []
            title_topic_aliases = []
            alias_field = None
            section = "ambiguous_alias_exclusions"
        elif section == "commodities" and indentation == 2 and stripped.endswith(":"):
            add_definition()
            key = _parse_string_scalar(
                stripped.removesuffix(":").strip(),
                "commodity key",
            )
            label = None
            aliases = []
            title_topic_aliases = []
            alias_field = None
        elif section == "commodities" and indentation == 4 and stripped.startswith("label:"):
            label = _parse_string_scalar(
                stripped.removeprefix("label:").strip(),
                f"Commodity {key or '<unknown>'} label",
            )
        elif section == "commodities" and indentation == 4 and stripped == "aliases:":
            alias_field = "aliases"
        elif (
            section == "commodities"
            and indentation == 4
            and stripped == "title_topic_aliases:"
        ):
            alias_field = "title_topic_aliases"
        elif (
            section == "commodities"
            and indentation == 6
            and stripped.startswith("- ")
            and alias_field in {"aliases", "title_topic_aliases"}
        ):
            value = _parse_string_scalar(
                stripped.removeprefix("- ").strip(),
                f"Commodity {key or '<unknown>'} {alias_field.removesuffix('es')}",
            )
            (aliases if alias_field == "aliases" else title_topic_aliases).append(
                value
            )
        elif section == "ambiguous_alias_exclusions" and indentation == 2 and stripped.endswith(":"):
            add_exclusions()
            excluded_alias = _parse_string_scalar(
                stripped.removesuffix(":").strip(),
                "Ambiguous alias reference",
            )
            excluded_phrases = []
        elif (
            section == "ambiguous_alias_exclusions"
            and indentation == 4
            and stripped.startswith("- ")
        ):
            excluded_phrases.append(
                _parse_string_scalar(
                    stripped.removeprefix("- ").strip(),
                    f"Ambiguous alias {excluded_alias or '<unknown>'} exclusion phrase",
                )
            )
        else:
            raise ValueError(f"Invalid commodity keyword entry: {line}")

    add_definition()
    add_exclusions()
    return tuple(definitions), tuple(exclusions)


def _validate_aliases(commodity_key: str, aliases: list[str]) -> None:
    """Reject malformed registry entries and unsafe one-character CJK aliases."""
    for alias in aliases:
        if not alias:
            raise ValueError(f"Commodity {commodity_key} has an invalid alias")
        if len(alias) == 1 and _is_cjk_ideograph(alias):
            raise ValueError(
                f"Commodity {commodity_key} has an unsafe one-character CJK alias"
            )


def _validate_title_topic_aliases(
    commodity_key: str,
    aliases: list[str],
    title_topic_aliases: list[str],
) -> None:
    """Allow only reviewed one-character CJK aliases through the title grammar."""
    if len(title_topic_aliases) != len(set(title_topic_aliases)):
        raise ValueError(f"Commodity {commodity_key} has duplicate title topic aliases")
    for alias in title_topic_aliases:
        if len(alias) != 1 or not _is_cjk_ideograph(alias):
            raise ValueError(
                f"Commodity {commodity_key} title topic aliases must be one CJK ideograph"
            )
        if alias in aliases:
            raise ValueError(
                f"Commodity {commodity_key} title topic aliases duplicate ordinary aliases"
            )


_PLAIN_NON_STRING_SCALAR = re.compile(
    r"(?:[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?|"
    r"0[xX][0-9A-Fa-f]+|0[oO][0-7]+|0[bB][01]+)$"
)
_PLAIN_BOOLEAN_OR_NULL = frozenset({"true", "false", "null", "~"})


def _parse_string_scalar(value: str, field: str) -> str:
    """Parse one required string scalar while rejecting YAML non-string forms."""
    scalar = value.strip()
    if not scalar or scalar[0] in "[{":
        raise ValueError(f"{field} must be a non-empty string")

    if scalar[0] in "\"'":
        if len(scalar) < 2 or scalar[-1] != scalar[0]:
            raise ValueError(f"{field} must be a valid string scalar")
        scalar = scalar[1:-1]
        if not scalar.strip():
            raise ValueError(f"{field} must be a non-empty string")
        return scalar

    if scalar[-1] in "\"'":
        raise ValueError(f"{field} must be a valid string scalar")
    if (
        scalar.casefold() in _PLAIN_BOOLEAN_OR_NULL
        or _PLAIN_NON_STRING_SCALAR.fullmatch(scalar) is not None
    ):
        raise ValueError(f"{field} must be a string scalar")
    return scalar


def _is_cjk_ideograph(value: str) -> bool:
    """Recognize the CJK ranges relevant to the reviewed registry policy."""
    code_point = ord(value)
    return (
        0x3400 <= code_point <= 0x4DBF
        or 0x4E00 <= code_point <= 0x9FFF
        or 0xF900 <= code_point <= 0xFAFF
    )
