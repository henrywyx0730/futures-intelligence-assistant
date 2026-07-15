"""Abstract collector contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from futures_intelligence.models import MarketInformation


class BaseCollector(ABC):
    """Collectors retrieve external information and normalize it into MarketInformation objects."""

    @abstractmethod
    def collect(self) -> list[MarketInformation]:
        """Retrieve and return normalized market information."""

