"""Knowledge-backed, article-level commodity matching."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

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


@dataclass(frozen=True)
class CommodityMatch:
    """One immutable article-level commodity match with supporting aliases."""

    commodity_key: str
    commodity_label: str
    matched_aliases: tuple[str, ...]


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
        text = f"{information.title} {information.content}"
        matches: list[CommodityMatch] = []
        for definition in self._definitions:
            aliases = tuple(
                alias
                for alias in sorted(definition.aliases, key=len, reverse=True)
                if self._alias_matches(text, alias)
            )
            if aliases:
                matches.append(
                    CommodityMatch(
                        commodity_key=definition.commodity_key,
                        commodity_label=definition.commodity_label,
                        matched_aliases=aliases,
                    )
                )
        return tuple(matches)

    def _alias_matches(self, text: str, alias: str) -> bool:
        """Apply explicit phrase exclusions before matching an ambiguous alias."""
        exclusions = self._ambiguous_alias_exclusions.get(alias.casefold(), ())
        if any(phrase_matches(text, phrase) for phrase in exclusions):
            return False
        return phrase_matches(text, alias)


def phrase_matches(text: str, phrase: str) -> bool:
    """Match a configured phrase outside larger tokens, allowing punctuation separators."""
    parts = phrase.casefold().split()
    pattern = r"(?:[\W_]+)".join(re.escape(part) for part in parts)
    return re.search(rf"(?<!\w){pattern}(?!\w)", text.casefold()) is not None


def _load_commodity_registry() -> tuple[
    tuple[CommodityDefinition, ...], tuple[tuple[str, tuple[str, ...]], ...]
]:
    """Parse the small project registry without adding a YAML dependency."""
    definitions: list[CommodityDefinition] = []
    exclusions: list[tuple[str, tuple[str, ...]]] = []
    key: str | None = None
    label: str | None = None
    aliases: list[str] = []
    excluded_alias: str | None = None
    excluded_phrases: list[str] = []
    section = "commodities"

    def add_definition() -> None:
        if key is None and label is None and not aliases:
            return
        if not key or not label or not aliases:
            raise ValueError("Each commodity entry must define a key, label, and aliases")
        definitions.append(
            CommodityDefinition(key, label, tuple(alias.casefold() for alias in aliases))
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
            section = "ambiguous_alias_exclusions"
        elif section == "commodities" and indentation == 2 and stripped.endswith(":"):
            add_definition()
            key = stripped.removesuffix(":").strip()
            label = None
            aliases = []
        elif section == "commodities" and indentation == 4 and stripped.startswith("label:"):
            label = stripped.removeprefix("label:").strip()
        elif section == "commodities" and indentation == 4 and stripped == "aliases:":
            continue
        elif section == "commodities" and indentation == 6 and stripped.startswith("- "):
            aliases.append(stripped.removeprefix("- ").strip())
        elif section == "ambiguous_alias_exclusions" and indentation == 2 and stripped.endswith(":"):
            add_exclusions()
            excluded_alias = stripped.removesuffix(":").strip()
            excluded_phrases = []
        elif (
            section == "ambiguous_alias_exclusions"
            and indentation == 4
            and stripped.startswith("- ")
        ):
            excluded_phrases.append(stripped.removeprefix("- ").strip())
        else:
            raise ValueError(f"Invalid commodity keyword entry: {line}")

    add_definition()
    add_exclusions()
    return tuple(definitions), tuple(exclusions)
