"""G3B1 enforcement for reviewed Chinese qualified fundamentals."""

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


_QUALIFICATION_REASON_BY_KIND = {
    "negated_signal": (
        "Detected a negated fundamental statement; "
        "no realized factual direction was assigned."
    ),
    "uncertain_signal": (
        "Detected an uncertain fundamental statement; "
        "no realized factual direction was assigned."
    ),
    "conditional_signal": (
        "Detected a conditional fundamental statement; "
        "no realized factual direction was assigned."
    ),
    "forecast_signal": (
        "Detected a forecast fundamental statement; "
        "no realized factual direction was assigned."
    ),
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


class ChineseQualifiedAnalysisCorpusTests(unittest.TestCase):
    """Run the exact active G3B1 subset through the real analysis stack."""

    def test_all_eleven_qualified_cases_abstain_with_reviewed_semantics(self) -> None:
        corpus = load_chinese_deterministic_corpus()
        cases = cases_for_phase(corpus, "g3b1")
        matcher = CommodityMatcher()
        resolver = CommodityRelevanceResolver(matcher=matcher)
        analyst = RuleBasedAnalyst(
            commodity_matcher=matcher,
            commodity_relevance_resolver=resolver,
        )

        self.assertEqual(
            corpus.active_enforcement_phases,
            ("g2", "g3a", "g3b1", "g3b2", "g4"),
        )
        self.assertEqual(len(cases), 11)
        self.assertEqual(
            tuple(case.id for case in cases),
            tuple(
                case.id
                for case in corpus.cases
                if case.enforcement.direction == "g3b1"
            ),
        )
        for case in cases:
            with self.subTest(case_id=case.id):
                information = _CorpusMarketInformation(case.title, case.content)
                relevance = resolver.assess(information)
                analysis = analyst.analyze([information])[0]
                qualification_kind = case.expected.signal_kind
                if qualification_kind == "conditional_signal" and (
                    "forecast" in case.scenario_tags
                    and "conditional" not in case.scenario_tags
                ):
                    qualification_kind = "forecast_signal"

                self.assertEqual(information.title, case.title)
                self.assertEqual(information.content, case.content)
                self.assertEqual(
                    tuple(item.commodity_key for item in relevance.primary),
                    case.expected.commodity_keys,
                )
                self.assertEqual(relevance.mentioned, ())
                self.assertEqual(
                    analysis.market_direction,
                    case.expected.market_direction,
                )
                self.assertEqual(analysis.confidence_score, 60)
                self.assertIn(
                    _QUALIFICATION_REASON_BY_KIND[qualification_kind],
                    analysis.reasoning_details,
                )
                self.assertNotIn(
                    "Detected direct",
                    " ".join(analysis.reasoning_details),
                )
                self.assertIs(analysis.market_information, information)


if __name__ == "__main__":
    unittest.main()
