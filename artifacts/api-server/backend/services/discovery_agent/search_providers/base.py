from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class SearchProviderResult:
    url: str
    title: str = ""
    snippet: str = ""
    source: str = ""
    published_date: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderExecutionLog:
    provider_id: str
    provider_name: str
    query: str
    status: str  # "SUCCESS", "FAILED", "NO_KEY", "RATE_LIMITED", "SKIPPED"
    result_count: int = 0
    latency_ms: float = 0.0
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "query": self.query,
            "status": self.status,
            "result_count": self.result_count,
            "latency_ms": round(self.latency_ms, 1),
            "error": self.error,
            "timestamp": self.timestamp,
        }


class BaseSearchProvider(abc.ABC):
    """Abstract interface for modern web search providers."""

    provider_id: str
    provider_name: str

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """Returns True if the provider has the credentials/setup required to execute."""
        pass

    @abc.abstractmethod
    def search(
        self,
        query: str,
        max_results: int = 5,
        country: str | None = None,
        date_range: tuple[str | None, str | None] | None = None,
    ) -> list[SearchProviderResult]:
        """Executes a search query and returns structured results."""
        pass
