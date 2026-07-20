"""Tests for the project configuration registry."""

import unittest

from futures_intelligence.collectors.factory import CollectorFactory
from futures_intelligence.config.loader import CONFIGURATION_FILES


def _source_entries_from_registry_text() -> list[dict[str, object]]:
    """Read the source fields needed for consistency checks without optional YAML imports."""
    entries: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line in CONFIGURATION_FILES["sources"].read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- name: "):
            if current is not None:
                entries.append(current)
            current = {"name": stripped.removeprefix("- name: ").strip()}
            continue
        if current is None:
            continue
        for field in ("source_type", "enabled", "content_path", "url"):
            prefix = f"{field}:"
            if stripped.startswith(prefix):
                value = stripped.removeprefix(prefix).strip()
                current[field] = (
                    value == "true" if field == "enabled" else value
                )
                break
    if current is not None:
        entries.append(current)
    return entries


class ConfigurationLoaderTests(unittest.TestCase):
    """Validate configuration files registered by the loader."""

    def test_registers_runtime_configuration_file(self) -> None:
        self.assertEqual(CONFIGURATION_FILES["runtime"].name, "runtime.yaml")
        self.assertTrue(CONFIGURATION_FILES["runtime"].is_file())

    def test_runtime_configuration_includes_safe_llm_defaults(self) -> None:
        runtime_text = CONFIGURATION_FILES["runtime"].read_text(encoding="utf-8")

        self.assertIn("  llm:\n", runtime_text)
        self.assertIn("    enabled: false\n", runtime_text)
        self.assertIn("    provider: openai\n", runtime_text)
        self.assertIn("    model: gpt-5.6-luna\n", runtime_text)
        self.assertIn("      - research_report\n", runtime_text)
        self.assertIn("    min_reliability_score: 4\n", runtime_text)
        self.assertIn("    max_items_per_run: 3\n", runtime_text)
        self.assertIn("    usage:\n", runtime_text)
        self.assertIn("      file_path: data/llm_usage.jsonl\n", runtime_text)
        self.assertIn("    pricing:\n", runtime_text)
        self.assertIn('      effective_date: "2026-07-19"\n', runtime_text)

    def test_local_research_report_sample_is_disabled_for_normal_collection(self) -> None:
        sources_text = CONFIGURATION_FILES["sources"].read_text(encoding="utf-8")

        self.assertIn(
            "      - name: Sample Local Research Desk\n"
            "        source_type: research_report\n"
            "        priority: medium\n"
            "        enabled: false\n"
            "        content_path: data/research_reports/sample_crude_oil_outlook.txt",
            sources_text,
        )

    def test_default_source_registry_matches_factory_capabilities(self) -> None:
        entries = _source_entries_from_registry_text()

        for entry in entries:
            collector = CollectorFactory.create(entry)
            if entry.get("enabled"):
                self.assertIsNotNone(collector, entry.get("name"))
            else:
                self.assertIsNone(collector, entry.get("name"))

        entries_by_name = {str(entry["name"]): entry for entry in entries}
        for name in (
            "Guotai Junan Futures",
            "Huatai Futures",
            "Dongwu Futures",
            "Reuters",
            "Bloomberg",
            "Financial Times",
            "CLS",
            "Jin10",
            "Federal Reserve",
            "National Bureau of Statistics China",
            "EIA",
        ):
            self.assertFalse(entries_by_name[name]["enabled"], name)

        self.assertTrue(entries_by_name["Google News Commodities"]["enabled"])
        self.assertFalse(entries_by_name["Sample Local Research Desk"]["enabled"])
        self.assertFalse(entries_by_name["Futures Exchange Data"]["enabled"])

        for entry in entries:
            if entry["source_type"] in {"financial_news", "official_data"}:
                self.assertFalse(entry["enabled"], entry.get("name"))
            if entry["source_type"] == "research_report" and "content_path" not in entry:
                self.assertFalse(entry["enabled"], entry.get("name"))


if __name__ == "__main__":
    unittest.main()
