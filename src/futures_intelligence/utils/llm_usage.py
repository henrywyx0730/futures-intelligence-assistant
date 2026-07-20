"""Local, sanitized accounting for actual OpenAI Responses API usage."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Literal

from futures_intelligence.models import MarketInformation


RequestPurpose = Literal["smoke_test", "morning_brief"]
FailureCategory = Literal[
    "authentication_error",
    "rate_limit_error",
    "api_error",
    "refusal",
    "malformed_output",
    "unavailable_sdk",
    "unknown_error",
]


@dataclass(frozen=True)
class LLMPricing:
    """A local pricing snapshot used only for transparent cost estimates."""

    model: str
    effective_date: str
    input_per_million_usd: float
    cached_input_per_million_usd: float
    output_per_million_usd: float
    cache_write_multiplier: float


@dataclass(frozen=True)
class LLMUsageRecord:
    """One sanitized, JSON-serializable Responses API usage record."""

    timestamp_utc: str
    purpose: RequestPurpose
    model: str
    response_id: str | None
    source_type: str
    source_name: str
    source_title: str
    success: bool
    failure_category: FailureCategory | None
    input_tokens: int | None
    cached_input_tokens: int | None
    cache_write_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: float | None
    pricing_effective_date: str

    def to_dict(self) -> dict[str, object]:
        """Return the record without prompts, contents, outputs, or exceptions."""
        return asdict(self)


class LLMUsageTracker:
    """Append sanitized usage records without affecting the analysis pipeline."""

    def __init__(self, file_path: str | Path, pricing: LLMPricing) -> None:
        self.file_path = Path(file_path)
        self.pricing = pricing
        self._last_append_succeeded: bool | None = None

    @property
    def last_append_succeeded(self) -> bool | None:
        """Return whether the most recently constructed record reached local storage."""
        return self._last_append_succeeded

    def record_success(
        self,
        *,
        purpose: RequestPurpose,
        information: MarketInformation,
        configured_model: str,
        response: object,
        timestamp: datetime | None = None,
    ) -> LLMUsageRecord:
        """Append one successful API response record derived from its usage object."""
        return self._record(
            purpose=purpose,
            information=information,
            configured_model=configured_model,
            response=response,
            success=True,
            failure_category=None,
            timestamp=timestamp,
        )

    def record_failure(
        self,
        *,
        purpose: RequestPurpose,
        information: MarketInformation,
        configured_model: str,
        failure_category: FailureCategory,
        response: object | None = None,
        timestamp: datetime | None = None,
    ) -> LLMUsageRecord:
        """Append one sanitized record for an attempted API call that failed."""
        return self._record(
            purpose=purpose,
            information=information,
            configured_model=configured_model,
            response=response,
            success=False,
            failure_category=failure_category,
            timestamp=timestamp,
        )

    def _record(
        self,
        *,
        purpose: RequestPurpose,
        information: MarketInformation,
        configured_model: str,
        response: object | None,
        success: bool,
        failure_category: FailureCategory | None,
        timestamp: datetime | None,
    ) -> LLMUsageRecord:
        token_usage = _response_token_usage(response)
        actual_model = _text_attribute(response, "model")
        record = LLMUsageRecord(
            timestamp_utc=(timestamp or datetime.now(timezone.utc)).astimezone(
                timezone.utc
            ).isoformat(),
            purpose=purpose,
            model=actual_model or configured_model,
            response_id=_text_attribute(response, "id"),
            source_type=information.source_type,
            source_name=information.source,
            source_title=information.title,
            success=success,
            failure_category=failure_category,
            input_tokens=token_usage.input_tokens,
            cached_input_tokens=token_usage.cached_input_tokens,
            cache_write_tokens=token_usage.cache_write_tokens,
            output_tokens=token_usage.output_tokens,
            reasoning_tokens=token_usage.reasoning_tokens,
            total_tokens=token_usage.total_tokens,
            estimated_cost_usd=estimate_cost_usd(
                token_usage,
                configured_model=configured_model,
                actual_model=actual_model,
                pricing=self.pricing,
            ),
            pricing_effective_date=self.pricing.effective_date,
        )
        self._last_append_succeeded = self._append(record)
        return record

    def _append(self, record: LLMUsageRecord) -> bool:
        """Append one line atomically enough for a local single-process utility."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("a", encoding="utf-8") as output:
                output.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
            return True
        except OSError:
            # Usage accounting must not turn an optional LLM failure into a pipeline crash.
            return False


@dataclass(frozen=True)
class _TokenUsage:
    """Token values copied directly from an optional Responses API usage object."""

    input_tokens: int | None
    cached_input_tokens: int | None
    cache_write_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    total_tokens: int | None


def _response_token_usage(response: object | None) -> _TokenUsage:
    """Read supported Response usage fields without estimating any token counts."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return _TokenUsage(None, None, None, None, None, None)
    input_details = getattr(usage, "input_tokens_details", None)
    output_details = getattr(usage, "output_tokens_details", None)
    return _TokenUsage(
        input_tokens=_required_token(getattr(usage, "input_tokens", None)),
        cached_input_tokens=_optional_token(
            getattr(input_details, "cached_tokens", None)
        ),
        cache_write_tokens=_optional_token(
            getattr(input_details, "cache_write_tokens", None)
        ),
        output_tokens=_required_token(getattr(usage, "output_tokens", None)),
        reasoning_tokens=_optional_token(
            getattr(output_details, "reasoning_tokens", None)
        ),
        total_tokens=_required_token(getattr(usage, "total_tokens", None)),
    )


def estimate_cost_usd(
    usage: _TokenUsage,
    *,
    configured_model: str,
    actual_model: str | None,
    pricing: LLMPricing,
) -> float | None:
    """Estimate one request's cost from response usage and a matching price snapshot."""
    if (
        actual_model is None
        or actual_model != configured_model
        or actual_model != pricing.model
        or usage.input_tokens is None
        or usage.output_tokens is None
    ):
        return None
    cached_tokens = usage.cached_input_tokens or 0
    cache_write_tokens = usage.cache_write_tokens or 0
    uncached_input_tokens = max(
        usage.input_tokens - cached_tokens - cache_write_tokens,
        0,
    )
    cost = (
        uncached_input_tokens * pricing.input_per_million_usd
        + cached_tokens * pricing.cached_input_per_million_usd
        + cache_write_tokens
        * pricing.input_per_million_usd
        * pricing.cache_write_multiplier
        + usage.output_tokens * pricing.output_per_million_usd
    ) / 1_000_000
    return round(cost, 8)


def _required_token(value: object) -> int | None:
    """Return a non-negative reported token count, otherwise mark it unavailable."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _optional_token(value: object) -> int:
    """Return an optional detail count, treating absent or invalid values as zero."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _text_attribute(value: object | None, name: str) -> str | None:
    """Read a non-empty response identifier or model name without coercion."""
    attribute = getattr(value, name, None)
    return attribute.strip() if isinstance(attribute, str) and attribute.strip() else None
