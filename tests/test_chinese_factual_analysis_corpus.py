"""G3A enforcement for reviewed direct Chinese factual fundamentals."""

from datetime import datetime, timezone
import unittest

from futures_intelligence.analyst.commodity_matcher import CommodityMatcher
from futures_intelligence.analyst.commodity_relevance import CommodityRelevanceResolver
from futures_intelligence.analyst.rule_based import RuleBasedAnalyst
from futures_intelligence.models import MarketInformation
from tests.chinese_deterministic_analysis_cases import (
    cases_for_phase,
    load_chinese_deterministic_corpus,
)


_REASONING_BY_TAG = {
    "supply_tightening": "Detected direct supply tightening for Crude Oil.",
    "supply_reduction": "Detected direct supply reduction for Fuel Oil.",
    "inventory_decline": "Detected direct inventory decline for Live Hog.",
    "inventory_destock": "Detected direct inventory destocking for Aluminum.",
    "demand_improvement": "Detected direct demand improvement for Wheat.",
    "cost_support": "Detected direct cost support strengthening for Corn.",
    "supply_increase": "Detected direct supply increase for Crude Oil.",
    "supply_loose": "Detected direct loose supply for Fuel Oil.",
    "inventory_accumulation": "Detected direct inventory accumulation for Live Hog.",
    "inventory_increase": "Detected direct inventory increase for Aluminum.",
    "demand_weakness": "Detected direct demand weakness for Soybean Meal.",
    "cost_decline": "Detected direct cost decline for Corn.",
}


class _CorpusMarketInformation(MarketInformation):
    """Immutable test input preserving authored empty corpus content exactly."""

    def __init__(self, title: str, content: str) -> None:
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "source", "Synthetic corpus")
        object.__setattr__(self, "source_type", "research_report")
        object.__setattr__(
            self,
            "published_time",
            datetime(2026, 8, 10, tzinfo=timezone.utc),
        )
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "category", ())
        object.__setattr__(self, "commodities", ())
        object.__setattr__(self, "regions", ())
        object.__setattr__(self, "importance", "medium")
        object.__setattr__(self, "reliability_score", 3)
        object.__setattr__(self, "url", None)
        object.__setattr__(self, "metadata", {})

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("corpus information is immutable")


class ChineseFactualAnalysisCorpusTests(unittest.TestCase):
    """Run all active G3A cases through real matcher, relevance, and analysis."""

    def test_all_twelve_factual_cases_match_their_direction_contracts(self) -> None:
        corpus = load_chinese_deterministic_corpus()
        cases = cases_for_phase(corpus, "g3a")
        matcher = CommodityMatcher()
        resolver = CommodityRelevanceResolver(matcher=matcher)
        analyst = RuleBasedAnalyst(
            commodity_matcher=matcher,
            commodity_relevance_resolver=resolver,
        )

        self.assertEqual(
            corpus.active_enforcement_phases,
            ("g2", "g3a", "g3b1", "g3b2"),
        )
        self.assertEqual(len(cases), 12)
        self.assertEqual(
            tuple(case.id for case in cases),
            tuple(
                case.id
                for case in corpus.cases
                if case.enforcement.direction == "g3a"
            ),
        )
        for case in cases:
            with self.subTest(case_id=case.id):
                information = _CorpusMarketInformation(case.title, case.content)
                self.assertEqual(information.title, case.title)
                self.assertEqual(information.content, case.content)

                relevance = resolver.assess(information)
                analysis = analyst.analyze([information])[0]

                self.assertEqual(
                    tuple(match.commodity_key for match in relevance.lexical_matches),
                    case.expected.commodity_keys,
                )
                self.assertEqual(
                    tuple(item.commodity_key for item in relevance.primary),
                    case.expected.commodity_keys,
                )
                self.assertEqual(relevance.mentioned, ())
                self.assertEqual(analysis.market_direction, case.expected.market_direction)
                self.assertEqual(case.expected.signal_kind, "fundamental_fact")
                self.assertEqual(len(case.expected.reasoning_tags), 1)
                self.assertIn(
                    _REASONING_BY_TAG[case.expected.reasoning_tags[0]],
                    analysis.reasoning_details,
                )
                self.assertEqual(analysis.confidence_score, 75)
                self.assertIs(analysis.market_information, information)


if __name__ == "__main__":
    unittest.main()
