"""Integrity tests for the isolated synthetic commodity-relevance corpus."""

from dataclasses import FrozenInstanceError
import copy
import json
import unittest
from unittest.mock import Mock, patch

from tests import chinese_commodity_relevance_cases as corpus_cases
from tests.chinese_commodity_relevance_cases import (
    ALLOWED_TAGS,
    FIXTURE_PATH,
    _parse_corpus_payload,
    cases_for_phase,
    cases_with_tag,
    load_chinese_commodity_relevance_corpus,
)


class ChineseCommodityRelevanceCorpusTests(unittest.TestCase):
    """Keep relevance expectations synthetic, exact, immutable, and ordered."""

    def setUp(self) -> None:
        self.corpus = load_chinese_commodity_relevance_corpus()

    def test_fixture_shape_and_phase_are_exact(self) -> None:
        self.assertTrue(FIXTURE_PATH.is_file())
        self.assertEqual(self.corpus.schema_version, 1)
        self.assertEqual(self.corpus.active_enforcement_phases, ("g2_5b",))
        self.assertEqual(len(self.corpus.cases), 18)
        self.assertEqual(cases_for_phase(self.corpus, "g2_5b"), self.corpus.cases)

    def test_cases_preserve_synthetic_contracts_and_role_order(self) -> None:
        ids = [case.id for case in self.corpus.cases]
        self.assertEqual(len(ids), len(set(ids)))
        for case in self.corpus.cases:
            with self.subTest(case_id=case.id):
                self.assertRegex(case.id, r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
                self.assertTrue(case.title)
                self.assertLessEqual(len(case.title), 180)
                self.assertLessEqual(len(case.content), 180)
                self.assertEqual(case.provenance, "synthetic_original")
                self.assertTrue(case.scenario_tags)
                self.assertTrue(set(case.scenario_tags) <= ALLOWED_TAGS)
                self.assertEqual(len(case.scenario_tags), len(set(case.scenario_tags)))
                self.assertEqual(len(case.expected.lexical_keys), len(set(case.expected.lexical_keys)))
                self.assertFalse(set(case.expected.primary_keys) & set(case.expected.mentioned_keys))
                self.assertEqual(
                    set(case.expected.primary_keys) | set(case.expected.mentioned_keys),
                    set(case.expected.lexical_keys),
                )
                self.assertEqual(
                    [key for key in case.expected.lexical_keys if key in case.expected.primary_keys],
                    list(case.expected.primary_keys),
                )
                self.assertEqual(
                    [key for key in case.expected.lexical_keys if key in case.expected.mentioned_keys],
                    list(case.expected.mentioned_keys),
                )
                self.assertNotRegex("\n".join((case.title, case.content, case.notes)), r"https?://|www\\.")
                self.assertFalse(any(marker in case.title + case.content + case.notes for marker in ("华泰期货", "免责声明", "请仔细阅读本报告")))

    def test_representative_policies_and_required_case_types_exist(self) -> None:
        cases = {case.id: case for case in self.corpus.cases}
        self.assertEqual(cases["macro-live-hog-mentioned"].expected.primary_keys, ())
        self.assertEqual(cases["macro-live-hog-mentioned"].expected.mentioned_keys, ("live_hog",))
        self.assertEqual(cases["ethylene-glycol-primary-crude-mentioned"].expected.lexical_keys, ("crude_oil", "ethylene_glycol"))
        self.assertEqual(cases["aluminum-cast-alloy-co-primary"].expected.primary_keys, ("aluminum", "cast_aluminum_alloy"))
        self.assertTrue(any(len(case.expected.primary_keys) > 1 for case in self.corpus.cases))
        self.assertTrue(any(not case.expected.primary_keys for case in self.corpus.cases))
        self.assertTrue(any(not case.expected.lexical_keys for case in self.corpus.cases))
        self.assertEqual(
            [case.id for case in cases_with_tag(self.corpus, "propylene")],
            [case.id for case in self.corpus.cases if "propylene" in case.scenario_tags],
        )

    def test_loader_values_are_immutable(self) -> None:
        self.assertIsInstance(self.corpus.cases, tuple)
        self.assertIsInstance(self.corpus.cases[0].scenario_tags, tuple)
        self.assertIsInstance(self.corpus.cases[0].expected.lexical_keys, tuple)
        with self.assertRaises(FrozenInstanceError):
            self.corpus.cases[0].title = "changed"  # type: ignore[misc]

    def test_loader_rejects_malformed_payloads_and_duplicate_keys(self) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        mutations = {
            "missing field": lambda value: value["cases"][0].pop("notes"),
            "unexpected field": lambda value: value["cases"][0].__setitem__("extra", "x"),
            "duplicate id": lambda value: value["cases"][1].__setitem__("id", value["cases"][0]["id"]),
            "bad tag": lambda value: value["cases"][0]["scenario_tags"].append("unknown"),
            "role overlap": lambda value: value["cases"][0]["expected"].__setitem__("mentioned_keys", ["propylene"]),
            "oversize title": lambda value: value["cases"][0].__setitem__("title", "测" * 181),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                malformed = copy.deepcopy(payload)
                mutate(malformed)
                with self.assertRaises(ValueError):
                    _parse_corpus_payload(malformed)

        raw_fixture = FIXTURE_PATH.read_text(encoding="utf-8")
        duplicate = raw_fixture.replace('  "schema_version": 1,', '  "schema_version": 1,\n  "schema_version": 1,', 1)
        fixture_path = Mock()
        fixture_path.read_text.return_value = duplicate
        with patch.object(corpus_cases, "FIXTURE_PATH", fixture_path):
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                load_chinese_commodity_relevance_corpus()

    def test_loader_rejects_unknown_or_whitespace_commodity_keys(self) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        mutations = {
            "unknown lexical": lambda value: value["cases"][0]["expected"].update(
                lexical_keys=["not_a_commodity"],
                primary_keys=["not_a_commodity"],
                mentioned_keys=[],
            ),
            "unknown mentioned": lambda value: value["cases"][1]["expected"].update(
                lexical_keys=["not_a_commodity"],
                primary_keys=[],
                mentioned_keys=["not_a_commodity"],
            ),
            "whitespace key": lambda value: value["cases"][0]["expected"].update(
                lexical_keys=["   "], primary_keys=["   "], mentioned_keys=[]
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                malformed = copy.deepcopy(payload)
                mutate(malformed)
                with self.assertRaisesRegex(ValueError, "corpus.cases"):
                    _parse_corpus_payload(malformed)

    def test_loader_preserves_empty_and_authored_content_but_rejects_whitespace(self) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(_parse_corpus_payload(payload).cases[6].content, "原油成本变化影响油制乙二醇利润。")

        empty_control = copy.deepcopy(payload)
        empty_control["cases"][0]["content"] = ""
        self.assertEqual(_parse_corpus_payload(empty_control).cases[0].content, "")

        for whitespace in ("   ", "\t\n"):
            with self.subTest(whitespace=repr(whitespace)):
                malformed = copy.deepcopy(payload)
                malformed["cases"][0]["content"] = whitespace
                with self.assertRaisesRegex(ValueError, "corpus.cases"):
                    _parse_corpus_payload(malformed)
