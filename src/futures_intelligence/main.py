"""Application entry point for the Futures Intelligence Assistant."""

from __future__ import annotations

import argparse

from futures_intelligence.models import MarketAnalysis, MarketInformation
from futures_intelligence.services import MorningBriefService
from futures_intelligence.utils.health import HealthReport


def main(argv: list[str] | None = None) -> None:
    """Parse a command and run its CLI presentation handler."""
    arguments = _parse_arguments(argv)
    if arguments.command in (None, "morning-brief"):
        _run_morning_brief()


def _parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    """Parse the current CLI command while leaving room for future commands."""
    parser = argparse.ArgumentParser(
        description="Futures Intelligence Assistant commands."
    )
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("morning-brief", help="Generate the morning brief.")
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
    main()
