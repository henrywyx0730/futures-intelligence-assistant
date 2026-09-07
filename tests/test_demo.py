"""Tests for the bounded, deterministic Huatai presentation command."""

from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import unittest
from unittest.mock import patch

from futures_intelligence.analyst.commodity_relevance import (
    CommodityRelevanceAssessment,
    CommodityRelevanceResolver,
)
from futures_intelligence.analyst.rule_based import RuleBasedAnalyst
from futures_intelligence.demo import HuataiDemoError, format_htfc_demo
from futures_intelligence.models import MarketAnalysis, MarketInformation
from futures_intelligence.processing.ranker import InformationRanker


def make_demo_information(title: str, content: str) -> MarketInformation:
    """Create one synthetic Huatai report without source-scope commodity hints."""
    return MarketInformation(
        title=title,
        source="Huatai Futures",
        source_type="research_report",
        published_time=datetime(2026, 7, 27, tzinfo=timezone.utc),
        content=content,
        category=("energy",),
        regions=("China",),
        reliability_score=3,
        url="https://htfc.com/wz_upload/synthetic.pdf",
    )


def synthetic_demo_reports() -> list[MarketInformation]:
    """Return three reviewed reports that exercise scoped aggregation."""
    return [
        make_demo_information(
            "原油专题",
            "原油供应收紧。REPORT_BODY_SECRET_CRUDE",
        ),
        make_demo_information(
            "燃料油专题",
            "燃料油供应宽松。REPORT_BODY_SECRET_FUEL",
        ),
        make_demo_information(
            "原油与燃料油专题",
            "原油供应收紧；燃料油供应宽松。REPORT_BODY_SECRET_CROSS",
        ),
    ]


def evaluate_demo_reports(
    reports: list[MarketInformation],
) -> tuple[
    list[MarketInformation],
    list[MarketAnalysis],
    tuple[CommodityRelevanceAssessment, ...],
]:
    """Exercise the real deterministic ranking, analysis, and relevance stack."""
    ranked = InformationRanker().rank(reports)
    analyses = RuleBasedAnalyst().analyze(ranked)
    resolver = CommodityRelevanceResolver()
    relevance = tuple(resolver.assess(report) for report in ranked)
    return ranked, analyses, relevance


class HuataiDemoTests(unittest.TestCase):
    """Validate the offline demo while faking only Huatai acquisition."""

    def test_formats_real_deterministic_analysis_and_aggregation(self) -> None:
        reports = synthetic_demo_reports()
        evaluated = evaluate_demo_reports(reports)

        output = format_htfc_demo(*evaluated)

        self.assertIn("FUTURES INTELLIGENCE DEMO", output)
        self.assertIn("Huatai reports collected: 3", output)
        self.assertEqual(output.count("REPORT "), 3)
        self.assertIn("Title: 原油专题", output)
        self.assertIn("Title: 燃料油专题", output)
        self.assertIn("Title: 原油与燃料油专题", output)
        self.assertIn("Published: 2026-07-27T00:00:00+00:00", output)
        self.assertIn("Source: Huatai Futures", output)
        self.assertIn("Primary commodities: Crude Oil", output)
        self.assertIn("Primary commodities: Fuel Oil", output)
        self.assertIn("Report direction: bullish", output)
        self.assertIn("Report direction: bearish", output)
        self.assertIn("Report direction: neutral", output)
        self.assertIn("Directional provenance: direct_fundamental", output)
        self.assertIn("Directional provenance: cross_commodity_abstention", output)
        self.assertIn("- Crude Oil: bullish", output)
        self.assertIn("- Fuel Oil: bearish", output)
        self.assertIn(
            "Crude Oil\nDirection: bullish\nConfidence: 67/100\nReports: 2",
            output,
        )
        self.assertIn(
            "Fuel Oil\nDirection: bearish\nConfidence: 67/100\nReports: 2",
            output,
        )
        self.assertIn(
            "Global direction: neutral\nGlobal confidence: 70/100\nReports analyzed: 3",
            output,
        )
        self.assertIn("DEMO BRIEF", output)
        self.assertIn("- Crude Oil — bullish (67/100, 2 reports)", output)
        self.assertIn("- Fuel Oil — bearish (67/100, 2 reports)", output)
        self.assertIn("Market-wide view: neutral (70/100)", output)
        self.assertIn(
            "Demo complete: 3 reports analyzed, 2 commodity views generated.",
            output,
        )
        self.assertTrue(all(report.commodities == () for report in reports))
        self.assertNotIn("REPORT_BODY_SECRET", output)

    def test_bounds_report_text_and_reasoning_presentation(self) -> None:
        report = make_demo_information(
            "原油专题 " + "T" * 600,
            "原油供应收紧。" + "REPORT_BODY_SECRET_LONG" * 100,
        )
        evaluated = evaluate_demo_reports([report])

        output = format_htfc_demo(*evaluated)

        title_line = next(
            line for line in output.splitlines() if line.startswith("Title: ")
        )
        self.assertLessEqual(len(title_line.removeprefix("Title: ")), 300)
        reasoning_lines = [
            line for line in output.splitlines() if line.startswith("- ")
        ]
        self.assertTrue(
            all(len(line.removeprefix("- ")) <= 240 for line in reasoning_lines)
        )
        self.assertNotIn(report.content, output)

    def test_formats_empty_scoped_evidence_as_a_resolved_demo_state(self) -> None:
        report = make_demo_information(
            "原油展望",
            "预计原油供应收紧。REPORT_BODY_SECRET_QUALIFIED",
        )

        output = format_htfc_demo(*evaluate_demo_reports([report]))

        self.assertIn("Report direction: neutral", output)
        self.assertIn("Directional provenance: qualified_only", output)
        self.assertIn("Commodity-scoped direction:\n- none resolved", output)
        self.assertNotIn("REPORT_BODY_SECRET_QUALIFIED", output)

    def test_rejects_empty_or_over_limit_report_batches(self) -> None:
        with self.assertRaisesRegex(HuataiDemoError, "no Huatai research reports"):
            format_htfc_demo([], [], ())
        with self.assertRaisesRegex(HuataiDemoError, "more than 3"):
            format_htfc_demo(
                synthetic_demo_reports() + [synthetic_demo_reports()[0]],
                [],
                (),
            )

    def test_command_reuses_bounded_collection_and_has_no_pipeline_side_effects(
        self,
    ) -> None:
        import futures_intelligence.main as main_module

        runner = getattr(main_module, "_run_htfc_demo", None)
        self.assertTrue(callable(runner))
        reports = synthetic_demo_reports()
        output = StringIO()

        with (
            patch(
                "futures_intelligence.main._collect_bounded_htfc_pdf_market_information",
                return_value=reports,
            ) as collect,
            patch(
                "futures_intelligence.analyst.llm.LLMAnalyst.analyze",
                side_effect=AssertionError("demo must not invoke an LLM"),
            ) as llm_analyze,
            patch(
                "futures_intelligence.analyst.router.LLMAnalyst",
                side_effect=AssertionError("demo must not construct an LLM analyst"),
            ) as llm_constructor,
            patch(
                "futures_intelligence.main._openai_client_for_smoke_test",
                side_effect=AssertionError("demo must not construct an OpenAI client"),
            ) as openai_client_factory,
            patch(
                "futures_intelligence.main.MorningBriefService",
                side_effect=AssertionError("demo must not run persistence service"),
            ) as service,
            redirect_stdout(output),
        ):
            exit_code = runner()

        self.assertEqual(exit_code, 0)
        collect.assert_called_once_with(3)
        llm_analyze.assert_not_called()
        llm_constructor.assert_not_called()
        openai_client_factory.assert_not_called()
        service.assert_not_called()
        self.assertIn("Demo complete: 3 reports analyzed", output.getvalue())

    def test_command_reports_expected_failures_and_propagates_unexpected_errors(
        self,
    ) -> None:
        import futures_intelligence.main as main_module

        runner = getattr(main_module, "_run_htfc_demo", None)
        self.assertTrue(callable(runner))

        for result, expected in (
            ([], "no Huatai research reports"),
            (OSError("bounded collector unavailable"), "bounded collector unavailable"),
        ):
            with self.subTest(expected=expected):
                output = StringIO()
                patcher = patch(
                    "futures_intelligence.main._collect_bounded_htfc_pdf_market_information",
                    side_effect=result if isinstance(result, Exception) else None,
                    return_value=result if isinstance(result, list) else None,
                )
                with patcher, redirect_stdout(output):
                    exit_code = runner()
                self.assertEqual(exit_code, 1)
                self.assertIn(expected, output.getvalue())

        expected_error = KeyError("unexpected demo failure")
        with patch(
            "futures_intelligence.main._collect_bounded_htfc_pdf_market_information",
            side_effect=expected_error,
        ):
            with self.assertRaises(KeyError) as captured:
                runner()
        self.assertIs(captured.exception, expected_error)


if __name__ == "__main__":
    unittest.main()
