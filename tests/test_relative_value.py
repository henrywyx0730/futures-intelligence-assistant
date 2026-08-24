"""Tests for deterministic, non-directional relative-value observations."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import unittest

from futures_intelligence.analyst.commodity_matcher import CommodityMatcher
from futures_intelligence.analyst.commodity_relevance import CommodityRelevanceResolver
from futures_intelligence.analyst.fundamental_signal import (
    ChineseFundamentalSignalDetector,
)
from futures_intelligence.analyst.relative_value import (
    RelativeValueDetector,
)
from futures_intelligence.analyst.rule_based import RuleBasedAnalyst
from futures_intelligence.models import MarketInformation


def _information(
    title: str,
    content: str,
    *,
    source_type: str = "research_report",
    commodities: tuple[str, ...] = (),
) -> MarketInformation:
    return MarketInformation(
        title=title,
        source="Synthetic research",
        source_type=source_type,
        published_time=datetime(2026, 8, 21, tzinfo=timezone.utc),
        content=content,
        commodities=commodities,
        reliability_score=3,
    )


class RelativeValueDetectorTests(unittest.TestCase):
    """Exercise G4 through the real matcher and relevance boundary."""

    def setUp(self) -> None:
        self.matcher = CommodityMatcher()
        self.resolver = CommodityRelevanceResolver(matcher=self.matcher)
        self.detector = RelativeValueDetector()

    def _detect(self, information: MarketInformation):
        relevance = self.resolver.assess(information)
        primary_keys = {entry.commodity_key for entry in relevance.primary}
        primary_matches = tuple(
            match
            for match in relevance.lexical_matches
            if match.commodity_key in primary_keys
        )
        return relevance, self.detector.detect(
            information,
            primary_matches,
            relevance.lexical_matches,
        )

    def test_primary_anchor_can_relate_to_explicitly_named_mentioned_leg(self) -> None:
        information = _information(
            "原油专题报告",
            "原油与燃料油裂解价差走强。",
        )

        relevance, detection = self._detect(information)

        self.assertEqual(
            tuple(entry.commodity_key for entry in relevance.primary),
            ("crude_oil",),
        )
        self.assertEqual(
            tuple(entry.commodity_key for entry in relevance.mentioned),
            ("fuel_oil",),
        )
        self.assertEqual(len(detection.observations), 1)
        observation = detection.observations[0]
        self.assertEqual(observation.relationship_type, "crack_spread")
        self.assertEqual(
            observation.commodity_keys,
            ("crude_oil", "fuel_oil"),
        )
        self.assertEqual(observation.relationship_state, "strengthening")
        self.assertEqual(observation.direction, "not_applicable")
        self.assertEqual(observation.rule_ids, ("crack_spread_strength",))
        with self.assertRaises(FrozenInstanceError):
            observation.direction = "bullish"  # type: ignore[misc]

    def test_generic_relationship_language_is_context_only(self) -> None:
        for phrase in (
            "跨品种价差扩大。",
            "近远月价差存在修复空间。",
            "正套机会增强。",
        ):
            with self.subTest(phrase=phrase):
                information = _information("原油专题报告", phrase)
                _, detection = self._detect(information)
                self.assertEqual(detection.observations, ())

    def test_mentioned_only_and_source_scope_commodities_cannot_initiate_g4(self) -> None:
        information = _information(
            "市场结构观察",
            "原油近远月价差存在修复空间。",
            commodities=("crude_oil",),
        )

        relevance, detection = self._detect(information)

        self.assertEqual(relevance.primary, ())
        self.assertEqual(
            tuple(entry.commodity_key for entry in relevance.mentioned),
            ("crude_oil",),
        )
        self.assertEqual(detection.observations, ())

    def test_non_research_source_cannot_create_g4(self) -> None:
        information = _information(
            "原油近远月价差存在修复空间。",
            "结构变化。",
            source_type="rss",
        )
        matches = self.matcher.match(information)

        detection = self.detector.detect(information, matches, matches)

        self.assertEqual(detection.observations, ())

    def test_multi_primary_generic_language_does_not_invent_relationship(self) -> None:
        information = _information(
            "原油与燃料油专题报告",
            "跨品种价差扩大。",
        )

        relevance, detection = self._detect(information)

        self.assertEqual(
            tuple(entry.commodity_key for entry in relevance.primary),
            ("crude_oil", "fuel_oil"),
        )
        self.assertEqual(detection.observations, ())

    def test_opposing_states_for_same_relationship_are_unresolved(self) -> None:
        information = _information(
            "原铝专题报告",
            "原铝与铸造铝合金价差扩大；原铝与铸造铝合金价差收窄。",
        )

        _, detection = self._detect(information)

        self.assertEqual(len(detection.observations), 1)
        observation = detection.observations[0]
        self.assertEqual(observation.relationship_state, "unresolved")
        self.assertEqual(observation.direction, "not_applicable")
        self.assertEqual(
            observation.rule_ids,
            (
                "cross_commodity_spread_widening",
                "cross_commodity_spread_narrowing",
            ),
        )


class RelativeValueRuleBasedIntegrationTests(unittest.TestCase):
    """Protect G4 isolation from directional analysis and confidence."""

    def setUp(self) -> None:
        self.matcher = CommodityMatcher()
        self.resolver = CommodityRelevanceResolver(matcher=self.matcher)
        self.analyst = RuleBasedAnalyst(
            commodity_matcher=self.matcher,
            commodity_relevance_resolver=self.resolver,
        )

    def test_g4_observation_does_not_activate_g3_or_direction(self) -> None:
        information = _information(
            "原油近远月价差存在修复空间。",
            "结构关系受到关注。",
        )
        relevance = self.resolver.assess(information)
        primary_keys = {entry.commodity_key for entry in relevance.primary}
        primary_matches = tuple(
            match
            for match in relevance.lexical_matches
            if match.commodity_key in primary_keys
        )

        fundamental = ChineseFundamentalSignalDetector().detect(
            information,
            primary_matches,
            relevance.lexical_matches,
        )
        analysis = self.analyst.analyze([information])[0]

        self.assertEqual(fundamental.signals, ())
        self.assertEqual(fundamental.qualifications, ())
        self.assertEqual(fundamental.conflicts, ())
        self.assertEqual(analysis.market_direction, "neutral")
        self.assertEqual(analysis.confidence_score, 60)
        self.assertIn(
            "Detected a Crude Oil calendar-spread repair relationship; "
            "no outright market direction was assigned.",
            analysis.reasoning_details,
        )
        self.assertNotIn("Detected direct", " ".join(analysis.reasoning_details))
        self.assertIs(analysis.market_information, information)

    def test_g4_does_not_change_resolved_g3_direction_or_confidence(self) -> None:
        information = _information(
            "原油专题报告",
            "原油供应收紧。原油近远月价差存在修复空间。",
        )

        analysis = self.analyst.analyze([information])[0]

        self.assertEqual(analysis.market_direction, "bullish")
        self.assertEqual(analysis.confidence_score, 75)
        self.assertIn(
            "Detected direct supply tightening for Crude Oil.",
            analysis.reasoning_details,
        )
        self.assertIn(
            "Detected a Crude Oil calendar-spread repair relationship; "
            "no outright market direction was assigned.",
            analysis.reasoning_details,
        )

    def test_conflicting_g4_relationship_adds_no_directional_confidence(self) -> None:
        information = _information(
            "原铝专题报告",
            "原铝与铸造铝合金价差扩大；原铝与铸造铝合金价差收窄。",
        )

        analysis = self.analyst.analyze([information])[0]

        self.assertEqual(analysis.market_direction, "neutral")
        self.assertEqual(analysis.confidence_score, 60)
        self.assertIn(
            "Detected opposing Aluminum and Cast Aluminum Alloy spread states; "
            "the structural relationship remains unresolved.",
            analysis.reasoning_details,
        )


if __name__ == "__main__":
    unittest.main()
