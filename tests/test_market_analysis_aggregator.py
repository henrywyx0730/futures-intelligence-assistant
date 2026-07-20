"""Tests for deterministic market-analysis aggregation."""

from datetime import datetime, timezone
import unittest

from futures_intelligence.analyst import MarketAnalysisAggregator
from futures_intelligence.analyst.commodity_matcher import CommodityMatch
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
    )


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
