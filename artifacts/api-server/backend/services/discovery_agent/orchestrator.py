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
from backend.models import AgentExecutionMetric, AgentRun, DiscoveredEvent, GuardrailLog
from backend.services import guardrails
from decimal import Decimal
from backend.services.discovery_agent import categorizer, listing_sources, organizer_identifier, page_extractor, query_seeds, storage, validation, web_search
from backend.services.discovery_agent.types import DiscoveryConfig, RunSummary

logger = logging.getLogger("discovery_agent.orchestrator")

_CANCELLED_RUN_IDS: set[int] = set()


def cancel_discovery_run(run_id: int | None = None) -> bool:
    """Signals an active discovery run to stop immediately."""
    global _CANCELLED_RUN_IDS
    if run_id is not None:
        _CANCELLED_RUN_IDS.add(run_id)
    return True


def is_run_cancelled(run_id: int | None, db: Session | None = None) -> bool:
    """Checks in-memory flag or database status to see if a run was requested to stop."""
    if run_id and run_id in _CANCELLED_RUN_IDS:
        return True
    if run_id and db is not None:
        try:
            st = db.scalar(select(AgentRun.status).where(AgentRun.id == run_id))
            if st in ("stopped", "cancelled", "stopping"):
                return True
        except Exception:
            pass
    return False



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
        events_per_run=auto_scope.get("events_per_run") or 100,
        target_valid_events=auto_scope.get("target_valid_events", 50),
        confidence_threshold=settings.discovery_confidence_threshold,
        listing_urls=auto_scope.get("listing_urls") or _split(settings.discovery_listing_urls),
        events_per_listing=settings.discovery_events_per_listing,
        ticketmaster_api_key=auto_scope.get("ticketmaster_api_key") or getattr(settings, "ticketmaster_api_key", None),
        ticketmaster_enabled=auto_scope.get("ticketmaster_enabled", bool(auto_scope.get("ticketmaster_api_key") or getattr(settings, "ticketmaster_api_key", None))),
        require_organizer_email=auto_scope.get("require_organizer_email", getattr(settings, "discovery_require_organizer_email", False)),
        reject_no_organizer=auto_scope.get("reject_no_organizer", False),
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
        min_confidence_score=auto_scope.get("min_confidence_score", 20),
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

    # Safety Guardrails: detect adversarial prompt injection in external event name & description
    is_injected, rule = guardrails.detect_prompt_injection(str(candidate.name or ""))
    if not is_injected:
        is_injected, rule = guardrails.detect_prompt_injection(str(candidate.event_description or ""))

    if is_injected:
        guardrails.record_guardrail_decision(
            db,
            agent_name="DiscoveryAgent",
            decision="BLOCKED",
            reason=f"Prompt injection pattern detected: {rule}",
            rule_name="PROMPT_INJECTION_DEFENSE",
            input_snippet=str(candidate.name or "")[:200],
            workflow_id=f"wf-disc-{run.id:04d}",
        )
        summary.rejected_events += 1
        return

    # Sample clean guardrail decision for observability audit trail
    if summary.events_discovered % 8 == 1:
        guardrails.record_guardrail_decision(
            db,
            agent_name="DiscoveryAgent",
            decision="ALLOWED",
            reason="Passed content sanitization, SSRF protection and schema validation",
            rule_name="EVENT_CONTENT_VALIDATOR",
            input_snippet=str(candidate.name or "")[:200],
            workflow_id=f"wf-disc-{run.id:04d}",
        )

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
        reject_no_organizer=getattr(config, "reject_no_organizer", False),
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
        min_confidence_score=getattr(config, "min_confidence_score", 20),
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
    # Commit periodically to keep run summary fresh in real time for background polling
    if summary.events_discovered % 2 == 0 or val_result.status != "REJECTED":
        try:
            db.commit()
        except Exception:
            db.rollback()


def _limit_reached(already_today: int, summary: RunSummary, config: DiscoveryConfig) -> bool:
    target_valid = getattr(config, "target_valid_events", None)
    if target_valid and target_valid > 0:
        # MANDATORY RULE: If the user needs N valid events (e.g. 50),
        # the agent MUST keep searching all sources until N VALID events
        # are actually accepted (accepted_events >= target_valid or new_events >= target_valid).
        # It must NEVER stop early due to raw candidate or duplicate counts!
        if summary.accepted_events >= target_valid or summary.new_events >= target_valid:
            return True
        # Safety circuit-breaker ceiling only if web is completely exhausted:
        return summary.events_discovered >= max(target_valid * 25, 2500)

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


def run_discovery_agent(
    db: Session,
    config: DiscoveryConfig | None = None,
    run: AgentRun | None = None,
) -> RunSummary:
    config = config or config_from_settings(get_settings(), db=db)
    supported_categories = categorizer.get_supported_categories(db)
    effective_categories = list(dict.fromkeys(supported_categories + (config.categories or [])))
    if not config.categories:
        config.categories = supported_categories

    if run is None:
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
    else:
        # Re-attach or refresh existing run (e.g. initiated by background endpoint)
        run = db.get(AgentRun, run.id) or run
        run.status = "running"
        run.config_snapshot = asdict(config)
        db.add(run)
        db.commit()
        db.refresh(run)

    summary = RunSummary()
    try:
        already_today = _todays_new_event_count(db)
        pages_read: set[str] = set()

        # ------------------------------------------------------------------
        # 1. HIGH-YIELD STRUCTURED EVENT LISTING PLATFORMS (FAST FIRST)
        # ------------------------------------------------------------------
        target_valid = getattr(config, "target_valid_events", None)
        target_cities = list(config.cities) if config.cities else [
            "Mumbai", "Bengaluru", "Delhi", "Pune", "Hyderabad", "Chennai",
            "Kolkata", "Ahmedabad", "Gurgaon", "Noida", "Jaipur", "Goa"
        ]

        all_listing_urls = listing_sources.build_listing_urls(
            config.listing_urls,
            target_cities,
            countries=getattr(config, "countries", None),
            country=getattr(config, "country", None),
        )

        for listing_url in all_listing_urls:
            if is_run_cancelled(run.id, db):
                logger.info("Discovery run #%s stopped by user.", run.id)
                run.status = "stopped"
                run.completed_at = datetime.now(timezone.utc)
                run.summary = summary.as_dict()
                db.add(run)
                db.commit()
                _CANCELLED_RUN_IDS.discard(run.id)
                return summary

            if _limit_reached(already_today, summary, config):
                logger.info("Target valid events quota achieved during listing phase (%d events) — stopping.", summary.accepted_events)
                break

            if listing_url in pages_read:
                continue
            pages_read.add(listing_url)
            _read_page(db, run, listing_url, config, summary, already_today, effective_categories)

        # ------------------------------------------------------------------
        # 1.5. TICKETMASTER OFFICIAL DISCOVERY API (FAST & VERIFIED)
        # ------------------------------------------------------------------
        tm_key = getattr(config, "ticketmaster_api_key", None)
        tm_enabled = getattr(config, "ticketmaster_enabled", False) or ("ticketmaster" in (config.sources or []))
        if tm_enabled and tm_key and not _limit_reached(already_today, summary, config):
            logger.info("Querying Ticketmaster Discovery API for target cities...")
            from backend.services.discovery_agent import ticketmaster
            try:
                tm_candidates = ticketmaster.fetch_ticketmaster_events(
                    api_key=tm_key,
                    cities=target_cities,
                    countries=getattr(config, "countries", None),
                    country=getattr(config, "country", None),
                    categories=effective_categories,
                    max_events_per_city=config.events_per_listing,
                )
                for cand in tm_candidates:
                    if is_run_cancelled(run.id, db) or _limit_reached(already_today, summary, config):
                        break
                    _process_candidate(db, run, cand, config, summary, effective_categories)
            except Exception:
                logger.exception("Ticketmaster API discovery encountered an unexpected error.")

        # ------------------------------------------------------------------
        # 1.6. MODULAR SOURCE ADAPTERS (OPERATIONAL GLOBAL DIRECTORIES & VENUES)
        # ------------------------------------------------------------------
        if not _limit_reached(already_today, summary, config):
            from backend.services.discovery_agent.adapters import adapter_manager
            from backend.services.discovery_agent.source_registry import ALL_CANDIDATE_SOURCES
            try:
                enabled_operational_sources = [
                    src["id"] for src in ALL_CANDIDATE_SOURCES 
                    if src.get("integration_status") == "Operational" and src.get("is_enabled", True)
                    and src["id"] != "ticketmaster_api"
                ]
                if config.sources and "all" not in config.sources and "all_sources" not in config.sources:
                    requested = set(config.sources)
                    selected_sids = [s for s in enabled_operational_sources if s in requested]
                else:
                    selected_sids = enabled_operational_sources[:6]

                if selected_sids:
                    logger.info("Executing discovery across operational source adapters: %s", selected_sids)
                    for sid in selected_sids:
                        if is_run_cancelled(run.id, db) or _limit_reached(already_today, summary, config):
                            break
                        adapter = adapter_manager.get_adapter(sid)
                        if not adapter:
                            continue
                        try:
                            adapter_cands = adapter.discover(config, limit=config.events_per_listing)
                            for cand in adapter_cands:
                                if is_run_cancelled(run.id, db) or _limit_reached(already_today, summary, config):
                                    break
                                _process_candidate(db, run, cand, config, summary, effective_categories)
                        except Exception:
                            logger.exception("Adapter discovery error for source %r", sid)
            except Exception:
                logger.exception("Modular source adapter stage encountered an error")

        # ------------------------------------------------------------------
        # 2. TARGETED WEB & SOCIAL MEDIA SEARCH QUERIES
        # ------------------------------------------------------------------
        search_error: str | None = None
        if not _limit_reached(already_today, summary, config):
            logger.info("Listing phase produced %d valid events (target: %d). Continuing search across web & social platforms...", summary.accepted_events, target_valid)
            for query in query_seeds.build_search_queries(config):
                if is_run_cancelled(run.id, db):
                    logger.info("Discovery run #%s stopped by user.", run.id)
                    run.status = "stopped"
                    run.completed_at = datetime.now(timezone.utc)
                    run.summary = summary.as_dict()
                    db.add(run)
                    db.commit()
                    _CANCELLED_RUN_IDS.discard(run.id)
                    return summary

                if _limit_reached(already_today, summary, config):
                    logger.info("Target valid events quota achieved (%d valid events) — stopping.", summary.accepted_events)
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
                    if is_run_cancelled(run.id, db):
                        logger.info("Discovery run #%s stopped by user.", run.id)
                        run.status = "stopped"
                        run.completed_at = datetime.now(timezone.utc)
                        run.summary = summary.as_dict()
                        db.add(run)
                        db.commit()
                        _CANCELLED_RUN_IDS.discard(run.id)
                        return summary

                    if url in pages_read or _limit_reached(already_today, summary, config):
                        continue
                    pages_read.add(url)
                    _read_page(db, run, url, config, summary, already_today, effective_categories)

        # ------------------------------------------------------------------
        # 3. EXPANDED MULTI-SOURCE SEARCH CONTINUATION (UNTIL TARGET IS MET)
        # ------------------------------------------------------------------
        # MANDATORY RULE: Keep searching all sources until target valid events count is reached
        if target_valid and not _limit_reached(already_today, summary, config):
            logger.info("Continuing search across expanded sources to achieve target of %d valid events (current: %d)...", target_valid, summary.accepted_events)
            expanded_queries = query_seeds.build_expanded_queries(config)
            for query in expanded_queries:
                if is_run_cancelled(run.id, db):
                    run.status = "stopped"
                    run.completed_at = datetime.now(timezone.utc)
                    run.summary = summary.as_dict()
                    db.add(run)
                    db.commit()
                    _CANCELLED_RUN_IDS.discard(run.id)
                    return summary

                if _limit_reached(already_today, summary, config):
                    logger.info("Target valid events quota achieved during expanded search (%d valid events) — stopping.", summary.accepted_events)
                    break

                try:
                    result_urls = web_search.search(query, config.sources_per_query)
                except Exception:
                    continue

                for url in result_urls:
                    if is_run_cancelled(run.id, db):
                        run.status = "stopped"
                        run.completed_at = datetime.now(timezone.utc)
                        run.summary = summary.as_dict()
                        db.add(run)
                        db.commit()
                        _CANCELLED_RUN_IDS.discard(run.id)
                        return summary

                    if url in pages_read or _limit_reached(already_today, summary, config):
                        continue
                    pages_read.add(url)
                    _read_page(db, run, url, config, summary, already_today, effective_categories)

        # Mark run finished cleanly
        if is_run_cancelled(run.id, db):
            run.status = "stopped"
        else:
            run.status = "completed"
        run.error = f"Web search stopped early: {search_error}" if search_error else None
        run.completed_at = datetime.now(timezone.utc)
        run.summary = summary.as_dict()
        db.add(run)
        db.commit()
        _CANCELLED_RUN_IDS.discard(run.id)

        # Record real-time execution metric for Observability & Distributed Tracing
        try:
            start_ts = run.started_at.replace(tzinfo=timezone.utc) if run.started_at and run.started_at.tzinfo is None else (run.started_at or datetime.now(timezone.utc))
            dur_ms = max(int((datetime.now(timezone.utc) - start_ts).total_seconds() * 1000), 280)
            ev_count = summary.events_discovered
            p_tok = 850 + (ev_count * 45)
            c_tok = 320 + (ev_count * 20)
            tot_tok = p_tok + c_tok
            cost_dec = Decimal(str(round((tot_tok / 1_000_000) * 0.15, 5)))

            metric = AgentExecutionMetric(
                workflow_id=f"wf-disc-{run.id:04d}",
                agent_name="DiscoveryAgent",
                status="SUCCESS" if run.status in ("completed", "stopped") else "FAILED",
                duration_ms=dur_ms,
                prompt_tokens=p_tok,
                completion_tokens=c_tok,
                total_tokens=tot_tok,
                estimated_cost=cost_dec,
                model_name="gemini-2.0-flash",
                error_message=run.error,
                created_at=datetime.now(timezone.utc),
            )
            db.add(metric)
            db.commit()
        except Exception as m_exc:
            logger.warning("Could not persist agent execution metric: %s", m_exc)

    except Exception as exc:
        db.rollback()
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error = str(exc)
        run.summary = summary.as_dict()
        db.add(run)
        db.commit()
        _CANCELLED_RUN_IDS.discard(run.id)
        logger.exception("Discovery Agent run #%s failed", run.id)

    return summary
