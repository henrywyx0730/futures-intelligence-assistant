"""Tests for deterministic analyst routing."""

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from futures_intelligence.analyst import AnalystRouter, LLMAnalyst, RuleBasedAnalyst
from futures_intelligence.models import MarketInformation
from futures_intelligence.utils.llm_usage import LLMUsageTracker, LLMPricing


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

    def test_empty_selected_candidates_keep_research_reports_rule_based(self) -> None:
        llm_analyst = LLMAnalyst()
        router = AnalystRouter(
            llm_analyst=llm_analyst,
            llm_candidates=(),
            max_llm_items=3,
        )

        self.assertIsInstance(
            router.select_analyst(make_information("research_report")), RuleBasedAnalyst
        )

    def test_routes_only_the_selected_object_instance_to_llm(self) -> None:
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
        selected = make_information("research_report")
        equal_but_unselected = make_information("research_report")
        llm_analyst = LLMAnalyst(client=client, max_items_per_run=3)
        router = AnalystRouter(
            llm_analyst=llm_analyst,
            llm_candidates=(selected,),
            max_llm_items=3,
        )

        self.assertIs(router.select_analyst(selected), llm_analyst)
        self.assertIsInstance(
            router.select_analyst(equal_but_unselected), RuleBasedAnalyst
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
        first_report = make_information("research_report")
        second_report = make_information("research_report")
        router = AnalystRouter(
            llm_analyst=llm_analyst,
            llm_candidates=(first_report, second_report),
            max_llm_items=1,
        )
        information = [
            first_report,
            make_information("rss"),
            second_report,
        ]

        analyses = router.analyze(information)

        client.responses.create.assert_called_once()
        self.assertEqual([analysis.market_information for analysis in analyses], information)
        self.assertEqual(analyses[0].summary, "LLM summary.")
        self.assertIn("Detected commodity focus: Gold.", analyses[1].summary)
        self.assertIn("Detected commodity focus: Gold.", analyses[2].summary)

    def test_duplicate_selected_instance_falls_back_without_a_second_llm_call(self) -> None:
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
        selected = make_information("research_report")
        router = AnalystRouter(
            llm_analyst=LLMAnalyst(client=client, max_items_per_run=3),
            llm_candidates=(selected,),
            max_llm_items=3,
        )

        analyses = router.analyze([selected, selected])

        client.responses.create.assert_called_once()
        self.assertEqual([analysis.market_information for analysis in analyses], [selected, selected])
        self.assertEqual(analyses[0].summary, "LLM summary.")
        self.assertIn("Detected commodity focus: Gold.", analyses[1].summary)

    def test_failed_selected_llm_call_falls_back_to_rule_based_analysis(self) -> None:
        client = Mock()
        client.responses.create.side_effect = RuntimeError("unavailable")
        selected = make_information("research_report")
        router = AnalystRouter(
            llm_analyst=LLMAnalyst(client=client, max_items_per_run=3),
            llm_candidates=(selected,),
            max_llm_items=3,
        )

        analysis = router.analyze([selected])[0]

        client.responses.create.assert_called_once()
        self.assertIs(analysis.market_information, selected)
        self.assertIn("Detected commodity focus: Gold.", analysis.summary)

    def test_selected_production_call_writes_one_usage_record(self) -> None:
        with TemporaryDirectory() as directory:
            client = Mock()
            client.responses.create.return_value = SimpleNamespace(
                id="resp_test_123",
                model="gpt-5.6-luna",
                usage=SimpleNamespace(
                    input_tokens=10,
                    input_tokens_details=SimpleNamespace(
                        cached_tokens=0,
                        cache_write_tokens=0,
                    ),
                    output_tokens=5,
                    output_tokens_details=SimpleNamespace(reasoning_tokens=0),
                    total_tokens=15,
                ),
                output_text=json.dumps(
                    {
                        "summary": "LLM summary.",
                        "market_direction": "neutral",
                        "confidence_score": 25,
                        "reasoning_details": ["Mocked response."],
                    }
                ),
            )
            tracker_path = Path(directory) / "llm_usage.jsonl"
            tracker = LLMUsageTracker(
                tracker_path,
                LLMPricing(
                    model="gpt-5.6-luna",
                    effective_date="2026-07-19",
                    input_per_million_usd=1.0,
                    cached_input_per_million_usd=0.1,
                    output_per_million_usd=6.0,
                    cache_write_multiplier=1.25,
                ),
            )
            selected = make_information("research_report")
            router = AnalystRouter(
                llm_analyst=LLMAnalyst(
                    client=client,
                    max_items_per_run=3,
                    usage_tracker=tracker,
                ),
                llm_candidates=(selected,),
                max_llm_items=3,
            )

            router.analyze([selected, make_information("rss")])

            client.responses.create.assert_called_once()
            self.assertEqual(len(tracker_path.read_text(encoding="utf-8").splitlines()), 1)

    def test_rejects_non_market_information_values(self) -> None:
        with self.assertRaises(TypeError):
            self.router.select_analyst(object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
