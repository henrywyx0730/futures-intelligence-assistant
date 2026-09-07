"""Tests for the market-analysis model."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import unittest

from futures_intelligence.models import (
    CommodityDirectionalEvidence,
    MarketAnalysis,
    MarketInformation,
)


def make_information() -> MarketInformation:
    """Create a normalized item for analysis tests."""
    return MarketInformation(
        title="Oil inventory update",
        source="EIA",
        source_type="official_data",
        published_time=datetime(2026, 7, 16, tzinfo=timezone.utc),
        content="Weekly inventory data was published.",
    )


class MarketAnalysisTests(unittest.TestCase):
    """Validate the minimal analyst output model."""

    def test_creates_and_normalizes_analysis(self) -> None:
        information = make_information()
        analysis = MarketAnalysis(information, "  Inventory data was published.  ")

        self.assertIs(analysis.market_information, information)
        self.assertEqual(analysis.summary, "Inventory data was published.")
        self.assertEqual(analysis.market_direction, "neutral")
        self.assertEqual(analysis.confidence_score, 0)
        self.assertEqual(analysis.reasoning_details, ())
        self.assertEqual(analysis.directional_provenance, "unspecified")
        self.assertEqual(analysis.commodity_directional_evidence, ())

    def test_accepts_immutable_commodity_directional_evidence(self) -> None:
        crude_oil = CommodityDirectionalEvidence(
            "crude_oil",
            "Crude Oil",
            "bullish",
        )
        fuel_oil = CommodityDirectionalEvidence(
            "fuel_oil",
            "Fuel Oil",
            "bullish",
        )
        analysis = MarketAnalysis(
            make_information(),
            "Resolved direct fundamentals.",
            market_direction="bullish",
            directional_provenance="direct_fundamental",
            commodity_directional_evidence=(crude_oil, fuel_oil),
        )

        self.assertEqual(
            analysis.commodity_directional_evidence,
            (crude_oil, fuel_oil),
        )
        with self.assertRaises(FrozenInstanceError):
            crude_oil.market_direction = "bearish"

    def test_rejects_invalid_commodity_directional_evidence_values(self) -> None:
        for fields in (
            {
                "commodity_key": "",
                "commodity_label": "Crude Oil",
                "market_direction": "bullish",
            },
            {
                "commodity_key": " crude_oil ",
                "commodity_label": "Crude Oil",
                "market_direction": "bullish",
            },
            {
                "commodity_key": "crude_oil",
                "commodity_label": " ",
                "market_direction": "bullish",
            },
            {
                "commodity_key": "crude_oil",
                "commodity_label": " Crude Oil ",
                "market_direction": "bullish",
            },
            {
                "commodity_key": "crude_oil",
                "commodity_label": "Crude Oil",
                "market_direction": "neutral",
            },
            {
                "commodity_key": "crude_oil",
                "commodity_label": "Crude Oil",
                "market_direction": "higher",
            },
            {
                "commodity_key": "crude_oil",
                "commodity_label": "Crude Oil",
                "market_direction": True,
            },
            {
                "commodity_key": "crude_oil",
                "commodity_label": "Crude Oil",
                "market_direction": object(),
            },
            {
                "commodity_key": True,
                "commodity_label": "Crude Oil",
                "market_direction": "bullish",
            },
            {
                "commodity_key": "crude_oil",
                "commodity_label": object(),
                "market_direction": "bullish",
            },
        ):
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):
                    CommodityDirectionalEvidence(**fields)

    def test_rejects_invalid_commodity_directional_evidence_collections(self) -> None:
        evidence = CommodityDirectionalEvidence(
            "crude_oil",
            "Crude Oil",
            "bullish",
        )
        duplicate = CommodityDirectionalEvidence(
            "crude_oil",
            "Crude Oil",
            "bullish",
        )
        for values in (
            [evidence],
            ("not evidence",),
            (evidence, "not evidence"),
            (evidence, duplicate),
        ):
            with self.subTest(values=values):
                with self.assertRaises((TypeError, ValueError)):
                    MarketAnalysis(
                        make_information(),
                        "Summary",
                        market_direction="bullish",
                        directional_provenance="direct_fundamental",
                        commodity_directional_evidence=values,
                    )

    def test_rejects_incompatible_commodity_directional_evidence(self) -> None:
        bullish = CommodityDirectionalEvidence(
            "crude_oil",
            "Crude Oil",
            "bullish",
        )
        bearish = CommodityDirectionalEvidence(
            "fuel_oil",
            "Fuel Oil",
            "bearish",
        )
        cases = (
            ("structural_only", "neutral", (bullish,)),
            ("direct_fundamental", "bullish", (bullish, bearish)),
            ("cross_commodity_abstention", "neutral", (bullish,)),
            ("cross_commodity_abstention", "neutral", (bullish, bullish)),
        )

        for provenance, direction, evidence in cases:
            with self.subTest(provenance=provenance, evidence=evidence):
                with self.assertRaises(ValueError):
                    MarketAnalysis(
                        make_information(),
                        "Summary",
                        market_direction=direction,
                        directional_provenance=provenance,
                        commodity_directional_evidence=evidence,
                    )

    def test_creates_rich_analysis_with_normalized_fields(self) -> None:
        analysis = MarketAnalysis(
            make_information(),
            "Inventory data was published.",
            market_direction=" BULLISH ",
            confidence_score=85,
            reasoning_details=(" Inventory declined ", "Demand improved"),
            directional_provenance=" METADATA_DIRECTION ",
        )

        self.assertEqual(analysis.market_direction, "bullish")
        self.assertEqual(analysis.confidence_score, 85)
        self.assertEqual(
            analysis.reasoning_details,
            ("Inventory declined", "Demand improved"),
        )
        self.assertEqual(analysis.directional_provenance, "metadata_direction")

    def test_accepts_every_canonical_directional_provenance(self) -> None:
        cases = (
            ("metadata_direction", "neutral"),
            ("observed_market_movement", "neutral"),
            ("direct_fundamental", "bullish"),
            ("deterministic_text_signal", "bullish"),
            ("no_directional_signal", "neutral"),
            ("qualified_only", "neutral"),
            ("same_market_conflict", "neutral"),
            ("horizon_conflict", "neutral"),
            ("cross_commodity_abstention", "neutral"),
            ("structural_only", "neutral"),
            ("external_analyst", "bullish"),
            ("unspecified", "bullish"),
        )

        for provenance, direction in cases:
            with self.subTest(provenance=provenance):
                analysis = MarketAnalysis(
                    make_information(),
                    "Summary",
                    market_direction=direction,
                    directional_provenance=provenance,
                )

                self.assertEqual(analysis.directional_provenance, provenance)

    def test_rejects_invalid_directional_provenance(self) -> None:
        for provenance in ("", "unknown", True, None, 1):
            with self.subTest(provenance=provenance):
                with self.assertRaises(ValueError):
                    MarketAnalysis(
                        make_information(),
                        "Summary",
                        directional_provenance=provenance,
                    )

    def test_rejects_impossible_directional_provenance_combinations(self) -> None:
        cases = (
            ("direct_fundamental", "neutral"),
            ("no_directional_signal", "bullish"),
            ("qualified_only", "bearish"),
            ("same_market_conflict", "bullish"),
            ("horizon_conflict", "bearish"),
            ("cross_commodity_abstention", "bullish"),
            ("structural_only", "bearish"),
        )

        for provenance, direction in cases:
            with self.subTest(provenance=provenance, direction=direction):
                with self.assertRaises(ValueError):
                    MarketAnalysis(
                        make_information(),
                        "Summary",
                        market_direction=direction,
                        directional_provenance=provenance,
                    )

    def test_rejects_empty_summary(self) -> None:
        with self.assertRaises(ValueError):
            MarketAnalysis(make_information(), "   ")

    def test_rejects_invalid_market_information(self) -> None:
        with self.assertRaises(TypeError):
            MarketAnalysis("not information", "Summary")

    def test_rejects_invalid_rich_analysis_fields(self) -> None:
        invalid_fields = (
            {"market_direction": "sideways"},
            {"confidence_score": -1},
            {"confidence_score": 101},
            {"reasoning_details": (" ",)},
        )
        for fields in invalid_fields:
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):
                    MarketAnalysis(make_information(), "Summary", **fields)


if __name__ == "__main__":
    unittest.main()
