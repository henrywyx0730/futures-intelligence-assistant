"""Tests for deterministic rule-based market analysis."""

from datetime import datetime, timezone
import unittest

from futures_intelligence.analyst.commodity_matcher import (
    CommodityDefinition,
    CommodityMatcher,
)
from futures_intelligence.analyst.rule_based import RuleBasedAnalyst
from futures_intelligence.models import MarketInformation


def make_information(
    title: str,
    content: str,
    **fields: object,
) -> MarketInformation:
    """Create a normalized item for rule-based analysis tests."""
    return MarketInformation(
        title=title,
        source="Test Source",
        source_type="test",
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


if __name__ == "__main__":
    unittest.main()
