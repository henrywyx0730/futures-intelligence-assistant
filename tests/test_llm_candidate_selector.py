"""Tests for deterministic production LLM candidate selection."""

from datetime import datetime, timezone
import unittest

from futures_intelligence.analyst.candidate_selector import LLMCandidateSelector
from futures_intelligence.models import MarketInformation


def make_information(
    title: str,
    *,
    source_type: str = "research_report",
    reliability_score: int = 4,
) -> MarketInformation:
    """Create a normalized item in its pre-ranked caller-provided order."""
    return MarketInformation(
        title=title,
        source="Test Source",
        source_type=source_type,
        published_time=datetime(2026, 7, 20, tzinfo=timezone.utc),
        content="Market information content.",
        reliability_score=reliability_score,
    )


class LLMCandidateSelectorTests(unittest.TestCase):
    """Verify cost-controlled candidate policy without any analyst calls."""

    def test_disabled_llm_selects_no_candidates(self) -> None:
        items = [make_information("Eligible report")]

        selection = LLMCandidateSelector(
            enabled=False,
            source_types=("research_report",),
            min_reliability_score=4,
            max_items_per_run=3,
        ).select(items)

        self.assertEqual(selection.eligible_count, 0)
        self.assertEqual(selection.selected_items, ())

    def test_filters_source_type_reliability_and_blank_content(self) -> None:
        selected = make_information("Eligible report")
        low_reliability = make_information("Low reliability", reliability_score=3)
        unsupported = make_information("RSS item", source_type="rss")
        blank_content = make_information("Blank content")
        blank_content.content = "  "

        selection = LLMCandidateSelector(
            enabled=True,
            source_types=("research_report",),
            min_reliability_score=4,
            max_items_per_run=3,
        ).select([unsupported, low_reliability, blank_content, selected])

        self.assertEqual(selection.eligible_count, 1)
        self.assertEqual(selection.selected_items, (selected,))
        self.assertIs(selection.selected_items[0], selected)

    def test_preserves_ranked_order_and_enforces_global_maximum(self) -> None:
        items = [make_information(f"Report {index}") for index in range(4)]

        selection = LLMCandidateSelector(
            enabled=True,
            source_types=("research_report",),
            min_reliability_score=4,
            max_items_per_run=2,
        ).select(items)

        self.assertEqual(selection.eligible_count, 4)
        self.assertEqual(selection.selected_items, tuple(items[:2]))
        self.assertIs(selection.selected_items[0], items[0])
        self.assertIs(selection.selected_items[1], items[1])


if __name__ == "__main__":
    unittest.main()
