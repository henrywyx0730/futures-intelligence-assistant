"""Tests for deterministic analyst routing."""

from datetime import datetime, timezone
import unittest

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

    def test_accepts_a_future_llm_route_override(self) -> None:
        llm_analyst = LLMAnalyst()
        router = AnalystRouter({"rss": llm_analyst})

        self.assertIs(router.select_analyst(make_information("rss")), llm_analyst)

    def test_rejects_non_market_information_values(self) -> None:
        with self.assertRaises(TypeError):
            self.router.select_analyst(object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
