"""Deterministic text generation for a morning market brief."""

from futures_intelligence.models import MarketAnalysis


class MorningBriefGenerator:
    """Generate a readable morning brief from market analyses."""

    def generate(self, analyses: list[MarketAnalysis]) -> str:
        """Return a deterministic text report for the supplied analyses."""
        lines = [
            "Morning Futures Brief",
            f"Number of analyses: {len(analyses)}",
        ]

        for index, analysis in enumerate(analyses, start=1):
            information = analysis.market_information
            lines.extend(
                [
                    "",
                    f"{index}. Source: {information.source}",
                    f"   Title: {information.title}",
                    f"   Summary: {analysis.summary}",
                ]
            )

        return "\n".join(lines)
