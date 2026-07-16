"""Abstract analyst contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from futures_intelligence.models import MarketAnalysis, MarketInformation


class BaseAnalyst(ABC):
    """Analysts transform normalized market information into MarketAnalysis objects."""

    @abstractmethod
    def analyze(self, information: list[MarketInformation]) -> list[MarketAnalysis]:
        """Return analyses for normalized market information."""
