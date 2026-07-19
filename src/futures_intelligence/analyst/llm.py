"""Optional OpenAI Responses API analyst with deterministic fallback behavior."""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from futures_intelligence.analyst.base import BaseAnalyst
from futures_intelligence.analyst.rule_based import RuleBasedAnalyst
from futures_intelligence.models import MarketAnalysis, MarketInformation


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


class LLMAnalyst(BaseAnalyst):
    """Use a configured OpenAI client and fall back safely on any unavailable state."""

    def __init__(
        self,
        model: str = "gpt-5.6-luna",
        max_items_per_run: int = 5,
        client: ResponsesClient | None = None,
        fallback_analyst: BaseAnalyst | None = None,
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

    def _analyze_item(
        self, client: ResponsesClient, item: MarketInformation
    ) -> MarketAnalysis | None:
        """Request and validate one structured local-content-only analysis."""
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
            return _analysis_from_response(item, response)
        except Exception:
            return None


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
