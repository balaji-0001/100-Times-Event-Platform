"""Event Discovery automation orchestrator ("Agent 1") — fixed rules and a
headless browser, no AI.

Flow: read the configured event-listing sites for each target city, then
web-search (DuckDuckGo) the generated queries and read each result page ->
extract events (structured data first, best-effort text second) -> identify
the real organizer -> validate (date sanity, confidence) -> dedup-check ->
persist.

Every stage that can fail per-item (a bad page, a flaky fetch) is caught and
logged so one bad candidate can't abort the run. If the search engine
blocks the automation, searching stops and the run still completes with
what it found, recording why in `AgentRun.error`. Every DB write goes
through `storage.py`, which dedup-checks before inserting, so a resumed or
re-run pass never creates duplicate records — that's what makes this
restartable/idempotent.
"""

import logging
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import Settings, get_settings
from backend.models import AgentRun, DiscoveredEvent
from backend.services.discovery_agent import listing_sources, organizer_identifier, page_extractor, query_seeds, storage, validation, web_search
from backend.services.discovery_agent.types import DiscoveryConfig, RunSummary

logger = logging.getLogger("discovery_agent.orchestrator")


def _split(csv: str) -> list[str]:
    return [item.strip() for item in csv.split(",") if item.strip()]


def config_from_settings(settings: Settings) -> DiscoveryConfig:
    return DiscoveryConfig(
        cities=_split(settings.discovery_target_cities),
        states=_split(settings.discovery_target_states),
        categories=_split(settings.discovery_target_categories),
        search_depth=settings.discovery_search_depth,
        sources_per_query=settings.discovery_sources_per_query,
        daily_limit=settings.discovery_daily_limit,
        confidence_threshold=settings.discovery_confidence_threshold,
        listing_urls=_split(settings.discovery_listing_urls),
        events_per_listing=settings.discovery_events_per_listing,
    )


def _todays_new_event_count(db: Session) -> int:
    today = datetime.now(timezone.utc).date()
    rows = db.execute(
        select(DiscoveredEvent.discovered_at).where(DiscoveredEvent.discovered_by == "web_discovery_agent")
    ).scalars().all()
    return sum(1 for ts in rows if ts and ts.date() == today)


def _process_candidate(db: Session, run: AgentRun, candidate, config: DiscoveryConfig, summary: RunSummary) -> None:
    """Organizer lookup, validation and storage for one extracted event."""
    try:
        organizer_candidate = organizer_identifier.identify_organizer(candidate)
    except Exception:
        logger.exception("Organizer identification failed for %s — continuing without an organizer.", candidate.url)
        organizer_candidate = None

    status, notes, confidence, event_date = validation.validate_event(candidate, config.confidence_threshold)
    if status == "REJECTED":
        summary.events_discovered += 1
        logger.info("Rejected candidate %r: %s", candidate.name, "; ".join(notes) or "no reason given")
        run.summary = summary.as_dict()
        db.add(run)
        db.commit()
        return

    try:
        storage.persist_event(
            db,
            candidate=candidate,
            organizer=organizer_candidate,
            verification_status=status,
            verification_notes=notes,
            confidence_score=confidence,
            event_date=event_date,
            summary=summary,
        )
    except Exception:
        db.rollback()
        logger.exception("Failed to persist candidate %r — skipping.", candidate.name)
        return

    run.summary = summary.as_dict()
    db.add(run)
    db.commit()


def _limit_reached(already_today: int, summary: RunSummary, config: DiscoveryConfig) -> bool:
    return already_today + summary.new_events >= config.daily_limit


def _read_page(db: Session, run: AgentRun, page_url: str, config: DiscoveryConfig, summary: RunSummary, already_today: int) -> None:
    try:
        candidates = page_extractor.extract_events_from_page(page_url, config.events_per_listing, config.cities)
    except Exception:
        logger.exception("Reading %s failed — skipping it.", page_url)
        return
    for candidate in candidates:
        if _limit_reached(already_today, summary, config):
            return
        _process_candidate(db, run, candidate, config, summary)


def run_discovery_agent(db: Session, config: DiscoveryConfig | None = None) -> RunSummary:
    config = config or config_from_settings(get_settings())

    run = AgentRun(
        agent_type="discovery",
        status="running",
        started_at=datetime.now(timezone.utc),
        config_snapshot=asdict(config),
        summary=RunSummary().as_dict(),
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    summary = RunSummary()
    try:
        already_today = _todays_new_event_count(db)
        pages_read: set[str] = set()

        # 1. Known event-listing sites, per target city.
        for listing_url in listing_sources.build_listing_urls(config.listing_urls, config.cities):
            if _limit_reached(already_today, summary, config):
                break
            pages_read.add(listing_url)
            _read_page(db, run, listing_url, config, summary, already_today)

        # 2. Web search: every result page is read the same way. A block
        # (captcha / rate limit) stops searching but keeps what was found.
        search_error: str | None = None
        for query in query_seeds.build_search_queries(config):
            if _limit_reached(already_today, summary, config):
                logger.info("Daily discovery limit (%d) reached — stopping run early.", config.daily_limit)
                break
            try:
                result_urls = web_search.search(query, config.sources_per_query)
            except web_search.SearchBlocked as exc:
                search_error = str(exc)
                logger.warning("Web search stopped: %s", exc)
                break
            except Exception:
                logger.exception("Web search failed for query %r — skipping this query.", query)
                continue
            for url in result_urls:
                if url in pages_read or _limit_reached(already_today, summary, config):
                    continue
                pages_read.add(url)
                _read_page(db, run, url, config, summary, already_today)

        run.error = f"Web search stopped early: {search_error}" if search_error else None
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.summary = summary.as_dict()
        db.add(run)
        db.commit()

    except Exception as exc:
        db.rollback()
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error = str(exc)
        run.summary = summary.as_dict()
        db.add(run)
        db.commit()
        logger.exception("Discovery Agent run #%s failed", run.id)

    return summary
