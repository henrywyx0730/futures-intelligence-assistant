"""Deterministic rule-based market analyst."""

from __future__ import annotations

from pathlib import Path

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


class RuleBasedAnalyst(BaseAnalyst):
    """Create basic market interpretations from commodity keywords."""

    def __init__(self) -> None:
        """Load the configured commodity aliases."""
        self._commodity_keywords = _load_commodity_keywords()

    def analyze(self, information: list[MarketInformation]) -> list[MarketAnalysis]:
        """Return one deterministic analysis for each information item."""
        return [self._analysis_for(item) for item in information]

    def _analysis_for(self, item: MarketInformation) -> MarketAnalysis:
        """Build one rich, deterministic analysis without changing its summary."""
        text = f"{item.title} {item.content}".lower()
        commodities = _detected_commodities(text, self._commodity_keywords)
        market_direction, directional_details, directional_confidence = (
            _directional_signals(item, text)
        )
        reasoning_details = [
            f"Source type: {item.source_type}; reliability score: {item.reliability_score}/5."
        ]
        if commodities:
            reasoning_details.append(
                f"Detected commodity keywords: {', '.join(commodities)}."
            )
        if item.commodities:
            reasoning_details.append(
                f"Configured source commodities: {', '.join(item.commodities)}."
            )
        reasoning_details.extend(directional_details)

        confidence_score = min(
            95,
            20
            + item.reliability_score * 10
            + (10 if commodities else 0)
            + (10 if item.commodities else 0)
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
        commodities = _detected_commodities(text, self._commodity_keywords)
        if commodities:
            return (
                f"Detected commodity focus: {', '.join(commodities)}. "
                "Review potential supply, demand, inventory, and cost implications."
            )
        return (
            "No tracked commodity keywords detected. "
            "Review the information for broader market context."
        )


def _load_commodity_keywords() -> tuple[tuple[str, str], ...]:
    """Load keyword-to-label mappings in the YAML registry's stable order."""
    keywords: list[tuple[str, str]] = []
    label: str | None = None
    aliases: list[str] = []

    def add_commodity() -> None:
        if label is None:
            return
        if not aliases:
            raise ValueError("Each commodity keyword entry must define string aliases")
        keywords.extend((alias.lower(), label) for alias in aliases)

    lines = COMMODITY_KEYWORDS_FILE.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "commodities:":
        raise ValueError("Commodity keyword file must start with a commodities mapping")

    for line in lines[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indentation = len(line) - len(line.lstrip())
        if indentation == 2 and stripped.endswith(":"):
            add_commodity()
            label = None
            aliases = []
        elif indentation == 4 and stripped.startswith("label:"):
            label = stripped.removeprefix("label:").strip()
            if not label:
                raise ValueError("Each commodity keyword entry must define a label")
        elif indentation == 4 and stripped == "aliases:":
            continue
        elif indentation == 6 and stripped.startswith("- "):
            alias = stripped.removeprefix("- ").strip()
            if not alias:
                raise ValueError("Commodity aliases must be non-empty strings")
            aliases.append(alias)
        else:
            raise ValueError(f"Invalid commodity keyword entry: {line}")

    add_commodity()
    return tuple(keywords)


def _detected_commodities(
    text: str, commodity_keywords: tuple[tuple[str, str], ...]
) -> tuple[str, ...]:
    """Return unique commodity labels in a stable configured order."""
    detected: list[str] = []
    for keyword, commodity in commodity_keywords:
        if keyword in text and commodity not in detected:
            detected.append(commodity)
    return tuple(detected)


def _directional_signals(
    item: MarketInformation, text: str
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
    if len(bullish_matches) > len(bearish_matches):
        return (
            "bullish",
            (f"Bullish text signals: {', '.join(bullish_matches)}.",),
            10,
        )
    if len(bearish_matches) > len(bullish_matches):
        return (
            "bearish",
            (f"Bearish text signals: {', '.join(bearish_matches)}.",),
            10,
        )
    return (
        "neutral",
        ("No deterministic directional signal was detected.",),
        0,
    )


def _matched_keywords(text: str, keywords: tuple[str, ...]) -> tuple[str, ...]:
    """Return matched keywords in their configured deterministic order."""
    return tuple(keyword for keyword in keywords if keyword in text)


def _is_number(value: object) -> bool:
    """Return whether metadata contains a numeric, non-boolean value."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)
