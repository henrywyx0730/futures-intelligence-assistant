"""Deterministic detection of explicitly observed commodity-market price movement."""

from __future__ import annotations

from dataclasses import dataclass
import re

from futures_intelligence.analyst.commodity_matcher import CommodityMatch, phrase_matches
from futures_intelligence.models import MarketInformation


SETTLEMENT_PRIORITY = 3
NUMERICAL_PRIORITY = 2
MOVEMENT_PRIORITY = 1
MARKET_OBJECT_PATTERN = re.compile(
    r"\b(?:price|prices|futures?|contract|contracts|market|markets|index|spot|settlement)\b",
    re.IGNORECASE,
)
NON_PRICE_SUBJECT_PATTERN = re.compile(
    r"\b(?:production|inventories?|throughput|interest rates?|geopolitical risk)\b",
    re.IGNORECASE,
)
SETTLEMENT_PATTERN = re.compile(
    r"\b(?:settles?|settled|settling|closes?|closed|closing)\s+(?:at\s+)?"
    r"(?P<direction>higher|lower)\b",
    re.IGNORECASE,
)
SIGNED_MOVEMENT_PATTERN = re.compile(
    r"\b(?P<direction>up|down)\s+"
    r"(?:[₹$€£]\s*)?\d[\d,]*(?:\.\d+)?(?:\s*%|\s*(?:points?|basis points?))?",
    re.IGNORECASE,
)
NUMERICAL_VERB_PATTERN = re.compile(
    r"\b(?P<direction>jumped|rose|rallied|advanced|gained|gains|fell|dropped|"
    r"declined|declines|falls|slipped)\s+(?:by\s+)?(?:[₹$€£]\s*)?"
    r"\d[\d,]*(?:\.\d+)?(?:\s*%|\s*(?:points?|basis points?))?",
    re.IGNORECASE,
)
OPENING_PATTERN = re.compile(
    r"\b(?:opens?|opened|trades?|traded)\s+(?:[₹$€£]\s*\d[\d,]*(?:\.\d+)?\s*)?"
    r"(?P<direction>higher|lower)\b",
    re.IGNORECASE,
)
MOVEMENT_PATTERN = re.compile(
    r"\b(?P<direction>rises?|rallied|rallies|advances?|gains?|"
    r"fell|falls|dropped|declines?|slips?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MarketMovementSignal:
    """One resolved observed market-price movement signal."""

    direction: str
    evidence: str
    priority: int


@dataclass(frozen=True)
class _MovementCandidate:
    """One context-qualified movement phrase retained for priority resolution."""

    direction: str
    evidence: str
    priority: int
    position: int


class MarketMovementDetector:
    """Find observed price movement without treating unrelated metrics as prices."""

    def detect(
        self,
        information: MarketInformation,
        commodity_matches: tuple[CommodityMatch, ...],
    ) -> MarketMovementSignal:
        """Resolve all title/content movement candidates deterministically."""
        text = f"{information.title}\n{information.content}"
        candidates = [
            candidate
            for pattern, priority in (
                (SETTLEMENT_PATTERN, SETTLEMENT_PRIORITY),
                (SIGNED_MOVEMENT_PATTERN, NUMERICAL_PRIORITY),
                (NUMERICAL_VERB_PATTERN, NUMERICAL_PRIORITY),
                (OPENING_PATTERN, NUMERICAL_PRIORITY),
                (MOVEMENT_PATTERN, MOVEMENT_PRIORITY),
            )
            for candidate in self._candidates_for_pattern(
                text, pattern, priority, commodity_matches
            )
        ]
        if not candidates:
            return MarketMovementSignal(
                direction="neutral",
                evidence="No explicit observed market-price movement detected",
                priority=0,
            )

        highest_priority = max(candidate.priority for candidate in candidates)
        highest_candidates = [
            candidate
            for candidate in candidates
            if candidate.priority == highest_priority
        ]
        directions = {candidate.direction for candidate in highest_candidates}
        if len(directions) > 1:
            return MarketMovementSignal(
                direction="neutral",
                evidence="Conflicting observed market-price movements were detected",
                priority=highest_priority,
            )
        selected = min(highest_candidates, key=lambda candidate: candidate.position)
        return MarketMovementSignal(
            direction=selected.direction,
            evidence=selected.evidence,
            priority=selected.priority,
        )

    def _candidates_for_pattern(
        self,
        text: str,
        pattern: re.Pattern[str],
        priority: int,
        commodity_matches: tuple[CommodityMatch, ...],
    ) -> tuple[_MovementCandidate, ...]:
        """Collect all context-qualified candidates for one deterministic pattern."""
        candidates: list[_MovementCandidate] = []
        for match in pattern.finditer(text):
            if not _has_market_price_context(text, match.start(), match.end(), commodity_matches):
                continue
            direction = _direction_for(match.group("direction"))
            candidates.append(
                _MovementCandidate(
                    direction=direction,
                    evidence=_evidence_before(text, match.end()),
                    priority=priority,
                    position=match.start(),
                )
            )
        return tuple(candidates)


def _has_market_price_context(
    text: str,
    start: int,
    end: int,
    commodity_matches: tuple[CommodityMatch, ...],
) -> bool:
    """Require a nearby commodity or market object while rejecting metric subjects."""
    context_start = max(
        text.rfind(marker, 0, start)
        for marker in (".", "!", "?", ";", ":", "\n")
    ) + 1
    left = text[max(context_start, start - 60) : start]
    nearby = text[max(context_start, start - 60) : min(len(text), end + 20)]
    if NON_PRICE_SUBJECT_PATTERN.search(left):
        return False
    if MARKET_OBJECT_PATTERN.search(nearby):
        return True
    return any(
        phrase_matches(left, alias)
        for commodity_match in commodity_matches
        for alias in commodity_match.matched_aliases
    )


def _direction_for(value: str) -> str:
    """Normalize one configured movement phrase into bullish or bearish direction."""
    normalized = value.casefold()
    if normalized in {
        "up",
        "jumped",
        "rose",
        "rallied",
        "rallies",
        "advanced",
        "advances",
        "gained",
        "gains",
        "rise",
        "rises",
        "higher",
    }:
        return "bullish"
    return "bearish"


def _evidence_before(text: str, end: int) -> str:
    """Return concise original movement context from the containing sentence or clause."""
    start = max(text.rfind(marker, 0, end) for marker in (".", "!", "?", ";", ":")) + 1
    return text[start:end].strip(" \t,;:-—")
