"""Deterministic rule-based market analyst."""

from __future__ import annotations

from pathlib import Path

from futures_intelligence.analyst.base import BaseAnalyst
from futures_intelligence.models import MarketAnalysis, MarketInformation


COMMODITY_KEYWORDS_FILE = (
    Path(__file__).resolve().parents[3] / "knowledge" / "commodity_keywords.yaml"
)


class RuleBasedAnalyst(BaseAnalyst):
    """Create basic market interpretations from commodity keywords."""

    def __init__(self) -> None:
        """Load the configured commodity aliases."""
        self._commodity_keywords = _load_commodity_keywords()

    def analyze(self, information: list[MarketInformation]) -> list[MarketAnalysis]:
        """Return one deterministic analysis for each information item."""
        return [
            MarketAnalysis(item, self._summary_for(item)) for item in information
        ]

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
