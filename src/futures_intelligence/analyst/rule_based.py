"""Deterministic rule-based market analyst."""

from __future__ import annotations

from pathlib import Path
import re

from futures_intelligence.analyst.base import BaseAnalyst
from futures_intelligence.models import MarketAnalysis, MarketInformation


COMMODITY_KEYWORDS_FILE = (
    Path(__file__).resolve().parents[3] / "knowledge" / "commodity_keywords.yaml"
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

    def __init__(self) -> None:
        """Load the configured commodity aliases."""
        (
            self._commodity_keywords,
            self._ambiguous_alias_exclusions,
        ) = _load_commodity_keywords()

    def analyze(self, information: list[MarketInformation]) -> list[MarketAnalysis]:
        """Return one deterministic analysis for each information item."""
        return [self._analysis_for(item) for item in information]

    def _analysis_for(self, item: MarketInformation) -> MarketAnalysis:
        """Build one rich, deterministic analysis without changing its summary."""
        text = f"{item.title} {item.content}".lower()
        commodities = _detected_commodities(
            text,
            self._commodity_keywords,
            self._ambiguous_alias_exclusions,
        )
        market_direction, directional_details, directional_confidence = (
            _directional_signals(item, text, commodities)
        )
        reasoning_details = [
            f"Source type: {item.source_type}; reliability score: {item.reliability_score}/5."
        ]
        if commodities:
            reasoning_details.append(
                f"Detected commodity keywords: {', '.join(commodities)}."
            )
        reasoning_details.extend(directional_details)

        confidence_score = min(
            95,
            20
            + item.reliability_score * 10
            + (10 if commodities else 0)
            + directional_confidence,
        )
        return MarketAnalysis(
            market_information=item,
            summary=self._summary_for(item),
            market_direction=market_direction,
            confidence_score=confidence_score,
            reasoning_details=tuple(reasoning_details),
        )

    def _summary_for(self, item: MarketInformation) -> str:
        """Build a concise interpretation from title and content keywords."""
        text = f"{item.title} {item.content}".lower()
        commodities = _detected_commodities(
            text,
            self._commodity_keywords,
            self._ambiguous_alias_exclusions,
        )
        if commodities:
            return (
                f"Detected commodity focus: {', '.join(commodities)}. "
                "Review potential supply, demand, inventory, and cost implications."
            )
        return (
            "No tracked commodity keywords detected. "
            "Review the information for broader market context."
        )


def _load_commodity_keywords() -> tuple[
    tuple[tuple[str, str], ...], tuple[tuple[str, tuple[str, ...]], ...]
]:
    """Load aliases and explicit generic-alias exclusions in stable file order."""
    keywords: list[tuple[str, str]] = []
    exclusions: list[tuple[str, tuple[str, ...]]] = []
    label: str | None = None
    aliases: list[str] = []
    excluded_alias: str | None = None
    excluded_phrases: list[str] = []
    section = "commodities"

    def add_commodity() -> None:
        if label is None:
            return
        if not aliases:
            raise ValueError("Each commodity keyword entry must define string aliases")
        keywords.extend((alias.lower(), label) for alias in aliases)

    def add_exclusions() -> None:
        if excluded_alias is None:
            return
        if not excluded_phrases:
            raise ValueError("Ambiguous aliases must define exclusion phrases")
        exclusions.append(
            (excluded_alias.lower(), tuple(phrase.lower() for phrase in excluded_phrases))
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
            add_commodity()
            label = None
            aliases = []
            section = "ambiguous_alias_exclusions"
        elif section == "commodities" and indentation == 2 and stripped.endswith(":"):
            add_commodity()
            label = None
            aliases = []
        elif section == "commodities" and indentation == 4 and stripped.startswith("label:"):
            label = stripped.removeprefix("label:").strip()
            if not label:
                raise ValueError("Each commodity keyword entry must define a label")
        elif section == "commodities" and indentation == 4 and stripped == "aliases:":
            continue
        elif section == "commodities" and indentation == 6 and stripped.startswith("- "):
            alias = stripped.removeprefix("- ").strip()
            if not alias:
                raise ValueError("Commodity aliases must be non-empty strings")
            aliases.append(alias)
        elif section == "ambiguous_alias_exclusions" and indentation == 2 and stripped.endswith(":"):
            add_exclusions()
            excluded_alias = stripped.removesuffix(":").strip()
            excluded_phrases = []
            if not excluded_alias:
                raise ValueError("Ambiguous aliases must be non-empty strings")
        elif (
            section == "ambiguous_alias_exclusions"
            and indentation == 4
            and stripped.startswith("- ")
        ):
            phrase = stripped.removeprefix("- ").strip()
            if not phrase:
                raise ValueError("Ambiguous alias exclusions must be non-empty strings")
            excluded_phrases.append(phrase)
        else:
            raise ValueError(f"Invalid commodity keyword entry: {line}")

    add_commodity()
    add_exclusions()
    return tuple(keywords), tuple(exclusions)


def _detected_commodities(
    text: str,
    commodity_keywords: tuple[tuple[str, str], ...],
    ambiguous_alias_exclusions: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[str, ...]:
    """Return unique commodity labels in a stable configured order."""
    exclusions = dict(ambiguous_alias_exclusions)
    matched_keywords: set[tuple[str, str]] = set()
    for keyword, commodity in sorted(
        commodity_keywords, key=lambda entry: len(entry[0]), reverse=True
    ):
        if keyword in exclusions and any(
            _matches_phrase(text, phrase) for phrase in exclusions[keyword]
        ):
            continue
        if _matches_phrase(text, keyword):
            matched_keywords.add((keyword, commodity))

    detected: list[str] = []
    for keyword, commodity in commodity_keywords:
        if (keyword, commodity) in matched_keywords and commodity not in detected:
            detected.append(commodity)
    return tuple(detected)


def _directional_signals(
    item: MarketInformation,
    text: str,
    detected_commodities: tuple[str, ...],
) -> tuple[str, tuple[str, ...], int]:
    """Determine direction from structured quote data or deterministic text terms."""
    price_change = item.metadata.get("price_change")
    if _is_number(price_change):
        if price_change > 0:
            return (
                "bullish",
                (f"Structured price change is positive ({price_change}).",),
                20,
            )
        if price_change < 0:
            return (
                "bearish",
                (f"Structured price change is negative ({price_change}).",),
                20,
            )
        return (
            "neutral",
            ("Structured price change is unchanged (0).",),
            20,
        )

    bullish_matches = _matched_keywords(text, BULLISH_KEYWORDS)
    bearish_matches = _matched_keywords(text, BEARISH_KEYWORDS)
    commodity_bullish, commodity_bearish, commodity_details = _commodity_signals(
        text,
        detected_commodities,
    )
    bullish_details = _generic_signal_details(
        "Bullish", bullish_matches
    ) + commodity_details[0]
    bearish_details = _generic_signal_details(
        "Bearish", bearish_matches
    ) + commodity_details[1]
    bullish_count = len(bullish_matches) + len(commodity_bullish)
    bearish_count = len(bearish_matches) + len(commodity_bearish)
    confidence = 15 if commodity_bullish or commodity_bearish else 10
    if bullish_count > bearish_count:
        return (
            "bullish",
            bullish_details,
            confidence,
        )
    if bearish_count > bullish_count:
        return (
            "bearish",
            bearish_details,
            confidence,
        )
    if bullish_count or bearish_count:
        return (
            "neutral",
            ("Conflicting bullish and bearish deterministic signals were detected.",),
            confidence,
        )
    return (
        "neutral",
        ("No deterministic directional signal was detected.",),
        0,
    )


def _matched_keywords(text: str, keywords: tuple[str, ...]) -> tuple[str, ...]:
    """Return matched keywords in their configured deterministic order."""
    return tuple(keyword for keyword in keywords if _matches_phrase(text, keyword))


def _matches_phrase(text: str, phrase: str) -> bool:
    """Match a configured phrase outside larger tokens, allowing punctuation separators."""
    parts = phrase.casefold().split()
    pattern = r"(?:[\W_]+)".join(re.escape(part) for part in parts)
    return re.search(rf"(?<!\w){pattern}(?!\w)", text.casefold()) is not None


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
