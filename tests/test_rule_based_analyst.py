"""Tests for deterministic rule-based market analysis."""

from datetime import datetime, timezone
import unittest
from unittest.mock import Mock

from futures_intelligence.analyst.commodity_matcher import (
    CommodityDefinition,
    CommodityMatch,
    CommodityMatcher,
)
from futures_intelligence.analyst.commodity_relevance import (
    CommodityRelevance,
    CommodityRelevanceAssessment,
)
from futures_intelligence.analyst.rule_based import RuleBasedAnalyst
from futures_intelligence.models import MarketInformation


def make_information(
    title: str,
    content: str,
    source_type: str = "test",
    **fields: object,
) -> MarketInformation:
    """Create a normalized item for rule-based analysis tests."""
    return MarketInformation(
        title=title,
        source="Test Source",
        source_type=source_type,
        published_time=datetime(2026, 7, 16, tzinfo=timezone.utc),
        content=content,
        **fields,
    )


class RuleBasedAnalystTests(unittest.TestCase):
    """Validate deterministic keyword-based summaries."""

    def setUp(self) -> None:
        self.analyst = RuleBasedAnalyst()

    def test_detects_commodities_from_title_and_content(self) -> None:
        information = make_information(
            "Oil market update", "Copper inventory data was also released."
        )

        analysis = self.analyst.analyze([information])[0]

        self.assertIs(analysis.market_information, information)
        self.assertEqual(
            analysis.summary,
            "Detected commodity focus: Crude Oil, Copper. "
            "Review potential supply, demand, inventory, and cost implications.",
        )

    def test_detects_crude_oil_aliases(self) -> None:
        for alias in ("oil", "crude", "brent", "WTI"):
            with self.subTest(alias=alias):
                analysis = self.analyst.analyze(
                    [make_information(f"{alias} market update", "Market data")]
                )[0]

                self.assertIn("Detected commodity focus: Crude Oil.", analysis.summary)

    def test_matches_generic_oil_only_outside_agricultural_product_phrases(self) -> None:
        cases = {
            "Oil prices rise": True,
            "Crude futures rise": True,
            "WTI and Brent advance": True,
            "CONNECT WITH MARKET-MAKING FIRMS FOR GRAINS AND OILSEED PRODUCTS": False,
            "Palm oil futures rise": False,
            "Soybean oil demand improves": False,
            "Vegetable oil prices rise": False,
            "Canola oil prices rise": False,
            "Sunflower oil prices rise": False,
        }

        for title, expected in cases.items():
            with self.subTest(title=title):
                analysis = self.analyst.analyze([make_information(title, "Update.")])[0]
                self.assertEqual(
                    "Detected commodity focus: Crude Oil." in analysis.summary,
                    expected,
                )

    def test_matches_multi_word_aliases_with_token_boundaries_and_case_insensitivity(
        self,
    ) -> None:
        analysis = self.analyst.analyze(
            [make_information("CRUDE-OIL outlook", "Copper-market data.")]
        )[0]

        self.assertIn("Detected commodity focus: Crude Oil, Copper.", analysis.summary)

    def test_does_not_match_aliases_inside_larger_words(self) -> None:
        analysis = self.analyst.analyze(
            [make_information("Oilseed processing update", "Goldman commentary.")]
        )[0]

        self.assertEqual(
            analysis.summary,
            "No tracked commodity keywords detected. "
            "Review the information for broader market context.",
        )

    def test_safely_handles_aliases_with_regular_expression_metacharacters(self) -> None:
        self.analyst._commodity_matcher = CommodityMatcher(  # type: ignore[attr-defined]
            definitions=(
                CommodityDefinition("c_plus", "C Plus", ("c++",)),
            ),
            ambiguous_alias_exclusions=(),
        )

        analysis = self.analyst.analyze(
            [make_information("C++ futures update", "Market data.")]
        )[0]

        self.assertIn("Detected commodity focus: C Plus.", analysis.summary)

    def test_detects_gold(self) -> None:
        analysis = self.analyst.analyze(
            [make_information("Gold market update", "Market data")]
        )[0]

        self.assertIn("Detected commodity focus: Gold.", analysis.summary)

    def test_detects_wheat(self) -> None:
        analysis = self.analyst.analyze(
            [make_information("Wheat market update", "Market data")]
        )[0]

        self.assertIn("Detected commodity focus: Wheat.", analysis.summary)

    def test_returns_general_summary_without_tracked_keywords(self) -> None:
        information = make_information(
            "Central bank statement", "The policy statement was published."
        )

        analysis = self.analyst.analyze([information])[0]

        self.assertEqual(
            analysis.summary,
            "No tracked commodity keywords detected. "
            "Review the information for broader market context.",
        )

    def test_produces_bullish_analysis_from_structured_price_change(self) -> None:
        analysis = self.analyst.analyze(
            [
                make_information(
                    "Gold market update",
                    "Market data was published.",
                    reliability_score=4,
                    commodities=("gold",),
                    metadata={"price_change": 12.5, "symbol": "GC=F"},
                )
            ]
        )[0]

        self.assertEqual(analysis.market_direction, "bullish")
        self.assertEqual(analysis.confidence_score, 90)
        self.assertIn(
            "Structured price change is positive (12.5).",
            analysis.reasoning_details,
        )
        self.assertIn(
            "Detected commodity keywords: Gold.", analysis.reasoning_details
        )

    def test_produces_bearish_analysis_from_text_signals(self) -> None:
        analysis = self.analyst.analyze(
            [
                make_information(
                    "Crude oil update",
                    "Inventories increased as demand weakened.",
                    reliability_score=3,
                    commodities=("crude_oil",),
                )
            ]
        )[0]

        self.assertEqual(analysis.market_direction, "bearish")
        self.assertEqual(analysis.confidence_score, 70)
        self.assertIn(
            "Bearish text signals: inventories increased, demand weakened.",
            analysis.reasoning_details,
        )

    def test_explicit_price_movement_overrides_fundamental_rules_after_metadata(self) -> None:
        analysis = self.analyst.analyze(
            [
                make_information(
                    "Oil prices jumped 2%",
                    "Inventories increased during the session.",
                )
            ]
        )[0]

        self.assertEqual(analysis.market_direction, "bullish")
        self.assertIn("Observed market movement: Oil prices jumped 2%.", analysis.reasoning_details)
        self.assertNotIn(
            "No deterministic directional signal was detected.", analysis.reasoning_details
        )

    def test_metadata_price_change_remains_higher_priority_than_text_movement(self) -> None:
        analysis = self.analyst.analyze(
            [
                make_information(
                    "Gold falls 2%",
                    "Market update.",
                    metadata={"price_change": 4.0},
                )
            ]
        )[0]

        self.assertEqual(analysis.market_direction, "bullish")
        self.assertIn(
            "Structured price change is positive (4.0).", analysis.reasoning_details
        )
        self.assertNotIn("Observed market movement", " ".join(analysis.reasoning_details))

    def test_non_price_metric_changes_remain_without_observed_movement_reasoning(self) -> None:
        analysis = self.analyst.analyze(
            [make_information("Oil production is up 2%", "Market update.")]
        )[0]

        self.assertEqual(analysis.market_direction, "neutral")
        self.assertNotIn("Observed market movement", " ".join(analysis.reasoning_details))

    def test_produces_neutral_analysis_without_directional_signals(self) -> None:
        analysis = self.analyst.analyze(
            [make_information("Policy statement", "The statement was published.")]
        )[0]

        self.assertEqual(analysis.market_direction, "neutral")
        self.assertEqual(analysis.confidence_score, 50)
        self.assertIn(
            "No deterministic directional signal was detected.",
            analysis.reasoning_details,
        )

    def test_applies_crude_oil_specific_rules(self) -> None:
        analysis = self.analyst.analyze(
            [
                make_information(
                    "Crude oil outlook",
                    "OPEC production cuts were announced.",
                    commodities=("crude_oil",),
                )
            ]
        )[0]

        self.assertEqual(analysis.market_direction, "bullish")
        self.assertIn(
            "Crude oil bullish signals: opec production cuts.",
            analysis.reasoning_details,
        )

    def test_source_scope_commodities_do_not_create_evidence_or_confidence(self) -> None:
        information = make_information(
            "Central bank statement",
            "The policy statement was published.",
            commodities=("crude_oil", "gold", "metals"),
        )

        analysis = self.analyst.analyze([information])[0]

        self.assertEqual(
            analysis.summary,
            "No tracked commodity keywords detected. "
            "Review the information for broader market context.",
        )
        self.assertEqual(analysis.confidence_score, 50)
        self.assertNotIn("Configured source commodities", " ".join(analysis.reasoning_details))
        self.assertIn("crude_oil", information.commodities)

    def test_directional_analyses_do_not_include_neutral_boilerplate(self) -> None:
        bullish = self.analyst.analyze(
            [make_information("Oil update", "Supply disruption was reported.")]
        )[0]
        bearish = self.analyst.analyze(
            [make_information("Oil update", "Inventories increased.")]
        )[0]

        self.assertEqual(bullish.market_direction, "bullish")
        self.assertEqual(bearish.market_direction, "bearish")
        self.assertNotIn(
            "No deterministic directional signal was detected.", bullish.reasoning_details
        )
        self.assertNotIn(
            "No deterministic directional signal was detected.", bearish.reasoning_details
        )

    def test_applies_gold_specific_rules(self) -> None:
        analysis = self.analyst.analyze(
            [
                make_information(
                    "Gold outlook",
                    "Central bank buying continued this quarter.",
                )
            ]
        )[0]

        self.assertEqual(analysis.market_direction, "bullish")
        self.assertIn(
            "Gold bullish signals: central bank buying.",
            analysis.reasoning_details,
        )

    def test_applies_agriculture_specific_rules(self) -> None:
        analysis = self.analyst.analyze(
            [
                make_information(
                    "Wheat outlook",
                    "Favorable weather prevailed and crop conditions improved.",
                )
            ]
        )[0]

        self.assertEqual(analysis.market_direction, "bearish")
        self.assertIn(
            "Agriculture bearish signals: favorable weather, crop conditions improved.",
            analysis.reasoning_details,
        )

    def test_preserves_generic_behavior_for_unknown_commodities(self) -> None:
        analysis = self.analyst.analyze(
            [
                make_information(
                    "Lithium update",
                    "Market data was published.",
                    commodities=("lithium",),
                )
            ]
        )[0]

        self.assertEqual(analysis.market_direction, "neutral")
        self.assertIn(
            "No deterministic directional signal was detected.",
            analysis.reasoning_details,
        )

    def test_preserves_input_order_and_references(self) -> None:
        first = make_information("Gold update", "Market data")
        second = make_information("Corn update", "Crop data")

        analyses = self.analyst.analyze([first, second])

        self.assertEqual([analysis.market_information for analysis in analyses], [first, second])
        self.assertIs(analyses[0].market_information, first)
        self.assertIs(analyses[1].market_information, second)

    def test_returns_empty_list_for_empty_input(self) -> None:
        self.assertEqual(self.analyst.analyze([]), [])

    def test_research_report_uses_primary_focus_and_contextual_mentions(self) -> None:
        analysis = self.analyst.analyze(
            [
                make_information(
                    "乙二醇专题",
                    "原油成本变化影响油制乙二醇利润。",
                    source_type="research_report",
                )
            ]
        )[0]

        self.assertEqual(
            analysis.summary,
            "Detected commodity focus: Ethylene Glycol. "
            "Review potential supply, demand, inventory, and cost implications.",
        )
        self.assertIn(
            "Primary commodity focus: Ethylene Glycol.", analysis.reasoning_details
        )
        self.assertIn(
            "Mentioned tracked commodities: Crude Oil.", analysis.reasoning_details
        )
        self.assertNotIn("Crude Oil", analysis.summary)
        self.assertEqual(analysis.market_direction, "neutral")
        self.assertEqual(analysis.confidence_score, 60)

    def test_research_report_multiple_primary_commodities_keep_binary_focus_confidence(
        self,
    ) -> None:
        analysis = self.analyst.analyze(
            [
                make_information(
                    "原铝与铸造铝合金价差专题",
                    "价差变化受到两端供需影响。",
                    source_type="research_report",
                )
            ]
        )[0]
        one_primary_control = self.analyst.analyze(
            [
                make_information(
                    "Gold outlook",
                    "Macro context.",
                    source_type="research_report",
                )
            ]
        )[0]

        self.assertEqual(
            analysis.summary,
            "Detected commodity focus: Aluminum, Cast Aluminum Alloy. "
            "Review potential supply, demand, inventory, and cost implications.",
        )
        self.assertEqual(
            analysis.reasoning_details.count(
                "Primary commodity focus: Aluminum, Cast Aluminum Alloy."
            ),
            1,
        )
        self.assertNotIn("Mentioned tracked commodities:", analysis.reasoning_details)
        self.assertEqual(analysis.market_direction, "neutral")
        self.assertEqual(analysis.confidence_score, 60)
        self.assertEqual(analysis.confidence_score, one_primary_control.confidence_score)

    def test_research_report_mentioned_only_has_no_focus_or_fundamental_rule(self) -> None:
        mentioned_only = make_information(
            "Macro Policy Outlook",
            "OPEC production cuts affect crude oil inflation assumptions.",
            source_type="research_report",
        )
        no_match = make_information(
            "Macro Policy Outlook",
            "Inflation assumptions were reviewed.",
            source_type="research_report",
        )

        mentioned_analysis, no_match_analysis = self.analyst.analyze(
            [mentioned_only, no_match]
        )

        expected_summary = (
            "No primary tracked commodity focus detected. "
            "Review the information for broader market context."
        )
        self.assertEqual(mentioned_analysis.summary, expected_summary)
        self.assertEqual(no_match_analysis.summary, expected_summary)
        self.assertIn(
            "Mentioned tracked commodities: Crude Oil.",
            mentioned_analysis.reasoning_details,
        )
        self.assertIn(
            "No primary tracked commodity focus was detected.",
            mentioned_analysis.reasoning_details,
        )
        self.assertNotIn(
            "Crude oil bullish signals: opec production cuts.",
            mentioned_analysis.reasoning_details,
        )
        self.assertEqual(mentioned_analysis.market_direction, "neutral")
        self.assertEqual(
            mentioned_analysis.confidence_score, no_match_analysis.confidence_score
        )

    def test_research_report_primary_commodity_retains_existing_fundamental_rule(self) -> None:
        analysis = self.analyst.analyze(
            [
                make_information(
                    "Crude Oil Outlook",
                    "OPEC production cuts were announced.",
                    source_type="research_report",
                )
            ]
        )[0]

        self.assertEqual(analysis.market_direction, "bullish")
        self.assertIn(
            "Crude oil bullish signals: opec production cuts.", analysis.reasoning_details
        )

    def test_research_report_relevance_keeps_metadata_and_movement_priorities(self) -> None:
        metadata_analysis = self.analyst.analyze(
            [
                make_information(
                    "Macro Policy Outlook",
                    "OPEC production cuts affect inflation assumptions.",
                    source_type="research_report",
                    metadata={"price_change": -2.0},
                )
            ]
        )[0]
        movement_analysis = self.analyst.analyze(
            [
                make_information(
                    "Macro Market Update",
                    "Oil prices jumped 2%.",
                    source_type="research_report",
                )
            ]
        )[0]

        self.assertEqual(metadata_analysis.market_direction, "bearish")
        self.assertIn(
            "Structured price change is negative (-2.0).",
            metadata_analysis.reasoning_details,
        )
        self.assertEqual(movement_analysis.market_direction, "bullish")
        self.assertEqual(movement_analysis.confidence_score, 70)
        self.assertIn(
            "No primary tracked commodity focus was detected.",
            movement_analysis.reasoning_details,
        )
        self.assertIn(
            "Mentioned tracked commodities: Crude Oil.",
            movement_analysis.reasoning_details,
        )
        self.assertNotIn(
            "Primary commodity focus: Crude Oil.",
            movement_analysis.reasoning_details,
        )
        self.assertIn(
            "Observed market movement: Oil prices jumped 2%.",
            movement_analysis.reasoning_details,
        )

    def test_non_research_content_commodity_retains_flat_rule_behavior(self) -> None:
        analysis = self.analyst.analyze(
            [
                make_information(
                    "Macro Policy Outlook",
                    "OPEC production cuts affect crude oil assumptions.",
                    source_type="rss",
                )
            ]
        )[0]

        self.assertIn("Detected commodity focus: Crude Oil.", analysis.summary)
        self.assertEqual(analysis.market_direction, "bullish")

    def test_matching_collaborators_use_resolver_only_for_research_reports(self) -> None:
        primary_match = CommodityMatch("gold", "Gold", ("gold",))
        primary = CommodityRelevance(
            "gold",
            "Gold",
            "primary",
            ("gold",),
            (),
            1,
            0,
            ("Matched a tracked commodity alias in the report title.",),
        )
        resolver = Mock()
        resolver.assess.return_value = CommodityRelevanceAssessment(
            (primary_match,), (primary,), ()
        )
        matcher = Mock()
        matcher.match.return_value = (primary_match,)
        analyst = RuleBasedAnalyst(
            commodity_matcher=matcher,
            commodity_relevance_resolver=resolver,
        )
        research = make_information("Gold report", "Context.", source_type="research_report")
        rss = make_information("Gold report", "Context.", source_type="rss")

        analyst.analyze([research, rss])

        resolver.assess.assert_called_once_with(research)
        matcher.match.assert_called_once_with(rss)


if __name__ == "__main__":
    unittest.main()
