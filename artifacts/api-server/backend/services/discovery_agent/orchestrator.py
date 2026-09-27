"""Event Discovery & Organizer Research Agent orchestrator ("Agent 1").

Flow: build search queries -> web-search each one for candidate source URLs
-> extract structured event facts from each page -> identify the real
organizer -> validate (date sanity, confidence) -> dedup-check -> persist.

Every stage that can fail per-item (a bad page, a flaky fetch) is caught and
logged so one bad candidate can't abort the run — but a missing/invalid
AI provider key is NOT caught per-item: it's checked once up front and
raised immediately, so the run fails honestly (`AgentRun.status="failed"`)
instead of silently completing with zero results. Every DB write goes
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
from backend.services.discovery_agent import organizer_identifier, page_extractor, query_seeds, source_finder, storage, validation
from backend.services.discovery_agent.types import DiscoveryConfig, RunSummary
from backend.services.social_agent.ai_client import AIClientError, get_ai_client, not_configured_message

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
    )


def _todays_new_event_count(db: Session) -> int:
    today = datetime.now(timezone.utc).date()
    rows = db.execute(
        select(DiscoveredEvent.discovered_at).where(DiscoveredEvent.discovered_by == "web_discovery_agent")
    ).scalars().all()
    return sum(1 for ts in rows if ts and ts.date() == today)


def run_discovery_agent(db: Session, config: DiscoveryConfig | None = None) -> RunSummary:
    config = config or config_from_settings(get_settings())
    ai_client = get_ai_client()

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
        if not ai_client.is_configured:
            raise AIClientError(f"{not_configured_message()} — the Event Discovery Agent cannot search the web without it.")

        already_today = _todays_new_event_count(db)

        for query in query_seeds.build_search_queries(config):
            if already_today + summary.new_events >= config.daily_limit:
                logger.info("Daily discovery limit (%d) reached — stopping run early.", config.daily_limit)
                break

            try:
                sources = source_finder.find_candidate_sources(query, ai_client, config.sources_per_query)
            except AIClientError:
                raise
            except Exception:
                logger.exception("Web search failed for query %r — skipping this query.", query)
                continue

            for source in sources:
                if already_today + summary.new_events >= config.daily_limit:
                    break

                try:
                    candidate = page_extractor.extract_event_from_page(source, ai_client)
                except AIClientError:
                    raise
                except Exception:
                    logger.exception("Extraction failed for %s — skipping this page.", source.url)
                    continue
                if candidate is None:
                    continue

                try:
                    organizer_candidate = organizer_identifier.identify_organizer(candidate, ai_client)
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
                    continue

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
                    continue

                run.summary = summary.as_dict()
                db.add(run)
                db.commit()

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
