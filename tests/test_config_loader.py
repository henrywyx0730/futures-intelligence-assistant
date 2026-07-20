"""Tests for the project configuration registry."""

import unittest

from futures_intelligence.config.loader import CONFIGURATION_FILES


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


if __name__ == "__main__":
    unittest.main()
