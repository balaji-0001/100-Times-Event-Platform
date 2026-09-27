"""Stage: PLATFORM_SEARCH — generic, topic-agnostic relevance search.

A `PlatformConnector`'s `discover_signals()` is the only thing that varies
per platform (Bot-API polling for Telegram, curated samples for the others
until real credentials are added) — this module's job is purely to
rank/filter/dedupe/limit whatever a connector returns against the caller's
dynamically generated queries. It contains no topic- or platform-specific
logic: the exact same code searches for "biking events" or "AI conferences"
or "photography workshops", because the queries are the only input that
changes.

Telegram's Bot API has no cross-channel keyword-search endpoint — a bot can
only ever see messages from chats it has been added to (see
`connectors/telegram.py`). "Searching" a bot-only integration honestly means
ranking the messages it can legitimately see, not crawling arbitrary private
chats. This module's scoring step is exactly that: relevance filtering over
whatever a connector can legitimately access, generalized across platforms.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from backend.services.social_agent.connectors.base import PlatformConnector
from backend.services.social_agent.types import Signal

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


@dataclass
class ScoredSignal:
    signal: Signal
    relevance: float
    matched_queries: list[str] = field(default_factory=list)


def score_signal(signal: Signal, queries: list[str]) -> tuple[float, list[str]]:
    """Token-overlap relevance between a signal's text and each dynamically
    generated query. No fixed keyword list — `queries` is the only input,
    so the scoring behaves identically for any topic."""
    signal_tokens = _tokenize(f"{signal.title} {signal.content}")
    if not signal_tokens:
        return 0.0, []

    total = 0.0
    matched: list[str] = []
    for query in queries:
        query_tokens = _tokenize(query)
        if not query_tokens:
            continue
        overlap = query_tokens & signal_tokens
        if overlap:
            total += len(overlap) / len(query_tokens)
            matched.append(query)

    return total, matched


def search_platform(
    connector: PlatformConnector,
    queries: list[str],
    exclude_external_ids: set[str] | None = None,
    limit: int = 15,
    min_relevance: float = 0.15,
) -> list[ScoredSignal]:
    """Runs the connector's discovery, then ranks/filters/dedupes/limits the
    result against `queries` — dynamic search over whatever content the
    connector can legitimately return, for any topic, any platform."""
    exclude = exclude_external_ids or set()
    seen_queries: set[str] = set()
    clean_queries: list[str] = []
    for q in queries:
        q = (q or "").strip()
        if q and q.lower() not in seen_queries:
            seen_queries.add(q.lower())
            clean_queries.append(q)

    if not clean_queries:
        return []

    try:
        raw_signals = connector.discover_signals()
    except Exception:
        # A connector must never let a transient API error bubble up and
        # break the whole discovery pipeline — treat it as "no results this
        # run", the same way a zero-update poll would be handled.
        raw_signals = []

    scored: list[ScoredSignal] = []
    seen_ids: set[str] = set()
    for signal in raw_signals:
        ext_id = signal.external_id or f"{signal.platform}:{signal.community_name}:{signal.title}"
        if ext_id in exclude or ext_id in seen_ids:
            continue
        seen_ids.add(ext_id)

        relevance, matched = score_signal(signal, clean_queries)
        if relevance >= min_relevance:
            scored.append(ScoredSignal(signal=signal, relevance=round(relevance, 3), matched_queries=matched))

    scored.sort(key=lambda s: s.relevance, reverse=True)
    return scored[:limit]


def scored_signal_to_dict(scored: ScoredSignal) -> dict[str, Any]:
    return {
        "platform": scored.signal.platform,
        "community": scored.signal.community_name,
        "title": scored.signal.title,
        "content": scored.signal.content,
        "author": scored.signal.author,
        "url": scored.signal.url,
        "externalId": scored.signal.external_id,
        "relevance": scored.relevance,
        "matchedQueries": scored.matched_queries,
    }
