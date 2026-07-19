"""Optional OpenAI Responses API analyst with deterministic fallback behavior."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol

from futures_intelligence.analyst.base import BaseAnalyst
from futures_intelligence.analyst.rule_based import RuleBasedAnalyst
from futures_intelligence.models import MarketAnalysis, MarketInformation
from futures_intelligence.utils.llm_usage import (
    FailureCategory,
    LLMUsageRecord,
    LLMUsageTracker,
    RequestPurpose,
)


ANALYSIS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "market_direction": {
            "type": "string",
            "enum": ["bullish", "bearish", "neutral"],
        },
        "confidence_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "reasoning_details": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "summary",
        "market_direction",
        "confidence_score",
        "reasoning_details",
    ],
    "additionalProperties": False,
}
SYSTEM_INSTRUCTIONS = (
    "Analyze only the market-information content and metadata supplied by the user. "
    "Do not use external knowledge, tools, retrieval, or make trading recommendations."
)


class ResponsesClient(Protocol):
    """Minimal OpenAI Responses API boundary for dependency injection."""

    responses: Any


@dataclass(frozen=True)
class LLMSmokeTestResult:
    """The explicit result of one strict, no-fallback LLM smoke-test request."""

    success: bool
    analysis: MarketAnalysis | None = None
    error: str | None = None
    usage_record: LLMUsageRecord | None = None
    usage_file_path: str | None = None


class LLMAnalyst(BaseAnalyst):
    """Use a configured OpenAI client and fall back safely on any unavailable state."""

    def __init__(
        self,
        model: str = "gpt-5.6-luna",
        max_items_per_run: int = 5,
        client: ResponsesClient | None = None,
        fallback_analyst: BaseAnalyst | None = None,
        usage_tracker: LLMUsageTracker | None = None,
    ) -> None:
        """Configure a lazy client boundary without reading or logging credentials."""
        if not isinstance(model, str) or not (normalized_model := model.strip()):
            raise ValueError("model must be a non-empty string")
        if (
            isinstance(max_items_per_run, bool)
            or not isinstance(max_items_per_run, int)
            or max_items_per_run < 1
        ):
            raise ValueError("max_items_per_run must be a positive integer")
        self.model = normalized_model
        self.max_items_per_run = max_items_per_run
        self._client = client
        self._fallback_analyst = fallback_analyst or RuleBasedAnalyst()
        self._usage_tracker = usage_tracker

    def analyze(self, information: list[MarketInformation]) -> list[MarketAnalysis]:
        """Return ordered analyses, using deterministic fallback for unavailable items."""
        client = self._client or _openai_client_from_environment()
        analyses: list[MarketAnalysis] = []
        for index, item in enumerate(information):
            if client is None or index >= self.max_items_per_run:
                analyses.extend(self._fallback_analyst.analyze([item]))
                continue
            analysis = self._analyze_item(client, item)
            if analysis is None:
                analyses.extend(self._fallback_analyst.analyze([item]))
            else:
                analyses.append(analysis)
        return analyses

    def analyze_smoke_test(self, item: MarketInformation) -> LLMSmokeTestResult:
        """Run one strict LLM request and never substitute a rule-based result."""
        if not isinstance(item, MarketInformation):
            return LLMSmokeTestResult(
                success=False,
                error="Smoke-test input must be a MarketInformation instance.",
            )
        client = self._client
        if client is None:
            client, error = _openai_client_for_smoke_test()
            if client is None:
                return LLMSmokeTestResult(success=False, error=error)

        analysis, error, usage_record = self._request_analysis(
            client,
            item,
            purpose="smoke_test",
        )
        if analysis is None:
            return LLMSmokeTestResult(
                success=False,
                error=error,
                usage_record=usage_record,
                usage_file_path=self._usage_file_path(),
            )
        return LLMSmokeTestResult(
            success=True,
            analysis=analysis,
            usage_record=usage_record,
            usage_file_path=self._usage_file_path(),
        )

    def _analyze_item(
        self, client: ResponsesClient, item: MarketInformation
    ) -> MarketAnalysis | None:
        """Request and validate one structured local-content-only analysis."""
        analysis, _, _ = self._request_analysis(
            client,
            item,
            purpose="morning_brief",
        )
        return analysis

    def _request_analysis(
        self,
        client: ResponsesClient,
        item: MarketInformation,
        *,
        purpose: RequestPurpose,
    ) -> tuple[MarketAnalysis | None, str | None, LLMUsageRecord | None]:
        """Make one Responses API request and return an explicit validation error."""
        try:
            response = client.responses.create(
                model=self.model,
                instructions=SYSTEM_INSTRUCTIONS,
                input=json.dumps(
                    {"content": item.content, "metadata": item.metadata},
                    ensure_ascii=False,
                ),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "market_analysis",
                        "strict": True,
                        "schema": ANALYSIS_SCHEMA,
                    }
                },
                tools=[],
                tool_choice="none",
                store=False,
            )
        except Exception as error:
            return (
                None,
                "OpenAI API request failed.",
                self._record_failure(item, purpose, _failure_category(error)),
            )
        analysis = _analysis_from_response(item, response)
        if analysis is None:
            return (
                None,
                "OpenAI returned no valid structured analysis.",
                self._record_failure(
                    item,
                    purpose,
                    _response_failure_category(response),
                    response,
                ),
            )
        return analysis, None, self._record_success(item, purpose, response)

    def _record_success(
        self,
        item: MarketInformation,
        purpose: RequestPurpose,
        response: object,
    ) -> LLMUsageRecord | None:
        """Persist actual response usage without adding another API request."""
        if self._usage_tracker is None:
            return None
        return self._usage_tracker.record_success(
            purpose=purpose,
            information=item,
            configured_model=self.model,
            response=response,
        )

    def _record_failure(
        self,
        item: MarketInformation,
        purpose: RequestPurpose,
        failure_category: FailureCategory,
        response: object | None = None,
    ) -> LLMUsageRecord | None:
        """Persist a sanitized result for a request attempt that did not validate."""
        if self._usage_tracker is None:
            return None
        return self._usage_tracker.record_failure(
            purpose=purpose,
            information=item,
            configured_model=self.model,
            failure_category=failure_category,
            response=response,
        )

    def _usage_file_path(self) -> str | None:
        """Return the configured local usage location without reading its contents."""
        return str(self._usage_tracker.file_path) if self._usage_tracker else None


def _openai_client_from_environment() -> ResponsesClient | None:
    """Create the official SDK client only when the process has an API key."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI

        return OpenAI(api_key=api_key)
    except Exception:
        return None


def _openai_client_for_smoke_test() -> tuple[ResponsesClient | None, str | None]:
    """Create an SDK client or return a precise smoke-test failure reason."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None, "OPENAI_API_KEY is not set."
    try:
        from openai import OpenAI
    except ImportError:
        return None, "OpenAI SDK is unavailable. Install the configured dependency."
    try:
        return OpenAI(api_key=api_key), None
    except Exception:
        return None, "OpenAI SDK client initialization failed."


def _analysis_from_response(
    item: MarketInformation, response: object
) -> MarketAnalysis | None:
    """Convert a valid Responses API JSON text payload into MarketAnalysis."""
    response_text = getattr(response, "output_text", None)
    if not isinstance(response_text, str):
        return None
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not _valid_payload(payload):
        return None
    try:
        return MarketAnalysis(
            market_information=item,
            summary=payload["summary"],
            market_direction=payload["market_direction"],
            confidence_score=payload["confidence_score"],
            reasoning_details=tuple(payload["reasoning_details"]),
        )
    except (TypeError, ValueError):
        return None


def _valid_payload(payload: dict[str, object]) -> bool:
    """Validate the externally produced structured data before using it."""
    reasoning_details = payload.get("reasoning_details")
    return (
        isinstance(payload.get("summary"), str)
        and bool(payload["summary"].strip())
        and payload.get("market_direction") in {"bullish", "bearish", "neutral"}
        and isinstance(payload.get("confidence_score"), int)
        and not isinstance(payload.get("confidence_score"), bool)
        and 0 <= payload["confidence_score"] <= 100
        and isinstance(reasoning_details, list)
        and all(
            isinstance(detail, str) and detail.strip() for detail in reasoning_details
        )
    )


def _failure_category(error: Exception) -> FailureCategory:
    """Classify an exception without persisting its potentially sensitive message."""
    name = type(error).__name__.lower()
    if "auth" in name or "permission" in name:
        return "authentication_error"
    if "rate" in name and "limit" in name:
        return "rate_limit_error"
    if "api" in name:
        return "api_error"
    return "unknown_error"


def _response_failure_category(response: object) -> FailureCategory:
    """Distinguish a refusal from a malformed structured response."""
    if getattr(response, "refusal", None) or not isinstance(
        getattr(response, "output_text", None), str
    ):
        return "refusal"
    return "malformed_output"
