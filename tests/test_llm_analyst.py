"""Tests for the optional OpenAI-backed analyst without network access."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from futures_intelligence.analyst import BaseAnalyst, LLMAnalyst, LLMSmokeTestResult
from futures_intelligence.models import MarketInformation
from futures_intelligence.utils.llm_usage import LLMUsageTracker, LLMPricing


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


class AuthenticationError(Exception):
    """Mimic the SDK exception name without importing the SDK in tests."""


class RateLimitError(Exception):
    """Mimic the SDK exception name without importing the SDK in tests."""


class APIError(Exception):
    """Mimic the SDK exception name without importing the SDK in tests."""


def successful_response() -> SimpleNamespace:
    """Return one local structured Responses API result."""
    return SimpleNamespace(
        id="resp_test_123",
        model="gpt-5.6-luna",
        usage=SimpleNamespace(
            input_tokens=100,
            input_tokens_details=SimpleNamespace(
                cached_tokens=20,
                cache_write_tokens=10,
            ),
            output_tokens=30,
            output_tokens_details=SimpleNamespace(reasoning_tokens=12),
            total_tokens=130,
        ),
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

    def test_successful_production_call_appends_one_usage_record(self) -> None:
        with TemporaryDirectory() as directory:
            usage_path = Path(directory) / "llm_usage.jsonl"
            tracker = LLMUsageTracker(
                usage_path,
                LLMPricing(
                    model="gpt-5.6-luna",
                    effective_date="2026-07-19",
                    input_per_million_usd=1.0,
                    cached_input_per_million_usd=0.1,
                    output_per_million_usd=6.0,
                    cache_write_multiplier=1.25,
                ),
            )
            client = FakeClient([successful_response()])
            information = make_information()

            analysis = LLMAnalyst(client=client, usage_tracker=tracker).analyze(
                [information]
            )[0]

            self.assertIs(analysis.market_information, information)
            self.assertEqual(len(client.responses.calls), 1)
            records = usage_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(records), 1)
            self.assertIn('"purpose": "morning_brief"', records[0])
            self.assertIn('"success": true', records[0])

    def test_last_usage_record_is_cleared_for_each_analyze_invocation(self) -> None:
        with TemporaryDirectory() as directory:
            analyst = LLMAnalyst(
                client=FakeClient([successful_response()]),
                usage_tracker=LLMUsageTracker(
                    Path(directory) / "llm_usage.jsonl",
                    LLMPricing(
                        model="gpt-5.6-luna",
                        effective_date="2026-07-19",
                        input_per_million_usd=1.0,
                        cached_input_per_million_usd=0.1,
                        output_per_million_usd=6.0,
                        cache_write_multiplier=1.25,
                    ),
                ),
            )

            analyst.analyze([make_information()])
            first_record = analyst.last_usage_record
            first_record_persisted = analyst.last_usage_record_persisted
            analyst.analyze([])

            self.assertIsNotNone(first_record)
            self.assertTrue(first_record_persisted)
            self.assertIsNone(analyst.last_usage_record)
            self.assertIsNone(analyst.last_usage_record_persisted)

    def test_smoke_test_success_returns_the_appended_usage_record(self) -> None:
        with TemporaryDirectory() as directory:
            tracker = LLMUsageTracker(
                Path(directory) / "llm_usage.jsonl",
                LLMPricing(
                    model="gpt-5.6-luna",
                    effective_date="2026-07-19",
                    input_per_million_usd=1.0,
                    cached_input_per_million_usd=0.1,
                    output_per_million_usd=6.0,
                    cache_write_multiplier=1.25,
                ),
            )
            client = FakeClient([successful_response()])

            result = LLMAnalyst(
                client=client,
                usage_tracker=tracker,
            ).analyze_smoke_test(make_information())

            self.assertTrue(result.success)
            self.assertIsNotNone(result.usage_record)
            assert result.usage_record is not None
            self.assertEqual(result.usage_record.purpose, "smoke_test")
            self.assertEqual(len(client.responses.calls), 1)

    def test_attempted_api_failure_appends_one_sanitized_usage_record(self) -> None:
        with TemporaryDirectory() as directory:
            usage_path = Path(directory) / "llm_usage.jsonl"
            tracker = LLMUsageTracker(
                usage_path,
                LLMPricing(
                    model="gpt-5.6-luna",
                    effective_date="2026-07-19",
                    input_per_million_usd=1.0,
                    cached_input_per_million_usd=0.1,
                    output_per_million_usd=6.0,
                    cache_write_multiplier=1.25,
                ),
            )
            client = FakeClient([RuntimeError("private request failure")])

            LLMAnalyst(client=client, usage_tracker=tracker).analyze([make_information()])

            self.assertEqual(len(client.responses.calls), 1)
            record = usage_path.read_text(encoding="utf-8")
            self.assertIn('"failure_category": "unknown_error"', record)
            self.assertNotIn("private request failure", record)

    def test_refusal_and_malformed_responses_append_one_failure_record_each(self) -> None:
        with TemporaryDirectory() as directory:
            usage_path = Path(directory) / "llm_usage.jsonl"
            tracker = LLMUsageTracker(
                usage_path,
                LLMPricing(
                    model="gpt-5.6-luna",
                    effective_date="2026-07-19",
                    input_per_million_usd=1.0,
                    cached_input_per_million_usd=0.1,
                    output_per_million_usd=6.0,
                    cache_write_multiplier=1.25,
                ),
            )
            refusal = SimpleNamespace(
                output_text=None,
                refusal="Unable to comply",
                model="gpt-5.6-luna",
                usage=successful_response().usage,
            )
            malformed = SimpleNamespace(
                output_text="not JSON",
                model="gpt-5.6-luna",
                usage=successful_response().usage,
            )
            client = FakeClient([refusal, malformed])
            analyst = LLMAnalyst(client=client, usage_tracker=tracker)

            analyst.analyze([make_information("refusal")])
            analyst.analyze([make_information("malformed")])

            records = usage_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(records), 2)
            self.assertIn('"failure_category": "refusal"', records[0])
            self.assertIn('"failure_category": "malformed_output"', records[1])

    def test_missing_api_key_does_not_append_a_usage_record(self) -> None:
        with TemporaryDirectory() as directory:
            usage_path = Path(directory) / "llm_usage.jsonl"
            tracker = LLMUsageTracker(
                usage_path,
                LLMPricing(
                    model="gpt-5.6-luna",
                    effective_date="2026-07-19",
                    input_per_million_usd=1.0,
                    cached_input_per_million_usd=0.1,
                    output_per_million_usd=6.0,
                    cache_write_multiplier=1.25,
                ),
            )
            with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
                LLMAnalyst(usage_tracker=tracker).analyze([make_information()])

            self.assertFalse(usage_path.exists())

    def test_sdk_error_names_are_recorded_as_sanitized_categories(self) -> None:
        with TemporaryDirectory() as directory:
            usage_path = Path(directory) / "llm_usage.jsonl"
            tracker = LLMUsageTracker(
                usage_path,
                LLMPricing(
                    model="gpt-5.6-luna",
                    effective_date="2026-07-19",
                    input_per_million_usd=1.0,
                    cached_input_per_million_usd=0.1,
                    output_per_million_usd=6.0,
                    cache_write_multiplier=1.25,
                ),
            )
            client = FakeClient(
                [AuthenticationError("secret"), RateLimitError("secret"), APIError("secret")]
            )
            analyst = LLMAnalyst(client=client, usage_tracker=tracker)

            for index in range(3):
                analyst.analyze([make_information(f"error {index}")])

            records = usage_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(records), 3)
            self.assertIn('"failure_category": "authentication_error"', records[0])
            self.assertIn('"failure_category": "rate_limit_error"', records[1])
            self.assertIn('"failure_category": "api_error"', records[2])
            self.assertNotIn("secret", "".join(records))

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
