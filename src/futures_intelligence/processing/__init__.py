"""Market-information processing components."""

from futures_intelligence.processing.deduplicator import InformationDeduplicator
from futures_intelligence.processing.trend_detector import (
    MarketTrendChange,
    MarketTrendChangeDetector,
)

__all__ = [
    "InformationDeduplicator",
    "MarketTrendChange",
    "MarketTrendChangeDetector",
]
