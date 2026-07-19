"""Tests for local, sanitized LLM usage and cost tracking."""

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from futures_intelligence.models import MarketInformation
from futures_intelligence.utils.llm_usage import LLMUsageTracker, LLMPricing


def make_information() -> MarketInformation:
    """Create a normalized input without exposing its content in persisted records."""
    return MarketInformation(
        title="Crude oil outlook",
        source="Local Research Desk",
        source_type="research_report",
        published_time=datetime(2026, 7, 19, tzinfo=timezone.utc),
        content="Sensitive report content must not be persisted in usage tracking.",
        metadata={"internal_reference": "secret metadata value"},
    )


def response_with_usage(
    *,
    model: str = "gpt-5.6-luna",
    input_tokens: object = 100,
    cached_tokens: object | None = 20,
    cache_write_tokens: object | None = 10,
    output_tokens: object = 30,
    reasoning_tokens: object | None = 12,
    total_tokens: object = 130,
) -> SimpleNamespace:
    """Create a local Responses-like object with optional usage details."""
    input_details = SimpleNamespace()
    if cached_tokens is not None:
        input_details.cached_tokens = cached_tokens
    if cache_write_tokens is not None:
        input_details.cache_write_tokens = cache_write_tokens
    output_details = SimpleNamespace()
    if reasoning_tokens is not None:
        output_details.reasoning_tokens = reasoning_tokens
    return SimpleNamespace(
        id="resp_test_123",
        model=model,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            input_tokens_details=input_details,
            output_tokens=output_tokens,
            output_tokens_details=output_details,
            total_tokens=total_tokens,
        ),
    )


class LLMUsageTrackerTests(unittest.TestCase):
    """Verify response-derived usage records and deterministic cost estimates."""

    def setUp(self) -> None:
        self.pricing = LLMPricing(
            model="gpt-5.6-luna",
            effective_date="2026-07-19",
            input_per_million_usd=1.00,
            cached_input_per_million_usd=0.10,
            output_per_million_usd=6.00,
            cache_write_multiplier=1.25,
        )

    def test_records_successful_response_usage_and_cost(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "usage.jsonl"
            tracker = LLMUsageTracker(path, self.pricing)

            record = tracker.record_success(
                purpose="smoke_test",
                information=make_information(),
                configured_model="gpt-5.6-luna",
                response=response_with_usage(),
                timestamp=datetime(2026, 7, 19, tzinfo=timezone.utc),
            )

            self.assertEqual(record.input_tokens, 100)
            self.assertEqual(record.cached_input_tokens, 20)
            self.assertEqual(record.cache_write_tokens, 10)
            self.assertEqual(record.output_tokens, 30)
            self.assertEqual(record.reasoning_tokens, 12)
            self.assertEqual(record.total_tokens, 130)
            self.assertEqual(record.estimated_cost_usd, 0.0002645)
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["purpose"], "smoke_test")
            self.assertTrue(stored["success"])
            self.assertNotIn("content", stored)
            self.assertNotIn("metadata", stored)
            self.assertNotIn("prompt", stored)

    def test_missing_optional_usage_details_are_zero_without_extra_requests(self) -> None:
        with TemporaryDirectory() as directory:
            tracker = LLMUsageTracker(Path(directory) / "usage.jsonl", self.pricing)
            response = response_with_usage(
                cached_tokens=None,
                cache_write_tokens=None,
                reasoning_tokens=None,
            )

            record = tracker.record_success(
                purpose="morning_brief",
                information=make_information(),
                configured_model="gpt-5.6-luna",
                response=response,
            )

            self.assertEqual(record.cached_input_tokens, 0)
            self.assertEqual(record.cache_write_tokens, 0)
            self.assertEqual(record.reasoning_tokens, 0)
            self.assertEqual(record.estimated_cost_usd, 0.00028)

    def test_cost_is_null_when_actual_model_or_required_usage_is_unavailable(self) -> None:
        with TemporaryDirectory() as directory:
            tracker = LLMUsageTracker(Path(directory) / "usage.jsonl", self.pricing)

            mismatch = tracker.record_success(
                purpose="morning_brief",
                information=make_information(),
                configured_model="gpt-5.6-luna",
                response=response_with_usage(model="different-model"),
            )
            missing = tracker.record_success(
                purpose="morning_brief",
                information=make_information(),
                configured_model="gpt-5.6-luna",
                response=response_with_usage(input_tokens=None),
            )

            self.assertIsNone(mismatch.estimated_cost_usd)
            self.assertIsNone(missing.estimated_cost_usd)

    def test_records_sanitized_failure_without_raw_exception_text(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "usage.jsonl"
            record = LLMUsageTracker(path, self.pricing).record_failure(
                purpose="morning_brief",
                information=make_information(),
                configured_model="gpt-5.6-luna",
                failure_category="api_error",
            )

            self.assertFalse(record.success)
            self.assertEqual(record.failure_category, "api_error")
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("exception", stored)
            self.assertNotIn("secret", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
