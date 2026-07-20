"""Tests for command-line output in the application entry point."""

from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from futures_intelligence.analyst import LLMAnalyst, LLMSmokeTestResult
from futures_intelligence.main import (
    SMOKE_TEST_REPORT_PATH,
    _load_smoke_test_information,
    _parse_arguments,
    _run_llm_routing_smoke_test,
    _run_llm_smoke_test,
    _run_htfc_report_smoke_test,
    main,
)
from futures_intelligence.fetchers import (
    FetchedResearchReport,
    HuataiFetchResult,
    HuataiListingDiscovery,
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

        output = StringIO()
        with self.assertRaises(SystemExit), redirect_stdout(output):
            _parse_arguments(["--help"])
        self.assertIn("llm-smoke-test", output.getvalue())
        self.assertIn("llm-routing-smoke-test", output.getvalue())
        self.assertIn("htfc-report-smoke-test", output.getvalue())

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
                html_detail_links=(report.url,),
                pdf_attachment_links=("https://htfc.com/wz_upload/report.pdf",),
                unsupported_links=("https://example.com/nope",),
            ),
        )
        output = StringIO()

        with redirect_stdout(output):
            exit_code = _run_htfc_report_smoke_test(fetcher=fetcher)  # type: ignore[arg-type]

        self.assertEqual(exit_code, 0)
        fetcher.fetch_reports.assert_called_once_with()
        self.assertIn("Discovered HTML detail links: 1", output.getvalue())
        self.assertIn("Discovered PDF attachments: 1", output.getvalue())
        self.assertIn("Unsupported links skipped: 1", output.getvalue())
        self.assertIn("Huatai report", output.getvalue())

    def test_huatai_pdf_only_smoke_test_reports_precise_failure(self) -> None:
        fetcher = Mock()
        fetcher.fetch_reports.return_value = HuataiFetchResult(
            discovered_link_count=0,
            selected_urls=(),
            reports=(),
            discovery=HuataiListingDiscovery(
                pdf_attachment_links=("https://htfc.com/wz_upload/report.pdf",),
            ),
        )
        output = StringIO()

        with redirect_stdout(output):
            exit_code = _run_htfc_report_smoke_test(fetcher=fetcher)  # type: ignore[arg-type]

        self.assertEqual(exit_code, 1)
        self.assertIn("Discovered HTML detail links: 0", output.getvalue())
        self.assertIn("Discovered PDF attachments: 1", output.getvalue())
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
