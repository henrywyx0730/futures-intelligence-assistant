"""G2 enforcement for synthetic Chinese commodity-identity contracts."""

from dataclasses import dataclass
import unittest

from futures_intelligence.analyst.commodity_matcher import CommodityMatcher
from tests.chinese_deterministic_analysis_cases import (
    cases_for_phase,
    load_chinese_deterministic_corpus,
)


@dataclass(frozen=True)
class _CorpusInformation:
    """Minimal immutable matcher input that preserves authored empty content."""

    title: str
    content: str


class _CapturingCommodityMatcher(CommodityMatcher):
    """Record real matcher inputs to verify exact corpus fidelity."""

    def __init__(self) -> None:
        super().__init__()
        self.inputs: list[_CorpusInformation] = []

    def match(self, information: _CorpusInformation):  # type: ignore[override]
        self.inputs.append(information)
        return super().match(information)  # type: ignore[arg-type]


class ChineseCommodityMatchingCorpusTests(unittest.TestCase):
    """Exercise only the active G2 commodity expectation axis."""

    def test_active_g2_cases_match_their_approved_commodity_contracts(self) -> None:
        """Keep fixture order and avoid coupling identity tests to directional rules."""
        corpus = load_chinese_deterministic_corpus()
        self.assertIn("g2", corpus.active_enforcement_phases)
        g2_cases = tuple(
            case
            for case in cases_for_phase(corpus, "g2")
            if case.enforcement.commodity == "g2"
        )
        self.assertTrue(any(case.expected.commodity_keys for case in g2_cases))
        self.assertTrue(any(case.expected.no_commodity_keys for case in g2_cases))

        matcher = _CapturingCommodityMatcher()
        saw_empty_content = False
        for case in g2_cases:
            with self.subTest(case_id=case.id):
                information = _CorpusInformation(
                    title=case.title,
                    content=case.content,
                )
                self.assertEqual(information.title, case.title)
                self.assertEqual(information.content, case.content)
                actual_keys = tuple(
                    match.commodity_key for match in matcher.match(information)
                )

                self.assertEqual(actual_keys, case.expected.commodity_keys)
                for commodity_key in case.expected.no_commodity_keys:
                    self.assertNotIn(commodity_key, actual_keys)
                saw_empty_content = saw_empty_content or case.content == ""

        self.assertTrue(saw_empty_content)
        self.assertTrue(any(item.content == "" for item in matcher.inputs))
        self.assertEqual(
            tuple((item.title, item.content) for item in matcher.inputs),
            tuple((case.title, case.content) for case in g2_cases),
        )


if __name__ == "__main__":
    unittest.main()
