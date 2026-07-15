"""Orchestrate normalized information collectors."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from futures_intelligence.collectors.base import BaseCollector
from futures_intelligence.models import MarketInformation


logger = logging.getLogger(__name__)


class CollectorManager:
    """Run enabled collectors and combine their normalized results."""

    def __init__(self, collectors: Iterable[BaseCollector]) -> None:
        self.collectors = tuple(collectors)

    def collect(self) -> list[MarketInformation]:
        """Collect information, isolating failures from individual collectors."""
        information: list[MarketInformation] = []
        for collector in self.collectors:
            if not getattr(collector, "enabled", True):
                continue

            try:
                information.extend(collector.collect())
            except Exception:
                logger.exception(
                    "Collector failed: %s", collector.__class__.__name__
                )
        return information
