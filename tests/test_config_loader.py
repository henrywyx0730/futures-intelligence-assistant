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
        self.assertIn("    max_items_per_run: 5\n", runtime_text)


if __name__ == "__main__":
    unittest.main()
