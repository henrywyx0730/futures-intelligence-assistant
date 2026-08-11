"""Tests for the synthetic Chinese deterministic-analysis corpus."""

from collections import Counter
from dataclasses import FrozenInstanceError
import copy
import json
import re
import unittest
from unittest.mock import Mock, patch

from tests import chinese_deterministic_analysis_cases as corpus_cases
from tests.chinese_deterministic_analysis_cases import (
    ALLOWED_COMMODITY_KEYS,
    ALLOWED_ENFORCEMENT_PHASES,
    ALLOWED_SCENARIO_TAGS,
    ALLOWED_SIGNAL_KINDS,
    FIXTURE_PATH,
    VALID_DIRECTIONS,
    _parse_corpus_payload,
    cases_for_phase,
    cases_with_tag,
    load_chinese_deterministic_corpus,
)


class ChineseDeterministicAnalysisCorpusTests(unittest.TestCase):
    """Validate the standalone synthetic corpus fixture."""

    def setUp(self) -> None:
        self.corpus = load_chinese_deterministic_corpus()

    def test_fixture_loads_with_g3b1_qualification_enforcement(self) -> None:
        """Activate reviewed qualification semantics without G3b2 or G4."""
        self.assertTrue(FIXTURE_PATH.is_file())
        self.assertEqual(self.corpus.schema_version, 1)
        self.assertEqual(
            self.corpus.active_enforcement_phases,
            ("g2", "g3a", "g3b1"),
        )
        self.assertNotIn("g3b2", self.corpus.active_enforcement_phases)
        self.assertNotIn("g4", self.corpus.active_enforcement_phases)
        self.assertEqual(len(cases_for_phase(self.corpus, "g2")), 55)
        self.assertEqual(len(cases_for_phase(self.corpus, "g3a")), 12)
        self.assertEqual(len(cases_for_phase(self.corpus, "g3b1")), 11)
        self.assertEqual(len(cases_for_phase(self.corpus, "g3b2")), 5)

    def test_has_exact_case_count_and_primary_category_distribution(self) -> None:
        """Keep the initial corpus deliberately small and reviewable."""
        self.assertEqual(len(self.corpus.cases), 58)
        self.assertEqual(
            Counter(case.primary_category for case in self.corpus.cases),
            {
                "commodity_identity": 16,
                "simple_factual_direction": 12,
                "negation_or_uncertainty": 8,
                "qualified_or_conflicting": 8,
                "relative_value": 6,
                "false_positive_guard": 8,
            },
        )

    def test_cases_have_valid_identifiers_text_provenance_and_expectations(self) -> None:
        """Validate every public corpus field without invoking production behavior."""
        case_ids = [case.id for case in self.corpus.cases]
        self.assertEqual(len(case_ids), len(set(case_ids)))
        for case in self.corpus.cases:
            with self.subTest(case_id=case.id):
                self.assertRegex(case.id, r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
                self.assertLessEqual(len(case.id), 80)
                self.assertTrue(case.title)
                self.assertLessEqual(len(case.title), 180)
                self.assertLessEqual(len(case.content), 180)
                self.assertEqual(case.provenance, "synthetic_original")
                self.assertTrue(case.scenario_tags)
                self.assertEqual(len(case.scenario_tags), len(set(case.scenario_tags)))
                self.assertTrue(set(case.scenario_tags) <= ALLOWED_SCENARIO_TAGS)
                self.assertTrue(set(case.expected.commodity_keys) <= ALLOWED_COMMODITY_KEYS)
                self.assertTrue(
                    set(case.expected.no_commodity_keys) <= ALLOWED_COMMODITY_KEYS
                )
                self.assertFalse(
                    set(case.expected.commodity_keys)
                    & set(case.expected.no_commodity_keys)
                )
                self.assertIn(case.expected.market_direction, VALID_DIRECTIONS)
                self.assertEqual(
                    len(case.expected.reasoning_tags),
                    len(set(case.expected.reasoning_tags)),
                )
                self.assertTrue(
                    all(
                        re.fullmatch(r"[a-z][a-z0-9_]*", tag)
                        for tag in case.expected.reasoning_tags
                    )
                )
                self.assertIn(case.expected.signal_kind, ALLOWED_SIGNAL_KINDS)
                self.assertTrue(
                    set(case.enforcement.as_tuple()) <= ALLOWED_ENFORCEMENT_PHASES
                )
                self.assertTrue(case.notes)
                self.assertLessEqual(len(case.notes), 240)

    def test_utf8_text_and_representative_cases_survive_loading(self) -> None:
        """Preserve original Chinese fixture text and reviewed boundary examples."""
        cases_by_id = {case.id: case for case in self.corpus.cases}
        self.assertEqual(cases_by_id["live-hog-basic-identity"].title, "生猪现货成交平稳。")
        for case_id in (
            "low-sulfur-fuel-oil-identity",
            "pork-context-not-live-hog",
            "alumina-not-primary-aluminum",
            "crude-oil-clause-local-negation",
            "fuel-oil-horizon-conflict",
            "aluminum-cast-alloy-arbitrage",
            "refined-products-demand-no-commodity",
        ):
            self.assertIn(case_id, cases_by_id)

    def test_relative_value_cases_remain_neutral_and_deferred_to_g4(self) -> None:
        """Prevent arbitrage language from becoming an outright direction in G1."""
        cases = cases_with_tag(self.corpus, "relative_value")
        self.assertEqual(len(cases), 6)
        for case in cases:
            with self.subTest(case_id=case.id):
                self.assertEqual(case.expected.market_direction, "neutral")
                self.assertEqual(case.expected.signal_kind, "relative_value")
                self.assertEqual(case.enforcement.direction, "not_applicable")
                self.assertEqual(case.enforcement.relative_value, "g4")

    def test_fixture_is_synthetic_and_contains_no_urls_or_source_markers(self) -> None:
        """Ensure the corpus does not preserve report prose or source-specific text."""
        forbidden_markers = ("华泰期货", "免责声明", "请仔细阅读本报告")
        for case in self.corpus.cases:
            with self.subTest(case_id=case.id):
                rendered = "\n".join((case.title, case.content, case.notes))
                self.assertNotRegex(rendered, r"https?://|www\\.")
                self.assertFalse(any(marker in rendered for marker in forbidden_markers))

    def test_phase_and_tag_helpers_preserve_fixture_order(self) -> None:
        """Expose deterministic filters for later phase-specific test activation."""
        expected_g2_ids = [
            case.id
            for case in self.corpus.cases
            if "g2" in case.enforcement.as_tuple()
        ]
        self.assertEqual(
            [case.id for case in cases_for_phase(self.corpus, "g2")],
            expected_g2_ids,
        )
        expected_energy_ids = [
            case.id for case in self.corpus.cases if "energy" in case.scenario_tags
        ]
        self.assertEqual(
            [case.id for case in cases_with_tag(self.corpus, "energy")],
            expected_energy_ids,
        )

    def test_loader_returns_immutable_tuples_and_frozen_cases(self) -> None:
        """Prevent test callers from silently changing the reviewed corpus."""
        self.assertIsInstance(self.corpus.cases, tuple)
        self.assertIsInstance(self.corpus.cases[0].scenario_tags, tuple)
        self.assertIsInstance(self.corpus.cases[0].expected.commodity_keys, tuple)
        with self.assertRaises(FrozenInstanceError):
            self.corpus.cases[0].title = "changed"  # type: ignore[misc]

    def test_loader_rejects_representative_malformed_payloads(self) -> None:
        """Keep malformed future corpus edits from being silently normalized."""
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        malformed_cases = {
            "duplicate id": lambda value: value["cases"][1].__setitem__(
                "id", value["cases"][0]["id"]
            ),
            "invalid direction": lambda value: value["cases"][0]["expected"].__setitem__(
                "market_direction", "upward"
            ),
            "invalid phase": lambda value: value["cases"][0]["enforcement"].__setitem__(
                "commodity", "g9"
            ),
            "relative phase on identity": lambda value: value["cases"][0][
                "enforcement"
            ].__setitem__("relative_value", "g4"),
            "direction phase on relative value": lambda value: value["cases"][44][
                "enforcement"
            ].__setitem__("commodity", "g3a"),
            "missing field": lambda value: value["cases"][0].pop("notes"),
            "unexpected field": lambda value: value["cases"][0].__setitem__(
                "extra", "value"
            ),
            "commodity overlap": lambda value: value["cases"][0]["expected"].__setitem__(
                "no_commodity_keys", ["live_hog"]
            ),
            "oversize title": lambda value: value["cases"][0].__setitem__(
                "title", "测" * 181
            ),
            "invalid provenance": lambda value: value["cases"][0].__setitem__(
                "provenance", "external"
            ),
        }
        for name, mutate in malformed_cases.items():
            with self.subTest(name=name):
                malformed_payload = copy.deepcopy(payload)
                mutate(malformed_payload)
                with self.assertRaises(ValueError):
                    _parse_corpus_payload(malformed_payload)

    def test_loader_rejects_category_semantic_contradictions(self) -> None:
        """Keep future category labels from contradicting their expected outcome."""
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        malformed_cases = {
            "identity bullish": lambda value: value["cases"][0]["expected"].__setitem__(
                "market_direction", "bullish"
            ),
            "identity factual kind": lambda value: value["cases"][0]["expected"].__setitem__(
                "signal_kind", "fundamental_fact"
            ),
            "identity missing assertion": lambda value: (
                value["cases"][0]["expected"].__setitem__("commodity_keys", []),
                value["cases"][0]["expected"].__setitem__("no_commodity_keys", []),
            ),
            "factual neutral": lambda value: value["cases"][16]["expected"].__setitem__(
                "market_direction", "neutral"
            ),
            "guard positive commodity": lambda value: (
                value["cases"][50]["expected"].__setitem__(
                    "commodity_keys", ["crude_oil"]
                ),
                value["cases"][50]["expected"].__setitem__("no_commodity_keys", []),
            ),
            "guard missing exclusion": lambda value: value["cases"][50][
                "expected"
            ].__setitem__("no_commodity_keys", []),
        }
        for name, mutate in malformed_cases.items():
            with self.subTest(name=name):
                malformed_payload = copy.deepcopy(payload)
                mutate(malformed_payload)
                with self.assertRaises(ValueError):
                    _parse_corpus_payload(malformed_payload)

    def test_loader_rejects_g3b2_cases_relabelled_as_g3b1(self) -> None:
        """Keep conflict and horizon semantics out of the qualification-only phase."""
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        for case_id in (
            "crude-oil-supply-demand-conflict",
            "fuel-oil-horizon-conflict",
        ):
            with self.subTest(case_id=case_id):
                malformed_payload = copy.deepcopy(payload)
                case = next(
                    item
                    for item in malformed_payload["cases"]
                    if item["id"] == case_id
                )
                case["expected"]["signal_kind"] = "conditional_signal"
                case["enforcement"]["direction"] = "g3b1"

                with self.assertRaisesRegex(ValueError, "G3B2 semantic"):
                    _parse_corpus_payload(malformed_payload)

    def test_loader_rejects_duplicate_json_keys(self) -> None:
        """Reject duplicate names before JSON decoding can apply last-value-wins."""
        raw_fixture = FIXTURE_PATH.read_text(encoding="utf-8")
        duplicate_top_level = raw_fixture.replace(
            '  "schema_version": 1,',
            '  "schema_version": 1,\n  "schema_version": 1,',
            1,
        )
        duplicate_nested = raw_fixture.replace(
            '"market_direction": "neutral", "reasoning_tags"',
            '"market_direction": "neutral", "market_direction": "neutral", "reasoning_tags"',
            1,
        )
        for name, raw_json, duplicate_key in (
            ("top-level", duplicate_top_level, "schema_version"),
            ("nested expected", duplicate_nested, "market_direction"),
        ):
            with self.subTest(name=name):
                fixture_path = Mock()
                fixture_path.read_text.return_value = raw_json
                with patch.object(corpus_cases, "FIXTURE_PATH", fixture_path):
                    with self.assertRaisesRegex(ValueError, duplicate_key):
                        load_chinese_deterministic_corpus()

    def test_loader_rejects_whitespace_only_required_text(self) -> None:
        """Reject semantically empty required text without normalizing valid text."""
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        malformed_cases = {
            "whitespace title": lambda value: value["cases"][0].__setitem__(
                "title", "   "
            ),
            "whitespace notes": lambda value: value["cases"][0].__setitem__(
                "notes", "\t\n"
            ),
            "whitespace non-empty content": lambda value: value["cases"][0].__setitem__(
                "content", "  \t"
            ),
        }
        for name, mutate in malformed_cases.items():
            with self.subTest(name=name):
                malformed_payload = copy.deepcopy(payload)
                mutate(malformed_payload)
                with self.assertRaises(ValueError):
                    _parse_corpus_payload(malformed_payload)

        payload["cases"][0]["content"] = ""
        loaded = _parse_corpus_payload(payload)
        self.assertEqual(loaded.cases[0].content, "")
        self.assertEqual(loaded.cases[0].title, "生猪现货成交平稳。")


if __name__ == "__main__":
    unittest.main()
