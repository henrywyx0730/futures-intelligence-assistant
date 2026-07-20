"""Application entry point for the Futures Intelligence Assistant."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from futures_intelligence.analyst import AnalystRouter, LLMCandidateSelector, LLMAnalyst
from futures_intelligence.analyst.llm import _openai_client_for_smoke_test
from futures_intelligence.collectors.research_report import ResearchReportCollector
from futures_intelligence.fetchers import HuataiFuturesReportFetcher
from futures_intelligence.models import MarketAnalysis, MarketInformation
from futures_intelligence.processing.ranker import InformationRanker
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
HTFC_LISTING_URL = "https://htfc.com/main/yjzx/ssrdph/index.shtml"


def main(argv: list[str] | None = None) -> int:
    """Parse a command and run its CLI presentation handler."""
    arguments = _parse_arguments(argv)
    if arguments.command in (None, "morning-brief"):
        _run_morning_brief()
        return 0
    if arguments.command == "llm-smoke-test":
        return _run_llm_smoke_test()
    if arguments.command == "llm-routing-smoke-test":
        return _run_llm_routing_smoke_test()
    if arguments.command == "htfc-report-smoke-test":
        return _run_htfc_report_smoke_test()
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
    commands.add_parser(
        "llm-routing-smoke-test",
        help="Run one strict production-routing OpenAI smoke test.",
    )
    commands.add_parser(
        "htfc-report-smoke-test",
        help="Fetch and normalize at most one official Huatai Futures HTML report.",
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


def _run_htfc_report_smoke_test(
    fetcher: HuataiFuturesReportFetcher | None = None,
) -> int:
    """Run one bounded, non-persistent HTML-only Huatai report smoke test."""
    fetcher = fetcher or HuataiFuturesReportFetcher(HTFC_LISTING_URL, max_reports=1)
    collector = ResearchReportCollector(
        content_path=None,
        source="Huatai Futures",
        category=("macro", "energy", "metals", "chemical", "financial_futures"),
        regions=("China",),
        reliability_score=5,
        structured_fetcher=fetcher,
    )
    try:
        information = collector.collect()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Huatai Futures report smoke test failed: {_htfc_error_message(error)}")
        return 1
    result = collector.last_fetch_result
    discovery = getattr(result, "discovery", None) if result is not None else None
    html_count = len(discovery.html_detail_links) if discovery is not None else (
        result.discovered_link_count if result is not None else 0
    )
    pdf_count = len(discovery.pdf_attachment_links) if discovery is not None else 0
    unsupported_count = len(discovery.unsupported_links) if discovery is not None else 0
    print(f"Discovered HTML detail links: {html_count}")
    print(f"Discovered PDF attachments: {pdf_count}")
    print(f"Unsupported links skipped: {unsupported_count}")
    if result is None or not result.selected_urls or not information:
        if pdf_count:
            print(
                "Huatai Futures report smoke test failed: the official listing "
                "currently exposes PDF attachments but no usable HTML detail links; "
                "PDF parsing is intentionally disabled."
            )
        else:
            print("Huatai Futures report smoke test failed: no usable HTML detail was found.")
        return 1
    item = information[0]
    print("Huatai Futures report smoke test succeeded.")
    print(f"Discovered Link Count: {result.discovered_link_count}")
    print(f"Selected Detail URL: {result.selected_urls[0]}")
    print(f"Title: {item.title}")
    print(f"Published Time: {item.published_time.isoformat()}")
    print(f"Report Type: {item.metadata.get('report_type', 'unavailable')}")
    print(f"Author: {item.metadata.get('author', 'unavailable')}")
    print(f"Content Character Count: {len(item.content)}")
    print(f"Content Preview: {item.content[:240]}")
    return 0


def _htfc_error_message(error: Exception) -> str:
    """Add a safe direct-proxy retry hint only for tunnel failures."""
    message = str(error)
    lowered = message.lower()
    tunnel_failure = "tunnel" in lowered and (
        "502" in lowered or "bad gateway" in lowered
    )
    if tunnel_failure or ("proxy" in lowered and "502" in lowered):
        return (
            f"{message}; if the proxy tunnel is unavailable, retry with "
            "NO_PROXY=htfc.com,www.htfc.com "
            "no_proxy=htfc.com,www.htfc.com"
        )
    return message


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


def _run_llm_routing_smoke_test(
    analyst: LLMAnalyst | None = None,
    sample_path: Path = SMOKE_TEST_REPORT_PATH,
) -> int:
    """Run one strict real-API check through the production LLM routing chain."""
    try:
        information = _load_routing_smoke_test_information(sample_path)
        model = _configured_llm_model()
    except (OSError, ValueError, FileNotFoundError, RuntimeError) as error:
        print(f"LLM routing smoke test failed: unable to prepare input: {error}")
        return 1

    if analyst is None:
        client, error = _openai_client_for_smoke_test()
        if client is None:
            print(f"LLM routing smoke test failed: {error}")
            return 1
        analyst = LLMAnalyst(
            model=model,
            max_items_per_run=1,
            client=client,
            usage_tracker=_configured_llm_usage_tracker(),
            usage_purpose="smoke_test",
        )

    ranked_information = InformationRanker().rank([information])
    selection = LLMCandidateSelector(
        enabled=True,
        source_types=("research_report",),
        min_reliability_score=4,
        max_items_per_run=1,
    ).select(ranked_information)
    if selection.eligible_count != 1 or len(selection.selected_items) != 1:
        print("LLM routing smoke test failed: no candidates were selected.")
        return 1

    router = AnalystRouter(
        llm_analyst=analyst,
        llm_candidates=selection.selected_items,
        max_llm_items=1,
    )
    selected_analyst = router.select_analyst(ranked_information[0])
    analyses = router.analyze(ranked_information)
    usage_record = analyst.last_usage_record
    if (
        selected_analyst is not analyst
        or len(analyses) != 1
        or analyses[0].market_information is not information
        or usage_record is None
        or not analyst.last_usage_record_persisted
        or not usage_record.success
        or not usage_record.response_id
    ):
        print(
            "LLM routing smoke test failed: the real LLM request did not return "
            "a valid structured response."
        )
        return 1

    analysis = analyses[0]
    print("Real LLM routing smoke test succeeded: structured response received from OpenAI.")
    print(f"Model: {model}")
    print(f"Eligible Candidate Count: {selection.eligible_count}")
    print(f"Selected Candidate Count: {len(selection.selected_items)}")
    print(f"Selected Source Title: {information.title}")
    print(f"Analyst Implementation: {type(selected_analyst).__name__}")
    print(f"Summary: {analysis.summary}")
    print(f"Market Direction: {analysis.market_direction.title()}")
    print(f"Confidence Score: {analysis.confidence_score}")
    print("Reasoning Details:")
    for detail in analysis.reasoning_details:
        print(f"- {detail}")
    _print_llm_usage(usage_record, analyst.usage_file_path)
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


def _load_routing_smoke_test_information(
    sample_path: Path = SMOKE_TEST_REPORT_PATH,
) -> MarketInformation:
    """Load the fixed report as an eligible high-reliability routing candidate."""
    content = sample_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    title = next((line.strip() for line in lines if line.strip()), "")
    if not title:
        raise ValueError("research report does not contain a title")
    return MarketInformation(
        title=title,
        source="Local research report routing smoke test",
        source_type="research_report",
        published_time=datetime.now(timezone.utc),
        content=content,
        category=("energy",),
        commodities=("crude_oil",),
        regions=("global",),
        reliability_score=5,
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
