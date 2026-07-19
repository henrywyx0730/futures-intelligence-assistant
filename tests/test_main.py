"""Tests for command-line output in the application entry point."""

from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import unittest
from unittest.mock import Mock, patch

from futures_intelligence.analyst import LLMSmokeTestResult
from futures_intelligence.main import (
    SMOKE_TEST_REPORT_PATH,
    _load_smoke_test_information,
    _parse_arguments,
    _run_llm_smoke_test,
    main,
)
from futures_intelligence.models import MarketAnalysis, MarketInformation
from futures_intelligence.utils.health import HealthReport


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

        output = StringIO()
        with self.assertRaises(SystemExit), redirect_stdout(output):
            _parse_arguments(["--help"])
        self.assertIn("llm-smoke-test", output.getvalue())

    @patch("futures_intelligence.main._run_llm_smoke_test", return_value=1)
    def test_main_dispatches_llm_smoke_test_command(self, smoke_test: Mock) -> None:
        self.assertEqual(main(["llm-smoke-test"]), 1)
        smoke_test.assert_called_once_with()

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
