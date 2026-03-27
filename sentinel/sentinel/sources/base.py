"""Abstract base class for yield data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod

from sentinel.models.opportunity import YieldOpportunity
from sentinel.utils.http import HttpClient


class BaseYieldSource(ABC):
    """Interface for all yield data sources."""

    name: str = "base"

    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or HttpClient()

    @abstractmethod
    async def fetch_opportunities(
        self,
        underlying: str | None = None,
        chains: list[str] | None = None,
    ) -> list[YieldOpportunity]:
        """Fetch all yield opportunities, optionally filtered by underlying token and chains."""
        ...

    async def close(self) -> None:
        await self.http.close()
