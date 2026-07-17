"""Deterministic text generation for a morning market brief."""

from futures_intelligence.models import MarketAnalysis


class MorningBriefGenerator:
    """Generate a concise morning brief from analyses ordered by relevance."""

    MAX_ANALYSES = 5

    def generate(self, analyses: list[MarketAnalysis]) -> str:
        """Return a deterministic report containing the most relevant analyses."""
        selected_analyses = analyses[: self.MAX_ANALYSES]
        lines = [
            "Morning Futures Brief",
            f"Top analyses: {len(selected_analyses)} of {len(analyses)}",
        ]

        for index, analysis in enumerate(selected_analyses, start=1):
            information = analysis.market_information
            lines.extend(
                [
                    "",
                    f"{index}. {information.title} ({information.source})",
                    f"   {analysis.summary}",
                ]
            )

        return "\n".join(lines)
