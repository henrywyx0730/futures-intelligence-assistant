"""Abstract contract for retrieving research-report content."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ResearchReportFetcher(ABC):
    """Fetch raw content for a configured research report."""

    @abstractmethod
    def fetch(self) -> str | None:
        """Return report content, or None when it cannot be retrieved."""
