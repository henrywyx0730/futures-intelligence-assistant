"""Tests for the abstract collector contract."""

import unittest

from futures_intelligence.collectors.base import BaseCollector
from futures_intelligence.models import MarketInformation


class EmptyCollector(BaseCollector):
    """Minimal concrete collector used to verify the interface."""

    def collect(self) -> list[MarketInformation]:
        return []


class BaseCollectorTests(unittest.TestCase):
    """Validate collector abstraction behavior."""

    def test_cannot_instantiate_abstract_collector(self) -> None:
        with self.assertRaises(TypeError):
            BaseCollector()

    def test_concrete_subclass_implements_collect(self) -> None:
        collector = EmptyCollector()

        self.assertEqual(collector.collect(), [])


if __name__ == "__main__":
    unittest.main()
