"""Tests for the bounded, deterministic Huatai presentation command."""

from contextlib import redirect_stdout
from datetime import date, datetime, timezone
from io import StringIO
import unittest
from unittest.mock import Mock, patch

from futures_intelligence.analyst.commodity_relevance import (
    CommodityRelevanceAssessment,
    CommodityRelevanceResolver,
)
from futures_intelligence.analyst.rule_based import RuleBasedAnalyst
import futures_intelligence.demo as demo_module
from futures_intelligence.demo import HuataiDemoError, format_htfc_demo
from futures_intelligence.fetchers import (
    HuataiListingDiscovery,
    HuataiReportListingItem,
)
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


def make_listing_item(
    position: int,
    title: str,
    *,
    url: str | None = None,
) -> HuataiReportListingItem:
    """Create one already ordered Huatai PDF listing item."""
    return HuataiReportListingItem(
        canonical_url=url or f"https://htfc.com/wz_upload/report-{position}.pdf",
        link_kind="pdf_attachment",
        listing_title=title,
        publication_date=date(2026, 9, 7),
        report_type="专题报告",
        section_position=0,
        item_position=position,
    )


class HuataiDemoTests(unittest.TestCase):
    """Validate the offline demo while faking only Huatai acquisition."""

    def test_formats_real_deterministic_analysis_and_aggregation(self) -> None:
        reports = synthetic_demo_reports()
        evaluated = evaluate_demo_reports(reports)
        original_directions = tuple(
            analysis.market_direction for analysis in evaluated[1]
        )
        original_scoped_directions = tuple(
            tuple(
                evidence.market_direction
                for evidence in analysis.commodity_directional_evidence
            )
            for analysis in evaluated[1]
        )

        output = format_htfc_demo(*evaluated)

        self.assertIn("期货情报 DEMO", output)
        self.assertIn("已选华泰报告：3", output)
        self.assertIn("选样规则：优先选择标题明确命中已跟踪品种的华泰报告", output)
        self.assertEqual(output.count("\n报告 "), 3)
        self.assertIn("标题：原油专题", output)
        self.assertIn("标题：燃料油专题", output)
        self.assertIn("标题：原油与燃料油专题", output)
        self.assertIn("发布日期：2026-07-27T00:00:00+00:00", output)
        self.assertIn("来源：Huatai Futures", output)
        self.assertIn("主要品种：Crude Oil", output)
        self.assertIn("主要品种：Fuel Oil", output)
        self.assertIn("报告方向：偏多 (bullish)", output)
        self.assertIn("报告方向：偏空 (bearish)", output)
        self.assertIn("报告方向：中性 (neutral)", output)
        self.assertIn("判定依据：direct_fundamental", output)
        self.assertIn("判定依据：cross_commodity_abstention", output)
        self.assertIn("- Crude Oil：偏多 (bullish)", output)
        self.assertIn("- Fuel Oil：偏空 (bearish)", output)
        self.assertIn(
            "Crude Oil\n方向：偏多 (bullish)\n聚合方向置信度：67/100\n报告数：2",
            output,
        )
        self.assertIn(
            "Fuel Oil\n方向：偏空 (bearish)\n聚合方向置信度：67/100\n报告数：2",
            output,
        )
        self.assertIn(
            "市场整体方向：中性 (neutral)\n聚合方向置信度：70/100\n分析报告数：3",
            output,
        )
        self.assertIn("早间视图 / DEMO BRIEF", output)
        self.assertIn(
            "- Crude Oil — 偏多 (bullish)，聚合方向置信度 67/100，2 篇报告",
            output,
        )
        self.assertIn(
            "- Fuel Oil — 偏空 (bearish)，聚合方向置信度 67/100，2 篇报告",
            output,
        )
        self.assertIn("市场整体：中性 (neutral)，聚合方向置信度 70/100", output)
        self.assertIn(
            "Demo 完成：已分析 3 篇报告，生成 2 个品种视图。",
            output,
        )
        self.assertEqual(
            tuple(analysis.market_direction for analysis in evaluated[1]),
            original_directions,
        )
        self.assertEqual(
            tuple(
                tuple(
                    evidence.market_direction
                    for evidence in analysis.commodity_directional_evidence
                )
                for analysis in evaluated[1]
            ),
            original_scoped_directions,
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
            line for line in output.splitlines() if line.startswith("标题：")
        )
        self.assertLessEqual(len(title_line.removeprefix("标题：")), 300)
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

        self.assertIn("报告方向：中性 (neutral)", output)
        self.assertIn("判定依据：qualified_only", output)
        self.assertIn("品种级方向：\n- 未解析出品种级方向", output)
        self.assertNotIn("REPORT_BODY_SECRET_QUALIFIED", output)

    def test_formats_zero_commodity_neutral_result_as_an_intentional_state(self) -> None:
        reports = [
            make_demo_information(f"宏观跟踪 {index}", "政策信息保持稳定。")
            for index in range(3)
        ]

        output = format_htfc_demo(*evaluate_demo_reports(reports))

        self.assertIn("本次所选报告未形成明确的 Primary 品种视图。", output)
        self.assertIn("市场整体方向：中性 (neutral)", output)
        self.assertIn("聚合方向置信度：0/100", output)
        self.assertIn("分析报告数：3", output)
        self.assertIn("Demo 完成：已分析 3 篇报告，生成 0 个品种视图。", output)

    def test_selects_canonical_commodity_titles_before_broader_reports(self) -> None:
        selector = getattr(demo_module, "select_htfc_demo_pdf_items", None)
        self.assertTrue(callable(selector))
        items = (
            make_listing_item(0, "华泰期货宏观政策跟踪"),
            make_listing_item(
                1,
                "华泰期货黑色专题报告20260906：成本推升与复产博弈，关注煤炭价格对成本影响",
            ),
            make_listing_item(2, "华泰期货宏观数据跟踪"),
            make_listing_item(3, "华泰期货原油专题报告"),
            make_listing_item(4, "华泰期货燃料油专题报告"),
            make_listing_item(5, "华泰期货白银专题报告"),
        )

        discovery = HuataiListingDiscovery(
            report_items=items,
            recognized_report_section_count=3,
            recognized_report_list_count=3,
        )
        with (
            patch(
                "futures_intelligence.demo.MarketAnalysisAggregator",
                side_effect=AssertionError("selection must not aggregate"),
            ) as aggregator,
            patch(
                "futures_intelligence.analyst.rule_based.RuleBasedAnalyst",
                side_effect=AssertionError("selection must not analyze"),
            ) as analyst,
        ):
            selected = selector(discovery.report_items)

        self.assertEqual(selected, items[3:6])
        aggregator.assert_not_called()
        analyst.assert_not_called()

    def test_selection_fills_with_newest_broader_titles_without_duplicates(self) -> None:
        selector = getattr(demo_module, "select_htfc_demo_pdf_items", None)
        self.assertTrue(callable(selector))
        relevant = make_listing_item(1, "华泰期货原油专题报告")
        items = (
            make_listing_item(0, "华泰期货宏观政策跟踪"),
            relevant,
            make_listing_item(2, "华泰期货宏观数据跟踪"),
            make_listing_item(3, "华泰期货行业观察"),
            make_listing_item(4, "重复记录", url=relevant.canonical_url),
        )

        selected = selector(items)

        self.assertEqual(selected, (relevant, items[0], items[2]))
        self.assertEqual(len({item.canonical_url for item in selected}), 3)

    def test_selection_prioritizes_live_bitumen_title_before_broader_fallbacks(self) -> None:
        selector = getattr(demo_module, "select_htfc_demo_pdf_items", None)
        self.assertTrue(callable(selector))
        bitumen = make_listing_item(
            3,
            (
                "华泰期货石油沥青专题20260904：供应端矛盾支撑市场强现实，"
                "预期仍存变数——结合华南沥青调研情况分析"
            ),
        )
        items = (
            make_listing_item(0, "华泰期货宏观政策跟踪"),
            make_listing_item(
                1,
                "华泰期货黑色专题报告20260906：成本推升与复产博弈，"
                "关注煤炭价格对成本影响",
            ),
            make_listing_item(2, "华泰期货美国就业数据跟踪"),
            bitumen,
            make_listing_item(4, "华泰期货国债专题报告"),
            make_listing_item(5, "华泰期货化工行业观察"),
        )

        selected = selector(items)

        self.assertEqual(selected, (bitumen, items[0], items[1]))

    def test_selection_falls_back_to_first_three_when_no_title_is_relevant(self) -> None:
        selector = getattr(demo_module, "select_htfc_demo_pdf_items", None)
        self.assertTrue(callable(selector))
        items = tuple(
            make_listing_item(index, f"华泰期货宏观跟踪 {index}")
            for index in range(5)
        )

        self.assertEqual(selector(items), items[:3])

    def test_selection_caps_relevant_titles_before_pdf_processing(self) -> None:
        selector = getattr(demo_module, "select_htfc_demo_pdf_items", None)
        self.assertTrue(callable(selector))
        items = tuple(
            make_listing_item(index, f"华泰期货原油专题报告 {index}")
            for index in range(10)
        )

        self.assertEqual(selector(items), items[:3])

    def test_demo_acquisition_processes_only_the_selected_listing_items(self) -> None:
        import futures_intelligence.main as main_module

        collector = Mock()
        items = (
            make_listing_item(0, "华泰期货宏观政策跟踪"),
            make_listing_item(1, "华泰期货宏观数据跟踪"),
            make_listing_item(2, "华泰期货行业观察"),
            make_listing_item(3, "华泰期货原油专题报告"),
            make_listing_item(4, "华泰期货燃料油专题报告"),
            make_listing_item(5, "华泰期货白银专题报告"),
        )
        reports = synthetic_demo_reports()
        collector.discover_pdf_items.return_value = items
        collector.collect_selected_pdf_items.return_value = reports
        helper = getattr(
            main_module,
            "_collect_commodity_focused_htfc_demo_information",
            None,
        )
        self.assertTrue(callable(helper))

        with patch(
            "futures_intelligence.main._configured_htfc_pdf_collector",
            return_value=collector,
        ):
            result = helper(3)

        self.assertIs(result, reports)
        collector.discover_pdf_items.assert_called_once_with()
        collector.collect_selected_pdf_items.assert_called_once_with(items[3:6])

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
                "futures_intelligence.main._collect_commodity_focused_htfc_demo_information",
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
        self.assertIn("Demo 完成：已分析 3 篇报告", output.getvalue())

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
                    "futures_intelligence.main._collect_commodity_focused_htfc_demo_information",
                    side_effect=result if isinstance(result, Exception) else None,
                    return_value=result if isinstance(result, list) else None,
                )
                with patcher, redirect_stdout(output):
                    exit_code = runner()
                self.assertEqual(exit_code, 1)
                self.assertIn(expected, output.getvalue())

        expected_error = KeyError("unexpected demo failure")
        with patch(
            "futures_intelligence.main._collect_commodity_focused_htfc_demo_information",
            side_effect=expected_error,
        ):
            with self.assertRaises(KeyError) as captured:
                runner()
        self.assertIs(captured.exception, expected_error)


if __name__ == "__main__":
    unittest.main()
