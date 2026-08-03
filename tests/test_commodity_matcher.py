"""Tests for deterministic article-level commodity matching."""

from datetime import datetime, timezone
import unittest
from unittest.mock import Mock, patch

from futures_intelligence.analyst import commodity_matcher
from futures_intelligence.analyst.commodity_matcher import (
    CommodityDefinition,
    CommodityMatch,
    CommodityMatcher,
)
from futures_intelligence.models import MarketInformation


def make_information(title: str, content: str, **fields: object) -> MarketInformation:
    """Create normalized information for article-level commodity matching."""
    return MarketInformation(
        title=title,
        source="Test Source",
        source_type="test",
        published_time=datetime(2026, 7, 20, tzinfo=timezone.utc),
        content=content,
        **fields,
    )


class CommodityMatcherTests(unittest.TestCase):
    """Validate immutable, knowledge-ordered article-level commodity matches."""

    def setUp(self) -> None:
        self.matcher = CommodityMatcher()

    def test_returns_configured_ordered_matches_from_title_and_content(self) -> None:
        information = make_information(
            "Gold and crude oil outlook", "Copper inventory data was released."
        )

        matches = self.matcher.match(information)

        self.assertEqual(
            [(match.commodity_key, match.commodity_label) for match in matches],
            [
                ("crude_oil", "Crude Oil"),
                ("copper", "Copper"),
                ("gold", "Gold"),
            ],
        )
        self.assertEqual(
            self.matcher.commodity_order,
            tuple(match.commodity_key for match in self.matcher.commodity_ordered_matches),
        )

    def test_ignores_source_scope_commodities_without_article_evidence(self) -> None:
        information = make_information(
            "Central bank statement",
            "The policy statement was published.",
            commodities=("crude_oil", "gold", "wheat"),
        )

        self.assertEqual(self.matcher.match(information), ())

    def test_preserves_ambiguous_alias_exclusions(self) -> None:
        information = make_information("Soybean oil update", "Agricultural products.")

        self.assertEqual(self.matcher.match(information), ())

    def test_matches_bounded_chinese_commodity_identities(self) -> None:
        cases = {
            "生猪供应增加": ("live_hog",),
            "生猪期货成交活跃": ("live_hog",),
            "原油库存下降": ("crude_oil",),
            "WTI原油库存下降": ("crude_oil",),
            "布伦特原油供应收紧": ("crude_oil",),
            "燃料油库存下降": ("fuel_oil",),
            "低硫燃料油现货偏紧": ("low_sulfur_fuel_oil",),
            "原铝供应增加": ("aluminum",),
            "电解铝库存去化": ("aluminum",),
            "铝锭到货下降": ("aluminum",),
            "铸造铝合金需求改善": ("cast_aluminum_alloy",),
        }

        for text, expected_keys in cases.items():
            with self.subTest(text=text):
                actual_keys = tuple(
                    match.commodity_key
                    for match in self.matcher.match(make_information(text, "Details."))
                )
                self.assertEqual(actual_keys, expected_keys)

    def test_rejects_chinese_false_positive_contexts(self) -> None:
        cases = {
            "猪肉消费增加": (),
            "猪油库存增加": (),
            "豆油库存下降": (),
            "棕榈油供应增加": (),
            "菜籽油价格上涨": (),
            "成品油需求改善": (),
            "炼厂开工率下降": (),
            "普通铝合金订单下降": (),
            "氧化铝价格上涨": (),
        }

        for text, expected_keys in cases.items():
            with self.subTest(text=text):
                actual_keys = tuple(
                    match.commodity_key
                    for match in self.matcher.match(make_information(text, "Details."))
                )
                self.assertEqual(actual_keys, expected_keys)

    def test_resolves_overlapping_and_separate_commodity_spans(self) -> None:
        cases = {
            "原油与燃料油库存同步下降": ("crude_oil", "fuel_oil"),
            "原油与低硫燃料油供应变化": ("crude_oil", "low_sulfur_fuel_oil"),
            "低硫燃料油": ("low_sulfur_fuel_oil",),
            "fuel oil": ("fuel_oil",),
            "low sulfur fuel oil": ("low_sulfur_fuel_oil",),
            "crude oil and fuel oil": ("crude_oil", "fuel_oil"),
        }

        for text, expected_keys in cases.items():
            with self.subTest(text=text):
                actual_keys = tuple(
                    match.commodity_key
                    for match in self.matcher.match(make_information(text, "Details."))
                )
                self.assertEqual(actual_keys, expected_keys)

    def test_preserves_english_ascii_boundaries_and_local_oil_exclusions(self) -> None:
        cases = {
            "oil价格": ("crude_oil",),
            "oilseed outlook": (),
            "soil conditions": (),
            "soybean oil outlook": (),
            "palm oil outlook": (),
            "vegetable oil outlook": (),
            "crude oil and soybean oil": ("crude_oil",),
        }

        for text, expected_keys in cases.items():
            with self.subTest(text=text):
                actual_keys = tuple(
                    match.commodity_key
                    for match in self.matcher.match(make_information(text, "Details."))
                )
                self.assertEqual(actual_keys, expected_keys)

    def test_matches_propylene_in_chinese_and_english_fields(self) -> None:
        cases = (
            ("丙烯专题报告", "General market context."),
            ("Chemical report", "丙烯供应出现变化。"),
            ("Chemical report", "丙烯期货成交活跃。"),
            ("Chemical report", "Propylene market conditions changed."),
        )

        for title, content in cases:
            with self.subTest(title=title, content=content):
                self.assertEqual(
                    tuple(
                        match.commodity_key
                        for match in self.matcher.match(make_information(title, content))
                    ),
                    ("propylene",),
                )

    def test_excludes_propylene_derivatives_but_preserves_local_occurrences(self) -> None:
        excluded_cases = (
            "聚丙烯库存下降",
            "聚丙烯期货成交活跃",
            "丙烯腈市场回顾",
            "丙烯酸价格变化",
            "丙烯酰胺装置检修",
            "环氧丙烷供应增加",
            "丙烯画材料介绍",
            "丙烯颜料销售增长",
            "polypropylene market conditions changed.",
        )
        retained_cases = (
            "聚丙烯需求下降，但丙烯供应仍然偏紧。",
            "丙烯腈生产利润下降，上游丙烯价格变化。",
            "Polypropylene demand declined while propylene supply tightened.",
        )

        for text in excluded_cases:
            with self.subTest(excluded=text):
                self.assertNotIn(
                    "propylene",
                    tuple(
                        match.commodity_key
                        for match in self.matcher.match(make_information(text, "Details."))
                    ),
                )

        for text in retained_cases:
            with self.subTest(retained=text):
                self.assertIn(
                    "propylene",
                    tuple(
                        match.commodity_key
                        for match in self.matcher.match(make_information(text, "Details."))
                    ),
                )

        title_content_matches = self.matcher.match(
            make_information("聚丙烯周报", "正文另行讨论丙烯现货市场。")
        )
        self.assertEqual(
            tuple(match.commodity_key for match in title_content_matches),
            ("propylene",),
        )

    def test_matches_ethylene_glycol_in_chinese_and_english_fields(self) -> None:
        cases = (
            ("乙二醇库存专题", "General market context."),
            ("Chemical report", "乙二醇港口库存继续变化。"),
            ("Chemical report", "乙二醇期货成交活跃。"),
            ("Chemical report", "乙二醇期权市场启动。"),
            ("Chemical report", "Ethylene glycol inventories declined."),
            ("Chemical report", "Monoethylene glycol supply increased."),
            ("Chemical report", "Mono ethylene glycol demand improved."),
        )

        for title, content in cases:
            with self.subTest(title=title, content=content):
                self.assertEqual(
                    tuple(
                        match.commodity_key
                        for match in self.matcher.match(make_information(title, content))
                    ),
                    ("ethylene_glycol",),
                )

    def test_excludes_ethylene_glycol_derivatives_but_preserves_local_occurrences(self) -> None:
        excluded_cases = (
            "聚乙二醇需求增加",
            "乙二醇单丁醚价格变化",
            "乙二醇醚市场回顾",
            "二甘醇供应增加",
            "三甘醇价格变化",
            "丙二醇装置检修",
        )
        retained_cases = (
            "聚乙二醇需求下降，但乙二醇供应仍然偏紧。",
            "乙二醇单丁醚价格变化，乙二醇期货成交活跃。",
        )

        for text in excluded_cases:
            with self.subTest(excluded=text):
                self.assertNotIn(
                    "ethylene_glycol",
                    tuple(
                        match.commodity_key
                        for match in self.matcher.match(make_information(text, "Details."))
                    ),
                )

        for text in retained_cases:
            with self.subTest(retained=text):
                self.assertIn(
                    "ethylene_glycol",
                    tuple(
                        match.commodity_key
                        for match in self.matcher.match(make_information(text, "Details."))
                    ),
                )

    def test_does_not_treat_unconfigured_acronyms_as_new_commodities(self) -> None:
        for text in ("EG库存下降", "MEG供应增加", "PL期货成交活跃"):
            with self.subTest(text=text):
                self.assertNotIn(
                    "ethylene_glycol",
                    tuple(
                        match.commodity_key
                        for match in self.matcher.match(make_information(text, "Details."))
                    ),
                )
                self.assertNotIn(
                    "propylene",
                    tuple(
                        match.commodity_key
                        for match in self.matcher.match(make_information(text, "Details."))
                    ),
                )

    def test_preserves_registry_order_for_new_commodity_combinations(self) -> None:
        cases = {
            "乙二醇与原油成本同步变化。": ("crude_oil", "ethylene_glycol"),
            "丙烯与原油价格关联增强。": ("crude_oil", "propylene"),
            "丙烯与乙二醇库存均发生变化。": ("propylene", "ethylene_glycol"),
        }

        for text, expected_keys in cases.items():
            with self.subTest(text=text):
                self.assertEqual(
                    tuple(
                        match.commodity_key
                        for match in self.matcher.match(make_information(text, "Details."))
                    ),
                    expected_keys,
                )

        matches = self.matcher.match(
            make_information("乙二醇专题", "原油成本影响乙二醇利润。")
        )
        self.assertEqual(
            tuple(match.commodity_key for match in matches),
            ("crude_oil", "ethylene_glycol"),
        )

    def test_does_not_form_new_aliases_across_title_and_content_boundaries(self) -> None:
        cases = (
            ("丙", "烯市场", "propylene", "丙烯"),
            ("乙二", "醇库存", "ethylene_glycol", "乙二醇"),
            ("Ethylene", "glycol market", "ethylene_glycol", "ethylene glycol"),
            (
                "Monoethylene",
                "glycol market",
                "ethylene_glycol",
                "monoethylene glycol",
            ),
        )

        for title, content, absent_key, absent_alias in cases:
            with self.subTest(title=title, content=content):
                matches = self.matcher.match(make_information(title, content))
                aliases = tuple(
                    alias for match in matches for alias in match.matched_aliases
                )
                self.assertNotIn(absent_key, tuple(match.commodity_key for match in matches))
                self.assertNotIn(absent_alias, aliases)

    def test_retains_public_immutable_ordered_match_contract(self) -> None:
        matches = self.matcher.match(
            make_information("Crude oil", "Fuel oil and oil prices were discussed.")
        )

        self.assertIsInstance(matches, tuple)
        self.assertTrue(all(isinstance(match, CommodityMatch) for match in matches))
        self.assertEqual(
            tuple(match.commodity_key for match in matches),
            ("crude_oil", "fuel_oil"),
        )
        self.assertEqual(matches[0].matched_aliases, ("crude oil", "oil"))
        with self.assertRaises(AttributeError):
            matches[0].matched_aliases += ("new alias",)

    def test_title_and_content_occurrences_both_participate_without_duplicates(self) -> None:
        matches = self.matcher.match(
            make_information("Crude oil update", "Fuel oil and oil prices remain active.")
        )

        self.assertEqual(
            tuple(match.commodity_key for match in matches),
            ("crude_oil", "fuel_oil"),
        )
        self.assertEqual(matches[0].matched_aliases, ("crude oil", "oil"))

    def test_does_not_form_aliases_across_title_and_content_boundaries(self) -> None:
        cases = (
            (
                "Fuel",
                "oil outlook",
                "fuel_oil",
                "fuel oil",
                ("crude_oil",),
            ),
            (
                "Crude",
                "oil inventory falls",
                None,
                "crude oil",
                ("crude_oil",),
            ),
            (
                "Low sulfur",
                "fuel oil outlook",
                "low_sulfur_fuel_oil",
                "low sulfur fuel oil",
                ("fuel_oil",),
            ),
            (
                "低硫",
                "燃料油库存下降",
                "low_sulfur_fuel_oil",
                "低硫燃料油",
                ("fuel_oil",),
            ),
        )

        for title, content, absent_key, absent_alias, expected_keys in cases:
            with self.subTest(title=title, content=content):
                matches = self.matcher.match(make_information(title, content))
                aliases = {
                    match.commodity_key: match.matched_aliases for match in matches
                }
                self.assertEqual(tuple(aliases), expected_keys)
                if absent_key is not None:
                    self.assertNotIn(absent_key, aliases)
                self.assertNotIn(absent_alias, tuple(alias for values in aliases.values() for alias in values))

    def test_searches_same_field_aliases_without_cross_field_synthesis(self) -> None:
        cases = (
            ("Fuel oil outlook", "Unrelated text.", "fuel_oil", "fuel oil"),
            ("Unrelated text.", "Fuel oil outlook", "fuel_oil", "fuel oil"),
            (
                "低硫燃料油现货偏紧",
                "Unrelated text.",
                "low_sulfur_fuel_oil",
                "低硫燃料油",
            ),
        )

        for title, content, commodity_key, alias in cases:
            with self.subTest(title=title, content=content):
                matches = self.matcher.match(make_information(title, content))
                aliases = {
                    match.commodity_key: match.matched_aliases for match in matches
                }
                self.assertIn(commodity_key, aliases)
                self.assertIn(alias, aliases[commodity_key])

    def test_preserves_independent_field_matches_and_local_exclusions(self) -> None:
        cases = (
            ("Crude oil outlook", "Fuel oil outlook", ("crude_oil", "fuel_oil")),
            ("Soybean oil outlook", "Crude oil outlook", ("crude_oil",)),
            ("Crude oil outlook", "Soybean oil outlook", ("crude_oil",)),
            ("Fuel oil outlook", "Palm oil outlook", ("fuel_oil",)),
            ("猪油库存", "原油库存", ("crude_oil",)),
            (
                "Low sulfur fuel oil outlook",
                "Crude oil outlook",
                ("crude_oil", "low_sulfur_fuel_oil"),
            ),
        )

        for title, content, expected_keys in cases:
            with self.subTest(title=title, content=content):
                self.assertEqual(
                    tuple(
                        match.commodity_key
                        for match in self.matcher.match(make_information(title, content))
                    ),
                    expected_keys,
                )

    def test_deduplicates_the_same_alias_across_title_and_content(self) -> None:
        matches = self.matcher.match(
            make_information("Crude oil outlook", "Crude oil inventory update.")
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].commodity_key, "crude_oil")
        self.assertEqual(matches[0].matched_aliases, ("crude oil",))

    def test_preserves_historical_matched_alias_length_order(self) -> None:
        matcher = CommodityMatcher(
            definitions=(
                CommodityDefinition("test", "Test", ("oil", "crude oil")),
            ),
            ambiguous_alias_exclusions=(),
        )

        matches = matcher.match(
            make_information("Oil prices", "Crude oil benchmarks were updated.")
        )

        self.assertEqual(matches[0].matched_aliases, ("crude oil", "oil"))

    def test_preserves_alias_order_for_equal_lengths_regardless_of_field_order(self) -> None:
        matcher = CommodityMatcher(
            definitions=(
                CommodityDefinition("test", "Test", ("brent", "wti")),
            ),
            ambiguous_alias_exclusions=(),
        )

        matches = matcher.match(
            make_information("WTI update", "Brent update.")
        )

        self.assertEqual(matches[0].matched_aliases, ("brent", "wti"))

    def test_does_not_report_suppressed_overlapping_aliases(self) -> None:
        matches = self.matcher.match(make_information("Low sulfur fuel oil", "Details."))

        self.assertEqual(
            [(match.commodity_key, match.matched_aliases) for match in matches],
            [("low_sulfur_fuel_oil", ("low sulfur fuel oil",))],
        )

    def test_empty_input_is_safe(self) -> None:
        self.assertEqual(self.matcher.match(make_information("Update", "Details.")), ())

    def test_rejects_unsafe_single_character_cjk_aliases(self) -> None:
        for key, alias in (("live_hog", "猪"), ("crude_oil", "油"), ("aluminum", "铝")):
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, key):
                    self._load_matcher_from_registry(
                        self._registry_with_alias(key, "Test Commodity", alias)
                    )

    def test_accepts_safe_multi_character_cjk_aliases_and_existing_english_registry(self) -> None:
        live_hog_matcher = self._load_matcher_from_registry(
            self._registry_with_alias("live_hog", "Live Hog", "生猪")
        )
        crude_oil_matcher = self._load_matcher_from_registry(
            self._registry_with_alias("crude_oil", "Crude Oil", "原油")
        )

        self.assertEqual(
            tuple(
                match.commodity_key
                for match in live_hog_matcher.match(
                    make_information("生猪供应", "Details.")
                )
            ),
            ("live_hog",),
        )
        self.assertEqual(
            tuple(
                match.commodity_key
                for match in crude_oil_matcher.match(
                    make_information("原油供应", "Details.")
                )
            ),
            ("crude_oil",),
        )
        self.assertEqual(CommodityMatcher().commodity_order[0], "crude_oil")

    def test_rejects_malformed_alias_entries(self) -> None:
        malformed_registries = {
            "invalid alias type": """commodities:\n  test:\n    label: Test\n    aliases:\n      - [not-a-string]\n""",
            "empty alias": """commodities:\n  test:\n    label: Test\n    aliases:\n      - \n""",
        }

        for name, registry in malformed_registries.items():
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self._load_matcher_from_registry(registry)

    def test_rejects_non_string_plain_scalar_aliases(self) -> None:
        for scalar in ("123", "-7", "+4", "1.5", ".5", "1e3", "0x10", "true", "False", "NULL", "~"):
            with self.subTest(scalar=scalar):
                with self.assertRaises(ValueError):
                    self._load_matcher_from_registry(
                        self._registry_with_alias("test", "Test", scalar)
                    )

    def test_rejects_non_string_plain_scalars_in_other_required_fields(self) -> None:
        registries = (
            """commodities:\n  test:\n    label: true\n    aliases:\n      - valid\n""",
            """commodities:\n  true:\n    label: Test\n    aliases:\n      - valid\n""",
            """commodities:\n  test:\n    label: Test\n    aliases:\n      - oil\nambiguous_alias_exclusions:\n  oil:\n    - 123\n""",
        )

        for registry in registries:
            with self.subTest(registry=registry):
                with self.assertRaises(ValueError):
                    self._load_matcher_from_registry(registry)

    def test_accepts_quoted_scalar_aliases_as_strings(self) -> None:
        for alias in ('"123"', "'true'"):
            with self.subTest(alias=alias):
                matcher = self._load_matcher_from_registry(
                    self._registry_with_alias("test", "Test", alias)
                )
                expected = alias[1:-1]
                matches = matcher.match(make_information(expected, "Details."))
                self.assertEqual(matches[0].matched_aliases, (expected,))

    def test_accepts_quoted_null_alias_as_a_string(self) -> None:
        matcher = self._load_matcher_from_registry(
            self._registry_with_alias("test", "Test", '"null"')
        )

        matches = matcher.match(make_information("null outlook", "Details."))

        self.assertEqual(
            [(match.commodity_key, match.matched_aliases) for match in matches],
            [("test", ("null",))],
        )

    def test_rejects_quoted_single_character_cjk_alias(self) -> None:
        with self.assertRaisesRegex(ValueError, "crude_oil"):
            self._load_matcher_from_registry(
                self._registry_with_alias("crude_oil", "Crude Oil", '"油"')
            )

    @staticmethod
    def _registry_with_alias(key: str, label: str, alias: str) -> str:
        return (
            "commodities:\n"
            f"  {key}:\n"
            f"    label: {label}\n"
            "    aliases:\n"
            f"      - {alias}\n"
        )

    @staticmethod
    def _load_matcher_from_registry(registry: str) -> CommodityMatcher:
        registry_path = Mock()
        registry_path.read_text.return_value = registry
        with patch.object(commodity_matcher, "COMMODITY_KEYWORDS_FILE", registry_path):
            return CommodityMatcher()


if __name__ == "__main__":
    unittest.main()
