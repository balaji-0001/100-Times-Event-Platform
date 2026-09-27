"""Shared data shapes passed between connectors, the unified processor, and the orchestrator."""

from dataclasses import dataclass


@dataclass
class Signal:
    """A single normalized piece of public content collected from a platform."""

    platform: str
    community_name: str
    title: str
    content: str
    author: str
    url: str = ""
    external_id: str | None = None


@dataclass
class PublishResult:
    success: bool
    platform: str
    published_url: str | None
    message: str
