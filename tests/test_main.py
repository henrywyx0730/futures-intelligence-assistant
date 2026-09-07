"""Tests for command-line output in the application entry point."""

from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from futures_intelligence.analyst import LLMAnalyst, LLMSmokeTestResult
from futures_intelligence.analyst.commodity_matcher import CommodityMatch
from futures_intelligence.analyst.commodity_relevance import (
    CommodityRelevance,
    CommodityRelevanceAssessment,
    MENTIONED_REASON,
    PRIMARY_REASON,
)
from futures_intelligence.main import (
    SMOKE_TEST_REPORT_PATH,
    _collect_one_htfc_pdf_market_information,
    _load_smoke_test_information,
    _parse_arguments,
    _run_htfc_pdf_analysis_evaluation,
    _run_htfc_pdf_analysis_smoke_test,
    _run_llm_routing_smoke_test,
    _run_llm_smoke_test,
    _run_htfc_pdf_collector_smoke_test,
    _run_htfc_pdf_smoke_test,
    _run_htfc_report_smoke_test,
    main,
)
from futures_intelligence.fetchers import (
    FetchedResearchReport,
    HuataiFetchResult,
    HuataiListingDiscovery,
    HuataiPdfAttachment,
    HuataiPdfExtractionResult,
    HuataiReportListingItem,
)
from futures_intelligence.models import MarketAnalysis, MarketInformation
from futures_intelligence.utils.health import HealthReport
from futures_intelligence.utils.llm_usage import LLMUsageRecord, LLMUsageTracker, LLMPricing


class FakeResponses:
    """Record local Responses API calls without any network access."""

    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeClient:
    """Expose the minimal injected Responses API interface."""

    def __init__(self, result: object) -> None:
        self.responses = FakeResponses(result)


def relevance_assessment(
    matches: tuple[CommodityMatch, ...], primary_keys: tuple[str, ...] = ()
) -> CommodityRelevanceAssessment:
    """Build valid diagnostic relevance output with primary keys in lexical order."""
    primary = tuple(
        CommodityRelevance(
            match.commodity_key,
            match.commodity_label,
            "primary",
            (match.matched_aliases[0],),
            (),
            1,
            0,
            (PRIMARY_REASON,),
        )
        for match in matches
        if match.commodity_key in primary_keys
    )
    mentioned = tuple(
        CommodityRelevance(
            match.commodity_key,
            match.commodity_label,
            "mentioned",
            (),
            (match.matched_aliases[0],),
            0,
            1,
            (MENTIONED_REASON,),
        )
        for match in matches
        if match.commodity_key not in primary_keys
    )
    return CommodityRelevanceAssessment(matches, primary, mentioned)


def routing_response() -> SimpleNamespace:
    """Return a complete structured response with billable usage metadata."""
    return SimpleNamespace(
        id="resp_routing_test",
        model="gpt-5.6-luna",
        usage=SimpleNamespace(
            input_tokens=10,
            input_tokens_details=SimpleNamespace(
                cached_tokens=0,
                cache_write_tokens=0,
            ),
            output_tokens=5,
            output_tokens_details=SimpleNamespace(reasoning_tokens=0),
            total_tokens=15,
        ),
        output_text=(
            '{"summary":"Structured routing result.",'
            '"market_direction":"bullish",'
            '"confidence_score":81,'
            '"reasoning_details":["Mocked routing response."]}'
        ),
    )


class MainTests(unittest.TestCase):
    """Validate CLI presentation without running the pipeline."""

    @patch("futures_intelligence.main.MorningBriefService")
    def test_default_command_prints_previews_and_returned_brief(
        self, service_class: Mock
    ) -> None:
        information = MarketInformation(
            title="Gold market update",
            source="Test Source",
            source_type="test",
            published_time=datetime(2026, 7, 17, tzinfo=timezone.utc),
            content="Gold inventory data was released.",
            category=("metals",),
        )
        service = service_class.return_value
        service.information = [information]
        service.analyses = [
            MarketAnalysis(information, "Detected commodity focus: Gold.")
        ]
        service.run.return_value = "Morning Futures Brief\nTop analyses: 1 of 1"
        service.health_report = HealthReport(
            last_run_timestamp="2026-07-17T00:00:00+00:00",
            execution_status="success",
            collected_information_count=1,
            generated_analysis_count=1,
            brief_generation_status="success",
        )

        output = StringIO()
        with redirect_stdout(output):
            main([])

        service.run.assert_called_once_with()
        self.assertIn("Collected market information: 1", output.getvalue())
        self.assertIn("Market analyses: 1", output.getvalue())
        self.assertIn("Morning Futures Brief", output.getvalue())
        self.assertIn("Run status: success", output.getvalue())

    def test_parses_explicit_morning_brief_command(self) -> None:
        self.assertEqual(_parse_arguments(["morning-brief"]).command, "morning-brief")

    def test_parses_llm_smoke_test_and_help_lists_command(self) -> None:
        self.assertEqual(_parse_arguments(["llm-smoke-test"]).command, "llm-smoke-test")
        self.assertEqual(
            _parse_arguments(["llm-routing-smoke-test"]).command,
            "llm-routing-smoke-test",
        )
        self.assertEqual(
            _parse_arguments(["htfc-report-smoke-test"]).command,
            "htfc-report-smoke-test",
        )
        self.assertEqual(
            _parse_arguments(["htfc-pdf-smoke-test"]).command,
            "htfc-pdf-smoke-test",
        )
        self.assertEqual(
            _parse_arguments(["htfc-pdf-collector-smoke-test"]).command,
            "htfc-pdf-collector-smoke-test",
        )
        self.assertEqual(
            _parse_arguments(["htfc-pdf-analysis-smoke-test"]).command,
            "htfc-pdf-analysis-smoke-test",
        )
        self.assertEqual(
            _parse_arguments(["htfc-pdf-analysis-eval"]).command,
            "htfc-pdf-analysis-eval",
        )

        output = StringIO()
        with self.assertRaises(SystemExit), redirect_stdout(output):
            _parse_arguments(["--help"])
        self.assertIn("llm-smoke-test", output.getvalue())
        self.assertIn("llm-routing-smoke-test", output.getvalue())
        self.assertIn("htfc-report-smoke-test", output.getvalue())
        self.assertIn("htfc-pdf-smoke-test", output.getvalue())
        self.assertIn("htfc-pdf-collector-smoke-test", output.getvalue())
        self.assertIn("htfc-pdf-analysis-smoke-test", output.getvalue())
        self.assertIn("htfc-pdf-analysis-eval", output.getvalue())

    @patch(
        "futures_intelligence.main._run_htfc_pdf_collector_smoke_test",
        return_value=1,
    )
    def test_main_dispatches_huatai_pdf_collector_smoke_test_command(
        self, smoke_test: Mock
    ) -> None:
        self.assertEqual(main(["htfc-pdf-collector-smoke-test"]), 1)
        smoke_test.assert_called_once_with()

    @patch(
        "futures_intelligence.main._run_htfc_pdf_analysis_smoke_test",
        return_value=1,
    )
    def test_main_dispatches_huatai_pdf_analysis_smoke_test_command(
        self, smoke_test: Mock
    ) -> None:
        self.assertEqual(main(["htfc-pdf-analysis-smoke-test"]), 1)
        smoke_test.assert_called_once_with()

    @patch(
        "futures_intelligence.main._run_htfc_pdf_analysis_evaluation",
        return_value=1,
    )
    def test_main_dispatches_huatai_pdf_analysis_evaluation_command(
        self, evaluation: Mock
    ) -> None:
        self.assertEqual(main(["htfc-pdf-analysis-eval"]), 1)
        evaluation.assert_called_once_with()

    def test_huatai_pdf_collector_smoke_test_uses_shared_one_item_collection_helper(
        self,
    ) -> None:
        item = _huatai_pdf_market_information()
        output = StringIO()

        with (
            patch(
                "futures_intelligence.main._collect_one_htfc_pdf_market_information",
                return_value=item,
            ) as collect_one,
            redirect_stdout(output),
        ):
            exit_code = _run_htfc_pdf_collector_smoke_test()

        self.assertEqual(exit_code, 0)
        collect_one.assert_called_once_with()
        self.assertIn("Huatai Futures PDF collector smoke test succeeded.", output.getvalue())
        self.assertIn("Title: Huatai PDF report", output.getvalue())

    def test_one_item_huatai_collection_wrapper_uses_the_bounded_helper_limit_one(
        self,
    ) -> None:
        item = _huatai_pdf_market_information()

        with patch(
            "futures_intelligence.main._collect_bounded_htfc_pdf_market_information",
            return_value=[item],
        ) as collect_bounded:
            result = _collect_one_htfc_pdf_market_information()

        self.assertIs(result, item)
        collect_bounded.assert_called_once_with(1)

    def test_huatai_pdf_analysis_smoke_test_runs_ranker_and_default_router_for_valid_neutral_analysis(
        self,
    ) -> None:
        item = _huatai_pdf_market_information()
        analysis = MarketAnalysis(
            item,
            "No tracked commodity keywords detected.",
            market_direction="neutral",
            confidence_score=0,
            reasoning_details=(),
        )
        ranker = Mock()
        ranker.rank.return_value = [item]
        router = Mock()
        router.analyze.return_value = [analysis]
        output = StringIO()

        with (
            patch(
                "futures_intelligence.main._collect_one_htfc_pdf_market_information",
                return_value=item,
            ) as collect_one,
            patch("futures_intelligence.main.InformationRanker", return_value=ranker) as ranker_class,
            patch("futures_intelligence.main.AnalystRouter", return_value=router) as router_class,
            patch(
                "futures_intelligence.main.LLMAnalyst",
                side_effect=AssertionError("analysis smoke path must not construct an LLM"),
            ),
            redirect_stdout(output),
        ):
            exit_code = _run_htfc_pdf_analysis_smoke_test()

        self.assertEqual(exit_code, 0)
        collect_one.assert_called_once_with()
        ranker_class.assert_called_once_with()
        ranker.rank.assert_called_once_with([item])
        router_class.assert_called_once_with()
        router.analyze.assert_called_once_with([item])
        rendered = output.getvalue()
        self.assertIn("Huatai Futures PDF analysis smoke test succeeded.", rendered)
        self.assertIn("Source Commodities: none", rendered)
        self.assertIn("Analysis Summary: No tracked commodity keywords detected.", rendered)
        self.assertIn("Market Direction: neutral", rendered)
        self.assertIn("Confidence Score: 0", rendered)
        self.assertIn("Reasoning Detail Count: 0", rendered)
        self.assertIn("- none", rendered)
        self.assertNotIn(item.content, rendered)
        self.assertNotIn("FULL_DOCUMENT_METADATA_SECRET_MARKER_7E91", rendered)

    def test_huatai_pdf_analysis_smoke_test_rejects_invalid_ranker_or_router_results(
        self,
    ) -> None:
        item = _huatai_pdf_market_information()
        replacement = _huatai_pdf_market_information()
        valid_analysis = MarketAnalysis(item, "Valid summary.")
        invalid_model_analysis = MarketAnalysis(item, "Invalid model state.")
        invalid_model_analysis.confidence_score = 101
        invalid_cases = (
            ([], [valid_analysis], "expected exactly one ranked"),
            ([item, item], [valid_analysis], "expected exactly one ranked"),
            ([replacement], [valid_analysis], "did not preserve"),
            ([item], [], "expected exactly one marketanalysis"),
            ([item], [valid_analysis, valid_analysis], "expected exactly one marketanalysis"),
            ([item], [MarketAnalysis(replacement, "Other source.")], "did not preserve"),
            ([item], [object()], "router did not return"),
            ([item], [invalid_model_analysis], "invalid marketanalysis"),
        )

        for ranked, analyses, expected in invalid_cases:
            with self.subTest(expected=expected):
                ranker = Mock()
                ranker.rank.return_value = ranked
                router = Mock()
                router.analyze.return_value = analyses
                output = StringIO()
                with (
                    patch(
                        "futures_intelligence.main._collect_one_htfc_pdf_market_information",
                        return_value=item,
                    ),
                    patch("futures_intelligence.main.InformationRanker", return_value=ranker),
                    patch("futures_intelligence.main.AnalystRouter", return_value=router),
                    redirect_stdout(output),
                ):
                    exit_code = _run_htfc_pdf_analysis_smoke_test()

                self.assertEqual(exit_code, 1)
                self.assertIn(expected, output.getvalue().lower())

    def test_huatai_pdf_analysis_smoke_test_bounds_output_and_preserves_unexpected_errors(
        self,
    ) -> None:
        item = _huatai_pdf_market_information()
        long_summary = "S" * 600
        long_reasoning = tuple(f"R{index}-" + "x" * 300 for index in range(7))
        analysis = MarketAnalysis(
            item,
            long_summary,
            market_direction="bullish",
            confidence_score=88,
            reasoning_details=long_reasoning,
        )
        ranker = Mock()
        ranker.rank.return_value = [item]
        router = Mock()
        router.analyze.return_value = [analysis]
        output = StringIO()

        with (
            patch(
                "futures_intelligence.main._collect_one_htfc_pdf_market_information",
                return_value=item,
            ),
            patch("futures_intelligence.main.InformationRanker", return_value=ranker),
            patch("futures_intelligence.main.AnalystRouter", return_value=router),
            redirect_stdout(output),
        ):
            exit_code = _run_htfc_pdf_analysis_smoke_test()

        self.assertEqual(exit_code, 0)
        rendered = output.getvalue()
        summary_line = next(line for line in rendered.splitlines() if line.startswith("Analysis Summary: "))
        self.assertLessEqual(len(summary_line.removeprefix("Analysis Summary: ")), 500)
        reasoning_lines = [line for line in rendered.splitlines() if line.startswith("- R")]
        self.assertEqual(len(reasoning_lines), 5)
        self.assertTrue(all(len(line.removeprefix("- ")) <= 240 for line in reasoning_lines))
        self.assertIn("Reasoning Detail Count: 7", rendered)
        self.assertIn("Market Direction: bullish", rendered)
        self.assertIn("Confidence Score: 88", rendered)

        with patch(
            "futures_intelligence.main._collect_one_htfc_pdf_market_information",
            side_effect=KeyError("unexpected analysis collection failure"),
        ):
            with self.assertRaises(KeyError) as raised:
                _run_htfc_pdf_analysis_smoke_test()

        self.assertEqual(raised.exception.args, ("unexpected analysis collection failure",))

    def test_huatai_pdf_analysis_evaluation_runs_bounded_ranked_deterministic_batch(
        self,
    ) -> None:
        source = _huatai_pdf_source()
        source["evaluation_secret"] = "EVALUATION_CONFIGURATION_SECRET_MARKER"
        registry = {
            "sources": {"research_reports": {"futures_companies": [source]}}
        }
        first = _huatai_pdf_market_information()
        first.title = "First report"
        second = _huatai_pdf_market_information()
        second.title = "Second report"
        third = _huatai_pdf_market_information()
        third.title = "T" * 600
        items = [first, second, third]
        ranked = [third, first, second]
        analyses = [
            MarketAnalysis(
                third,
                "S" * 600,
                market_direction="bullish",
                confidence_score=91,
                reasoning_details=tuple(f"R{index}-" + "x" * 300 for index in range(4)),
            ),
            MarketAnalysis(
                first,
                "Bearish report.",
                market_direction="bearish",
                confidence_score=60,
                reasoning_details=("R-first.",),
            ),
            MarketAnalysis(
                second,
                "Neutral report.",
                market_direction="neutral",
                confidence_score=0,
                reasoning_details=(),
            ),
        ]
        collector = Mock()
        collector.collect.return_value = items
        ranker = Mock()
        ranker.rank.return_value = ranked
        router = Mock()
        router.analyze.return_value = analyses
        resolver = Mock()
        resolver.assess.side_effect = [
            relevance_assessment(
                (
                    CommodityMatch("crude_oil", "Crude Oil", ("oil",)),
                    CommodityMatch(
                        "ethylene_glycol", "Ethylene Glycol", ("ethylene glycol",)
                    ),
                ),
                ("ethylene_glycol",),
            ),
            relevance_assessment((CommodityMatch("live_hog", "Live Hog", ("live hog",)),)),
            relevance_assessment(
                (
                    CommodityMatch("aluminum", "Aluminum", ("aluminum",)),
                    CommodityMatch(
                        "cast_aluminum_alloy", "Cast Aluminum Alloy", ("alloy",)
                    ),
                ),
                ("aluminum", "cast_aluminum_alloy"),
            ),
        ]
        output = StringIO()

        with (
            patch("futures_intelligence.main.load_yaml_file", return_value=registry),
            patch(
                "futures_intelligence.main.CollectorFactory.create",
                return_value=collector,
            ) as create,
            patch("futures_intelligence.main.InformationRanker", return_value=ranker),
            patch("futures_intelligence.main.AnalystRouter", return_value=router),
            patch(
                "futures_intelligence.main.CommodityRelevanceResolver",
                return_value=resolver,
            ),
            patch(
                "futures_intelligence.main.LLMAnalyst",
                side_effect=AssertionError("evaluation must not construct an LLM"),
            ),
            redirect_stdout(output),
        ):
            exit_code = _run_htfc_pdf_analysis_evaluation()

        self.assertEqual(exit_code, 0)
        create.assert_called_once()
        detached_source = create.call_args.args[0]
        self.assertTrue(detached_source["enabled"])
        self.assertEqual(detached_source["pdf_extraction"]["max_selected_pdfs"], 3)
        self.assertIsNot(detached_source["pdf_extraction"], source["pdf_extraction"])
        self.assertEqual(
            detached_source["pdf_extraction"]["socket_timeout_seconds"],
            source["pdf_extraction"]["socket_timeout_seconds"],
        )
        self.assertEqual(
            {
                key: value
                for key, value in detached_source["pdf_extraction"].items()
                if key != "max_selected_pdfs"
            },
            {
                key: value
                for key, value in source["pdf_extraction"].items()
                if key != "max_selected_pdfs"
            },
        )
        self.assertFalse(source["enabled"])
        self.assertEqual(source["pdf_extraction"]["max_selected_pdfs"], 3)
        collector.collect.assert_called_once_with()
        ranker.rank.assert_called_once_with(items)
        router.analyze.assert_called_once_with(ranked)
        self.assertEqual(resolver.assess.call_args_list, [((item,),) for item in ranked])
        self.assertEqual(first.commodities, ())

        rendered = output.getvalue()
        self.assertIn("Requested PDF Limit: 3", rendered)
        self.assertIn("Collected MarketInformation Count: 3", rendered)
        self.assertIn("Analyzed MarketAnalysis Count: 3", rendered)
        self.assertIn("Bullish Count: 1", rendered)
        self.assertIn("Bearish Count: 1", rendered)
        self.assertIn("Neutral Count: 1", rendered)
        report_sections = rendered.split("Report Index: ")[1:]
        self.assertEqual(len(report_sections), 3)
        expected_diagnostics = (
            (
                "Detected Commodity Matches: Crude Oil, Ethylene Glycol",
                "Primary Commodity Candidates: Ethylene Glycol",
                "Mentioned Commodity Matches: Crude Oil",
            ),
            (
                "Detected Commodity Matches: Live Hog",
                "Primary Commodity Candidates: none",
                "Mentioned Commodity Matches: Live Hog",
            ),
            (
                "Detected Commodity Matches: Aluminum, Cast Aluminum Alloy",
                "Primary Commodity Candidates: Aluminum, Cast Aluminum Alloy",
                "Mentioned Commodity Matches: none",
            ),
        )
        for section, expected_lines in zip(report_sections, expected_diagnostics):
            for expected_line in expected_lines:
                self.assertEqual(section.count(expected_line), 1)
        self.assertIn("Collection Index: 3", report_sections[0])
        summary_line = next(
            line for line in rendered.splitlines() if line.startswith("Analysis Summary: ")
        )
        self.assertLessEqual(len(summary_line.removeprefix("Analysis Summary: ")), 500)
        title_line = next(
            line for line in rendered.splitlines() if line.startswith("Title: ")
        )
        title_value = title_line.removeprefix("Title: ")
        self.assertLessEqual(len(title_value), 500)
        self.assertEqual(title_value, "T" * 497 + "...")
        reasoning_lines = [line for line in rendered.splitlines() if line.startswith("- R")]
        self.assertEqual(len(reasoning_lines), 4)
        self.assertTrue(all(len(line.removeprefix("- ")) <= 240 for line in reasoning_lines))
        self.assertIn("Reasoning Detail Count: 4", rendered)
        self.assertNotIn(first.content, rendered)
        self.assertNotIn("FULL_DOCUMENT_METADATA_SECRET_MARKER_7E91", rendered)
        self.assertNotIn("PARSER_DIAGNOSTIC_SECRET_MARKER_3B51", rendered)
        self.assertNotIn("EVALUATION_CONFIGURATION_SECRET_MARKER", rendered)

    def test_huatai_pdf_analysis_evaluation_accepts_partial_collection_and_rejects_invalid_counts(
        self,
    ) -> None:
        for count, expected_exit_code in ((0, 1), (1, 0), (2, 0), (3, 0), (4, 1)):
            with self.subTest(count=count):
                source = _huatai_pdf_source()
                registry = {
                    "sources": {"research_reports": {"futures_companies": [source]}}
                }
                items = [_huatai_pdf_market_information() for _ in range(count)]
                for index, item in enumerate(items):
                    item.title = f"Report {index}"
                collector = Mock()
                collector.collect.return_value = items
                ranker = Mock()
                ranker.rank.return_value = items
                router = Mock()
                router.analyze.return_value = [
                    MarketAnalysis(item, "Neutral.") for item in items
                ]
                resolver = Mock()
                resolver.assess.return_value = relevance_assessment(())
                output = StringIO()

                with (
                    patch(
                        "futures_intelligence.main.load_yaml_file",
                        return_value=registry,
                    ),
                    patch(
                        "futures_intelligence.main.CollectorFactory.create",
                        return_value=collector,
                    ),
                    patch("futures_intelligence.main.InformationRanker", return_value=ranker),
                    patch("futures_intelligence.main.AnalystRouter", return_value=router),
                    patch(
                        "futures_intelligence.main.CommodityRelevanceResolver",
                        return_value=resolver,
                    ),
                    redirect_stdout(output),
                ):
                    exit_code = _run_htfc_pdf_analysis_evaluation()

                self.assertEqual(exit_code, expected_exit_code)
                collector.collect.assert_called_once_with()
                if expected_exit_code:
                    ranker.rank.assert_not_called()
                    router.analyze.assert_not_called()
                else:
                    ranker.rank.assert_called_once_with(items)
                    router.analyze.assert_called_once_with(items)
                    self.assertEqual(
                        resolver.assess.call_args_list,
                        [((item,),) for item in items],
                    )
                    self.assertIn("Detected Commodity Matches: none", output.getvalue())
                    self.assertIn(
                        "Primary Commodity Candidates: none", output.getvalue()
                    )
                    self.assertIn(
                        "Mentioned Commodity Matches: none", output.getvalue()
                    )

        source = _huatai_pdf_source()
        registry = {
            "sources": {"research_reports": {"futures_companies": [source]}}
        }
        collector = Mock()
        collector.collect.return_value = [object()]
        output = StringIO()
        with (
            patch("futures_intelligence.main.load_yaml_file", return_value=registry),
            patch(
                "futures_intelligence.main.CollectorFactory.create",
                return_value=collector,
            ),
            redirect_stdout(output),
        ):
            exit_code = _run_htfc_pdf_analysis_evaluation()

        self.assertEqual(exit_code, 1)
        self.assertIn("collector did not return a marketinformation item", output.getvalue().lower())

    def test_huatai_pdf_analysis_evaluation_rejects_invalid_ranker_and_router_shapes(
        self,
    ) -> None:
        first = _huatai_pdf_market_information()
        first.title = "First"
        second = _huatai_pdf_market_information()
        second.title = "Second"
        replacement = _huatai_pdf_market_information()
        replacement.title = "Second"
        valid_analyses = [MarketAnalysis(first, "First."), MarketAnalysis(second, "Second.")]
        invalid_cases = (
            ([first], valid_analyses, "ranker did not return the same number"),
            ([first, first], valid_analyses, "ranker did not preserve"),
            ([first, replacement], valid_analyses, "ranker did not preserve"),
            ([first, second], [valid_analyses[0]], "router did not return the same number"),
            ([first, second], [valid_analyses[0], object()], "router did not return a marketanalysis"),
            ([first, second], [valid_analyses[1], valid_analyses[0]], "analysis did not preserve"),
        )

        for ranked, analyses, expected in invalid_cases:
            with self.subTest(expected=expected):
                source = _huatai_pdf_source()
                registry = {
                    "sources": {"research_reports": {"futures_companies": [source]}}
                }
                collector = Mock()
                collector.collect.return_value = [first, second]
                ranker = Mock()
                ranker.rank.return_value = ranked
                router = Mock()
                router.analyze.return_value = analyses
                output = StringIO()

                with (
                    patch(
                        "futures_intelligence.main.load_yaml_file",
                        return_value=registry,
                    ),
                    patch(
                        "futures_intelligence.main.CollectorFactory.create",
                        return_value=collector,
                    ),
                    patch("futures_intelligence.main.InformationRanker", return_value=ranker),
                    patch("futures_intelligence.main.AnalystRouter", return_value=router),
                    patch("futures_intelligence.main.CommodityMatcher") as matcher_class,
                    redirect_stdout(output),
                ):
                    exit_code = _run_htfc_pdf_analysis_evaluation()

                self.assertEqual(exit_code, 1)
                self.assertIn(expected, output.getvalue().lower())
                if "ranker" in expected:
                    matcher_class.assert_not_called()

    def test_huatai_pdf_analysis_evaluation_propagates_analysis_and_resolver_errors(
        self,
    ) -> None:
        for collaborator, exception in (
            ("ranker", OSError("EVALUATION_RANKER_SECRET")),
            ("ranker", TypeError("EVALUATION_RANKER_TYPE_SECRET")),
            ("resolver", TypeError("EVALUATION_RESOLVER_SECRET")),
            ("resolver", AssertionError("EVALUATION_RESOLVER_ASSERTION_SECRET")),
            ("resolver", OSError("EVALUATION_RESOLVER_OSERROR_SECRET")),
            ("router", OSError("EVALUATION_ROUTER_OSERROR_SECRET")),
            ("router", AssertionError("EVALUATION_ROUTER_SECRET")),
        ):
            with self.subTest(collaborator=collaborator):
                source = _huatai_pdf_source()
                registry = {
                    "sources": {"research_reports": {"futures_companies": [source]}}
                }
                item = _huatai_pdf_market_information()
                collector = Mock()
                collector.collect.return_value = [item]
                ranker = Mock()
                ranker.rank.side_effect = exception if collaborator == "ranker" else None
                ranker.rank.return_value = [item]
                router = Mock()
                router.analyze.side_effect = exception if collaborator == "router" else None
                router.analyze.return_value = [MarketAnalysis(item, "Neutral.")]
                resolver = Mock()
                resolver.assess.side_effect = exception if collaborator == "resolver" else None
                resolver.assess.return_value = relevance_assessment(())
                output = StringIO()

                with (
                    patch(
                        "futures_intelligence.main.load_yaml_file",
                        return_value=registry,
                    ),
                    patch(
                        "futures_intelligence.main.CollectorFactory.create",
                        return_value=collector,
                    ) as create,
                    patch("futures_intelligence.main.InformationRanker", return_value=ranker),
                    patch("futures_intelligence.main.AnalystRouter", return_value=router),
                    patch(
                        "futures_intelligence.main.CommodityRelevanceResolver",
                        return_value=resolver,
                    ),
                    redirect_stdout(output),
                ):
                    with self.assertRaises(type(exception)) as raised:
                        _run_htfc_pdf_analysis_evaluation()

                self.assertEqual(raised.exception.args, exception.args)
                self.assertNotIn("NO_PROXY", output.getvalue())
                self.assertNotIn(str(exception), output.getvalue())
                self.assertFalse(source["enabled"])
                self.assertEqual(source["pdf_extraction"]["max_selected_pdfs"], 3)
                detached_source = create.call_args.args[0]
                self.assertTrue(detached_source["enabled"])
                self.assertEqual(
                    detached_source["pdf_extraction"]["max_selected_pdfs"], 3
                )
                self.assertEqual(
                    {
                        key: value
                        for key, value in detached_source["pdf_extraction"].items()
                        if key != "max_selected_pdfs"
                    },
                    {
                        key: value
                        for key, value in source["pdf_extraction"].items()
                        if key != "max_selected_pdfs"
                    },
                )

    def test_huatai_pdf_analysis_evaluation_keeps_collection_failures_narrow(
        self,
    ) -> None:
        for exception, expected_exit_code in (
            (OSError("Tunnel connection failed: 502 Bad Gateway"), 1),
            (TypeError("EVALUATION_COLLECTOR_SECRET"), None),
        ):
            with self.subTest(exception=type(exception).__name__):
                source = _huatai_pdf_source()
                registry = {
                    "sources": {"research_reports": {"futures_companies": [source]}}
                }
                collector = Mock()
                collector.collect.side_effect = exception
                output = StringIO()
                with (
                    patch(
                        "futures_intelligence.main.load_yaml_file",
                        return_value=registry,
                    ),
                    patch(
                        "futures_intelligence.main.CollectorFactory.create",
                        return_value=collector,
                    ) as create,
                    patch("futures_intelligence.main.InformationRanker") as ranker_class,
                    patch("futures_intelligence.main.AnalystRouter") as router_class,
                    redirect_stdout(output),
                ):
                    if expected_exit_code is None:
                        with self.assertRaises(type(exception)) as raised:
                            _run_htfc_pdf_analysis_evaluation()
                        self.assertEqual(raised.exception.args, exception.args)
                    else:
                        self.assertEqual(
                            _run_htfc_pdf_analysis_evaluation(), expected_exit_code
                        )

                ranker_class.assert_not_called()
                router_class.assert_not_called()
                if expected_exit_code is None:
                    self.assertNotIn("EVALUATION_COLLECTOR_SECRET", output.getvalue())
                else:
                    self.assertIn("NO_PROXY=htfc.com,www.htfc.com", output.getvalue())
                    self.assertIn("no_proxy=htfc.com,www.htfc.com", output.getvalue())
                self.assertFalse(source["enabled"])
                self.assertEqual(source["pdf_extraction"]["max_selected_pdfs"], 3)
                detached_source = create.call_args.args[0]
                self.assertTrue(detached_source["enabled"])
                self.assertEqual(
                    detached_source["pdf_extraction"]["max_selected_pdfs"], 3
                )
                self.assertEqual(
                    {
                        key: value
                        for key, value in detached_source["pdf_extraction"].items()
                        if key != "max_selected_pdfs"
                    },
                    {
                        key: value
                        for key, value in source["pdf_extraction"].items()
                        if key != "max_selected_pdfs"
                    },
                )

    def test_huatai_pdf_analysis_evaluation_rejects_noncanonical_analysis_fields(
        self,
    ) -> None:
        for field_name, value in (
            ("market_direction", "BULLISH"),
            ("market_direction", " bullish "),
            ("summary", " Summary with surrounding whitespace "),
            ("reasoning_details", (" Detail with surrounding whitespace ",)),
            ("confidence_score", True),
            ("directional_provenance", "STRUCTURAL_ONLY"),
            ("commodity_directional_evidence", ["not canonical evidence"]),
        ):
            with self.subTest(field_name=field_name, value=value):
                source = _huatai_pdf_source()
                registry = {
                    "sources": {"research_reports": {"futures_companies": [source]}}
                }
                item = _huatai_pdf_market_information()
                analysis = MarketAnalysis(item, "Canonical summary.")
                setattr(analysis, field_name, value)
                collector = Mock()
                collector.collect.return_value = [item]
                ranker = Mock()
                ranker.rank.return_value = [item]
                router = Mock()
                router.analyze.return_value = [analysis]
                output = StringIO()

                with (
                    patch(
                        "futures_intelligence.main.load_yaml_file",
                        return_value=registry,
                    ),
                    patch(
                        "futures_intelligence.main.CollectorFactory.create",
                        return_value=collector,
                    ) as create,
                    patch("futures_intelligence.main.InformationRanker", return_value=ranker),
                    patch("futures_intelligence.main.AnalystRouter", return_value=router),
                    patch("futures_intelligence.main.CommodityMatcher") as matcher_class,
                    redirect_stdout(output),
                ):
                    exit_code = _run_htfc_pdf_analysis_evaluation()

                self.assertEqual(exit_code, 1)
                rendered = output.getvalue()
                self.assertNotIn("deterministic analysis evaluation succeeded", rendered)
                self.assertNotIn("Bullish Count:", rendered)
                self.assertNotIn(str(value), rendered)
                matcher_class.assert_not_called()
                self.assertFalse(source["enabled"])
                self.assertEqual(source["pdf_extraction"]["max_selected_pdfs"], 3)
                detached_source = create.call_args.args[0]
                self.assertTrue(detached_source["enabled"])
                self.assertEqual(
                    detached_source["pdf_extraction"]["max_selected_pdfs"], 3
                )
                self.assertIsNot(
                    detached_source["pdf_extraction"], source["pdf_extraction"]
                )

    def test_huatai_pdf_analysis_evaluation_rejects_malformed_resolver_results(
        self,
    ) -> None:
        foreign_assessment = SimpleNamespace(
            lexical_matches=(), primary=(), mentioned=()
        )
        for resolver_result in (
            None,
            [],
            (value for value in ()),
            foreign_assessment,
            (object(),),
        ):
            with self.subTest(resolver_result_type=type(resolver_result).__name__):
                source = _huatai_pdf_source()
                registry = {
                    "sources": {"research_reports": {"futures_companies": [source]}}
                }
                item = _huatai_pdf_market_information()
                collector = Mock()
                collector.collect.return_value = [item]
                ranker = Mock()
                ranker.rank.return_value = [item]
                router = Mock()
                router.analyze.return_value = [MarketAnalysis(item, "Neutral.")]
                resolver = Mock()
                resolver.assess.return_value = resolver_result
                output = StringIO()

                with (
                    patch(
                        "futures_intelligence.main.load_yaml_file",
                        return_value=registry,
                    ),
                    patch(
                        "futures_intelligence.main.CollectorFactory.create",
                        return_value=collector,
                    ) as create,
                    patch("futures_intelligence.main.InformationRanker", return_value=ranker),
                    patch("futures_intelligence.main.AnalystRouter", return_value=router),
                    patch(
                        "futures_intelligence.main.CommodityRelevanceResolver",
                        return_value=resolver,
                    ),
                    redirect_stdout(output),
                ):
                    exit_code = _run_htfc_pdf_analysis_evaluation()

                self.assertEqual(exit_code, 1)
                rendered = output.getvalue()
                self.assertNotIn("deterministic analysis evaluation succeeded", rendered)
                self.assertNotIn("foreign_assessment", rendered)
                self.assertEqual(item.commodities, ())
                self.assertFalse(source["enabled"])
                self.assertEqual(source["pdf_extraction"]["max_selected_pdfs"], 3)
                self.assertTrue(create.call_args.args[0]["enabled"])

    def test_huatai_pdf_analysis_evaluation_rejects_out_of_contract_collector_results(
        self,
    ) -> None:
        item = _huatai_pdf_market_information()
        for collected in (
            None,
            (item,),
            (value for value in (item,)),
            [object()],
            [item, object()],
        ):
            with self.subTest(collected_type=type(collected).__name__):
                source = _huatai_pdf_source()
                registry = {
                    "sources": {"research_reports": {"futures_companies": [source]}}
                }
                collector = Mock()
                collector.collect.return_value = collected
                output = StringIO()

                with (
                    patch(
                        "futures_intelligence.main.load_yaml_file",
                        return_value=registry,
                    ),
                    patch(
                        "futures_intelligence.main.CollectorFactory.create",
                        return_value=collector,
                    ) as create,
                    patch("futures_intelligence.main.InformationRanker") as ranker_class,
                    patch("futures_intelligence.main.AnalystRouter") as router_class,
                    patch("futures_intelligence.main.CommodityMatcher") as matcher_class,
                    redirect_stdout(output),
                ):
                    exit_code = _run_htfc_pdf_analysis_evaluation()

                self.assertEqual(exit_code, 1)
                self.assertNotIn(
                    "deterministic analysis evaluation succeeded", output.getvalue()
                )
                ranker_class.assert_not_called()
                router_class.assert_not_called()
                matcher_class.assert_not_called()
                self.assertFalse(source["enabled"])
                self.assertEqual(source["pdf_extraction"]["max_selected_pdfs"], 3)
                detached_source = create.call_args.args[0]
                self.assertTrue(detached_source["enabled"])
                self.assertEqual(
                    detached_source["pdf_extraction"]["max_selected_pdfs"], 3
                )
                self.assertIsNot(
                    detached_source["pdf_extraction"], source["pdf_extraction"]
                )
                self.assertEqual(
                    {
                        key: value
                        for key, value in detached_source["pdf_extraction"].items()
                        if key != "max_selected_pdfs"
                    },
                    {
                        key: value
                        for key, value in source["pdf_extraction"].items()
                        if key != "max_selected_pdfs"
                    },
                )

    def test_huatai_pdf_analysis_evaluation_rejects_out_of_contract_ranker_results(
        self,
    ) -> None:
        first = _huatai_pdf_market_information()
        second = _huatai_pdf_market_information()
        replacement = _huatai_pdf_market_information()
        for ranked in (
            None,
            (first, second),
            (value for value in (first, second)),
            [first, object()],
            [first, replacement],
            [first],
            [first, first],
        ):
            with self.subTest(ranked_type=type(ranked).__name__):
                source = _huatai_pdf_source()
                registry = {
                    "sources": {"research_reports": {"futures_companies": [source]}}
                }
                collector = Mock()
                collector.collect.return_value = [first, second]
                ranker = Mock()
                ranker.rank.return_value = ranked
                output = StringIO()

                with (
                    patch(
                        "futures_intelligence.main.load_yaml_file",
                        return_value=registry,
                    ),
                    patch(
                        "futures_intelligence.main.CollectorFactory.create",
                        return_value=collector,
                    ) as create,
                    patch("futures_intelligence.main.InformationRanker", return_value=ranker),
                    patch("futures_intelligence.main.AnalystRouter") as router_class,
                    patch("futures_intelligence.main.CommodityMatcher") as matcher_class,
                    redirect_stdout(output),
                ):
                    exit_code = _run_htfc_pdf_analysis_evaluation()

                self.assertEqual(exit_code, 1)
                self.assertNotIn(
                    "deterministic analysis evaluation succeeded", output.getvalue()
                )
                router_class.assert_not_called()
                matcher_class.assert_not_called()
                self.assertFalse(source["enabled"])
                self.assertEqual(source["pdf_extraction"]["max_selected_pdfs"], 3)
                self.assertTrue(create.call_args.args[0]["enabled"])

    def test_huatai_pdf_analysis_evaluation_preserves_equal_valued_identities_when_ranked(
        self,
    ) -> None:
        first = _huatai_pdf_market_information()
        second = _huatai_pdf_market_information()
        self.assertIsNot(first, second)
        self.assertEqual(first, second)
        source = _huatai_pdf_source()
        registry = {
            "sources": {"research_reports": {"futures_companies": [source]}}
        }
        collector = Mock()
        collector.collect.return_value = [first, second]
        ranker = Mock()
        ranker.rank.return_value = [second, first]
        router = Mock()
        router.analyze.return_value = [
            MarketAnalysis(second, "Second."),
            MarketAnalysis(first, "First."),
        ]
        matcher = Mock()
        matcher.match.return_value = ()
        output = StringIO()

        with (
            patch("futures_intelligence.main.load_yaml_file", return_value=registry),
            patch(
                "futures_intelligence.main.CollectorFactory.create",
                return_value=collector,
            ),
            patch("futures_intelligence.main.InformationRanker", return_value=ranker),
            patch("futures_intelligence.main.AnalystRouter", return_value=router),
            patch("futures_intelligence.main.CommodityMatcher", return_value=matcher),
            redirect_stdout(output),
        ):
            exit_code = _run_htfc_pdf_analysis_evaluation()

        self.assertEqual(exit_code, 0)
        self.assertEqual(router.analyze.call_args.args[0], [second, first])
        self.assertIs(router.analyze.call_args.args[0][0], second)
        self.assertIs(router.analyze.call_args.args[0][1], first)
        collection_indexes = [
            line
            for line in output.getvalue().splitlines()
            if line.startswith("Collection Index: ")
        ]
        ranked_indexes = [
            line
            for line in output.getvalue().splitlines()
            if line.startswith("Ranked Index: ")
        ]
        self.assertEqual(collection_indexes, ["Collection Index: 2", "Collection Index: 1"])
        self.assertEqual(ranked_indexes, ["Ranked Index: 1", "Ranked Index: 2"])

    def test_huatai_pdf_collector_smoke_test_uses_detached_exact_source_and_prints_provenance(
        self,
    ) -> None:
        source = _huatai_pdf_source()
        registry = {
            "sources": {
                "research_reports": {
                    "futures_companies": [
                        {"name": "Lookalike", "source_type": "research_report"},
                        source,
                    ]
                }
            }
        }
        item = _huatai_pdf_market_information()
        collector = Mock()
        collector.collect.return_value = [item]
        output = StringIO()

        with (
            patch("futures_intelligence.main.load_yaml_file", return_value=registry),
            patch(
                "futures_intelligence.main.CollectorFactory.create",
                return_value=collector,
            ) as create,
            redirect_stdout(output),
        ):
            exit_code = _run_htfc_pdf_collector_smoke_test()

        self.assertEqual(exit_code, 0)
        create.assert_called_once()
        smoke_source = create.call_args.args[0]
        self.assertIsNot(smoke_source, source)
        self.assertIsNot(smoke_source["pdf_extraction"], source["pdf_extraction"])
        self.assertTrue(smoke_source["enabled"])
        self.assertEqual(smoke_source["pdf_extraction"]["max_selected_pdfs"], 1)
        self.assertFalse(source["enabled"])
        self.assertEqual(source["pdf_extraction"]["max_selected_pdfs"], 3)
        self.assertEqual(
            {
                key: value
                for key, value in smoke_source["pdf_extraction"].items()
                if key != "max_selected_pdfs"
            },
            {
                key: value
                for key, value in source["pdf_extraction"].items()
                if key != "max_selected_pdfs"
            },
        )
        collector.collect.assert_called_once_with()
        rendered = output.getvalue()
        self.assertIn("Huatai Futures PDF collector smoke test succeeded.", rendered)
        self.assertIn("Collected MarketInformation Count: 1", rendered)
        self.assertIn("Title: Huatai PDF report", rendered)
        self.assertIn("Published Time: 2026-07-29T00:00:00+08:00", rendered)
        self.assertIn("Published Time Precision: date", rendered)
        self.assertIn("Canonical PDF URL: https://htfc.com/wz_upload/report.pdf", rendered)
        self.assertIn("Commodities: none", rendered)
        self.assertIn("Report Author: Report analyst", rendered)
        self.assertIn("Document Metadata Author: PDF author", rendered)
        self.assertIn("Parser Diagnostic Count: 2", rendered)
        self.assertNotIn(item.content, rendered)
        self.assertNotIn("FULL_DOCUMENT_METADATA_SECRET_MARKER_7E91", rendered)
        self.assertNotIn("PARSER_DIAGNOSTIC_SECRET_MARKER_3B51", rendered)
        self.assertNotIn("document_metadata", rendered)

    def test_huatai_pdf_collector_smoke_test_rejects_missing_or_ambiguous_sources(
        self,
    ) -> None:
        missing_registry = {"sources": {"research_reports": {"futures_companies": []}}}
        ambiguous_registry = {
            "sources": {
                "research_reports": {
                    "futures_companies": [_huatai_pdf_source(), _huatai_pdf_source()]
                }
            }
        }

        for registry, expected in (
            (missing_registry, "no matching"),
            (ambiguous_registry, "ambiguous"),
        ):
            with self.subTest(expected=expected):
                output = StringIO()
                with (
                    patch(
                        "futures_intelligence.main.load_yaml_file",
                        return_value=registry,
                    ),
                    patch("futures_intelligence.main.CollectorFactory.create") as create,
                    redirect_stdout(output),
                ):
                    exit_code = _run_htfc_pdf_collector_smoke_test()

                self.assertEqual(exit_code, 1)
                self.assertIn(expected, output.getvalue().lower())
                create.assert_not_called()

    def test_huatai_pdf_collector_smoke_test_fails_for_no_factory_collector_or_invalid_item_count(
        self,
    ) -> None:
        for factory_result, expected in (
            (None, "factory did not create"),
            (Mock(collect=Mock(return_value=[])), "no marketinformation item"),
            (
                Mock(
                    collect=Mock(
                        return_value=[
                            _huatai_pdf_market_information(),
                            _huatai_pdf_market_information(),
                        ]
                    )
                ),
                "expected exactly one",
            ),
        ):
            with self.subTest(expected=expected):
                source = _huatai_pdf_source()
                registry = {
                    "sources": {
                        "research_reports": {"futures_companies": [source]}
                    }
                }
                output = StringIO()
                with (
                    patch(
                        "futures_intelligence.main.load_yaml_file",
                        return_value=registry,
                    ),
                    patch(
                        "futures_intelligence.main.CollectorFactory.create",
                        return_value=factory_result,
                    ),
                    redirect_stdout(output),
                ):
                    exit_code = _run_htfc_pdf_collector_smoke_test()

                self.assertEqual(exit_code, 1)
                self.assertIn(expected, output.getvalue().lower())
                self.assertFalse(source["enabled"])
                self.assertEqual(source["pdf_extraction"]["max_selected_pdfs"], 3)

    def test_huatai_pdf_collector_smoke_test_reports_proxy_tunnel_failures(
        self,
    ) -> None:
        source = _huatai_pdf_source()
        registry = {
            "sources": {"research_reports": {"futures_companies": [source]}}
        }
        collector = Mock()
        collector.collect.side_effect = OSError("Tunnel connection failed: 502 Bad Gateway")
        output = StringIO()

        with (
            patch("futures_intelligence.main.load_yaml_file", return_value=registry),
            patch(
                "futures_intelligence.main.CollectorFactory.create",
                return_value=collector,
            ) as create,
            redirect_stdout(output),
        ):
            exit_code = _run_htfc_pdf_collector_smoke_test()

        self.assertEqual(exit_code, 1)
        rendered = output.getvalue()
        self.assertIn("Tunnel connection failed: 502 Bad Gateway", rendered)
        self.assertIn("NO_PROXY=htfc.com,www.htfc.com", rendered)
        self.assertIn("no_proxy=htfc.com,www.htfc.com", rendered)
        self.assertNotIn("pdf_extraction", rendered)
        self.assertNotIn("socket_timeout_seconds", rendered)
        self.assertFalse(source["enabled"])
        self.assertEqual(source["pdf_extraction"]["max_selected_pdfs"], 3)
        smoke_source = create.call_args.args[0]
        self.assertTrue(smoke_source["enabled"])
        self.assertEqual(smoke_source["pdf_extraction"]["max_selected_pdfs"], 1)
        self.assertIsNot(smoke_source["pdf_extraction"], source["pdf_extraction"])
        collector.collect.assert_called_once_with()

    def test_huatai_pdf_analysis_smoke_test_reports_collection_proxy_failure_before_analysis(
        self,
    ) -> None:
        source = _huatai_pdf_source()
        registry = {
            "sources": {"research_reports": {"futures_companies": [source]}}
        }
        collector = Mock()
        collector.collect.side_effect = OSError("Tunnel connection failed: 502 Bad Gateway")
        output = StringIO()

        with (
            patch("futures_intelligence.main.load_yaml_file", return_value=registry),
            patch(
                "futures_intelligence.main.CollectorFactory.create",
                return_value=collector,
            ),
            patch("futures_intelligence.main.InformationRanker") as ranker_class,
            patch("futures_intelligence.main.AnalystRouter") as router_class,
            redirect_stdout(output),
        ):
            exit_code = _run_htfc_pdf_analysis_smoke_test()

        self.assertEqual(exit_code, 1)
        rendered = output.getvalue()
        self.assertIn("NO_PROXY=htfc.com,www.htfc.com", rendered)
        self.assertIn("no_proxy=htfc.com,www.htfc.com", rendered)
        ranker_class.assert_not_called()
        router_class.assert_not_called()
        self.assertFalse(source["enabled"])
        self.assertEqual(source["pdf_extraction"]["max_selected_pdfs"], 3)
        collector.collect.assert_called_once_with()

    def test_huatai_pdf_collector_smoke_test_propagates_unexpected_collector_error_without_mutating_config(
        self,
    ) -> None:
        source = _huatai_pdf_source()
        registry = {
            "sources": {"research_reports": {"futures_companies": [source]}}
        }
        collector = Mock()
        collector.collect.side_effect = KeyError("unexpected collector failure")

        with (
            patch("futures_intelligence.main.load_yaml_file", return_value=registry),
            patch(
                "futures_intelligence.main.CollectorFactory.create",
                return_value=collector,
            ) as create,
        ):
            with self.assertRaises(KeyError) as raised:
                _run_htfc_pdf_collector_smoke_test()

        self.assertEqual(raised.exception.args, ("unexpected collector failure",))
        create.assert_called_once()
        smoke_source = create.call_args.args[0]
        self.assertTrue(smoke_source["enabled"])
        self.assertEqual(smoke_source["pdf_extraction"]["max_selected_pdfs"], 1)
        self.assertIsNot(smoke_source["pdf_extraction"], source["pdf_extraction"])
        self.assertFalse(source["enabled"])
        self.assertEqual(source["pdf_extraction"]["max_selected_pdfs"], 3)
        collector.collect.assert_called_once_with()

    def test_huatai_pdf_collector_smoke_test_propagates_unexpected_type_error(
        self,
    ) -> None:
        source = _huatai_pdf_source()
        registry = {
            "sources": {"research_reports": {"futures_companies": [source]}}
        }
        collector = Mock()
        collector.collect.side_effect = TypeError("PHASE_D_INTERNAL_TYPE_ERROR_SECRET")
        output = StringIO()

        with (
            patch("futures_intelligence.main.load_yaml_file", return_value=registry),
            patch(
                "futures_intelligence.main.CollectorFactory.create",
                return_value=collector,
            ) as create,
            redirect_stdout(output),
        ):
            with self.assertRaises(TypeError) as raised:
                _run_htfc_pdf_collector_smoke_test()

        self.assertEqual(raised.exception.args, ("PHASE_D_INTERNAL_TYPE_ERROR_SECRET",))
        self.assertNotIn("Huatai Futures PDF collector smoke test failed", output.getvalue())
        self.assertTrue(create.call_args.args[0]["enabled"])
        self.assertEqual(
            create.call_args.args[0]["pdf_extraction"]["max_selected_pdfs"], 1
        )
        self.assertIsNot(
            create.call_args.args[0]["pdf_extraction"], source["pdf_extraction"]
        )
        self.assertFalse(source["enabled"])
        self.assertEqual(source["pdf_extraction"]["max_selected_pdfs"], 3)
        collector.collect.assert_called_once_with()

    def test_huatai_pdf_analysis_smoke_test_propagates_unexpected_ranker_type_error(
        self,
    ) -> None:
        source = _huatai_pdf_source()
        registry = {
            "sources": {"research_reports": {"futures_companies": [source]}}
        }
        item = _huatai_pdf_market_information()
        collector = Mock()
        collector.collect.return_value = [item]
        ranker = Mock()
        ranker.rank.side_effect = TypeError("RANKER_INTERNAL_TYPE_ERROR_SECRET")
        output = StringIO()

        with (
            patch("futures_intelligence.main.load_yaml_file", return_value=registry),
            patch(
                "futures_intelligence.main.CollectorFactory.create",
                return_value=collector,
            ),
            patch("futures_intelligence.main.InformationRanker", return_value=ranker),
            patch("futures_intelligence.main.AnalystRouter") as router_class,
            redirect_stdout(output),
        ):
            with self.assertRaises(TypeError) as raised:
                _run_htfc_pdf_analysis_smoke_test()

        self.assertEqual(raised.exception.args, ("RANKER_INTERNAL_TYPE_ERROR_SECRET",))
        router_class.assert_not_called()
        self.assertNotIn("Huatai Futures PDF analysis smoke test failed", output.getvalue())
        self.assertFalse(source["enabled"])
        self.assertEqual(source["pdf_extraction"]["max_selected_pdfs"], 3)

    def test_huatai_pdf_analysis_smoke_test_propagates_unexpected_ranker_os_error(
        self,
    ) -> None:
        source = _huatai_pdf_source()
        registry = {
            "sources": {"research_reports": {"futures_companies": [source]}}
        }
        item = _huatai_pdf_market_information()
        collector = Mock()
        collector.collect.return_value = [item]
        ranker = Mock()
        ranker.rank.side_effect = OSError("RANKER_OSERROR_SECRET_MARKER")
        output = StringIO()

        with (
            patch("futures_intelligence.main.load_yaml_file", return_value=registry),
            patch(
                "futures_intelligence.main.CollectorFactory.create",
                return_value=collector,
            ),
            patch("futures_intelligence.main.InformationRanker", return_value=ranker),
            patch("futures_intelligence.main.AnalystRouter") as router_class,
            redirect_stdout(output),
        ):
            with self.assertRaises(OSError) as raised:
                _run_htfc_pdf_analysis_smoke_test()

        self.assertEqual(raised.exception.args, ("RANKER_OSERROR_SECRET_MARKER",))
        self.assertNotIn("NO_PROXY", output.getvalue())
        self.assertNotIn("no_proxy", output.getvalue())
        self.assertNotIn("RANKER_OSERROR_SECRET_MARKER", output.getvalue())
        router_class.assert_not_called()
        self.assertFalse(source["enabled"])
        self.assertEqual(source["pdf_extraction"]["max_selected_pdfs"], 3)

    def test_huatai_pdf_analysis_smoke_test_propagates_unexpected_router_os_error(
        self,
    ) -> None:
        source = _huatai_pdf_source()
        registry = {
            "sources": {"research_reports": {"futures_companies": [source]}}
        }
        item = _huatai_pdf_market_information()
        collector = Mock()
        collector.collect.return_value = [item]
        ranker = Mock()
        ranker.rank.return_value = [item]
        router = Mock()
        router.analyze.side_effect = OSError("ROUTER_OSERROR_SECRET_MARKER")
        output = StringIO()

        with (
            patch("futures_intelligence.main.load_yaml_file", return_value=registry),
            patch(
                "futures_intelligence.main.CollectorFactory.create",
                return_value=collector,
            ),
            patch("futures_intelligence.main.InformationRanker", return_value=ranker),
            patch("futures_intelligence.main.AnalystRouter", return_value=router),
            redirect_stdout(output),
        ):
            with self.assertRaises(OSError) as raised:
                _run_htfc_pdf_analysis_smoke_test()

        self.assertEqual(raised.exception.args, ("ROUTER_OSERROR_SECRET_MARKER",))
        self.assertNotIn("NO_PROXY", output.getvalue())
        self.assertNotIn("no_proxy", output.getvalue())
        self.assertNotIn("ROUTER_OSERROR_SECRET_MARKER", output.getvalue())
        self.assertFalse(source["enabled"])
        self.assertEqual(source["pdf_extraction"]["max_selected_pdfs"], 3)

    def test_huatai_pdf_analysis_smoke_test_propagates_unexpected_router_errors(
        self,
    ) -> None:
        for exception in (
            TypeError("ROUTER_INTERNAL_TYPE_ERROR_SECRET"),
            AssertionError("ROUTER_INTERNAL_ASSERTION_SECRET"),
        ):
            with self.subTest(exception=type(exception).__name__):
                source = _huatai_pdf_source()
                registry = {
                    "sources": {
                        "research_reports": {"futures_companies": [source]}
                    }
                }
                item = _huatai_pdf_market_information()
                collector = Mock()
                collector.collect.return_value = [item]
                ranker = Mock()
                ranker.rank.return_value = [item]
                router = Mock()
                router.analyze.side_effect = exception
                output = StringIO()

                with (
                    patch(
                        "futures_intelligence.main.load_yaml_file",
                        return_value=registry,
                    ),
                    patch(
                        "futures_intelligence.main.CollectorFactory.create",
                        return_value=collector,
                    ),
                    patch(
                        "futures_intelligence.main.InformationRanker",
                        return_value=ranker,
                    ),
                    patch(
                        "futures_intelligence.main.AnalystRouter",
                        return_value=router,
                    ),
                    redirect_stdout(output),
                ):
                    with self.assertRaises(type(exception)) as raised:
                        _run_htfc_pdf_analysis_smoke_test()

                self.assertEqual(raised.exception.args, exception.args)
                self.assertNotIn(
                    "Huatai Futures PDF analysis smoke test failed", output.getvalue()
                )
                self.assertFalse(source["enabled"])
                self.assertEqual(source["pdf_extraction"]["max_selected_pdfs"], 3)

    def test_runs_mocked_huatai_pdf_smoke_test_without_pipeline_side_effects(self) -> None:
        listing_fetcher = Mock()
        listing_fetcher.fetch_reports.return_value = HuataiFetchResult(
            discovered_link_count=0,
            selected_urls=(),
            reports=(),
            discovery=HuataiListingDiscovery(
                report_items=(
                    HuataiReportListingItem(
                        canonical_url="https://htfc.com/wz_upload/20260721/report.pdf",
                        link_kind="pdf_attachment",
                        listing_title="Explicit title",
                        publication_date=date(2026, 7, 21),
                        report_type="专题报告",
                        section_position=0,
                        item_position=0,
                    ),
                ),
            ),
        )
        extractor = Mock()
        extractor.extract.return_value = HuataiPdfExtractionResult(
            canonical_pdf_url="https://htfc.com/wz_upload/20260721/report.pdf",
            byte_count=1024,
            page_count=19,
            document_metadata=(("Author", "Analyst"),),
            extracted_text="中文研究报告正文。",
            extracted_character_count=9,
            extraction_status="success",
            failure_category=None,
            ocr_required=False,
            title="Explicit title",
            publication_date=date(2026, 7, 21),
            report_type="专题报告",
            document_metadata_author="Analyst",
        )
        output = StringIO()

        with redirect_stdout(output):
            exit_code = _run_htfc_pdf_smoke_test(
                listing_fetcher=listing_fetcher,
                extractor=extractor,
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("Discovered report PDF attachments: 1", output.getvalue())
        self.assertIn("Downloaded Byte Count: 1024", output.getvalue())
        self.assertIn("中文研究报告正文", output.getvalue())
        extractor.extract.assert_called_once_with(
            HuataiPdfAttachment(
                "https://htfc.com/wz_upload/20260721/report.pdf",
                "Explicit title",
                date(2026, 7, 21),
                "专题报告",
            )
        )

    def test_huatai_pdf_smoke_test_selects_newest_report_with_stable_tie_breaking(self) -> None:
        listing_fetcher = Mock()
        listing_fetcher.fetch_reports.return_value = HuataiFetchResult(
            discovered_link_count=0,
            selected_urls=(),
            reports=(),
            discovery=HuataiListingDiscovery(
                report_items=(
                    HuataiReportListingItem(
                        canonical_url="https://htfc.com/wz_upload/service.pdf",
                        link_kind="pdf_attachment",
                        listing_title="专题报告",
                        publication_date=date(2026, 7, 20),
                        report_type="专题报告",
                        section_position=0,
                        item_position=0,
                    ),
                    HuataiReportListingItem(
                        canonical_url="https://htfc.com/wz_upload/undated.pdf",
                        link_kind="pdf_attachment",
                        listing_title="未注明日期报告",
                        publication_date=None,
                        report_type="周期报告",
                        section_position=1,
                        item_position=0,
                    ),
                    HuataiReportListingItem(
                        canonical_url="https://htfc.com/wz_upload/strategy.pdf",
                        link_kind="pdf_attachment",
                        listing_title="策略报告",
                        publication_date=date(2026, 7, 20),
                        report_type="策略报告",
                        section_position=2,
                        item_position=0,
                    ),
                ),
            ),
        )
        extractor = Mock()
        extractor.extract.return_value = _successful_pdf_result(
            "https://htfc.com/wz_upload/service.pdf"
        )

        with redirect_stdout(StringIO()):
            exit_code = _run_htfc_pdf_smoke_test(listing_fetcher, extractor)

        self.assertEqual(exit_code, 0)
        extractor.extract.assert_called_once_with(
            HuataiPdfAttachment(
                "https://htfc.com/wz_upload/service.pdf",
                "专题报告",
                date(2026, 7, 20),
                "专题报告",
            )
        )

    def test_runs_mocked_huatai_report_smoke_test_without_pipeline_side_effects(self) -> None:
        report = FetchedResearchReport(
            title="Huatai report",
            published_time=datetime(2026, 7, 20, tzinfo=timezone.utc),
            content="Normalized HTML report content.",
            url="https://htfc.com/main/yjzx/ssrdph/report-one.shtml",
            report_type="Strategy",
            author="Analyst",
        )
        fetcher = Mock()
        fetcher.fetch_reports.return_value = HuataiFetchResult(
            discovered_link_count=2,
            selected_urls=(report.url,),
            reports=(report,),
            discovery=HuataiListingDiscovery(
                report_items=(
                    HuataiReportListingItem(
                        canonical_url=report.url,
                        link_kind="html_detail",
                        listing_title="Huatai report",
                        publication_date=date(2026, 7, 20),
                        report_type="策略报告",
                        section_position=0,
                        item_position=0,
                    ),
                    HuataiReportListingItem(
                        canonical_url="https://htfc.com/wz_upload/report.pdf",
                        link_kind="pdf_attachment",
                        listing_title="PDF report",
                        publication_date=date(2026, 7, 20),
                        report_type="策略报告",
                        section_position=0,
                        item_position=1,
                    ),
                ),
                ignored_non_report_links=("https://example.com/nope",),
            ),
        )
        output = StringIO()

        with redirect_stdout(output):
            exit_code = _run_htfc_report_smoke_test(fetcher=fetcher)  # type: ignore[arg-type]

        self.assertEqual(exit_code, 0)
        fetcher.fetch_reports.assert_called_once_with()
        self.assertIn("Discovered report HTML detail links: 1", output.getvalue())
        self.assertIn("Discovered report PDF attachments: 1", output.getvalue())
        self.assertIn("Ignored non-report links: 1", output.getvalue())
        self.assertIn("Huatai report", output.getvalue())

    def test_huatai_pdf_only_smoke_test_reports_precise_failure(self) -> None:
        fetcher = Mock()
        fetcher.fetch_reports.return_value = HuataiFetchResult(
            discovered_link_count=0,
            selected_urls=(),
            reports=(),
            discovery=HuataiListingDiscovery(
                report_items=(
                    HuataiReportListingItem(
                        canonical_url="https://htfc.com/wz_upload/report.pdf",
                        link_kind="pdf_attachment",
                        listing_title="PDF report",
                        publication_date=date(2026, 7, 20),
                        report_type="策略报告",
                        section_position=0,
                        item_position=0,
                    ),
                ),
            ),
        )
        output = StringIO()

        with redirect_stdout(output):
            exit_code = _run_htfc_report_smoke_test(fetcher=fetcher)  # type: ignore[arg-type]

        self.assertEqual(exit_code, 1)
        self.assertIn("Discovered report HTML detail links: 0", output.getvalue())
        self.assertIn("Discovered report PDF attachments: 1", output.getvalue())
        self.assertIn("PDF parsing is intentionally disabled", output.getvalue())
        self.assertNotIn("no usable HTML report was found", output.getvalue())

    def test_huatai_proxy_tunnel_failure_includes_safe_retry_hint(self) -> None:
        fetcher = Mock()
        fetcher.fetch_reports.side_effect = OSError("Tunnel connection failed: 502 Bad Gateway")
        output = StringIO()

        with redirect_stdout(output):
            exit_code = _run_htfc_report_smoke_test(fetcher=fetcher)  # type: ignore[arg-type]

        self.assertEqual(exit_code, 1)
        self.assertIn("NO_PROXY=htfc.com,www.htfc.com", output.getvalue())
        self.assertIn("no_proxy=htfc.com,www.htfc.com", output.getvalue())

    def test_huatai_report_smoke_test_returns_nonzero_for_fetch_failure(self) -> None:
        fetcher = Mock()
        fetcher.fetch_reports.side_effect = OSError("network unavailable")
        output = StringIO()

        with redirect_stdout(output):
            exit_code = _run_htfc_report_smoke_test(fetcher=fetcher)  # type: ignore[arg-type]

        self.assertEqual(exit_code, 1)
        self.assertIn("failed", output.getvalue())

    @patch("futures_intelligence.main._run_llm_smoke_test", return_value=1)
    def test_main_dispatches_llm_smoke_test_command(self, smoke_test: Mock) -> None:
        self.assertEqual(main(["llm-smoke-test"]), 1)
        smoke_test.assert_called_once_with()

    @patch("futures_intelligence.main._run_llm_routing_smoke_test", return_value=1)
    def test_main_dispatches_llm_routing_smoke_test_command(
        self, routing_smoke_test: Mock
    ) -> None:
        self.assertEqual(main(["llm-routing-smoke-test"]), 1)
        routing_smoke_test.assert_called_once_with()

    @patch("futures_intelligence.main._configured_llm_model", return_value="gpt-5.6-luna")
    def test_routing_smoke_test_runs_complete_chain_once(
        self, configured_model: Mock
    ) -> None:
        with TemporaryDirectory() as directory:
            usage_path = Path(directory) / "routing_usage.jsonl"
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
            client = FakeClient(routing_response())
            analyst = LLMAnalyst(
                client=client,
                max_items_per_run=1,
                usage_tracker=tracker,
                usage_purpose="smoke_test",
            )
            output = StringIO()

            with redirect_stdout(output):
                exit_code = _run_llm_routing_smoke_test(analyst=analyst)

            self.assertEqual(exit_code, 0)
            self.assertEqual(len(client.responses.calls), 1)
            self.assertIsNotNone(analyst.last_usage_record)
            assert analyst.last_usage_record is not None
            self.assertTrue(analyst.last_usage_record.success)
            self.assertEqual(analyst.last_usage_record.purpose, "smoke_test")
            self.assertEqual(analyst.last_usage_record.response_id, "resp_routing_test")
            self.assertEqual(len(usage_path.read_text(encoding="utf-8").splitlines()), 1)
            self.assertIn("Eligible Candidate Count: 1", output.getvalue())
            self.assertIn("Selected Candidate Count: 1", output.getvalue())
            self.assertIn("Analyst Implementation: LLMAnalyst", output.getvalue())
            self.assertIn("Real LLM routing smoke test succeeded", output.getvalue())
            self.assertIn("Structured routing result.", output.getvalue())
            self.assertIn(f"Usage Record Path: {usage_path}", output.getvalue())
            configured_model.assert_called_once_with()

    @patch("futures_intelligence.main._configured_llm_model", return_value="gpt-5.6-luna")
    def test_routing_smoke_test_rejects_zero_candidates(self, configured_model: Mock) -> None:
        information = _load_smoke_test_information()
        information.reliability_score = 3
        analyst = Mock()
        output = StringIO()

        with (
            patch(
                "futures_intelligence.main._load_routing_smoke_test_information",
                return_value=information,
            ),
            redirect_stdout(output),
        ):
            exit_code = _run_llm_routing_smoke_test(analyst=analyst)

        self.assertEqual(exit_code, 1)
        analyst.analyze.assert_not_called()
        self.assertIn("no candidates were selected", output.getvalue().lower())
        configured_model.assert_called_once_with()

    @patch("futures_intelligence.main._configured_llm_model", return_value="gpt-5.6-luna")
    def test_routing_smoke_test_rejects_api_failure_without_fallback_success(
        self, configured_model: Mock
    ) -> None:
        with TemporaryDirectory() as directory:
            tracker = LLMUsageTracker(
                Path(directory) / "routing_usage.jsonl",
                LLMPricing(
                    model="gpt-5.6-luna",
                    effective_date="2026-07-19",
                    input_per_million_usd=1.0,
                    cached_input_per_million_usd=0.1,
                    output_per_million_usd=6.0,
                    cache_write_multiplier=1.25,
                ),
            )
            client = FakeClient(RuntimeError("unavailable"))
            analyst = LLMAnalyst(
                client=client,
                max_items_per_run=1,
                usage_tracker=tracker,
                usage_purpose="smoke_test",
            )
            output = StringIO()

            with redirect_stdout(output):
                exit_code = _run_llm_routing_smoke_test(analyst=analyst)

            self.assertEqual(exit_code, 1)
            self.assertEqual(len(client.responses.calls), 1)
            self.assertIn("did not return a valid structured response", output.getvalue())
            self.assertNotIn("succeeded", output.getvalue().lower())
            configured_model.assert_called_once_with()

    @patch("futures_intelligence.main._configured_llm_model", return_value="gpt-5.6-luna")
    @patch(
        "futures_intelligence.main._openai_client_for_smoke_test",
        return_value=(None, "OPENAI_API_KEY is not set."),
    )
    def test_routing_smoke_test_missing_api_key_returns_nonzero(
        self, strict_client: Mock, configured_model: Mock
    ) -> None:
        output = StringIO()

        with redirect_stdout(output):
            exit_code = _run_llm_routing_smoke_test()

        self.assertEqual(exit_code, 1)
        self.assertIn("OPENAI_API_KEY is not set.", output.getvalue())
        strict_client.assert_called_once_with()
        configured_model.assert_called_once_with()

    @patch("futures_intelligence.main._configured_llm_model", return_value="gpt-5.6-luna")
    @patch(
        "futures_intelligence.main._openai_client_for_smoke_test",
        return_value=(None, "OpenAI SDK is unavailable. Install the configured dependency."),
    )
    def test_routing_smoke_test_unavailable_sdk_returns_nonzero(
        self, strict_client: Mock, configured_model: Mock
    ) -> None:
        output = StringIO()

        with redirect_stdout(output):
            exit_code = _run_llm_routing_smoke_test()

        self.assertEqual(exit_code, 1)
        self.assertIn("OpenAI SDK is unavailable", output.getvalue())
        strict_client.assert_called_once_with()
        configured_model.assert_called_once_with()

    @patch("futures_intelligence.main._configured_llm_model", return_value="gpt-5.6-luna")
    def test_routing_smoke_test_rejects_malformed_structured_response(
        self, configured_model: Mock
    ) -> None:
        with TemporaryDirectory() as directory:
            tracker = LLMUsageTracker(
                Path(directory) / "routing_usage.jsonl",
                LLMPricing(
                    model="gpt-5.6-luna",
                    effective_date="2026-07-19",
                    input_per_million_usd=1.0,
                    cached_input_per_million_usd=0.1,
                    output_per_million_usd=6.0,
                    cache_write_multiplier=1.25,
                ),
            )
            malformed = SimpleNamespace(
                id="resp_malformed",
                model="gpt-5.6-luna",
                usage=routing_response().usage,
                output_text='{"summary":"missing required fields"}',
            )
            client = FakeClient(malformed)
            analyst = LLMAnalyst(
                client=client,
                max_items_per_run=1,
                usage_tracker=tracker,
                usage_purpose="smoke_test",
            )
            output = StringIO()

            with redirect_stdout(output):
                exit_code = _run_llm_routing_smoke_test(analyst=analyst)

            self.assertEqual(exit_code, 1)
            self.assertEqual(len(client.responses.calls), 1)
            self.assertIsNotNone(analyst.last_usage_record)
            assert analyst.last_usage_record is not None
            self.assertFalse(analyst.last_usage_record.success)
            self.assertNotIn("succeeded", output.getvalue().lower())
            configured_model.assert_called_once_with()

    @patch("futures_intelligence.main._configured_llm_model", return_value="gpt-5.6-luna")
    def test_routing_smoke_test_rejects_refusal(self, configured_model: Mock) -> None:
        with TemporaryDirectory() as directory:
            tracker = LLMUsageTracker(
                Path(directory) / "routing_usage.jsonl",
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
                id="resp_refusal",
                model="gpt-5.6-luna",
                usage=routing_response().usage,
                output_text=None,
                refusal="Mocked refusal",
            )
            client = FakeClient(refusal)
            analyst = LLMAnalyst(
                client=client,
                max_items_per_run=1,
                usage_tracker=tracker,
                usage_purpose="smoke_test",
            )
            output = StringIO()

            with redirect_stdout(output):
                exit_code = _run_llm_routing_smoke_test(analyst=analyst)

            self.assertEqual(exit_code, 1)
            self.assertEqual(len(client.responses.calls), 1)
            self.assertIsNotNone(analyst.last_usage_record)
            assert analyst.last_usage_record is not None
            self.assertFalse(analyst.last_usage_record.success)
            self.assertEqual(analyst.last_usage_record.failure_category, "refusal")
            self.assertNotIn("succeeded", output.getvalue().lower())
            configured_model.assert_called_once_with()

    def test_loads_exactly_one_fixed_local_report_for_smoke_test(self) -> None:
        information = _load_smoke_test_information()

        self.assertEqual(
            SMOKE_TEST_REPORT_PATH.name, "sample_crude_oil_outlook.txt"
        )
        self.assertEqual(information.source_type, "research_report")
        self.assertEqual(information.title, "Sample local research report: Crude Oil Outlook")
        self.assertIn("Crude oil inventories declined", information.content)

    @patch("futures_intelligence.main._configured_llm_model", return_value="test-model")
    def test_smoke_test_prints_one_real_llm_result(
        self, configured_model: Mock
    ) -> None:
        information = _load_smoke_test_information()
        analysis = MarketAnalysis(
            information,
            "Real structured LLM summary.",
            market_direction="bullish",
            confidence_score=83,
            reasoning_details=("Mocked structured response.",),
        )
        analyst = Mock()
        analyst.analyze_smoke_test.return_value = LLMSmokeTestResult(
            success=True,
            analysis=analysis,
            usage_record=LLMUsageRecord(
                timestamp_utc="2026-07-19T00:00:00+00:00",
                purpose="smoke_test",
                model="test-model",
                response_id="resp_test_123",
                source_type="research_report",
                source_name="Test Source",
                source_title=information.title,
                success=True,
                failure_category=None,
                input_tokens=100,
                cached_input_tokens=20,
                cache_write_tokens=10,
                output_tokens=30,
                reasoning_tokens=12,
                total_tokens=130,
                estimated_cost_usd=0.0002645,
                pricing_effective_date="2026-07-19",
            ),
            usage_file_path="data/llm_usage.jsonl",
        )

        output = StringIO()
        with (
            patch(
                "futures_intelligence.main._load_smoke_test_information",
                return_value=information,
            ) as load_information,
            redirect_stdout(output),
        ):
            exit_code = _run_llm_smoke_test(analyst=analyst)

        self.assertEqual(exit_code, 0)
        load_information.assert_called_once_with(SMOKE_TEST_REPORT_PATH)
        analyst.analyze_smoke_test.assert_called_once()
        supplied_information = analyst.analyze_smoke_test.call_args.args[0]
        self.assertIs(supplied_information, information)
        self.assertIn("Real LLM smoke test succeeded", output.getvalue())
        self.assertIn("Model: test-model", output.getvalue())
        self.assertIn("Market Direction: Bullish", output.getvalue())
        self.assertIn("Input Tokens: 100", output.getvalue())
        self.assertIn("Cached Input Tokens: 20", output.getvalue())
        self.assertIn("Output Tokens: 30", output.getvalue())
        self.assertIn("Total Tokens: 130", output.getvalue())
        self.assertIn("Estimated Cost (USD): 0.0002645", output.getvalue())
        self.assertIn("Usage Record Path: data/llm_usage.jsonl", output.getvalue())
        configured_model.assert_called_once_with()

    @patch("futures_intelligence.main._configured_llm_model", return_value="test-model")
    def test_smoke_test_failure_prints_error_and_returns_nonzero(
        self, configured_model: Mock
    ) -> None:
        analyst = Mock()
        analyst.analyze_smoke_test.return_value = LLMSmokeTestResult(
            success=False,
            error="OPENAI_API_KEY is not set.",
        )

        output = StringIO()
        with redirect_stdout(output):
            exit_code = _run_llm_smoke_test(analyst=analyst)

        self.assertEqual(exit_code, 1)
        self.assertIn("LLM smoke test failed: OPENAI_API_KEY is not set.", output.getvalue())
        configured_model.assert_called_once_with()

    def test_smoke_test_missing_report_returns_nonzero_without_api_call(self) -> None:
        analyst = Mock()
        missing_path = SMOKE_TEST_REPORT_PATH.with_name("missing-report.txt")

        output = StringIO()
        with redirect_stdout(output):
            exit_code = _run_llm_smoke_test(
                analyst=analyst,
                sample_path=missing_path,
            )

        self.assertEqual(exit_code, 1)
        analyst.analyze_smoke_test.assert_not_called()
        self.assertIn("unable to read", output.getvalue().lower())


if __name__ == "__main__":
    unittest.main()


def _successful_pdf_result(url: str) -> HuataiPdfExtractionResult:
    return HuataiPdfExtractionResult(
        canonical_pdf_url=url,
        byte_count=1,
        page_count=1,
        document_metadata=(),
        extracted_text="text",
        extracted_character_count=4,
        extraction_status="success",
        failure_category=None,
        ocr_required=False,
    )


def _huatai_pdf_source() -> dict[str, object]:
    """Return a disabled registry-shaped Huatai PDF source for CLI tests."""
    return {
        "name": "Huatai Futures",
        "source_type": "research_report",
        "provider": "huatai_futures",
        "collection_mode": "huatai_pdf_listing",
        "enabled": False,
        "url": "https://htfc.com/main/yjzx/ssrdph/index.shtml",
        "max_reports": 3,
        "category": ["macro", "energy"],
        "regions": ["China"],
        "reliability_score": 5,
        "pdf_extraction": {
            "socket_timeout_seconds": 10,
            "download_deadline_seconds": 30,
            "max_response_bytes": 20_971_520,
            "max_redirects": 3,
            "max_selected_pdfs": 3,
            "max_pages": 50,
            "max_content_stream_bytes_per_page": 8_388_608,
            "max_content_stream_bytes": 67_108_864,
            "max_extracted_characters_per_page": 20_000,
            "max_extracted_characters": 250_000,
            "parser_deadline_seconds": 20,
            "minimum_meaningful_characters": 20,
        },
    }


def _huatai_pdf_market_information() -> MarketInformation:
    """Return normalized provenance without exposing report body text."""
    return MarketInformation(
        title="Huatai PDF report",
        source="Huatai Futures",
        source_type="research_report",
        published_time=datetime(
            2026,
            7,
            29,
            tzinfo=timezone(timedelta(hours=8)),
        ),
        content="This raw report content must never appear in smoke output.",
        category=("macro", "energy"),
        regions=("China",),
        reliability_score=5,
        url="https://htfc.com/wz_upload/report.pdf",
        metadata={
            "published_time_precision": "date",
            "report_type": "专题报告",
            "report_author": "Report analyst",
            "document_metadata_author": "PDF author",
            "page_count": 12,
            "byte_count": 2048,
            "extracted_character_count": 512,
            "parser_diagnostics": [
                "non_zero_indexed_xref",
                "PARSER_DIAGNOSTIC_SECRET_MARKER_3B51",
            ],
            "document_metadata": {
                "Author": "PDF author",
                "Marker": "FULL_DOCUMENT_METADATA_SECRET_MARKER_7E91",
            },
        },
    )
