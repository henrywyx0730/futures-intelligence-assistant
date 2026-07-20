"""Market-analysis contracts and future implementations."""

from futures_intelligence.analyst.aggregator import (
    AggregatedMarketView,
    CommodityMarketView,
    MarketAnalysisAggregator,
)
from futures_intelligence.analyst.base import BaseAnalyst
from futures_intelligence.analyst.candidate_selector import (
    LLMCandidateSelection,
    LLMCandidateSelector,
)
from futures_intelligence.analyst.llm import LLMAnalyst, LLMSmokeTestResult
from futures_intelligence.analyst.router import AnalystRouter
from futures_intelligence.analyst.rule_based import RuleBasedAnalyst

__all__ = [
    "AggregatedMarketView",
    "AnalystRouter",
    "BaseAnalyst",
    "CommodityMarketView",
    "LLMCandidateSelection",
    "LLMCandidateSelector",
    "LLMAnalyst",
    "LLMSmokeTestResult",
    "MarketAnalysisAggregator",
    "RuleBasedAnalyst",
]
