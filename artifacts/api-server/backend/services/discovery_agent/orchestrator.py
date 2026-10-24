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
from backend.services.discovery_agent import categorizer, listing_sources, organizer_identifier, page_extractor, query_seeds, storage, validation, web_search
from backend.services.discovery_agent.types import DiscoveryConfig, RunSummary

logger = logging.getLogger("discovery_agent.orchestrator")


def _split(csv: str) -> list[str]:
    return [item.strip() for item in csv.split(",") if item.strip()]


def config_from_settings(settings: Settings, db: Session | None = None) -> DiscoveryConfig:
    # Dynamically retrieve categories from the website/database if available
    db_cats = categorizer.get_supported_categories(db) if db is not None else []
    target_categories = db_cats if db_cats else _split(settings.discovery_target_categories)

    # Check for admin-configured auto discovery scope settings in db
    auto_scope: dict = {}
    if db is not None:
        try:
            from backend.services.discovery_agent.auto_toggle import get_discovery_auto_settings
            auto_scope = get_discovery_auto_settings(db)
        except Exception:
            pass

    cities = auto_scope.get("cities") if auto_scope.get("cities") else _split(settings.discovery_target_cities)
    states = auto_scope.get("states") if auto_scope.get("states") else _split(settings.discovery_target_states)
    if auto_scope.get("categories"):
        target_categories = auto_scope["categories"]
    country = auto_scope.get("country")
    countries = auto_scope.get("countries") if auto_scope.get("countries") else _split(getattr(settings, "discovery_target_countries", ""))
    if not countries and country:
        countries = [country]
    search_depth = auto_scope.get("search_depth") or settings.discovery_search_depth
    daily_limit = auto_scope.get("daily_limit") or settings.discovery_daily_limit

    return DiscoveryConfig(
        cities=cities,
        states=states,
        categories=target_categories,
        sources=auto_scope.get("sources") or ["web", "linkedin", "facebook", "instagram", "twitter", "telegram", "reddit", "event_platforms"],
        countries=countries,
        country=country,
        search_depth=search_depth,
        sources_per_query=settings.discovery_sources_per_query,
        daily_limit=daily_limit,
        events_per_run=auto_scope.get("events_per_run") or 50,
        target_valid_events=auto_scope.get("target_valid_events", 25),
        confidence_threshold=settings.discovery_confidence_threshold,
        listing_urls=_split(settings.discovery_listing_urls),
        events_per_listing=settings.discovery_events_per_listing,
        require_organizer_email=auto_scope.get("require_organizer_email", getattr(settings, "discovery_require_organizer_email", True)),
        reject_no_organizer=auto_scope.get("reject_no_organizer", True),
        require_organizer_phone=auto_scope.get("require_organizer_phone", False),
        require_organizer_website=auto_scope.get("require_organizer_website", False),
        reject_past_events=auto_scope.get("reject_past_events", True),
        reject_unparseable_dates=auto_scope.get("reject_unparseable_dates", True),
        reject_missing_location=auto_scope.get("reject_missing_location", False),
        reject_missing_ticket_url=auto_scope.get("reject_missing_ticket_url", False),
        reject_unmatched_category=auto_scope.get("reject_unmatched_category", False),
        fallback_to_other_sector=auto_scope.get("fallback_to_other_sector", True),
        min_title_length=auto_scope.get("min_title_length", 8),
        min_description_length=auto_scope.get("min_description_length", 20),
        min_confidence_score=auto_scope.get("min_confidence_score", 50),
        blacklisted_keywords=auto_scope.get("blacklisted_keywords") or [],
        excluded_domains=auto_scope.get("excluded_domains") or [],
    )


def _todays_new_event_count(db: Session) -> int:
    today = datetime.now(timezone.utc).date()
    rows = db.execute(
        select(DiscoveredEvent.discovered_at).where(DiscoveredEvent.discovered_by == "web_discovery_agent")
    ).scalars().all()
    return sum(1 for ts in rows if ts and ts.date() == today)


def _process_candidate(
    db: Session,
    run: AgentRun,
    candidate,
    config: DiscoveryConfig,
    summary: RunSummary,
    supported_categories: list[str],
) -> None:
    """Categorization, organizer lookup, validation and storage for one extracted event."""
    summary.events_discovered += 1

    candidate.category, candidate.subcategory = categorizer.categorize(
        candidate.name,
        candidate.event_description,
        candidate.url,
        supported_categories=supported_categories,
        db=db,
    )

    # Category handling: check if candidate matches target categories or falls back to 'Other' sector
    target_categories = set(config.categories) if config.categories else set(supported_categories)
    is_unmatched = candidate.category not in target_categories or candidate.category.lower() == "other"
    if is_unmatched:
        if getattr(config, "fallback_to_other_sector", True):
            candidate.category = "Other"
        elif getattr(config, "reject_unmatched_category", False):
            summary.unsupported_category += 1
            summary.rejected_events += 1
            run.summary = summary.as_dict()
            db.add(run)
            return

    try:
        organizer_candidate = organizer_identifier.identify_organizer(candidate)
    except Exception:
        logger.exception("Organizer identification failed for %s — continuing without an organizer.", candidate.url)
        organizer_candidate = OrganizerCandidate(found=False)

    if organizer_candidate is None:
        organizer_candidate = OrganizerCandidate(found=False)

    # Strictly enforce organizer details: skip events without organizer details/email for this run
    if config.require_organizer_email and (not organizer_candidate.found or not organizer_candidate.email):
        summary.missing_organizer_email += 1
        summary.rejected_events += 1
        run.summary = summary.as_dict()
        db.add(run)
        return

    val_result = validation.validate_event(
        candidate,
        config.confidence_threshold,
        organizer=organizer_candidate,
        require_organizer_email=config.require_organizer_email,
        supported_categories=supported_categories,
        date_from=getattr(config, "date_from", None),
        date_to=getattr(config, "date_to", None),
        reject_no_organizer=getattr(config, "reject_no_organizer", True),
        require_organizer_phone=getattr(config, "require_organizer_phone", False),
        require_organizer_website=getattr(config, "require_organizer_website", False),
        reject_past_events=getattr(config, "reject_past_events", True),
        reject_unparseable_dates=getattr(config, "reject_unparseable_dates", True),
        reject_missing_location=getattr(config, "reject_missing_location", False),
        reject_missing_ticket_url=getattr(config, "reject_missing_ticket_url", False),
        reject_unmatched_category=getattr(config, "reject_unmatched_category", False),
        fallback_to_other_sector=getattr(config, "fallback_to_other_sector", True),
        min_title_length=getattr(config, "min_title_length", 8),
        min_description_length=getattr(config, "min_description_length", 20),
        min_confidence_score=getattr(config, "min_confidence_score", 50),
        blacklisted_keywords=getattr(config, "blacklisted_keywords", None),
        excluded_domains=getattr(config, "excluded_domains", None),
    )
    status, notes, confidence, event_date = val_result
    rejection_reason = getattr(val_result, "rejection_reason", None)

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
            rejection_reason=rejection_reason,
        )
    except Exception:
        db.rollback()
        logger.exception("Failed to persist candidate %r — skipping.", candidate.name)
        return

    run.summary = summary.as_dict()
    db.add(run)
    # Commit periodically to keep run summary fresh without thrashing disk I/O on every candidate
    if summary.events_discovered % 10 == 0:
        db.commit()


def _limit_reached(already_today: int, summary: RunSummary, config: DiscoveryConfig) -> bool:
    target_valid = getattr(config, "target_valid_events", None)
    if target_valid and (summary.accepted_events >= target_valid or summary.new_events >= target_valid):
        return True
    max_for_run = getattr(config, "events_per_run", None)
    if max_for_run and summary.events_discovered >= max_for_run:
        return True
    return summary.new_events >= config.daily_limit


def _read_page(
    db: Session,
    run: AgentRun,
    page_url: str,
    config: DiscoveryConfig,
    summary: RunSummary,
    already_today: int,
    supported_categories: list[str],
) -> None:
    try:
        candidates = page_extractor.extract_events_from_page(page_url, config.events_per_listing, config.cities)
    except Exception:
        logger.exception("Reading %s failed — skipping it.", page_url)
        return
    for candidate in candidates:
        if _limit_reached(already_today, summary, config):
            return
        _process_candidate(db, run, candidate, config, summary, supported_categories)


def run_discovery_agent(db: Session, config: DiscoveryConfig | None = None) -> RunSummary:
    config = config or config_from_settings(get_settings(), db=db)
    supported_categories = categorizer.get_supported_categories(db)
    effective_categories = list(dict.fromkeys(supported_categories + (config.categories or [])))
    if not config.categories:
        config.categories = supported_categories

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

        # 1. Targeted web search: prioritized first so manual and automated runs find
        # high-precision sector-matched events (LinkedIn, Facebook, Twitter, and
        # conference queries) directly without wasting time crawling generic directories.
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
                _read_page(db, run, url, config, summary, already_today, effective_categories)

        # 2. Known event-listing sites, with an adaptive budget so a run never hangs for 45+ minutes.
        # In manual research runs (or low search depth), cap to at most 2 listing pages.
        # In background runs, cap to at most 6 listing pages.
        is_manual = getattr(config, "is_manual", False)
        listing_budget = 2 if (is_manual or config.search_depth <= 6) else 6
        all_listing_urls = listing_sources.build_listing_urls(
            config.listing_urls,
            config.cities[:3] if len(config.cities) > 3 else config.cities,
            countries=getattr(config, "countries", None),
            country=getattr(config, "country", None),
        )
        for listing_url in all_listing_urls[:listing_budget]:
            if _limit_reached(already_today, summary, config):
                break
            if listing_url in pages_read:
                continue
            pages_read.add(listing_url)
            _read_page(db, run, listing_url, config, summary, already_today, effective_categories)

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
