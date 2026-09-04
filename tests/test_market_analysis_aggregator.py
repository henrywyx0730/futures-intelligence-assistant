"""Tests for deterministic market-analysis aggregation."""

from datetime import datetime, timezone
import unittest

from futures_intelligence.analyst import MarketAnalysisAggregator, RuleBasedAnalyst
from futures_intelligence.analyst.commodity_matcher import (
    CommodityDefinition,
    CommodityMatch,
    CommodityMatcher,
)
from futures_intelligence.analyst.commodity_relevance import CommodityRelevanceResolver
from futures_intelligence.models import MarketAnalysis, MarketInformation


def make_analysis(
    direction: str,
    confidence_score: int,
    reasoning_details: tuple[str, ...],
    source_type: str = "test",
    reliability_score: int = 3,
    title: str = "Market update",
    content: str = "Test content.",
    commodities: tuple[str, ...] = (),
    directional_provenance: str = "unspecified",
) -> MarketAnalysis:
    """Create an analysis with the requested aggregate inputs."""
    information = MarketInformation(
        title=title,
        source="Test Source",
        source_type=source_type,
        published_time=datetime(2026, 7, 19, tzinfo=timezone.utc),
        content=content,
        reliability_score=reliability_score,
        commodities=commodities,
    )
    return MarketAnalysis(
        information,
        "Summary.",
        market_direction=direction,
        confidence_score=confidence_score,
        reasoning_details=reasoning_details,
        directional_provenance=directional_provenance,
    )


def make_research_analysis(
    title: str,
    content: str,
    *,
    commodities: tuple[str, ...] = (),
) -> MarketAnalysis:
    """Create a research analysis through the real deterministic analyst stack."""
    information = MarketInformation(
        title=title,
        source="Synthetic research",
        source_type="research_report",
        published_time=datetime(2026, 7, 19, tzinfo=timezone.utc),
        content=content,
        reliability_score=3,
        commodities=commodities,
    )
    return RuleBasedAnalyst().analyze([information])[0]


class MarketAnalysisAggregatorTests(unittest.TestCase):
    """Validate aggregated directional views and reasoning."""

    def setUp(self) -> None:
        self.aggregator = MarketAnalysisAggregator()

    def test_uses_confidence_weighted_direction_and_combined_reasoning(self) -> None:
        view = self.aggregator.aggregate(
            [
                make_analysis("bullish", 80, ("Shared signal.", "Bullish signal.")),
                make_analysis("bearish", 70, ("Shared signal.", "Bearish signal.")),
                make_analysis("neutral", 60, ("Neutral context.",)),
            ]
        )

        self.assertEqual(view.overall_market_direction, "bullish")
        self.assertEqual(view.aggregated_confidence_score, 70)
        self.assertEqual(
            view.reasoning_details,
            (
                "Shared signal.",
                "Bullish signal.",
            ),
        )
        self.assertEqual(view.analysis_count, 3)

    def test_returns_neutral_view_for_tied_directional_weight(self) -> None:
        view = self.aggregator.aggregate(
            [
                make_analysis("bullish", 75, ("Positive evidence.",)),
                make_analysis("bearish", 75, ("Negative evidence.",)),
            ]
        )

        self.assertEqual(view.overall_market_direction, "neutral")
        self.assertEqual(view.aggregated_confidence_score, 75)
        self.assertEqual(
            view.reasoning_details,
            ("Conflicting bullish and bearish directional signals were detected.",),
        )

    def test_non_neutral_view_excludes_neutral_and_losing_direction_reasoning(self) -> None:
        view = self.aggregator.aggregate(
            [
                make_analysis(
                    "bullish",
                    80,
                    ("Bullish text signals: supply disruption.",),
                ),
                make_analysis(
                    "bearish",
                    60,
                    ("Bearish text signals: inventories increased.",),
                ),
                make_analysis(
                    "neutral",
                    50,
                    ("No deterministic directional signal was detected.",),
                ),
            ]
        )

        self.assertEqual(view.overall_market_direction, "bullish")
        self.assertEqual(
            view.reasoning_details,
            ("Bullish text signals: supply disruption.",),
        )

    def test_neutral_view_without_directional_evidence_keeps_neutral_explanation(self) -> None:
        view = self.aggregator.aggregate(
            [
                make_analysis(
                    "neutral",
                    50,
                    ("No deterministic directional signal was detected.",),
                )
            ]
        )

        self.assertEqual(view.overall_market_direction, "neutral")
        self.assertEqual(
            view.reasoning_details,
            ("No deterministic directional signal was detected.",),
        )

    def test_aggregates_each_detected_commodity_without_cross_commodity_leakage(self) -> None:
        analyses = [
            make_analysis(
                "bullish",
                80,
                (
                    "Source type: rss; reliability score: 4/5.",
                    "Detected commodity keywords: Crude Oil.",
                    "Crude oil bullish signals: inventory draw.",
                ),
                title="Crude oil outlook",
                content="Inventory draw was reported.",
                source_type="rss",
                reliability_score=4,
            ),
            make_analysis(
                "bearish",
                70,
                (
                    "Detected commodity keywords: Gold.",
                    "Gold bearish signals: stronger dollar.",
                ),
                title="Gold outlook",
                content="A stronger dollar pressured gold.",
            ),
            make_analysis(
                "bullish",
                60,
                ("Detected commodity keywords: Wheat.", "Bullish text signals: supply risk."),
                title="Wheat outlook",
                content="Supply risk remains elevated.",
            ),
        ]

        views = self.aggregator.aggregate_by_commodity(analyses)

        self.assertEqual([view.commodity_key for view in views], ["crude_oil", "gold", "wheat"])
        self.assertEqual([view.overall_direction for view in views], ["bullish", "bearish", "bullish"])
        self.assertNotIn("Gold", " ".join(views[0].reasoning_details))
        self.assertNotIn("Crude Oil", " ".join(views[1].reasoning_details))
        self.assertEqual(views[0].analysis_count, 1)
        self.assertEqual(views[1].analysis_count, 1)
        self.assertEqual(views[2].analysis_count, 1)

    def test_multi_commodity_analysis_contributes_once_to_each_detected_group(self) -> None:
        analysis = make_analysis(
            "bullish",
            80,
            ("Detected commodity keywords: Crude Oil, Gold.", "Bullish text signals: supply disruption."),
            title="Gold and crude oil outlook",
            content="Supply disruption was reported.",
        )

        views = self.aggregator.aggregate_by_commodity([analysis, analysis])

        self.assertEqual([view.commodity_key for view in views], ["crude_oil", "gold"])
        self.assertEqual([view.analysis_count for view in views], [1, 1])
        self.assertIn("Detected commodity keywords: Crude Oil.", views[0].reasoning_details)
        self.assertIn("Detected commodity keywords: Gold.", views[1].reasoning_details)
        self.assertNotIn("Gold", " ".join(views[0].reasoning_details))
        self.assertNotIn("Crude Oil", " ".join(views[1].reasoning_details))

    def test_llm_analysis_groups_from_its_original_market_information(self) -> None:
        analysis = make_analysis(
            "neutral",
            65,
            ("LLM summary detail.",),
            title="Copper market update",
            content="Copper demand was discussed.",
        )

        views = self.aggregator.aggregate_by_commodity([analysis])

        self.assertEqual(len(views), 1)
        self.assertEqual(views[0].commodity_key, "copper")
        self.assertEqual(views[0].analysis_count, 1)

    def test_unclassified_and_source_scope_only_analyses_create_no_view(self) -> None:
        views = self.aggregator.aggregate_by_commodity(
            [
                make_analysis("neutral", 50, (), title="Policy update"),
                make_analysis(
                    "neutral",
                    50,
                    (),
                    title="Central bank update",
                    commodities=("gold", "wheat"),
                ),
            ]
        )

        self.assertEqual(views, ())

    def test_research_report_groups_only_primary_not_mentioned_commodities(self) -> None:
        analysis = make_research_analysis(
            "乙二醇专题",
            "原油成本变化影响油制乙二醇利润。",
        )
        relevance = CommodityRelevanceResolver().assess(
            analysis.market_information
        )

        views = self.aggregator.aggregate_by_commodity([analysis])

        self.assertEqual(
            tuple(item.commodity_key for item in relevance.primary),
            ("ethylene_glycol",),
        )
        self.assertEqual(
            tuple(item.commodity_key for item in relevance.mentioned),
            ("crude_oil",),
        )
        self.assertEqual(tuple(view.commodity_key for view in views), ("ethylene_glycol",))

    def test_research_report_mentioned_only_commodity_creates_no_view(self) -> None:
        analysis = make_research_analysis(
            "Macro Policy Outlook",
            "OPEC production cuts affect crude oil inflation assumptions.",
        )
        relevance = CommodityRelevanceResolver().assess(
            analysis.market_information
        )

        views = self.aggregator.aggregate_by_commodity([analysis])

        self.assertEqual(relevance.primary, ())
        self.assertEqual(
            tuple(item.commodity_key for item in relevance.mentioned),
            ("crude_oil",),
        )
        self.assertEqual(views, ())

    def test_research_report_zero_primary_drops_all_lexical_mentions(self) -> None:
        analysis = make_research_analysis(
            "Macro market tracking",
            "Gold and crude oil were discussed as contextual markets.",
        )
        relevance = CommodityRelevanceResolver().assess(
            analysis.market_information
        )

        views = self.aggregator.aggregate_by_commodity([analysis])

        self.assertEqual(relevance.primary, ())
        self.assertEqual(
            tuple(item.commodity_key for item in relevance.mentioned),
            ("crude_oil", "gold"),
        )
        self.assertEqual(views, ())

    def test_research_source_scope_commodities_do_not_create_a_view(self) -> None:
        analysis = make_research_analysis(
            "Macro market tracking",
            "Policy assumptions were reviewed.",
            commodities=("crude_oil",),
        )

        views = self.aggregator.aggregate_by_commodity([analysis])

        self.assertEqual(views, ())

    def test_multi_primary_research_report_contributes_once_in_relevance_order(self) -> None:
        analysis = make_research_analysis(
            "原铝与铸造铝合金价差专题",
            "价差变化受到两端供需影响。",
        )
        relevance = CommodityRelevanceResolver().assess(
            analysis.market_information
        )

        views = self.aggregator.aggregate_by_commodity([analysis, analysis])

        self.assertEqual(
            tuple(item.commodity_key for item in relevance.primary),
            ("aluminum", "cast_aluminum_alloy"),
        )
        self.assertEqual(
            tuple(view.commodity_key for view in views),
            ("aluminum", "cast_aluminum_alloy"),
        )
        self.assertEqual(tuple(view.analysis_count for view in views), (1, 1))

    def test_non_research_grouping_keeps_legacy_matcher_ownership(self) -> None:
        class FalseyResolver:
            def __init__(self) -> None:
                self.call_count = 0

            def __bool__(self) -> bool:
                return False

            def assess(self, information: MarketInformation):
                self.call_count += 1
                raise AssertionError("non-research sources must not use relevance")

        resolver = FalseyResolver()
        aggregator = MarketAnalysisAggregator(
            commodity_relevance_resolver=resolver,  # type: ignore[arg-type]
        )
        analysis = make_analysis(
            "neutral",
            50,
            ("Legacy non-research context.",),
            source_type="rss",
            title="Macro market update",
            content="Crude oil remained in focus.",
        )

        views = aggregator.aggregate_by_commodity([analysis])

        self.assertEqual(tuple(view.commodity_key for view in views), ("crude_oil",))
        self.assertEqual(resolver.call_count, 0)

    def test_falsey_relevance_resolver_is_retained_for_research_reports(self) -> None:
        class FalseyDelegatingResolver:
            def __init__(self) -> None:
                self.delegate = CommodityRelevanceResolver()
                self.calls: list[MarketInformation] = []

            def __bool__(self) -> bool:
                return False

            def assess(self, information: MarketInformation):
                self.calls.append(information)
                return self.delegate.assess(information)

        resolver = FalseyDelegatingResolver()
        aggregator = MarketAnalysisAggregator(
            commodity_relevance_resolver=resolver,  # type: ignore[arg-type]
        )
        analysis = make_research_analysis("Gold outlook", "Macro context.")

        views = aggregator.aggregate_by_commodity([analysis])

        self.assertEqual(tuple(view.commodity_key for view in views), ("gold",))
        self.assertEqual(resolver.calls, [analysis.market_information])

    def test_relevance_resolver_is_called_once_per_research_analysis(self) -> None:
        class CountingResolver:
            def __init__(self) -> None:
                self.delegate = CommodityRelevanceResolver()
                self.calls: list[MarketInformation] = []

            def assess(self, information: MarketInformation):
                self.calls.append(information)
                return self.delegate.assess(information)

        resolver = CountingResolver()
        aggregator = MarketAnalysisAggregator(
            commodity_relevance_resolver=resolver,  # type: ignore[arg-type]
        )
        analysis = make_research_analysis("Gold outlook", "Macro context.")

        views = aggregator.aggregate_by_commodity([analysis, analysis])

        self.assertEqual(tuple(view.commodity_key for view in views), ("gold",))
        self.assertEqual(resolver.calls, [analysis.market_information])

    def test_relevance_resolver_programming_errors_propagate_unchanged(self) -> None:
        expected_error = OSError("resolver failed")

        class RaisingResolver:
            def assess(self, information: MarketInformation):
                raise expected_error

        aggregator = MarketAnalysisAggregator(
            commodity_relevance_resolver=RaisingResolver(),  # type: ignore[arg-type]
        )
        analysis = make_research_analysis("Gold outlook", "Macro context.")

        with self.assertRaises(OSError) as captured:
            aggregator.aggregate_by_commodity([analysis])

        self.assertIs(captured.exception, expected_error)

    def test_g4_only_research_analysis_keeps_ownership_without_directional_contribution(
        self,
    ) -> None:
        structural_reasoning = (
            "Detected a Crude Oil calendar-spread repair relationship; "
            "no outright market direction was assigned."
        )
        analysis = make_research_analysis(
            "原油近远月价差存在修复空间。",
            "结构关系受到关注。",
        )
        relevance = CommodityRelevanceResolver().assess(
            analysis.market_information
        )

        global_view = self.aggregator.aggregate([analysis])
        commodity_views = self.aggregator.aggregate_by_commodity([analysis])

        self.assertEqual(
            tuple(item.commodity_key for item in relevance.primary),
            ("crude_oil",),
        )
        self.assertEqual(analysis.market_direction, "neutral")
        self.assertEqual(analysis.confidence_score, 60)
        self.assertEqual(analysis.directional_provenance, "structural_only")
        self.assertIn(structural_reasoning, analysis.reasoning_details)
        self.assertEqual(global_view.overall_market_direction, "neutral")
        self.assertEqual(global_view.aggregated_confidence_score, 0)
        self.assertEqual(global_view.analysis_count, 1)
        self.assertIn(structural_reasoning, global_view.reasoning_details)
        self.assertEqual(len(commodity_views), 1)
        self.assertEqual(commodity_views[0].commodity_key, "crude_oil")
        self.assertEqual(commodity_views[0].overall_direction, "neutral")
        self.assertEqual(commodity_views[0].confidence_score, 0)
        self.assertEqual(commodity_views[0].analysis_count, 1)
        self.assertIn(structural_reasoning, commodity_views[0].reasoning_details)

    def test_non_directional_provenances_have_zero_aggregate_confidence(self) -> None:
        cases = (
            (
                "structural only",
                make_research_analysis(
                    "原油近远月价差存在修复空间。",
                    "结构关系受到关注。",
                ),
                "structural_only",
            ),
            (
                "qualification only",
                make_research_analysis(
                    "原油专题",
                    "如果制裁升级，供应收紧。",
                ),
                "qualified_only",
            ),
            (
                "no directional signal",
                make_research_analysis(
                    "原油专题",
                    "Market context.",
                ),
                "no_directional_signal",
            ),
        )

        for name, analysis, expected_provenance in cases:
            with self.subTest(name=name):
                view = self.aggregator.aggregate([analysis])

                self.assertEqual(analysis.market_direction, "neutral")
                self.assertEqual(analysis.confidence_score, 60)
                self.assertEqual(
                    analysis.directional_provenance,
                    expected_provenance,
                )
                self.assertEqual(view.overall_market_direction, "neutral")
                self.assertEqual(view.aggregated_confidence_score, 0)
                self.assertEqual(view.analysis_count, 1)

    def test_all_non_directional_provenances_keep_membership_with_zero_confidence(
        self,
    ) -> None:
        analyses = [
            make_analysis(
                "neutral",
                60,
                ("Structural context.",),
                directional_provenance="structural_only",
            ),
            make_analysis(
                "neutral",
                60,
                ("Qualified context.",),
                directional_provenance="qualified_only",
            ),
            make_analysis(
                "neutral",
                60,
                ("No directional evidence.",),
                directional_provenance="no_directional_signal",
            ),
        ]

        view = self.aggregator.aggregate(analyses)

        self.assertEqual(view.overall_market_direction, "neutral")
        self.assertEqual(view.aggregated_confidence_score, 0)
        self.assertEqual(view.analysis_count, 3)
        self.assertEqual(
            view.reasoning_details,
            (
                "Structural context.",
                "Qualified context.",
                "No directional evidence.",
            ),
        )

    def test_non_directional_provenances_do_not_dilute_direct_fundamental(self) -> None:
        direct = make_research_analysis(
            "原油供应收紧。",
            "Market context.",
        )
        non_directional = (
            make_research_analysis(
                "原油近远月价差存在修复空间。",
                "结构关系受到关注。",
            ),
            make_research_analysis(
                "原油专题",
                "如果制裁升级，供应收紧。",
            ),
            make_research_analysis(
                "原油专题",
                "Market context.",
            ),
        )

        direct_view = self.aggregator.aggregate([direct])

        self.assertEqual(direct.directional_provenance, "direct_fundamental")
        self.assertEqual(direct_view.overall_market_direction, "bullish")
        self.assertEqual(direct_view.aggregated_confidence_score, 75)
        self.assertEqual(
            tuple(analysis.directional_provenance for analysis in non_directional),
            ("structural_only", "qualified_only", "no_directional_signal"),
        )
        for analysis in non_directional:
            with self.subTest(provenance=analysis.directional_provenance):
                combined = self.aggregator.aggregate([direct, analysis])

                self.assertEqual(combined.overall_market_direction, "bullish")
                self.assertEqual(combined.aggregated_confidence_score, 75)
                self.assertEqual(combined.analysis_count, 2)

    def test_structural_only_does_not_dilute_direct_bearish_fundamental(self) -> None:
        direct = make_research_analysis(
            "原油供应增加。",
            "Market context.",
        )
        structural = make_research_analysis(
            "原油近远月价差存在修复空间。",
            "结构关系受到关注。",
        )

        view = self.aggregator.aggregate([direct, structural])

        self.assertEqual(direct.directional_provenance, "direct_fundamental")
        self.assertEqual(structural.directional_provenance, "structural_only")
        self.assertEqual(view.overall_market_direction, "bearish")
        self.assertEqual(view.aggregated_confidence_score, 75)
        self.assertEqual(view.analysis_count, 2)

    def test_conflict_and_abstention_provenances_retain_legacy_contribution(
        self,
    ) -> None:
        direct = make_research_analysis(
            "原油供应收紧。",
            "Market context.",
        )
        controls = (
            make_research_analysis(
                "原油供应收紧；原油供应增加。",
                "Market context.",
            ),
            make_research_analysis(
                "燃料油短期偏强，中长期承压。",
                "Market context.",
            ),
            make_research_analysis(
                "原油与燃料油专题",
                "原油供应收紧；燃料油供应宽松。",
            ),
        )

        self.assertEqual(
            tuple(analysis.directional_provenance for analysis in controls),
            (
                "same_market_conflict",
                "horizon_conflict",
                "cross_commodity_abstention",
            ),
        )
        for analysis in controls:
            with self.subTest(provenance=analysis.directional_provenance):
                view = self.aggregator.aggregate([direct, analysis])

                self.assertEqual(view.overall_market_direction, "bullish")
                self.assertEqual(view.aggregated_confidence_score, 67)
                self.assertEqual(view.analysis_count, 2)

    def test_neutral_legacy_provenances_remain_directional_contributors(self) -> None:
        provenances = (
            "metadata_direction",
            "observed_market_movement",
            "deterministic_text_signal",
            "external_analyst",
            "unspecified",
        )

        for provenance in provenances:
            with self.subTest(provenance=provenance):
                analysis = make_analysis(
                    "neutral",
                    61,
                    (f"{provenance} neutral evidence.",),
                    directional_provenance=provenance,
                )
                view = self.aggregator.aggregate([analysis])

                self.assertEqual(view.overall_market_direction, "neutral")
                self.assertEqual(view.aggregated_confidence_score, 61)
                self.assertEqual(view.analysis_count, 1)

    def test_directional_unspecified_analysis_keeps_legacy_contribution(self) -> None:
        analysis = make_analysis(
            "bullish",
            65,
            ("Legacy bullish evidence.",),
            directional_provenance="unspecified",
        )

        view = self.aggregator.aggregate([analysis])

        self.assertEqual(view.overall_market_direction, "bullish")
        self.assertEqual(view.aggregated_confidence_score, 65)
        self.assertEqual(view.analysis_count, 1)

    def test_zero_primary_research_analysis_remains_globally_eligible(self) -> None:
        information = MarketInformation(
            title="Macro outlook",
            source="Synthetic research",
            source_type="research_report",
            published_time=datetime(2026, 7, 19, tzinfo=timezone.utc),
            content="Crude oil remained contextual.",
            reliability_score=3,
            metadata={"price_change": 2},
        )
        analysis = RuleBasedAnalyst().analyze([information])[0]
        relevance = CommodityRelevanceResolver().assess(information)

        global_view = self.aggregator.aggregate([analysis])
        commodity_views = self.aggregator.aggregate_by_commodity([analysis])

        self.assertEqual(relevance.primary, ())
        self.assertEqual(
            tuple(item.commodity_key for item in relevance.mentioned),
            ("crude_oil",),
        )
        self.assertEqual(commodity_views, ())
        self.assertEqual(analysis.market_direction, "bullish")
        self.assertEqual(analysis.confidence_score, 70)
        self.assertEqual(global_view.overall_market_direction, "bullish")
        self.assertEqual(global_view.aggregated_confidence_score, 70)
        self.assertEqual(global_view.analysis_count, 1)

    def test_default_resolver_shares_injected_matcher_for_research_ownership(self) -> None:
        matcher = CommodityMatcher(
            definitions=(
                CommodityDefinition(
                    "custom_asset",
                    "Custom Asset",
                    ("customasset",),
                ),
            ),
            ambiguous_alias_exclusions=(),
        )
        analysis = make_analysis(
            "neutral",
            60,
            ("Custom research context.",),
            source_type="research_report",
            title="Customasset outlook",
            content="Research context.",
        )
        information = analysis.market_information

        self.assertEqual(CommodityRelevanceResolver().assess(information).primary, ())
        self.assertEqual(
            tuple(
                item.commodity_key
                for item in CommodityRelevanceResolver(matcher=matcher).assess(
                    information
                ).primary
            ),
            ("custom_asset",),
        )

        views = MarketAnalysisAggregator(
            commodity_matcher=matcher,
        ).aggregate_by_commodity([analysis])

        self.assertEqual(tuple(view.commodity_key for view in views), ("custom_asset",))
        self.assertEqual(tuple(view.commodity_label for view in views), ("Custom Asset",))

    def test_uses_stable_first_appearance_order_without_registry_order(self) -> None:
        class UnorderedMatcher:
            commodity_order: tuple[str, ...] = ()
            commodity_ordered_matches: tuple[object, ...] = ()

            def match(self, information: MarketInformation) -> tuple[CommodityMatch, ...]:
                if information.title == "Gold update":
                    return (CommodityMatch("gold", "Gold", ("gold",)),)
                return (CommodityMatch("crude_oil", "Crude Oil", ("crude oil",)),)

        aggregator = MarketAnalysisAggregator(commodity_matcher=UnorderedMatcher())  # type: ignore[arg-type]
        views = aggregator.aggregate_by_commodity(
            [
                make_analysis("neutral", 50, (), title="Gold update"),
                make_analysis("neutral", 50, (), title="Crude oil update"),
            ]
        )

        self.assertEqual([view.commodity_key for view in views], ["gold", "crude_oil"])

    def test_preserves_source_weighting_and_confidence_within_a_commodity_group(self) -> None:
        view = self.aggregator.aggregate_by_commodity(
            [
                make_analysis(
                    "bullish",
                    90,
                    ("Lower-weight RSS signal.",),
                    source_type="rss",
                    reliability_score=1,
                    title="Gold update",
                ),
                make_analysis(
                    "bearish",
                    70,
                    ("Higher-weight official-data signal.",),
                    source_type="official_data",
                    reliability_score=5,
                    title="Gold update",
                ),
            ]
        )[0]

        self.assertEqual(view.commodity_key, "gold")
        self.assertEqual(view.overall_direction, "bearish")
        self.assertEqual(view.confidence_score, 72)
        self.assertEqual(view.reasoning_details, ("Higher-weight official-data signal.",))

    def test_observed_oil_movement_stays_in_the_crude_oil_view(self) -> None:
        analysis = make_analysis(
            "bullish",
            80,
            ("Observed market movement: Oil prices jumped 2%.",),
            title="Oil prices jumped 2%",
        )

        views = self.aggregator.aggregate_by_commodity([analysis])

        self.assertEqual([view.commodity_key for view in views], ["crude_oil"])
        self.assertEqual(views[0].overall_direction, "bullish")
        self.assertIn("Observed market movement", " ".join(views[0].reasoning_details))

    def test_uses_scoped_movement_directions_and_evidence_from_one_analysis(self) -> None:
        information = MarketInformation(
            title="Gold opens ₹733 higher; Silver gains ₹2,796",
            source="Test Source",
            source_type="rss",
            published_time=datetime(2026, 7, 19, tzinfo=timezone.utc),
            content="Market update.",
            reliability_score=4,
        )
        analysis = RuleBasedAnalyst().analyze([information])[0]

        views = self.aggregator.aggregate_by_commodity([analysis])
        views_by_key = {view.commodity_key: view for view in views}

        self.assertIs(analysis.market_information, information)
        self.assertEqual(analysis.market_direction, "bullish")
        self.assertEqual(views_by_key["gold"].overall_direction, "bullish")
        self.assertEqual(views_by_key["silver"].overall_direction, "bullish")
        self.assertIn("Gold opens ₹733 higher", " ".join(views_by_key["gold"].reasoning_details))
        self.assertIn("Silver gains ₹2,796", " ".join(views_by_key["silver"].reasoning_details))
        self.assertNotIn("Silver", " ".join(views_by_key["gold"].reasoning_details))
        self.assertNotIn("Gold", " ".join(views_by_key["silver"].reasoning_details))

    def test_scopes_opposite_commodity_movements_without_changing_global_aggregate(self) -> None:
        information = MarketInformation(
            title="Gold gains while Silver falls",
            source="Test Source",
            source_type="official_data",
            published_time=datetime(2026, 7, 19, tzinfo=timezone.utc),
            content="Market update.",
            reliability_score=5,
        )
        analysis = RuleBasedAnalyst().analyze([information])[0]

        aggregate = self.aggregator.aggregate([analysis])
        views_by_key = {
            view.commodity_key: view
            for view in self.aggregator.aggregate_by_commodity([analysis])
        }

        self.assertEqual(aggregate.overall_market_direction, "neutral")
        self.assertEqual(views_by_key["gold"].overall_direction, "bullish")
        self.assertEqual(views_by_key["silver"].overall_direction, "bearish")
        self.assertIn("Gold gains", " ".join(views_by_key["gold"].reasoning_details))
        self.assertIn("Silver falls", " ".join(views_by_key["silver"].reasoning_details))

    def test_source_reliability_and_type_weight_directional_signals(self) -> None:
        view = self.aggregator.aggregate(
            [
                make_analysis(
                    "bullish",
                    90,
                    ("Lower-weight RSS signal.",),
                    source_type="rss",
                    reliability_score=1,
                ),
                make_analysis(
                    "bearish",
                    70,
                    ("Higher-weight official-data signal.",),
                    source_type="official_data",
                    reliability_score=5,
                ),
            ]
        )

        self.assertEqual(view.overall_market_direction, "bearish")
        self.assertEqual(view.aggregated_confidence_score, 72)

    def test_returns_empty_neutral_view(self) -> None:
        view = self.aggregator.aggregate([])

        self.assertEqual(view.overall_market_direction, "neutral")
        self.assertEqual(view.aggregated_confidence_score, 0)
        self.assertEqual(
            view.reasoning_details, ("No analyses available for aggregation.",)
        )
        self.assertEqual(view.analysis_count, 0)

    def test_rejects_non_analysis_values(self) -> None:
        with self.assertRaises(TypeError):
            self.aggregator.aggregate(["not an analysis"])  # type: ignore[list-item]


if __name__ == "__main__":
    unittest.main()
