"""Market-analysis contracts and future implementations."""

from futures_intelligence.analyst.aggregator import (
    AggregatedMarketView,
    MarketAnalysisAggregator,
)
from futures_intelligence.analyst.base import BaseAnalyst
from futures_intelligence.analyst.router import AnalystRouter
from futures_intelligence.analyst.rule_based import RuleBasedAnalyst

__all__ = [
    "AggregatedMarketView",
    "AnalystRouter",
    "BaseAnalyst",
    "MarketAnalysisAggregator",
    "RuleBasedAnalyst",
]
