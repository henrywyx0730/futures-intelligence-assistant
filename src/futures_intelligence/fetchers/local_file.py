"""Local-file implementation of the research-report fetcher contract."""

from __future__ import annotations

from pathlib import Path

from futures_intelligence.fetchers.research_report import ResearchReportFetcher


class LocalFileResearchReportFetcher(ResearchReportFetcher):
    """Read raw research-report content from a configured local path."""

    def __init__(self, content_path: str | Path) -> None:
        self.content_path = Path(content_path)

    def fetch(self) -> str | None:
        """Return UTF-8 file content, or None when the file is unavailable."""
        try:
            return self.content_path.read_text(encoding="utf-8")
        except OSError:
            return None
