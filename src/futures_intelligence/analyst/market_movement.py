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
NUMBER_PATTERN = r"(?:[+-]\s*)?(?:[₹$€£]\s*)?\d[\d,]*(?:\.\d+)?"
SETTLEMENT_PATTERN = re.compile(
    r"\b(?:settles?|settled|settling|closes?|closed|closing)\s+(?:at\s+)?"
    r"(?P<direction>higher|lower)\b",
    re.IGNORECASE,
)
SIGNED_MOVEMENT_PATTERN = re.compile(
    rf"\b(?P<direction>up|down)\s+{NUMBER_PATTERN}"
    r"(?:\s*%|\s*(?:points?|basis points?))?",
    re.IGNORECASE,
)
NUMERICAL_VERB_PATTERN = re.compile(
    rf"\b(?P<direction>jumped|rose|rallied|advanced|gained|gains|fell|dropped|"
    rf"declined|declines|falls|slipped)\s+(?:by\s+)?{NUMBER_PATTERN}"
    r"(?:\s*%|\s*(?:points?|basis points?))?",
    re.IGNORECASE,
)
OPENING_PATTERN = re.compile(
    rf"\b(?:opens?|opened|trades?|traded)\s+{NUMBER_PATTERN}\s*"
    r"(?P<direction>higher|lower)\b",
    re.IGNORECASE,
)
MOVEMENT_PATTERN = re.compile(
    r"\b(?P<direction>rises?|rallied|rallies|advances?|gains?|"
    r"fell|falls|dropped|declines?|slips?)\b",
    re.IGNORECASE,
)
SUBJECT_SEPARATOR_PATTERN = re.compile(r"\b(?:while|but)\b", re.IGNORECASE)


@dataclass(frozen=True)
class MarketMovementSignal:
    """One resolved observed market-price movement signal."""

    direction: str
    evidence: str
    priority: int


@dataclass(frozen=True)
class CommodityMovementSignal:
    """One resolved observed price movement for a detected commodity only."""

    commodity_key: str
    commodity_label: str
    direction: str
    evidence: str
    priority: int


@dataclass(frozen=True)
class _MovementCandidate:
    """One context-qualified phrase retained for deterministic resolution."""

    direction: str
    evidence: str
    priority: int
    position: int
    subject: str


class MarketMovementDetector:
    """Find observed price movement without treating unrelated metrics as prices."""

    def detect(
        self,
        information: MarketInformation,
        commodity_matches: tuple[CommodityMatch, ...],
    ) -> MarketMovementSignal:
        """Resolve all article-level movement candidates deterministically."""
        candidates = self._candidates(information, commodity_matches)
        return _resolve_market_signal(candidates)

    def detect_by_commodity(
        self,
        information: MarketInformation,
        commodity_matches: tuple[CommodityMatch, ...],
    ) -> tuple[CommodityMovementSignal, ...]:
        """Resolve one isolated movement signal for each genuinely detected commodity."""
        candidates = self._candidates(information, commodity_matches)
        signals: list[CommodityMovementSignal] = []
        for commodity_match in commodity_matches:
            scoped_candidates = tuple(
                candidate
                for candidate in candidates
                if _candidate_belongs_to(candidate, commodity_match)
            )
            if not scoped_candidates:
                continue
            resolved = _resolve_market_signal(scoped_candidates)
            signals.append(
                CommodityMovementSignal(
                    commodity_key=commodity_match.commodity_key,
                    commodity_label=commodity_match.commodity_label,
                    direction=resolved.direction,
                    evidence=resolved.evidence,
                    priority=resolved.priority,
                )
            )
        return tuple(signals)

    def _candidates(
        self,
        information: MarketInformation,
        commodity_matches: tuple[CommodityMatch, ...],
    ) -> tuple[_MovementCandidate, ...]:
        """Collect every price-context-qualified movement candidate exactly once."""
        text = f"{information.title}\n{information.content}"
        return tuple(
            candidate
            for pattern, priority in (
                (SETTLEMENT_PATTERN, SETTLEMENT_PRIORITY),
                (SIGNED_MOVEMENT_PATTERN, NUMERICAL_PRIORITY),
                (NUMERICAL_VERB_PATTERN, NUMERICAL_PRIORITY),
                (OPENING_PATTERN, NUMERICAL_PRIORITY),
                (MOVEMENT_PATTERN, MOVEMENT_PRIORITY),
            )
            for candidate in _candidates_for_pattern(
                text, pattern, priority, commodity_matches
            )
        )


def _candidates_for_pattern(
    text: str,
    pattern: re.Pattern[str],
    priority: int,
    commodity_matches: tuple[CommodityMatch, ...],
) -> tuple[_MovementCandidate, ...]:
    """Collect context-qualified candidates for one movement pattern."""
    candidates: list[_MovementCandidate] = []
    for match in pattern.finditer(text):
        if not _has_market_price_context(text, match.start(), match.end(), commodity_matches):
            continue
        subject = _movement_subject(text, match.start(), commodity_matches)
        candidates.append(
            _MovementCandidate(
                direction=_direction_for(match.group("direction")),
                evidence=_evidence_for_match(
                    text,
                    match.start(),
                    match.end(),
                    subject,
                ),
                priority=priority,
                position=match.start(),
                subject=subject,
            )
        )
    return tuple(candidates)


def _resolve_market_signal(
    candidates: tuple[_MovementCandidate, ...],
) -> MarketMovementSignal:
    """Resolve the highest-priority candidates, treating equal conflicts as neutral."""
    if not candidates:
        return MarketMovementSignal(
            direction="neutral",
            evidence="No explicit observed market-price movement detected",
            priority=0,
        )
    highest_priority = max(candidate.priority for candidate in candidates)
    highest_candidates = tuple(
        candidate for candidate in candidates if candidate.priority == highest_priority
    )
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


def _candidate_belongs_to(
    candidate: _MovementCandidate,
    commodity_match: CommodityMatch,
) -> bool:
    """Associate candidates only with aliases in their grammatical subject segment."""
    return any(
        phrase_matches(candidate.subject, alias)
        for alias in commodity_match.matched_aliases
    )


def _has_market_price_context(
    text: str,
    start: int,
    end: int,
    commodity_matches: tuple[CommodityMatch, ...],
) -> bool:
    """Require a nearby commodity or market object while rejecting metric subjects."""
    context_start = _context_start(text, start)
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


def _context_start(text: str, position: int) -> int:
    """Return the current sentence or clause start without splitting decimal values."""
    for index in range(position - 1, -1, -1):
        character = text[index]
        if character in "!?;:\n":
            return index + 1
        if character == "." and not (
            index > 0
            and index + 1 < len(text)
            and text[index - 1].isdigit()
            and text[index + 1].isdigit()
        ):
            return index + 1
    return 0


def _movement_subject(
    text: str,
    start: int,
    commodity_matches: tuple[CommodityMatch, ...],
) -> str:
    """Return a commodity subject, retaining earlier context when a contrast omits it."""
    context = text[_context_start(text, start) : start]
    separators = tuple(SUBJECT_SEPARATOR_PATTERN.finditer(context))
    if separators:
        subject = context[separators[-1].end() :]
        if _contains_detected_alias(subject, commodity_matches):
            return subject
    return context


def _contains_detected_alias(
    text: str,
    commodity_matches: tuple[CommodityMatch, ...],
) -> bool:
    """Return whether a bounded subject contains an article-level commodity alias."""
    return any(
        phrase_matches(text, alias)
        for commodity_match in commodity_matches
        for alias in commodity_match.matched_aliases
    )


def _direction_for(value: str) -> str:
    """Normalize one configured movement phrase into bullish or bearish direction."""
    if value.casefold() in {
        "up",
        "jumped",
        "rose",
        "rallied",
        "rallies",
        "advanced",
        "advances",
        "gained",
        "gains",
        "gain",
        "rise",
        "rises",
        "higher",
    }:
        return "bullish"
    return "bearish"


def _evidence_for_match(text: str, start: int, end: int, subject: str) -> str:
    """Return the complete matched phrase with its local subject context."""
    return f"{subject}{text[start:end]}".strip(" \t,;:-—")
