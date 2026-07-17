"""A scheduler-facing runner for the morning brief service."""

from __future__ import annotations

from futures_intelligence.services import MorningBriefService


class SchedulerRunner:
    """Invoke the morning brief workflow without depending on the CLI."""

    def __init__(self, service: MorningBriefService | None = None) -> None:
        """Use an injected service or create the default morning brief service."""
        self.service = service or MorningBriefService()

    def run(self) -> str:
        """Run the morning brief service once and return its generated brief."""
        return self.service.run()
