"""Tests for deterministic analyst routing."""

from datetime import datetime, timezone
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from futures_intelligence.analyst import AnalystRouter, LLMAnalyst, RuleBasedAnalyst
from futures_intelligence.models import MarketInformation


def make_information(source_type: str) -> MarketInformation:
    """Create one normalized item for router tests."""
    return MarketInformation(
        title="Gold market update",
        source="Test Source",
        source_type=source_type,
        published_time=datetime(2026, 7, 19, tzinfo=timezone.utc),
        content="Gold demand improved.",
    )


class AnalystRouterTests(unittest.TestCase):
    """Validate source-type analyst selection."""

    def setUp(self) -> None:
        self.router = AnalystRouter()

    def test_routes_supported_source_types_to_rule_based_analyst(self) -> None:
        for source_type in (
            "market_data",
            "official_data",
            "research_report",
            "rss",
        ):
            with self.subTest(source_type=source_type):
                analyst = self.router.select_analyst(make_information(source_type))

                self.assertIsInstance(analyst, RuleBasedAnalyst)

    def test_preserves_rule_based_analysis_behavior(self) -> None:
        information = make_information("official_data")

        routed_analysis = self.router.select_analyst(information).analyze([information])
        direct_analysis = RuleBasedAnalyst().analyze([information])

        self.assertEqual(routed_analysis, direct_analysis)
        self.assertIs(routed_analysis[0].market_information, information)

    def test_uses_rule_based_analyst_for_unknown_source_types(self) -> None:
        analyst = self.router.select_analyst(make_information("future_source"))

        self.assertIsInstance(analyst, RuleBasedAnalyst)

    def test_disabled_llm_keeps_research_reports_rule_based(self) -> None:
        llm_analyst = LLMAnalyst()
        router = AnalystRouter(
            llm_enabled=False,
            llm_source_types=("research_report",),
            llm_analyst=llm_analyst,
        )

        self.assertIsInstance(
            router.select_analyst(make_information("research_report")), RuleBasedAnalyst
        )

    def test_enabled_llm_routes_only_configured_research_reports(self) -> None:
        llm_analyst = LLMAnalyst()
        router = AnalystRouter(
            llm_enabled=True,
            llm_source_types=("research_report",),
            llm_analyst=llm_analyst,
        )

        self.assertIs(
            router.select_analyst(make_information("research_report")), llm_analyst
        )
        for source_type in ("rss", "market_data", "official_data", "future_source"):
            with self.subTest(source_type=source_type):
                self.assertIsInstance(
                    router.select_analyst(make_information(source_type)), RuleBasedAnalyst
                )

    def test_preserves_order_and_enforces_llm_limit_across_routed_items(self) -> None:
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text=json.dumps(
                {
                    "summary": "LLM summary.",
                    "market_direction": "neutral",
                    "confidence_score": 25,
                    "reasoning_details": ["Mocked response."],
                }
            )
        )
        llm_analyst = LLMAnalyst(client=client, max_items_per_run=1)
        router = AnalystRouter(
            llm_enabled=True,
            llm_source_types=("research_report",),
            llm_analyst=llm_analyst,
        )
        information = [
            make_information("research_report"),
            make_information("rss"),
            make_information("research_report"),
        ]

        analyses = router.analyze(information)

        client.responses.create.assert_called_once()
        self.assertEqual([analysis.market_information for analysis in analyses], information)
        self.assertEqual(analyses[0].summary, "LLM summary.")
        self.assertIn("Detected commodity focus: Gold.", analyses[1].summary)
        self.assertIn("Detected commodity focus: Gold.", analyses[2].summary)

    def test_rejects_non_market_information_values(self) -> None:
        with self.assertRaises(TypeError):
            self.router.select_analyst(object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
