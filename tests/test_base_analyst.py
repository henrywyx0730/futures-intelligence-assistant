"""Tests for the abstract analyst contract."""

from datetime import datetime, timezone
import unittest

from futures_intelligence.analyst.base import BaseAnalyst
from futures_intelligence.models import MarketAnalysis, MarketInformation


class SummaryAnalyst(BaseAnalyst):
    """Minimal concrete analyst used to verify the interface."""

    def analyze(self, information: list[MarketInformation]) -> list[MarketAnalysis]:
        return [MarketAnalysis(item, "Summary") for item in information]


def make_information() -> MarketInformation:
    """Create a normalized item for analyst tests."""
    return MarketInformation(
        title="Market update",
        source="Test Source",
        source_type="test",
        published_time=datetime(2026, 7, 16, tzinfo=timezone.utc),
        content="Test content.",
    )


class BaseAnalystTests(unittest.TestCase):
    """Validate analyst abstraction behavior."""

    def test_cannot_instantiate_abstract_analyst(self) -> None:
        with self.assertRaises(TypeError):
            BaseAnalyst()

    def test_concrete_subclass_implements_analyze(self) -> None:
        information = make_information()

        analyses = SummaryAnalyst().analyze([information])

        self.assertEqual(len(analyses), 1)
        self.assertIs(analyses[0].market_information, information)


if __name__ == "__main__":
    unittest.main()
