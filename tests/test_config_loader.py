"""Tests for the project configuration registry."""

import unittest

from futures_intelligence.config.loader import CONFIGURATION_FILES


class ConfigurationLoaderTests(unittest.TestCase):
    """Validate configuration files registered by the loader."""

    def test_registers_runtime_configuration_file(self) -> None:
        self.assertEqual(CONFIGURATION_FILES["runtime"].name, "runtime.yaml")
        self.assertTrue(CONFIGURATION_FILES["runtime"].is_file())


if __name__ == "__main__":
    unittest.main()
