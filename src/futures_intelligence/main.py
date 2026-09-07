"""Application entry point for the Futures Intelligence Assistant."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from futures_intelligence.analyst import (
    AnalystRouter,
    LLMCandidateSelector,
    LLMAnalyst,
)
from futures_intelligence.analyst.commodity_matcher import CommodityMatch, CommodityMatcher
from futures_intelligence.analyst.commodity_relevance import (
    CommodityRelevance,
    CommodityRelevanceAssessment,
    CommodityRelevanceResolver,
)
from futures_intelligence.analyst.llm import _openai_client_for_smoke_test
from futures_intelligence.collectors.research_report import ResearchReportCollector
from futures_intelligence.collectors.factory import CollectorFactory
from futures_intelligence.config.loader import CONFIGURATION_FILES, load_yaml_file
from futures_intelligence.fetchers import (
    HuataiFuturesReportFetcher,
    HuataiPdfAttachment,
    HuataiPdfDownloadLimits,
    HuataiPdfParseLimits,
    HuataiPdfTextExtractor,
    HuataiReportListingItem,
)
from futures_intelligence.fetchers.huatai_futures import HuataiListingStructureError
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
HTFC_PDF_COLLECTOR_MODE = "huatai_pdf_listing"
HTFC_PDF_ANALYSIS_EVALUATION_LIMIT = 3


class _HuataiSmokeTestFailure(RuntimeError):
    """A bounded failure deliberately detected by a Huatai smoke command."""


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
    if arguments.command == "htfc-pdf-smoke-test":
        return _run_htfc_pdf_smoke_test()
    if arguments.command == "htfc-pdf-collector-smoke-test":
        return _run_htfc_pdf_collector_smoke_test()
    if arguments.command == "htfc-pdf-analysis-smoke-test":
        return _run_htfc_pdf_analysis_smoke_test()
    if arguments.command == "htfc-pdf-analysis-eval":
        return _run_htfc_pdf_analysis_evaluation()
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
    commands.add_parser(
        "htfc-pdf-smoke-test",
        help="Extract text from one official Huatai Futures PDF attachment.",
    )
    commands.add_parser(
        "htfc-pdf-collector-smoke-test",
        help="Run one isolated Huatai Futures PDF collector integration smoke test.",
    )
    commands.add_parser(
        "htfc-pdf-analysis-smoke-test",
        help="Run one isolated Huatai Futures PDF analysis integration smoke test.",
    )
    commands.add_parser(
        "htfc-pdf-analysis-eval",
        help="Evaluate up to three Huatai Futures PDF reports with deterministic analysis.",
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
    print(f"Discovered report HTML detail links: {html_count}")
    print(f"Discovered report PDF attachments: {pdf_count}")
    print(f"Ignored non-report links: {unsupported_count}")
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


def _run_htfc_pdf_smoke_test(
    listing_fetcher: HuataiFuturesReportFetcher | None = None,
    extractor: HuataiPdfTextExtractor | None = None,
) -> int:
    """Run one bounded, non-persistent text-layer PDF extraction smoke test."""
    listing_fetcher = listing_fetcher or HuataiFuturesReportFetcher(
        HTFC_LISTING_URL, max_reports=1
    )
    try:
        listing = listing_fetcher.fetch_reports()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Huatai Futures PDF smoke test failed: {_htfc_error_message(error)}")
        return 1
    discovery = listing.discovery
    html_count = len(discovery.html_detail_links) if discovery is not None else 0
    pdf_items = (
        tuple(item for item in discovery.report_items if item.link_kind == "pdf_attachment")
        if discovery is not None
        else ()
    )
    ignored_count = len(discovery.ignored_non_report_links) if discovery is not None else 0
    print(f"Discovered report HTML detail links: {html_count}")
    print(f"Discovered report PDF attachments: {len(pdf_items)}")
    print(f"Ignored non-report links: {ignored_count}")
    if not pdf_items:
        print("Huatai Futures PDF smoke test failed: no official PDF attachments were found.")
        return 1
    listing_entry = _newest_report_pdf(pdf_items)
    attachment = HuataiPdfAttachment(
        listing_entry.canonical_url,
        listing_entry.listing_title,
        listing_entry.publication_date,
        listing_entry.report_type,
    )
    try:
        extractor = extractor or _configured_htfc_pdf_extractor()
    except (FileNotFoundError, RuntimeError, ValueError, TypeError) as error:
        print(f"Huatai Futures PDF smoke test failed: invalid PDF configuration: {error}")
        return 1
    result = extractor.extract(attachment)
    if result.extraction_status != "success":
        print(
            "Huatai Futures PDF smoke test failed: "
            f"{result.failure_category or 'extraction_failed'}"
        )
        if result.proxy_tunnel_failure:
            print(
                "If the proxy tunnel is unavailable, retry with "
                "NO_PROXY=htfc.com,www.htfc.com "
                "no_proxy=htfc.com,www.htfc.com"
            )
        return 1
    print("Huatai Futures PDF smoke test succeeded: text layer extracted.")
    print(f"Selected Canonical PDF URL: {result.canonical_pdf_url}")
    print(f"Downloaded Byte Count: {result.byte_count}")
    print(f"Page Count: {result.page_count}")
    print(f"Title: {result.title or 'unavailable'}")
    print(f"Publication Date: {result.publication_date or 'unavailable'}")
    print(f"Report Type: {result.report_type or 'unavailable'}")
    print(f"Report Author: {result.report_author or 'unavailable'}")
    print(
        "Document Metadata Author: "
        f"{result.document_metadata_author or 'unavailable'}"
    )
    print(
        "Parser Diagnostics: "
        f"{', '.join(result.parser_diagnostics) or 'none'}"
    )
    print(f"Extracted Character Count: {result.extracted_character_count}")
    print(f"Extraction Status: {result.extraction_status}")
    print(f"Content Preview: {result.extracted_text[:240]}")
    return 0


def _run_htfc_pdf_collector_smoke_test() -> int:
    """Run the disabled Huatai PDF collector once with in-memory overrides only."""
    try:
        item = _collect_one_htfc_pdf_market_information()
    except OSError as error:
        print(
            "Huatai Futures PDF collector smoke test failed: "
            f"{_htfc_error_message(error)}"
        )
        return 1
    except HuataiListingStructureError:
        print(
            "Huatai Futures PDF collector smoke test failed: "
            "Huatai Futures report listing structure was not recognized."
        )
        return 1
    except _HuataiSmokeTestFailure as error:
        print(f"Huatai Futures PDF collector smoke test failed: {error}")
        return 1

    _print_htfc_pdf_collector_smoke_result(item)
    return 0


def _run_htfc_pdf_analysis_smoke_test() -> int:
    """Replay one Huatai PDF item through ranking and deterministic analysis only."""
    try:
        item = _collect_one_htfc_pdf_market_information()
    except OSError as error:
        print(
            "Huatai Futures PDF analysis smoke test failed: "
            f"{_htfc_error_message(error)}"
        )
        return 1
    except HuataiListingStructureError:
        print(
            "Huatai Futures PDF analysis smoke test failed: "
            "Huatai Futures report listing structure was not recognized."
        )
        return 1
    except _HuataiSmokeTestFailure as error:
        print(f"Huatai Futures PDF analysis smoke test failed: {error}")
        return 1

    try:
        analysis = _analyze_one_htfc_pdf_market_information(item)
    except _HuataiSmokeTestFailure as error:
        print(f"Huatai Futures PDF analysis smoke test failed: {error}")
        return 1

    _print_htfc_pdf_analysis_smoke_result(item, analysis)
    return 0


def _run_htfc_pdf_analysis_evaluation() -> int:
    """Evaluate a fixed small Huatai PDF batch without production side effects."""
    try:
        collected_information = _collect_bounded_htfc_pdf_market_information(
            HTFC_PDF_ANALYSIS_EVALUATION_LIMIT
        )
    except OSError as error:
        print(
            "Huatai Futures PDF analysis evaluation failed: "
            f"{_htfc_error_message(error)}"
        )
        return 1
    except HuataiListingStructureError:
        print(
            "Huatai Futures PDF analysis evaluation failed: "
            "Huatai Futures report listing structure was not recognized."
        )
        return 1
    except _HuataiSmokeTestFailure as error:
        print(f"Huatai Futures PDF analysis evaluation failed: {error}")
        return 1

    try:
        (
            ranked_information,
            analyses,
            commodity_matches,
            commodity_relevance,
        ) = _evaluate_htfc_pdf_information(collected_information)
    except _HuataiSmokeTestFailure as error:
        print(f"Huatai Futures PDF analysis evaluation failed: {error}")
        return 1

    _print_htfc_pdf_analysis_evaluation(
        collected_information,
        ranked_information,
        analyses,
        commodity_matches,
        commodity_relevance,
    )
    return 0


def _collect_one_htfc_pdf_market_information() -> MarketInformation:
    """Collect exactly one normalized Huatai PDF item using detached configuration."""
    information = _collect_bounded_htfc_pdf_market_information(1)
    if not information:
        raise _HuataiSmokeTestFailure("no MarketInformation item was produced.")
    if len(information) != 1:
        raise _HuataiSmokeTestFailure(
            f"expected exactly one MarketInformation item, received {len(information)}."
        )
    return information[0]


def _collect_bounded_htfc_pdf_market_information(
    max_selected_pdfs: int,
) -> list[MarketInformation]:
    """Collect a validated bounded Huatai PDF batch using detached configuration."""
    if (
        isinstance(max_selected_pdfs, bool)
        or not isinstance(max_selected_pdfs, int)
        or max_selected_pdfs < 1
    ):
        raise _HuataiSmokeTestFailure("Huatai PDF collection limit must be positive.")
    try:
        source_registry = load_yaml_file(CONFIGURATION_FILES["sources"])
    except FileNotFoundError as error:
        raise _HuataiSmokeTestFailure("source registry could not be loaded.") from error
    source = _find_htfc_pdf_collector_source(source_registry)
    smoke_source = _htfc_pdf_collector_smoke_source(source, max_selected_pdfs)
    collector = CollectorFactory.create(smoke_source)
    if collector is None:
        raise _HuataiSmokeTestFailure("factory did not create a collector.")

    information = collector.collect()
    if not isinstance(information, list):
        raise _HuataiSmokeTestFailure("collector did not return a list of MarketInformation.")
    if not all(isinstance(item, MarketInformation) for item in information):
        raise _HuataiSmokeTestFailure(
            "collector did not return a MarketInformation item."
        )
    return information


def _evaluate_htfc_pdf_information(
    collected_information: list[MarketInformation],
) -> tuple[
    list[MarketInformation],
    list[MarketAnalysis],
    tuple[tuple[CommodityMatch, ...], ...],
    tuple[CommodityRelevanceAssessment, ...],
]:
    """Rank, analyze, and label a non-empty bounded batch without side effects."""
    if not collected_information:
        raise _HuataiSmokeTestFailure("no MarketInformation items were produced.")
    if len(collected_information) > HTFC_PDF_ANALYSIS_EVALUATION_LIMIT:
        raise _HuataiSmokeTestFailure(
            "collector returned more MarketInformation items than the evaluation limit."
        )
    if len({id(item) for item in collected_information}) != len(collected_information):
        raise _HuataiSmokeTestFailure(
            "collector returned duplicate MarketInformation object identities."
        )

    ranked_information = InformationRanker().rank(collected_information)
    _validate_ranked_htfc_information(collected_information, ranked_information)

    analyses = AnalystRouter().analyze(ranked_information)
    _validate_htfc_analyses(ranked_information, analyses)
    _validate_htfc_direction_counts(analyses)

    resolver = CommodityRelevanceResolver()
    commodity_relevance = tuple(
        _validated_htfc_commodity_relevance(resolver.assess(item))
        for item in ranked_information
    )
    commodity_matches = tuple(
        assessment.lexical_matches for assessment in commodity_relevance
    )
    return ranked_information, analyses, commodity_matches, commodity_relevance


def _validate_ranked_htfc_information(
    collected_information: list[MarketInformation],
    ranked_information: object,
) -> None:
    """Require ranker output to contain each collected object exactly once."""
    if not isinstance(ranked_information, list):
        raise _HuataiSmokeTestFailure(
            "ranker did not return a list of MarketInformation items."
        )
    if len(ranked_information) != len(collected_information):
        raise _HuataiSmokeTestFailure(
            "ranker did not return the same number of MarketInformation items."
        )
    if not all(isinstance(item, MarketInformation) for item in ranked_information):
        raise _HuataiSmokeTestFailure(
            "ranker did not return MarketInformation items."
        )
    if Counter(map(id, ranked_information)) != Counter(map(id, collected_information)):
        raise _HuataiSmokeTestFailure(
            "ranker did not preserve the collected MarketInformation identities."
        )


def _validate_htfc_analyses(
    ranked_information: list[MarketInformation],
    analyses: object,
) -> None:
    """Require one valid provenance-preserving analysis per ranked item."""
    if not isinstance(analyses, list):
        raise _HuataiSmokeTestFailure(
            "router did not return a list of MarketAnalysis items."
        )
    if len(analyses) != len(ranked_information):
        raise _HuataiSmokeTestFailure(
            "router did not return the same number of MarketAnalysis items."
        )
    for ranked_item, analysis in zip(ranked_information, analyses):
        if not isinstance(analysis, MarketAnalysis):
            raise _HuataiSmokeTestFailure("router did not return a MarketAnalysis item.")
        if analysis.market_information is not ranked_item:
            raise _HuataiSmokeTestFailure(
                "analysis did not preserve ranked MarketInformation provenance."
            )
        try:
            canonical = MarketAnalysis(
                analysis.market_information,
                analysis.summary,
                analysis.market_direction,
                analysis.confidence_score,
                analysis.reasoning_details,
                analysis.directional_provenance,
                analysis.commodity_directional_evidence,
            )
        except (TypeError, ValueError) as error:
            raise _HuataiSmokeTestFailure(
                "router returned an invalid MarketAnalysis item."
            ) from error
        if (
            canonical.market_information is not ranked_item
            or analysis.summary != canonical.summary
            or analysis.market_direction != canonical.market_direction
            or analysis.confidence_score != canonical.confidence_score
            or analysis.reasoning_details != canonical.reasoning_details
            or analysis.directional_provenance
            != canonical.directional_provenance
            or analysis.commodity_directional_evidence
            != canonical.commodity_directional_evidence
        ):
            raise _HuataiSmokeTestFailure(
                "router returned a non-canonical MarketAnalysis item."
            )


def _validate_htfc_direction_counts(analyses: list[MarketAnalysis]) -> None:
    """Require every accepted analysis to contribute to exactly one direction count."""
    counted_analyses = sum(
        analysis.market_direction in {"bullish", "bearish", "neutral"}
        for analysis in analyses
    )
    if counted_analyses != len(analyses):
        raise _HuataiSmokeTestFailure(
            "analysis directions did not match the aggregate direction counts."
        )


def _validated_htfc_commodity_matches(
    matches: object,
) -> tuple[CommodityMatch, ...]:
    """Require the public immutable matcher result contract for diagnostics."""
    if type(matches) is not tuple or not all(
        isinstance(match, CommodityMatch) for match in matches
    ):
        raise _HuataiSmokeTestFailure(
            "matcher did not return a tuple of CommodityMatch values."
        )
    return matches


def _validated_htfc_commodity_relevance(
    assessment: object,
) -> CommodityRelevanceAssessment:
    """Require public immutable relevance values for bounded diagnostics."""
    if type(assessment) is not CommodityRelevanceAssessment:
        raise _HuataiSmokeTestFailure(
            "relevance resolver did not return a CommodityRelevanceAssessment."
        )
    if (
        type(assessment.lexical_matches) is not tuple
        or type(assessment.primary) is not tuple
        or type(assessment.mentioned) is not tuple
        or not all(isinstance(match, CommodityMatch) for match in assessment.lexical_matches)
        or not all(
            isinstance(relevance, CommodityRelevance)
            for relevance in assessment.primary + assessment.mentioned
        )
    ):
        raise _HuataiSmokeTestFailure(
            "relevance resolver returned invalid CommodityRelevanceAssessment values."
        )
    return assessment


def _analyze_one_htfc_pdf_market_information(item: MarketInformation) -> MarketAnalysis:
    """Rank and deterministically analyze one unchanged normalized item."""
    ranked_information = InformationRanker().rank([item])
    if not isinstance(ranked_information, list):
        raise _HuataiSmokeTestFailure(
            "ranker did not return a list of MarketInformation items."
        )
    if len(ranked_information) != 1:
        raise _HuataiSmokeTestFailure(
            "expected exactly one ranked MarketInformation item, "
            f"received {len(ranked_information)}"
        )
    ranked_item = ranked_information[0]
    if ranked_item is not item:
        raise _HuataiSmokeTestFailure(
            "ranker did not preserve the original MarketInformation item."
        )

    analyses = AnalystRouter().analyze([ranked_item])
    if not isinstance(analyses, list):
        raise _HuataiSmokeTestFailure(
            "router did not return a list of MarketAnalysis items."
        )
    if len(analyses) != 1:
        raise _HuataiSmokeTestFailure(
            f"expected exactly one MarketAnalysis item, received {len(analyses)}"
        )
    analysis = analyses[0]
    if not isinstance(analysis, MarketAnalysis):
        raise _HuataiSmokeTestFailure("router did not return a MarketAnalysis item.")
    if analysis.market_information is not item:
        raise _HuataiSmokeTestFailure(
            "analysis did not preserve the original MarketInformation item."
        )
    try:
        MarketAnalysis(
            analysis.market_information,
            analysis.summary,
            analysis.market_direction,
            analysis.confidence_score,
            analysis.reasoning_details,
            analysis.directional_provenance,
            analysis.commodity_directional_evidence,
        )
    except (TypeError, ValueError) as error:
        raise _HuataiSmokeTestFailure(
            "router returned an invalid MarketAnalysis item."
        ) from error
    return analysis


def _print_htfc_pdf_analysis_smoke_result(
    item: MarketInformation,
    analysis: MarketAnalysis,
) -> None:
    """Print bounded deterministic analysis without exposing report content."""
    print("Huatai Futures PDF analysis smoke test succeeded.")
    print("Collected MarketInformation Count: 1")
    print(f"Title: {item.title}")
    print(f"Source: {item.source}")
    print(f"Published Time: {item.published_time.isoformat()}")
    print(f"Canonical PDF URL: {item.url or 'unavailable'}")
    print(f"Source Commodities: {_smoke_text_tuple(item.commodities)}")
    print(f"Analysis Summary: {_truncate_smoke_text(analysis.summary, 500)}")
    print(f"Market Direction: {analysis.market_direction}")
    print(f"Confidence Score: {analysis.confidence_score}")
    print(f"Reasoning Detail Count: {len(analysis.reasoning_details)}")
    print("Reasoning Details:")
    if not analysis.reasoning_details:
        print("- none")
        return
    for detail in analysis.reasoning_details[:5]:
        print(f"- {_truncate_smoke_text(detail, 240)}")


def _print_htfc_pdf_analysis_evaluation(
    collected_information: list[MarketInformation],
    ranked_information: list[MarketInformation],
    analyses: list[MarketAnalysis],
    commodity_matches: tuple[tuple[CommodityMatch, ...], ...],
    commodity_relevance: tuple[CommodityRelevanceAssessment, ...],
) -> None:
    """Print a bounded diagnostic summary without exposing report content."""
    print("Huatai Futures PDF deterministic analysis evaluation succeeded.")
    print(f"Requested PDF Limit: {HTFC_PDF_ANALYSIS_EVALUATION_LIMIT}")
    print(f"Collected MarketInformation Count: {len(collected_information)}")
    print(f"Analyzed MarketAnalysis Count: {len(analyses)}")
    for direction in ("bullish", "bearish", "neutral"):
        print(
            f"{direction.capitalize()} Count: "
            f"{sum(analysis.market_direction == direction for analysis in analyses)}"
        )

    collection_indexes = {
        id(item): index for index, item in enumerate(collected_information, start=1)
    }
    for ranked_index, (item, analysis, matches, relevance) in enumerate(
        zip(ranked_information, analyses, commodity_matches, commodity_relevance),
        start=1,
    ):
        print()
        print(f"Report Index: {ranked_index}")
        print(f"Collection Index: {collection_indexes[id(item)]}")
        print(f"Ranked Index: {ranked_index}")
        print(f"Title: {_truncate_smoke_text(item.title, 500)}")
        print(f"Published Time: {item.published_time.isoformat()}")
        print(f"Canonical PDF URL: {item.url or 'unavailable'}")
        print(f"Source Commodities: {_smoke_text_tuple(item.commodities)}")
        print(
            "Detected Commodity Matches: "
            f"{_smoke_text_tuple(_commodity_match_labels(matches))}"
        )
        print(
            "Primary Commodity Candidates: "
            f"{_smoke_text_tuple(_commodity_relevance_labels(relevance.primary))}"
        )
        print(
            "Mentioned Commodity Matches: "
            f"{_smoke_text_tuple(_commodity_relevance_labels(relevance.mentioned))}"
        )
        print(f"Analysis Summary: {_truncate_smoke_text(analysis.summary, 500)}")
        print(f"Market Direction: {analysis.market_direction}")
        print(f"Confidence Score: {analysis.confidence_score}")
        print(f"Reasoning Detail Count: {len(analysis.reasoning_details)}")
        print("Reasoning Details:")
        if not analysis.reasoning_details:
            print("- none")
            continue
        for detail in analysis.reasoning_details[:3]:
            print(f"- {_truncate_smoke_text(detail, 240)}")


def _commodity_match_labels(matches: tuple[CommodityMatch, ...]) -> tuple[str, ...]:
    """Return only public matcher labels for bounded diagnostic output."""
    return tuple(match.commodity_label for match in matches)


def _commodity_relevance_labels(
    relevance: tuple[CommodityRelevance, ...],
) -> tuple[str, ...]:
    """Return bounded display labels from validated relevance values."""
    return tuple(item.commodity_label for item in relevance)


def _truncate_smoke_text(value: str, maximum_characters: int) -> str:
    """Return deterministic bounded terminal text with an explicit truncation marker."""
    if len(value) <= maximum_characters:
        return value
    return f"{value[: maximum_characters - 3]}..."


def _find_htfc_pdf_collector_source(
    source_registry: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the one source using the explicit Huatai PDF collector route."""
    matching_sources = [
        source
        for source in _source_configuration_entries(source_registry)
        if source.get("source_type") == "research_report"
        and source.get("provider") == "huatai_futures"
        and source.get("collection_mode") == HTFC_PDF_COLLECTOR_MODE
    ]
    if not matching_sources:
        raise _HuataiSmokeTestFailure(
            "no matching Huatai Futures PDF collector source was found."
        )
    if len(matching_sources) != 1:
        raise _HuataiSmokeTestFailure(
            "ambiguous Huatai Futures PDF collector source configuration."
        )
    return matching_sources[0]


def _source_configuration_entries(value: object) -> tuple[dict[str, Any], ...]:
    """Return all source-shaped mappings from the loaded source registry."""
    if isinstance(value, list):
        return tuple(
            entry
            for item in value
            for entry in _source_configuration_entries(item)
        )
    if not isinstance(value, dict):
        return ()
    entries = (value,) if "source_type" in value else ()
    return entries + tuple(
        entry
        for item in value.values()
        for entry in _source_configuration_entries(item)
    )


def _htfc_pdf_collector_smoke_source(
    source: Mapping[str, Any],
    max_selected_pdfs: int = 1,
) -> dict[str, Any]:
    """Make the sole permitted detached in-memory collector smoke overrides."""
    smoke_source = deepcopy(dict(source))
    pdf_extraction = smoke_source.get("pdf_extraction")
    if not isinstance(pdf_extraction, dict):
        raise _HuataiSmokeTestFailure(
            "Huatai Futures PDF collector source requires pdf_extraction."
        )
    smoke_source["enabled"] = True
    pdf_extraction["max_selected_pdfs"] = max_selected_pdfs
    return smoke_source


def _print_htfc_pdf_collector_smoke_result(item: MarketInformation) -> None:
    """Print concise normalized report provenance without printing report content."""
    metadata = item.metadata
    diagnostics = metadata.get("parser_diagnostics")
    diagnostic_count = len(diagnostics) if isinstance(diagnostics, list) else 0
    print("Huatai Futures PDF collector smoke test succeeded.")
    print("Collected MarketInformation Count: 1")
    print(f"Title: {item.title}")
    print(f"Source: {item.source}")
    print(f"Source Type: {item.source_type}")
    print(f"Published Time: {item.published_time.isoformat()}")
    print(
        "Published Time Precision: "
        f"{_smoke_metadata_text(metadata, 'published_time_precision')}"
    )
    print(f"Canonical PDF URL: {item.url or 'unavailable'}")
    print(f"Category: {_smoke_text_tuple(item.category)}")
    print(f"Regions: {_smoke_text_tuple(item.regions)}")
    print(f"Reliability Score: {item.reliability_score}")
    print(f"Commodities: {_smoke_text_tuple(item.commodities)}")
    print(f"Report Type: {_smoke_metadata_text(metadata, 'report_type')}")
    print(f"Report Author: {_smoke_metadata_text(metadata, 'report_author')}")
    print(
        "Document Metadata Author: "
        f"{_smoke_metadata_text(metadata, 'document_metadata_author')}"
    )
    print(f"Page Count: {_smoke_metadata_value(metadata, 'page_count')}")
    print(f"Downloaded Byte Count: {_smoke_metadata_value(metadata, 'byte_count')}")
    print(
        "Extracted Character Count: "
        f"{_smoke_metadata_value(metadata, 'extracted_character_count')}"
    )
    print(f"Parser Diagnostic Count: {diagnostic_count}")


def _smoke_metadata_text(metadata: Mapping[str, Any], field_name: str) -> str:
    """Format optional textual provenance without exposing arbitrary metadata."""
    value = metadata.get(field_name)
    return value.strip() if isinstance(value, str) and value.strip() else "unavailable"


def _smoke_metadata_value(metadata: Mapping[str, Any], field_name: str) -> str:
    """Format optional scalar provenance without serializing metadata mappings."""
    value = metadata.get(field_name)
    return str(value) if isinstance(value, (int, float, str)) else "unavailable"


def _smoke_text_tuple(values: tuple[str, ...]) -> str:
    """Render an empty normalized source-scope tuple as a stable concise value."""
    return ", ".join(values) or "none"


def _newest_report_pdf(
    items: tuple[HuataiReportListingItem, ...],
) -> HuataiReportListingItem:
    """Select one report PDF by explicit date, then source listing position."""
    return min(
        items,
        key=lambda item: (
            item.publication_date is None,
            -item.publication_date.toordinal()
            if item.publication_date is not None
            else 0,
            item.section_position,
            item.item_position,
        ),
    )


def _configured_htfc_pdf_extractor() -> HuataiPdfTextExtractor:
    """Load only the disabled Huatai source's bounded PDF smoke-test limits."""
    source_registry = load_yaml_file(CONFIGURATION_FILES["sources"])
    sources = source_registry.get("sources", {})
    reports = sources.get("research_reports", {}) if isinstance(sources, dict) else {}
    companies = reports.get("futures_companies", []) if isinstance(reports, dict) else []
    huatai = next(
        (
            source
            for source in companies
            if isinstance(source, dict) and source.get("provider") == "huatai_futures"
        ),
        None,
    )
    settings = huatai.get("pdf_extraction", {}) if isinstance(huatai, dict) else {}
    if not isinstance(settings, dict):
        raise ValueError("Huatai PDF settings must be a mapping")
    return HuataiPdfTextExtractor(
        download_limits=HuataiPdfDownloadLimits(
            socket_timeout_seconds=float(settings.get("socket_timeout_seconds", 10)),
            download_deadline_seconds=float(settings.get("download_deadline_seconds", 30)),
            max_response_bytes=int(settings.get("max_response_bytes", 20 * 1024 * 1024)),
            max_redirects=int(settings.get("max_redirects", 3)),
            max_selected_pdfs=int(settings.get("max_selected_pdfs", 3)),
        ),
        parse_limits=HuataiPdfParseLimits(
            max_pages=int(settings.get("max_pages", 50)),
            max_content_stream_bytes_per_page=int(
                settings.get("max_content_stream_bytes_per_page", 8 * 1024 * 1024)
            ),
            max_content_stream_bytes=int(settings.get("max_content_stream_bytes", 64 * 1024 * 1024)),
            max_extracted_characters_per_page=int(
                settings.get("max_extracted_characters_per_page", 20_000)
            ),
            max_extracted_characters=int(settings.get("max_extracted_characters", 250_000)),
            parser_deadline_seconds=float(settings.get("parser_deadline_seconds", 20)),
            minimum_meaningful_characters=int(settings.get("minimum_meaningful_characters", 20)),
        ),
    )


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
