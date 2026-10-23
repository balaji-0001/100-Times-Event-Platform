"""Community Discovery automation orchestrator ("Agent 5") — fixed rules,
no AI. Reuses `discovery_agent.web_search` (DuckDuckGo, keyless) directly —
it's already generic, not event-specific — and `discovery_agent.categorizer`
for the same deterministic category classification events already use, so a
community and the events it's eventually matched against (Agent 4) share one
category vocabulary.

Flow: generate search queries -> for each query, web-search for candidate
invite links -> read each candidate's own public page/API for real metadata
-> categorize -> validate -> dedup-check -> persist. Every stage that can
fail per-item is caught and logged so one bad candidate can't abort the run;
a search-engine block stops searching but keeps everything already found,
same discipline as Agent 1.
"""

import logging
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import Settings, get_settings
from backend.models import AgentRun, DiscoveredCommunity
from backend.services.community_agent import candidate_extractor, discovery_dedup, query_seeds, storage, validation
from backend.services.community_agent.types import CandidateSource, CommunityDiscoveryConfig, RunSummary
from backend.services.discovery_agent import web_search
from backend.services.discovery_agent.categorizer import categorize

logger = logging.getLogger("community_agent.orchestrator")


DEFAULT_SECTOR_COMMUNITY_SEEDS: tuple[str, ...] = (
    "https://t.me/pharmaindia",
    "https://t.me/healthcare_india",
    "https://t.me/solarenergyindia",
    "https://t.me/telecomtalk",
    "https://t.me/civilengineering_india",
    "https://t.me/mining_engineers",
    "https://t.me/fintech_india",
    "https://t.me/packaging_industry",
    "https://t.me/logistics_india",
    "https://t.me/oilandgas_india",
    "https://t.me/textile_india",
    "https://t.me/manufacturing_india",
)


def _split(csv: str) -> list[str]:
    return [item.strip() for item in csv.split(",") if item.strip()]


def config_from_settings(settings: Settings) -> CommunityDiscoveryConfig:
    return CommunityDiscoveryConfig(
        cities=_split(settings.discovery_target_cities),
        states=_split(settings.discovery_target_states),
        categories=_split(settings.discovery_target_categories),
        search_depth=settings.community_discovery_search_depth,
        sources_per_query=settings.community_discovery_sources_per_query,
        daily_limit=settings.community_discovery_daily_limit,
        confidence_threshold=settings.community_discovery_confidence_threshold,
        seed_urls=list(DEFAULT_SECTOR_COMMUNITY_SEEDS),
    )


def _todays_new_community_count(db: Session) -> int:
    today = datetime.now(timezone.utc).date()
    rows = db.execute(select(DiscoveredCommunity.discovered_at)).scalars().all()
    return sum(1 for ts in rows if ts and ts.date() == today)


def _limit_reached(already_today: int, summary: RunSummary, config: CommunityDiscoveryConfig) -> bool:
    return already_today + summary.new_communities >= config.daily_limit


def _process_url(
    db: Session,
    run: AgentRun,
    url: str,
    config: CommunityDiscoveryConfig,
    summary: RunSummary,
    source_type: str = "search_result",
) -> None:
    source = CandidateSource(url=url, source_type=source_type)
    try:
        candidate = candidate_extractor.extract_community(source)
    except Exception:
        logger.exception("Reading candidate %s failed — skipping it.", url)
        return
    if candidate is None or not candidate.name:
        return

    category, subcategory = categorize(candidate.name, candidate.description, candidate.canonical_url)
    if not category or category == "Other":
        logger.info("Skipping community candidate %r — not matching 12 approved platform categories", candidate.name)
        return
    if config.categories and category not in config.categories:
        logger.info("Skipping community candidate %r — category %r not in target categories", candidate.name, category)
        return

    status, notes, confidence = validation.validate_community(candidate, config.confidence_threshold)

    try:
        storage.persist_community(
            db, candidate=candidate, approval_status=status, verification_notes=notes,
            confidence_score=confidence, category=category, subcategory=subcategory, summary=summary,
        )
    except Exception:
        db.rollback()
        logger.exception("Failed to persist candidate %r — skipping.", candidate.name)
        return

    run.summary = summary.as_dict()
    db.add(run)
    db.commit()


def run_community_discovery_agent(db: Session, config: CommunityDiscoveryConfig | None = None) -> RunSummary:
    config = config or config_from_settings(get_settings())

    run = AgentRun(
        agent_type="community_discovery", status="running", started_at=datetime.now(timezone.utc),
        config_snapshot=asdict(config), summary=RunSummary().as_dict(), created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    summary = RunSummary()
    try:
        already_today = _todays_new_community_count(db)
        seen_urls: set[str] = set()
        search_error: str | None = None

        # Stage 1: Ingest configured / sector seed URLs
        for url in config.seed_urls:
            if _limit_reached(already_today, summary, config):
                break
            if url in seen_urls:
                continue
            seen_urls.add(url)
            _process_url(db, run, url, config, summary, source_type="seed_directory")

        # Stage 2: Web-search the generated queries
        for query in query_seeds.build_search_queries(config):
            if _limit_reached(already_today, summary, config):
                logger.info("Daily community-discovery limit (%d) reached — stopping run early.", config.daily_limit)
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
                if url in seen_urls or _limit_reached(already_today, summary, config):
                    continue
                seen_urls.add(url)
                _process_url(db, run, url, config, summary, source_type="search_result")

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
        logger.exception("Community Discovery Agent run #%s failed", run.id)

    return summary
