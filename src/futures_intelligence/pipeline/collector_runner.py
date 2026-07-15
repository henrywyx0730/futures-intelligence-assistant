"""Run collectors created from already-loaded source configuration."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from futures_intelligence.collectors.base import BaseCollector
from futures_intelligence.collectors.factory import CollectorFactory
from futures_intelligence.models import MarketInformation
from futures_intelligence.pipeline.collector_manager import CollectorManager


logger = logging.getLogger(__name__)


class CollectorRunner:
    """Create configured collectors and run them through the collector manager."""

    def __init__(self, source_configurations: Iterable[Mapping[str, Any]]) -> None:
        self.source_configurations = tuple(source_configurations)

    def run(self) -> list[MarketInformation]:
        """Create enabled collectors and return their normalized information."""
        collectors: list[BaseCollector] = []
        for source_config in self.source_configurations:
            try:
                collector = CollectorFactory.create(source_config)
            except ValueError as error:
                logger.warning("Skipping source configuration: %s", error)
                continue

            if collector is not None:
                collectors.append(collector)

        return CollectorManager(collectors).collect()
