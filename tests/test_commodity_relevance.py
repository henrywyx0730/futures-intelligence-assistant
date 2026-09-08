"""Tests for deterministic title-primary commodity relevance assessment."""

from dataclasses import FrozenInstanceError, dataclass
from datetime import datetime, timezone
import unittest

from futures_intelligence.analyst.commodity_matcher import (
    CommodityMatch,
    CommodityMatchEvidence,
    CommodityMatcher,
    CommodityOccurrence,
)
from futures_intelligence.analyst.commodity_relevance import (
    CommodityRelevance,
    CommodityRelevanceAssessment,
    CommodityRelevanceError,
    CommodityRelevanceResolver,
    MENTIONED_REASON,
    PRIMARY_REASON,
)
from futures_intelligence.models import MarketInformation
from tests.chinese_commodity_relevance_cases import (
    cases_for_phase,
    load_chinese_commodity_relevance_corpus,
)


def make_information(title: str, content: str, **fields: object) -> MarketInformation:
    return MarketInformation(
        title=title,
        source="Synthetic source",
        source_type="research_report",
        published_time=datetime(2026, 8, 3, tzinfo=timezone.utc),
        content=content,
        **fields,
    )


class _EvidenceMatcher:
    def __init__(self, result: object | None = None, error: BaseException | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def match_with_evidence(self, information: MarketInformation) -> object:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


@dataclass(frozen=True)
class _CorpusInformation:
    """Minimal immutable input retaining authored fixture text exactly."""

    title: str
    content: str


class _RecordingMatcher(CommodityMatcher):
    """Record exact inputs while delegating lexical work to the real matcher."""

    def __init__(self) -> None:
        super().__init__()
        self.inputs: list[_CorpusInformation] = []

    def match_with_evidence(self, information: _CorpusInformation) -> CommodityMatchEvidence:  # type: ignore[override]
        self.inputs.append(information)
        return super().match_with_evidence(information)  # type: ignore[arg-type]


class _FalseyEvidenceMatcher(_EvidenceMatcher):
    """A valid collaborator whose false truth value must not replace it."""

    def __bool__(self) -> bool:
        return False


class CommodityRelevanceTests(unittest.TestCase):
    """Validate immutable lexical-only relevance roles and contract boundaries."""

    def test_enforces_every_active_synthetic_relevance_case(self) -> None:
        corpus = load_chinese_commodity_relevance_corpus()
        cases = cases_for_phase(corpus, "g2_5b")
        matcher = _RecordingMatcher()
        resolver = CommodityRelevanceResolver(matcher=matcher)

        self.assertEqual(len(cases), 18)
        for case in cases:
            with self.subTest(case_id=case.id):
                information = _CorpusInformation(case.title, case.content)
                assessment = resolver.assess(information)  # type: ignore[arg-type]
                self.assertEqual(
                    tuple(match.commodity_key for match in assessment.lexical_matches),
                    case.expected.lexical_keys,
                )
                self.assertEqual(
                    tuple(item.commodity_key for item in assessment.primary),
                    case.expected.primary_keys,
                )
                self.assertEqual(
                    tuple(item.commodity_key for item in assessment.mentioned),
                    case.expected.mentioned_keys,
                )
        self.assertEqual(len(matcher.inputs), 18)
        self.assertEqual(
            tuple((item.title, item.content) for item in matcher.inputs),
            tuple((case.title, case.content) for case in cases),
        )
        self.assertIn("", tuple(item.content for item in matcher.inputs))

    def test_title_content_aliases_counts_and_reasons_are_deterministic(self) -> None:
        information = make_information("乙二醇专题", "乙二醇库存下降，乙二醇进口减少。")

        assessment = CommodityRelevanceResolver().assess(information)

        self.assertEqual(len(assessment.primary), 1)
        relevance = assessment.primary[0]
        self.assertEqual(relevance.commodity_key, "ethylene_glycol")
        self.assertEqual(relevance.title_aliases, ("乙二醇",))
        self.assertEqual(relevance.content_aliases, ("乙二醇",))
        self.assertEqual(relevance.title_occurrence_count, 1)
        self.assertEqual(relevance.content_occurrence_count, 2)
        self.assertEqual(relevance.reasons, ("Matched a tracked commodity alias in the report title.",))
        self.assertFalse(hasattr(relevance, "score"))

    def test_preserves_roles_order_and_ignores_nonlexical_information_fields(self) -> None:
        information = make_information(
            "原铝与铸造铝合金价差专题",
            "正文未提及其他品种。",
            commodities=("crude_oil",),
            category=("macro",),
            reliability_score=1,
            metadata={"market_direction": "bearish"},
        )

        assessment = CommodityRelevanceResolver().assess(information)

        self.assertEqual(
            tuple(item.commodity_key for item in assessment.primary),
            ("aluminum", "cast_aluminum_alloy"),
        )
        self.assertEqual(assessment.mentioned, ())
        self.assertEqual(information.commodities, ("crude_oil",))

    def test_content_only_and_zero_lexical_cases_are_valid(self) -> None:
        resolver = CommodityRelevanceResolver()
        mentioned = resolver.assess(make_information("宏观政策跟踪", "正文提到生猪产能。"))
        empty = resolver.assess(make_information("宏观政策跟踪", "财政安排成为讨论重点。"))

        self.assertEqual(mentioned.primary, ())
        self.assertEqual(mentioned.mentioned[0].role, "mentioned")
        self.assertEqual(
            mentioned.mentioned[0].reasons,
            ("Matched tracked commodity aliases only in report content.",),
        )
        self.assertEqual(empty.lexical_matches, ())
        self.assertEqual(empty.primary, ())
        self.assertEqual(empty.mentioned, ())

    def test_chinese_silver_title_and_content_evidence_have_expected_relevance_roles(self) -> None:
        resolver = CommodityRelevanceResolver()

        title_assessment = resolver.assess(
            make_information("白银期货动态策略研究", "Details.")
        )
        content_assessment = resolver.assess(
            make_information("量化策略报告", "正文讨论白银库存。")
        )

        self.assertEqual(
            tuple(item.commodity_key for item in title_assessment.primary), ("silver",)
        )
        self.assertEqual(title_assessment.mentioned, ())
        self.assertEqual(content_assessment.primary, ())
        self.assertEqual(
            tuple(item.commodity_key for item in content_assessment.mentioned), ("silver",)
        )

    def test_bitumen_title_is_primary_and_body_only_evidence_is_mentioned(self) -> None:
        resolver = CommodityRelevanceResolver()
        live_title = (
            "华泰期货石油沥青专题20260904：供应端矛盾支撑市场强现实，"
            "预期仍存变数——结合华南沥青调研情况分析"
        )

        live_assessment = resolver.assess(
            make_information(live_title, "General market context.")
        )
        title_assessment = resolver.assess(
            make_information("石油沥青专题", "General market context.")
        )
        content_assessment = resolver.assess(
            make_information("宏观政策观察", "石油沥青库存受到关注。")
        )

        for label, assessment in (
            ("live title", live_assessment),
            ("short title", title_assessment),
        ):
            with self.subTest(label=label):
                self.assertEqual(
                    tuple(item.commodity_key for item in assessment.primary),
                    ("bitumen",),
                )
                self.assertEqual(assessment.primary[0].commodity_label, "Bitumen")
                self.assertEqual(assessment.primary[0].role, "primary")
                self.assertEqual(assessment.primary[0].reasons, (PRIMARY_REASON,))
                self.assertEqual(assessment.mentioned, ())

        self.assertEqual(content_assessment.primary, ())
        self.assertEqual(
            tuple(item.commodity_key for item in content_assessment.mentioned),
            ("bitumen",),
        )
        self.assertEqual(content_assessment.mentioned[0].commodity_label, "Bitumen")
        self.assertEqual(content_assessment.mentioned[0].role, "mentioned")
        self.assertEqual(content_assessment.mentioned[0].reasons, (MENTIONED_REASON,))

    def test_copper_title_topic_evidence_is_primary_while_body_only_is_mentioned(self) -> None:
        resolver = CommodityRelevanceResolver()

        title_assessment = resolver.assess(
            make_information("某期货铜专题报告", "电解铜库存变化。")
        )
        content_assessment = resolver.assess(
            make_information("宏观政策跟踪", "电解铜库存变化。")
        )

        self.assertEqual(
            tuple(item.commodity_key for item in title_assessment.lexical_matches),
            ("copper",),
        )
        self.assertEqual(
            tuple(item.commodity_key for item in title_assessment.primary), ("copper",)
        )
        self.assertEqual(title_assessment.mentioned, ())
        self.assertEqual(content_assessment.primary, ())
        self.assertEqual(
            tuple(item.commodity_key for item in content_assessment.mentioned), ("copper",)
        )

    def test_calls_matcher_once_and_propagates_unexpected_exception(self) -> None:
        actual = CommodityMatcher().match_with_evidence(make_information("乙二醇专题", "正文。"))
        matcher = _EvidenceMatcher(actual)
        resolver = CommodityRelevanceResolver(matcher=matcher)  # type: ignore[arg-type]

        resolver.assess(make_information("乙二醇专题", "正文。"))
        self.assertEqual(matcher.calls, 1)

        failure = KeyError("unexpected matcher failure")
        with self.assertRaisesRegex(KeyError, "unexpected matcher failure"):
            CommodityRelevanceResolver(matcher=_EvidenceMatcher(error=failure)).assess(
                make_information("Title", "Content")
            )

    def test_preserves_and_calls_a_falsey_injected_matcher_once(self) -> None:
        information = make_information("gold", "Details.")
        match = CommodityMatch("gold", "Gold", ("gold",))
        occurrence = CommodityOccurrence("gold", "Gold", "gold", "title", 0, 4)
        matcher = _FalseyEvidenceMatcher(CommodityMatchEvidence((match,), (occurrence,)))

        assessment = CommodityRelevanceResolver(matcher=matcher).assess(information)  # type: ignore[arg-type]

        self.assertEqual(matcher.calls, 1)
        self.assertEqual(assessment.primary[0].commodity_key, "gold")

    def test_accepts_case_insensitive_injected_source_slice_and_rejects_wrong_slice(self) -> None:
        information = make_information("Gold outlook", "Details.")
        case_insensitive_match = CommodityMatch("gold", "Gold", ("GOLD",))
        case_insensitive_occurrence = CommodityOccurrence(
            "gold", "Gold", "GOLD", "title", 0, 4
        )

        assessment = CommodityRelevanceResolver(
            matcher=_EvidenceMatcher(
                CommodityMatchEvidence(
                    (case_insensitive_match,), (case_insensitive_occurrence,)
                )
            )
        ).assess(information)

        self.assertEqual(assessment.primary[0].commodity_key, "gold")
        wrong_slice = CommodityMatchEvidence(
            (CommodityMatch("gold", "Gold", ("Silver",)),),
            (CommodityOccurrence("gold", "Gold", "Silver", "title", 0, 4),),
        )
        with self.assertRaises(CommodityRelevanceError):
            CommodityRelevanceResolver(matcher=_EvidenceMatcher(wrong_slice)).assess(
                information
            )

    def test_rejects_malformed_injected_evidence(self) -> None:
        match = CommodityMatch("gold", "Gold", ("gold",))
        valid_occurrence = CommodityOccurrence("gold", "Gold", "gold", "title", 0, 4)
        valid = CommodityMatchEvidence((match,), (valid_occurrence,))
        malformed = (
            None,
            object(),
            CommodityMatchEvidence([], (valid_occurrence,)),  # type: ignore[arg-type]
            CommodityMatchEvidence((match,), []),  # type: ignore[arg-type]
            CommodityMatchEvidence((object(),), (valid_occurrence,)),  # type: ignore[arg-type]
            CommodityMatchEvidence((match,), (object(),)),  # type: ignore[arg-type]
            CommodityMatchEvidence((), (valid_occurrence,)),
            CommodityMatchEvidence((match,), ()),
            CommodityMatchEvidence((match,), (valid_occurrence, valid_occurrence)),
            CommodityMatchEvidence((match,), (CommodityOccurrence("gold", "Gold", "gold", "invalid", 0, 4),)),  # type: ignore[arg-type]
            CommodityMatchEvidence((match,), (CommodityOccurrence("gold", "Gold", "gold", "title", -1, 4),)),
            CommodityMatchEvidence((match,), (CommodityOccurrence("gold", "Gold", "gold", "title", 4, 4),)),
            CommodityMatchEvidence((match,), (CommodityOccurrence("gold", "Gold", "gold", "title", 0, 5),)),
            CommodityMatchEvidence((match,), (CommodityOccurrence("gold", "Gold", "gold", "title", 1, 4),)),
            CommodityMatchEvidence((match,), (CommodityOccurrence("gold", "Gold", "gold", "title", True, 4),)),
            CommodityMatchEvidence((match,), (CommodityOccurrence("gold", "Gold", "gold", "title", 0, True),)),
            CommodityMatchEvidence((match,), (CommodityOccurrence("gold", "Gold", "silver", "title", 0, 4),)),
            CommodityMatchEvidence((match,), (CommodityOccurrence("gold", "Silver", "gold", "title", 0, 4),)),
        )
        information = make_information("gold", "Content")
        for evidence in malformed:
            with self.subTest(evidence_type=type(evidence).__name__):
                with self.assertRaises(CommodityRelevanceError):
                    CommodityRelevanceResolver(matcher=_EvidenceMatcher(evidence)).assess(information)  # type: ignore[arg-type]

        self.assertEqual(
            CommodityRelevanceResolver(matcher=_EvidenceMatcher(valid)).assess(information).primary[0].commodity_key,
            "gold",
        )

    def test_assessment_requires_labels_to_match_lexical_identity(self) -> None:
        match = CommodityMatch("gold", "Gold", ("gold",))
        primary = CommodityRelevance(
            "gold", "Gold", "primary", ("gold",), (), 1, 0, (PRIMARY_REASON,)
        )
        mentioned = CommodityRelevance(
            "gold", "Gold", "mentioned", (), ("gold",), 0, 1, (MENTIONED_REASON,)
        )
        self.assertEqual(
            CommodityRelevanceAssessment((match,), (primary,), ()).primary[0].commodity_label,
            "Gold",
        )

        invalid_assessments = (
            lambda: CommodityRelevanceAssessment(
                (match,),
                (
                    CommodityRelevance(
                        "gold", "Silver", "primary", ("gold",), (), 1, 0, (PRIMARY_REASON,)
                    ),
                ),
                (),
            ),
            lambda: CommodityRelevanceAssessment(
                (match,),
                (),
                (
                    CommodityRelevance(
                        "gold", "Silver", "mentioned", (), ("gold",), 0, 1, (MENTIONED_REASON,)
                    ),
                ),
            ),
            lambda: CommodityRelevanceAssessment(
                (match, CommodityMatch("gold", "Silver", ("gold",))),
                (primary,),
                (),
            ),
        )
        for construct in invalid_assessments:
            with self.subTest(construct=construct):
                with self.assertRaises(CommodityRelevanceError):
                    construct()

    def test_relevance_results_are_frozen_and_tuple_backed(self) -> None:
        assessment = CommodityRelevanceResolver().assess(
            make_information("乙二醇专题", "乙二醇库存变化。")
        )
        self.assertIsInstance(assessment.lexical_matches, tuple)
        self.assertIsInstance(assessment.primary, tuple)
        self.assertIsInstance(assessment.primary[0].title_aliases, tuple)
        with self.assertRaises(FrozenInstanceError):
            assessment.primary[0].role = "mentioned"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            assessment.primary = ()  # type: ignore[misc]

    def test_relevance_counts_require_corresponding_field_aliases(self) -> None:
        invalid_values = (
            ("primary", (), (), 1, 0, ("Matched a tracked commodity alias in the report title.",)),
            ("mentioned", (), (), 0, 1, ("Matched tracked commodity aliases only in report content.",)),
        )

        for role, title_aliases, content_aliases, title_count, content_count, reasons in invalid_values:
            with self.subTest(role=role):
                with self.assertRaises(CommodityRelevanceError):
                    CommodityRelevance(
                        "gold",
                        "Gold",
                        role,  # type: ignore[arg-type]
                        title_aliases,
                        content_aliases,
                        title_count,
                        content_count,
                        reasons,
                    )
