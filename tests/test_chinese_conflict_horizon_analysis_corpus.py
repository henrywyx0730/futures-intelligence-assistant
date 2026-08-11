"""G3B2 enforcement for reviewed Chinese conflict and horizon semantics."""

from datetime import datetime, timezone
import unittest

from futures_intelligence.analyst.commodity_matcher import CommodityMatcher
from futures_intelligence.analyst.commodity_relevance import CommodityRelevanceResolver
from futures_intelligence.analyst.fundamental_signal import (
    ChineseFundamentalSignalDetector,
)
from futures_intelligence.analyst.rule_based import RuleBasedAnalyst
from futures_intelligence.models import MarketInformation
from tests.chinese_deterministic_analysis_cases import (
    cases_for_phase,
    load_chinese_deterministic_corpus,
)


class _CorpusMarketInformation(MarketInformation):
    """Immutable test input preserving authored empty corpus content exactly."""

    def __init__(self, title: str, content: str) -> None:
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "source", "Synthetic corpus")
        object.__setattr__(self, "source_type", "research_report")
        object.__setattr__(
            self,
            "published_time",
            datetime(2026, 8, 11, tzinfo=timezone.utc),
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


class ChineseConflictHorizonAnalysisCorpusTests(unittest.TestCase):
    """Run all active G3B2 cases through the real deterministic analysis stack."""

    def test_all_five_cases_match_their_conflict_and_horizon_contracts(self) -> None:
        corpus = load_chinese_deterministic_corpus()
        cases = cases_for_phase(corpus, "g3b2")
        matcher = CommodityMatcher()
        resolver = CommodityRelevanceResolver(matcher=matcher)
        detector = ChineseFundamentalSignalDetector()
        analyst = RuleBasedAnalyst(
            commodity_matcher=matcher,
            commodity_relevance_resolver=resolver,
        )

        self.assertEqual(
            corpus.active_enforcement_phases,
            ("g2", "g3a", "g3b1", "g3b2"),
        )
        self.assertEqual(len(cases), 5)
        self.assertEqual(
            tuple(case.id for case in cases),
            (
                "crude-oil-clause-local-negation",
                "crude-oil-supply-demand-conflict",
                "aluminum-inventory-stock-conflict",
                "fuel-oil-horizon-conflict",
                "aluminum-capacity-horizon-conflict",
            ),
        )

        for case in cases:
            with self.subTest(case_id=case.id):
                information = _CorpusMarketInformation(case.title, case.content)
                relevance = resolver.assess(information)
                primary_keys = {entry.commodity_key for entry in relevance.primary}
                primary_matches = tuple(
                    match
                    for match in relevance.lexical_matches
                    if match.commodity_key in primary_keys
                )
                detection = detector.detect(
                    information,
                    primary_matches,
                    relevance.lexical_matches,
                )
                analysis = analyst.analyze([information])[0]

                self.assertEqual(information.title, case.title)
                self.assertEqual(information.content, case.content)
                self.assertEqual(
                    tuple(entry.commodity_key for entry in relevance.primary),
                    case.expected.commodity_keys,
                )
                self.assertEqual(relevance.mentioned, ())
                self.assertEqual(detection.signal_kind, case.expected.signal_kind)
                actual_reasoning_tags = tuple(
                    qualification.rule_id
                    for qualification in detection.qualifications
                    if qualification.rule_id is not None
                ) + tuple(signal.rule_id for signal in detection.signals)
                self.assertEqual(
                    actual_reasoning_tags,
                    case.expected.reasoning_tags,
                )
                self.assertEqual(
                    analysis.market_direction,
                    case.expected.market_direction,
                )
                self.assertEqual(
                    analysis.confidence_score,
                    75 if case.id == "crude-oil-clause-local-negation" else 60,
                )
                self.assertIs(analysis.market_information, information)


if __name__ == "__main__":
    unittest.main()
