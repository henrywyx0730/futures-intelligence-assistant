"""Deterministic change detection for persisted market-intelligence history."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from futures_intelligence.utils.market_history import read_market_intelligence_history


VALID_DIRECTIONS = frozenset({"bullish", "bearish", "neutral"})


@dataclass(frozen=True)
class MarketTrendChange:
    """A structured comparison of the latest two persisted market views."""

    previous_date: str | None
    latest_date: str | None
    previous_direction: str | None
    latest_direction: str | None
    direction_changed: bool
    previous_confidence_score: int | None
    latest_confidence_score: int | None
    confidence_change: int
    confidence_changed: bool


class MarketTrendChangeDetector:
    """Detect deterministic changes between the latest local history records."""

    def detect(self, history_path: str | Path) -> MarketTrendChange:
        """Read local history and compare its final two valid market views."""
        records = [
            normalized
            for record in read_market_intelligence_history(history_path)
            if (normalized := _normalize_record(record)) is not None
        ]
        if not records:
            return _empty_change()

        latest = records[-1]
        if len(records) == 1:
            return MarketTrendChange(
                previous_date=None,
                latest_date=latest["date"],
                previous_direction=None,
                latest_direction=latest["overall_direction"],
                direction_changed=False,
                previous_confidence_score=None,
                latest_confidence_score=latest["confidence_score"],
                confidence_change=0,
                confidence_changed=False,
            )

        previous = records[-2]
        confidence_change = latest["confidence_score"] - previous["confidence_score"]
        return MarketTrendChange(
            previous_date=previous["date"],
            latest_date=latest["date"],
            previous_direction=previous["overall_direction"],
            latest_direction=latest["overall_direction"],
            direction_changed=(
                previous["overall_direction"] != latest["overall_direction"]
            ),
            previous_confidence_score=previous["confidence_score"],
            latest_confidence_score=latest["confidence_score"],
            confidence_change=confidence_change,
            confidence_changed=confidence_change != 0,
        )


def _normalize_record(record: dict[str, object]) -> dict[str, str | int] | None:
    """Validate the fields needed for deterministic trend comparison."""
    date = record.get("date")
    direction = record.get("overall_direction")
    confidence_score = record.get("confidence_score")
    if (
        not isinstance(date, str)
        or not date
        or not isinstance(direction, str)
        or direction not in VALID_DIRECTIONS
        or isinstance(confidence_score, bool)
        or not isinstance(confidence_score, int)
        or not 0 <= confidence_score <= 100
    ):
        return None
    return {
        "date": date,
        "overall_direction": direction,
        "confidence_score": confidence_score,
    }


def _empty_change() -> MarketTrendChange:
    """Return the stable result when no valid history views exist."""
    return MarketTrendChange(
        previous_date=None,
        latest_date=None,
        previous_direction=None,
        latest_direction=None,
        direction_changed=False,
        previous_confidence_score=None,
        latest_confidence_score=None,
        confidence_change=0,
        confidence_changed=False,
    )
