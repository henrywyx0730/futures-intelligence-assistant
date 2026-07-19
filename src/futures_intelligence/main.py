"""Application entry point for the Futures Intelligence Assistant."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from futures_intelligence.analyst import LLMAnalyst
from futures_intelligence.models import MarketAnalysis, MarketInformation
from futures_intelligence.services import MorningBriefService
from futures_intelligence.services.morning_brief_service import (
    DEFAULT_LLM_MODEL,
    load_runtime_configuration,
)
from futures_intelligence.utils.health import HealthReport
from futures_intelligence.utils.llm_usage import (
    LLMPricing,
    LLMUsageRecord,
    LLMUsageTracker,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SMOKE_TEST_REPORT_PATH = (
    PROJECT_ROOT / "data" / "research_reports" / "sample_crude_oil_outlook.txt"
)


def main(argv: list[str] | None = None) -> int:
    """Parse a command and run its CLI presentation handler."""
    arguments = _parse_arguments(argv)
    if arguments.command in (None, "morning-brief"):
        _run_morning_brief()
        return 0
    if arguments.command == "llm-smoke-test":
        return _run_llm_smoke_test()
    return 1


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    """Parse the current CLI command while leaving room for future commands."""
    parser = argparse.ArgumentParser(
        description="Futures Intelligence Assistant commands."
    )
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("morning-brief", help="Generate the morning brief.")
    commands.add_parser(
        "llm-smoke-test",
        help="Run one strict OpenAI smoke test against the local research report.",
    )
    return parser.parse_args(argv)


def _run_morning_brief() -> None:
    """Run the morning brief application service and print CLI output."""
    service = MorningBriefService()
    brief = service.run()
    _print_information_preview(service.information)
    _print_analysis_preview(service.analyses)
    print(brief)
    if service.health_report is not None:
        _print_health_status(service.health_report)


def _run_llm_smoke_test(
    analyst: LLMAnalyst | None = None,
    sample_path: Path = SMOKE_TEST_REPORT_PATH,
) -> int:
    """Run exactly one strict LLM analysis against the fixed local sample report."""
    try:
        information = _load_smoke_test_information(sample_path)
    except (OSError, ValueError) as error:
        print(f"LLM smoke test failed: unable to read local report: {error}")
        return 1

    try:
        model = _configured_llm_model()
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"LLM smoke test failed: unable to load runtime configuration: {error}")
        return 1

    analyst = analyst or LLMAnalyst(
        model=model,
        max_items_per_run=1,
        usage_tracker=_configured_llm_usage_tracker(),
    )
    result = analyst.analyze_smoke_test(information)
    if not result.success or result.analysis is None:
        print(f"LLM smoke test failed: {result.error or 'no structured result returned.'}")
        return 1

    analysis = result.analysis
    print("Real LLM smoke test succeeded: structured response received from OpenAI.")
    print(f"Model: {model}")
    print(f"Source Title: {analysis.market_information.title}")
    print(f"Summary: {analysis.summary}")
    print(f"Market Direction: {analysis.market_direction.title()}")
    print(f"Confidence Score: {analysis.confidence_score}")
    print("Reasoning Details:")
    for detail in analysis.reasoning_details:
        print(f"- {detail}")
    _print_llm_usage(result.usage_record, result.usage_file_path)
    return 0


def _load_smoke_test_information(
    sample_path: Path = SMOKE_TEST_REPORT_PATH,
) -> MarketInformation:
    """Load exactly one deterministic local research-report sample."""
    content = sample_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    title = next((line.strip() for line in lines if line.strip()), "")
    if not title:
        raise ValueError("research report does not contain a title")
    return MarketInformation(
        title=title,
        source="Local research report smoke test",
        source_type="research_report",
        published_time=datetime.now(timezone.utc),
        content=content,
        category=("energy",),
        commodities=("crude_oil",),
        regions=("global",),
        reliability_score=3,
        metadata={"local_report_path": str(sample_path)},
    )


def _configured_llm_model() -> str:
    """Return the configured OpenAI model, using the runtime safe default."""
    return load_runtime_configuration().llm.model or DEFAULT_LLM_MODEL


def _configured_llm_usage_tracker() -> LLMUsageTracker:
    """Build a local tracker from runtime settings without reading any secret."""
    llm = load_runtime_configuration().llm
    return LLMUsageTracker(
        llm.usage.file_path,
        LLMPricing(
            model=llm.pricing.model,
            effective_date=llm.pricing.effective_date,
            input_per_million_usd=llm.pricing.input_per_million_usd,
            cached_input_per_million_usd=llm.pricing.cached_input_per_million_usd,
            output_per_million_usd=llm.pricing.output_per_million_usd,
            cache_write_multiplier=llm.pricing.cache_write_multiplier,
        ),
    )


def _print_llm_usage(
    usage_record: LLMUsageRecord | None,
    usage_file_path: str | None,
) -> None:
    """Print safe local accounting details from the single completed API response."""
    if usage_record is None:
        print("Input Tokens: unavailable")
        print("Cached Input Tokens: unavailable")
        print("Output Tokens: unavailable")
        print("Total Tokens: unavailable")
        print("Estimated Cost (USD): unavailable")
    else:
        print(f"Input Tokens: {usage_record.input_tokens}")
        print(f"Cached Input Tokens: {usage_record.cached_input_tokens}")
        print(f"Output Tokens: {usage_record.output_tokens}")
        print(f"Total Tokens: {usage_record.total_tokens}")
        print(f"Estimated Cost (USD): {usage_record.estimated_cost_usd}")
    print(f"Usage Record Path: {usage_file_path or 'unavailable'}")


def _print_information_preview(information: list[MarketInformation]) -> None:
    """Print a concise preview of up to five collected information items."""
    print(f"Collected market information: {len(information)}")
    for item in information[:5]:
        category = ", ".join(item.category) or "uncategorized"
        print(
            f"- Source: {item.source} | Title: {item.title} | "
            f"Category: {category} | Published: {item.published_time.isoformat()}"
        )


def _print_analysis_preview(analyses: list[MarketAnalysis]) -> None:
    """Print a concise preview of up to five market analyses."""
    print(f"Market analyses: {len(analyses)}")
    for analysis in analyses[:5]:
        information = analysis.market_information
        print(
            f"- Source: {information.source} | Title: {information.title} | "
            f"Analysis: {analysis.summary}"
        )


def _print_health_status(report: HealthReport) -> None:
    """Print the status summary persisted after a successful run."""
    print(
        f"Run status: {report.execution_status} | "
        f"Collected: {report.collected_information_count} | "
        f"Analyses: {report.generated_analysis_count} | "
        f"Brief: {report.brief_generation_status} | "
        f"Timestamp: {report.last_run_timestamp}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
