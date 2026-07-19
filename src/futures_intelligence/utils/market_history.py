"""Local JSON persistence for aggregated market-intelligence history."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from futures_intelligence.analyst import AggregatedMarketView
from futures_intelligence.models import MarketInformation


@dataclass(frozen=True)
class MarketIntelligenceHistoryEntry:
    """One persisted aggregate market view for a morning brief run."""

    date: str
    commodities: tuple[str, ...]
    categories: tuple[str, ...]
    overall_direction: str
    confidence_score: int
    reasoning_details: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible history record."""
        return asdict(self)


def append_market_intelligence_history(
    path: str | Path,
    market_view: AggregatedMarketView,
    information: list[MarketInformation],
    timestamp: datetime | None = None,
) -> MarketIntelligenceHistoryEntry:
    """Append one UTC-dated aggregate view to a local JSON history file."""
    entry = MarketIntelligenceHistoryEntry(
        date=(timestamp or datetime.now(timezone.utc)).date().isoformat(),
        commodities=_combined_values(information, "commodities"),
        categories=_combined_values(information, "category"),
        overall_direction=market_view.overall_market_direction,
        confidence_score=market_view.aggregated_confidence_score,
        reasoning_details=market_view.reasoning_details,
    )
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    history = _read_history(output_path)
    history.append(entry.to_dict())
    output_path.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
    return entry


def _combined_values(
    information: list[MarketInformation], field_name: str
) -> tuple[str, ...]:
    """Combine tuple-valued source fields in stable input order."""
    combined: list[str] = []
    for item in information:
        for value in getattr(item, field_name):
            if value not in combined:
                combined.append(value)
    return tuple(combined)


def _read_history(path: Path) -> list[dict[str, object]]:
    """Return a valid existing local history list, or an empty history."""
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(history, list):
        return []
    return [entry for entry in history if isinstance(entry, dict)]
