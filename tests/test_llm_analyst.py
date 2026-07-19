"""Tests for the optional OpenAI-backed analyst without network access."""

from datetime import datetime, timezone
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from futures_intelligence.analyst import BaseAnalyst, LLMAnalyst, LLMSmokeTestResult
from futures_intelligence.models import MarketInformation


class FakeResponses:
    """Record structured requests and return configured local responses."""

    def __init__(self, results: list[object]) -> None:
        self.results = results
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeClient:
    """Expose the minimal Responses API surface used by LLMAnalyst."""

    def __init__(self, results: list[object]) -> None:
        self.responses = FakeResponses(results)


def successful_response() -> SimpleNamespace:
    """Return one local structured Responses API result."""
    return SimpleNamespace(
        output_text=json.dumps(
            {
                "summary": "Report points to improving gold demand.",
                "market_direction": "bullish",
                "confidence_score": 81,
                "reasoning_details": ["Demand language is positive."],
            }
        )
    )


def make_information(title: str = "Gold report") -> MarketInformation:
    """Create normalized information for LLM analyst tests."""
    return MarketInformation(
        title=title,
        source="Test Source",
        source_type="research_report",
        published_time=datetime(2026, 7, 19, tzinfo=timezone.utc),
        content="Gold demand improved.",
        metadata={"report_id": "test-1"},
    )


class LLMAnalystTests(unittest.TestCase):
    """Validate safe structured-output and deterministic fallback behavior."""

    def test_implements_base_analyst(self) -> None:
        self.assertIsInstance(LLMAnalyst(), BaseAnalyst)

    def test_missing_api_key_uses_rule_based_fallback_without_network(self) -> None:
        information = make_information()
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            analyses = LLMAnalyst().analyze([information])

        self.assertIs(analyses[0].market_information, information)
        self.assertIn("Detected commodity focus: Gold.", analyses[0].summary)

    def test_uses_mocked_structured_openai_response(self) -> None:
        client = FakeClient([successful_response()])
        information = make_information()

        analysis = LLMAnalyst(client=client).analyze([information])[0]

        self.assertIs(analysis.market_information, information)
        self.assertEqual(analysis.summary, "Report points to improving gold demand.")
        self.assertEqual(analysis.market_direction, "bullish")
        self.assertEqual(analysis.confidence_score, 81)
        self.assertEqual(analysis.reasoning_details, ("Demand language is positive.",))
        request = client.responses.calls[0]
        self.assertEqual(json.loads(str(request["input"])), {
            "content": information.content,
            "metadata": information.metadata,
        })
        self.assertEqual(request["tools"], [])
        self.assertEqual(request["tool_choice"], "none")
        self.assertFalse(request["store"])

    def test_api_failure_falls_back_to_rule_based_analysis(self) -> None:
        client = FakeClient([RuntimeError("unavailable")])
        information = make_information()

        analysis = LLMAnalyst(client=client).analyze([information])[0]

        self.assertIs(analysis.market_information, information)
        self.assertIn("Detected commodity focus: Gold.", analysis.summary)

    def test_malformed_response_falls_back_to_rule_based_analysis(self) -> None:
        malformed = SimpleNamespace(output_text='{"summary": "Missing fields"}')
        client = FakeClient([malformed])
        information = make_information()

        analysis = LLMAnalyst(client=client).analyze([information])[0]

        self.assertIs(analysis.market_information, information)
        self.assertIn("Detected commodity focus: Gold.", analysis.summary)

    def test_refusal_or_missing_output_falls_back_to_rule_based_analysis(self) -> None:
        client = FakeClient([SimpleNamespace(output_text=None)])
        information = make_information()

        analysis = LLMAnalyst(client=client).analyze([information])[0]

        self.assertIs(analysis.market_information, information)
        self.assertIn("Detected commodity focus: Gold.", analysis.summary)

    def test_enforces_max_items_and_preserves_order_and_references(self) -> None:
        client = FakeClient([successful_response(), successful_response()])
        information = [make_information(f"Gold report {index}") for index in range(3)]

        analyses = LLMAnalyst(client=client, max_items_per_run=2).analyze(information)

        self.assertEqual(len(client.responses.calls), 2)
        self.assertEqual([analysis.market_information for analysis in analyses], information)
        self.assertEqual(analyses[0].summary, "Report points to improving gold demand.")
        self.assertEqual(analyses[1].summary, "Report points to improving gold demand.")
        self.assertIn("Detected commodity focus: Gold.", analyses[2].summary)

    def test_handles_empty_input_without_client_calls(self) -> None:
        client = FakeClient([])

        self.assertEqual(LLMAnalyst(client=client).analyze([]), [])
        self.assertEqual(client.responses.calls, [])

    def test_smoke_test_returns_one_real_structured_analysis(self) -> None:
        client = FakeClient([successful_response()])
        information = make_information()

        result = LLMAnalyst(client=client).analyze_smoke_test(information)

        self.assertIsInstance(result, LLMSmokeTestResult)
        self.assertTrue(result.success)
        self.assertIsNotNone(result.analysis)
        assert result.analysis is not None
        self.assertIs(result.analysis.market_information, information)
        self.assertEqual(len(client.responses.calls), 1)

    def test_smoke_test_missing_api_key_fails_without_fallback(self) -> None:
        information = make_information()
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            result = LLMAnalyst().analyze_smoke_test(information)

        self.assertFalse(result.success)
        self.assertIsNone(result.analysis)
        self.assertIn("OPENAI_API_KEY", result.error or "")

    @patch(
        "futures_intelligence.analyst.llm._openai_client_for_smoke_test",
        return_value=(None, "OpenAI SDK is unavailable. Install the configured dependency."),
    )
    def test_smoke_test_unavailable_sdk_fails_without_fallback(
        self, smoke_client: object
    ) -> None:
        result = LLMAnalyst().analyze_smoke_test(make_information())

        self.assertFalse(result.success)
        self.assertIsNone(result.analysis)
        self.assertIn("OpenAI SDK is unavailable", result.error or "")

    def test_smoke_test_api_failure_is_not_reported_as_fallback_success(self) -> None:
        client = FakeClient([RuntimeError("unavailable")])

        result = LLMAnalyst(client=client).analyze_smoke_test(make_information())

        self.assertFalse(result.success)
        self.assertIsNone(result.analysis)
        self.assertNotIn("Detected commodity", result.error or "")

    def test_smoke_test_refusal_or_malformed_response_fails(self) -> None:
        for response in (
            SimpleNamespace(output_text=None),
            SimpleNamespace(output_text='{"summary": "Missing fields"}'),
        ):
            with self.subTest(response=response.output_text):
                result = LLMAnalyst(client=FakeClient([response])).analyze_smoke_test(
                    make_information()
                )

                self.assertFalse(result.success)
                self.assertIsNone(result.analysis)


if __name__ == "__main__":
    unittest.main()
