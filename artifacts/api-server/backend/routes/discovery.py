import threading
"""Event Discovery & Organizer Research Agent admin API — manual trigger,
run history, and read access to what the agent has found so far.

Every endpoint here requires ADMIN: unlike `acquisition.py`/`outreach.py`
(which currently have no auth dependency at all — a pre-existing gap, not a
pattern worth copying), this router triggers real web scraping runs and
exposes scraped personal contact info (emails/phones), so it gets the same
`require_roles("ADMIN")` gate `routes/dashboard.py` already uses.
"""

from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.core.config import get_settings
from backend.db import get_db
from backend.dependencies import require_roles
from backend.models import AgentRun, DiscoveredEvent, DiscoveredOrganizer, OrganizerContact, User
from backend.schemas import (
    AgentRunOut,
    DiscoveredEventOut,
    DiscoveredOrganizerOut,
    DiscoveryAutoStatusOut,
    DiscoveryAutoToggleRequest,
    DiscoveryRunRequest,
    DiscoveryStatsOut,
    VenueMissingEventOut,
)
from backend.services.discovery_agent.export import XLSX_MEDIA_TYPE, build_events_workbook
from backend.services.discovery_agent.auto_toggle import (
    get_discovery_auto_settings,
    is_discovery_auto_enabled,
    set_discovery_auto_enabled,
    set_discovery_auto_settings,
)
from backend.services.discovery_agent.orchestrator import config_from_settings, run_discovery_agent

router = APIRouter(prefix="/discovery", tags=["event-discovery"])

_admin = Depends(require_roles("ADMIN"))


def _serialize_event(event: DiscoveredEvent) -> DiscoveredEventOut:
    return DiscoveredEventOut.model_validate(event)


def _serialize_organizer(organizer: DiscoveredOrganizer) -> DiscoveredOrganizerOut:
    return DiscoveredOrganizerOut.model_validate(organizer)


@router.post("/run")
def trigger_discovery_run(
    payload: DiscoveryRunRequest | None = None,
    db: Session = Depends(get_db),
    _user: User = _admin,
) -> dict[str, Any]:
    """Manually runs one full discovery cycle now (the same work the
    background scheduler runs on `DISCOVERY_SCAN_INTERVAL_MINUTES`) and
    returns the run id plus the exact structured summary shape the spec
    requires. Blocks until the run finishes, like `/acquisition/organizer-
    scan`'s equivalent manual trigger."""
    config = config_from_settings(get_settings(), db=db)
    config.require_organizer_email = False
    config.is_manual = True
    if payload:
        if payload.cities is not None:
            config.cities = payload.cities
        if payload.states is not None:
            config.states = payload.states
        if payload.countries is not None:
            config.countries = payload.countries
            if payload.countries and not payload.country:
                config.country = payload.countries[0]
            if not payload.cities and payload.countries:
                from backend.services.discovery_agent.country_utils import cities_for_country
                multi_cities = []
                for c in payload.countries:
                    multi_cities.extend(cities_for_country(c))
                if multi_cities:
                    config.cities = list(dict.fromkeys(multi_cities))
        if payload.country is not None:
            config.country = payload.country
            if not payload.cities and not payload.countries:
                from backend.services.discovery_agent.country_utils import cities_for_country
                country_cities = cities_for_country(payload.country)
                if country_cities:
                    config.cities = country_cities
                if payload.country.strip().lower() == "dubai":
                    config.states = ["Dubai Emirate"]
        if payload.categories is not None:
            config.categories = payload.categories
        if payload.search_depth is not None:
            config.search_depth = payload.search_depth
        if payload.sources_per_query is not None:
            config.sources_per_query = payload.sources_per_query
        if payload.daily_limit is not None:
            config.daily_limit = payload.daily_limit
        if payload.confidence_threshold is not None:
            config.confidence_threshold = payload.confidence_threshold
        if payload.require_organizer_email is not None:
            config.require_organizer_email = payload.require_organizer_email
        if payload.date_from is not None:
            config.date_from = payload.date_from
        if payload.date_to is not None:
            config.date_to = payload.date_to
        if payload.sources is not None:
            config.sources = payload.sources
        if payload.events_per_run is not None:
            config.events_per_run = payload.events_per_run
        if payload.target_valid_events is not None:
            config.target_valid_events = payload.target_valid_events
            config.events_per_run = max(config.events_per_run or 0, payload.target_valid_events * 10, 500)
        if payload.fallback_to_other_sector is not None:
            config.fallback_to_other_sector = payload.fallback_to_other_sector
        if payload.reject_no_organizer is not None:
            config.reject_no_organizer = payload.reject_no_organizer
        if payload.require_organizer_phone is not None:
            config.require_organizer_phone = payload.require_organizer_phone
        if payload.require_organizer_website is not None:
            config.require_organizer_website = payload.require_organizer_website
        if payload.reject_past_events is not None:
            config.reject_past_events = payload.reject_past_events
        if payload.reject_unparseable_dates is not None:
            config.reject_unparseable_dates = payload.reject_unparseable_dates
        if payload.reject_missing_location is not None:
            config.reject_missing_location = payload.reject_missing_location
        if payload.reject_missing_ticket_url is not None:
            config.reject_missing_ticket_url = payload.reject_missing_ticket_url
        if payload.reject_unmatched_category is not None:
            config.reject_unmatched_category = payload.reject_unmatched_category
        if payload.min_title_length is not None:
            config.min_title_length = payload.min_title_length
        if payload.min_description_length is not None:
            config.min_description_length = payload.min_description_length
        if payload.min_confidence_score is not None:
            config.min_confidence_score = payload.min_confidence_score
        if payload.blacklisted_keywords is not None:
            config.blacklisted_keywords = payload.blacklisted_keywords
        if payload.excluded_domains is not None:
            config.excluded_domains = payload.excluded_domains

    # Check if a discovery run is already executing in the background
    active_run = db.execute(
        select(AgentRun)
        .where(AgentRun.agent_type == "discovery", AgentRun.status == "running")
        .order_by(AgentRun.id.desc())
    ).scalars().first()

    if active_run is not None:
        return {
            "runId": active_run.id,
            "status": "running",
            "message": f"Discovery run #{active_run.id} is already executing in the background.",
            "isBackground": True,
            "config": active_run.config_snapshot or asdict(config),
            **(active_run.summary or {}),
        }

    # Initialize new AgentRun in running state
    from backend.services.discovery_agent.types import RunSummary
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

    run_id = run.id

    def _bg_discovery_worker():
        from backend.db import SessionLocal
        bg_db = SessionLocal()
        try:
            bg_run = bg_db.get(AgentRun, run_id)
            run_discovery_agent(bg_db, config, run=bg_run)
        except Exception:
            import logging
            logging.getLogger("discovery_agent.worker").exception("Background discovery worker failed for run #%s", run_id)
        finally:
            bg_db.close()

    import sys
    is_testing = "pytest" in sys.modules
    should_run_bg = payload.background if (payload and getattr(payload, "background", None) is not None) else not is_testing

    if should_run_bg:
        worker_thread = threading.Thread(
            target=_bg_discovery_worker,
            name=f"discovery-worker-{run_id}",
            daemon=True,
        )
        worker_thread.start()

        return {
            "runId": run.id,
            "status": "running",
            "message": f"Discovery run #{run.id} started in the background.",
            "isBackground": True,
            "config": asdict(config),
            **run.summary,
        }
    else:
        summary = run_discovery_agent(db, config, run=run)
        db.refresh(run)
        return {
            "runId": run.id,
            "status": run.status,
            **summary.as_dict(),
        }


@router.get("/auto")
def get_discovery_auto(db: Session = Depends(get_db), _user: User = _admin) -> DiscoveryAutoStatusOut:
    """Live state of the discovery-scan on/off switch. When enabled, the
    background loop that's always running (see `services/social_agent/
    scheduler.py`) actually calls `run_discovery_agent` on its configured
    interval instead of skipping the tick."""
    settings = get_settings()
    auto_scope = get_discovery_auto_settings(db)
    return DiscoveryAutoStatusOut(
        enabled=is_discovery_auto_enabled(db),
        interval_minutes=settings.discovery_scan_interval_minutes,
        country=auto_scope.get("country"),
        countries=auto_scope.get("countries") or ([] if not auto_scope.get("country") else [auto_scope.get("country")]),
        cities=auto_scope.get("cities") or [],
        states=auto_scope.get("states") or [],
        categories=auto_scope.get("categories") or [],
        sources=auto_scope.get("sources") or ["web", "linkedin", "facebook", "instagram", "twitter", "telegram", "reddit", "event_platforms"],
        search_depth=auto_scope.get("search_depth"),
        daily_limit=auto_scope.get("daily_limit"),
        events_per_run=auto_scope.get("events_per_run", 50),
        target_valid_events=auto_scope.get("target_valid_events", 25),
        reject_no_organizer=auto_scope.get("reject_no_organizer", False),
        require_organizer_email=auto_scope.get("require_organizer_email", False),
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
        blacklisted_keywords=auto_scope.get("blacklisted_keywords", []),
        excluded_domains=auto_scope.get("excluded_domains", []),
    )


@router.patch("/auto")
def set_discovery_auto(payload: DiscoveryAutoToggleRequest, db: Session = Depends(get_db), _user: User = _admin) -> DiscoveryAutoStatusOut:
    """Flip the switch or configure automated discovery scope. Takes effect on the next scheduler tick — no restart
    needed — and persists across restarts (`agent_settings` table)."""
    settings = get_settings()
    if payload.enabled is not None:
        set_discovery_auto_enabled(db, payload.enabled)

    settings_updates: dict = {}
    if payload.country is not None:
        settings_updates["country"] = payload.country
    if payload.countries is not None:
        settings_updates["countries"] = payload.countries
        if payload.countries and not payload.country:
            settings_updates["country"] = payload.countries[0]
    if payload.cities is not None:
        settings_updates["cities"] = payload.cities
    if payload.states is not None:
        settings_updates["states"] = payload.states
    if payload.categories is not None:
        settings_updates["categories"] = payload.categories
    if payload.sources is not None:
        settings_updates["sources"] = payload.sources
    if payload.search_depth is not None:
        settings_updates["search_depth"] = payload.search_depth
    if payload.daily_limit is not None:
        settings_updates["daily_limit"] = payload.daily_limit
    if payload.events_per_run is not None:
        settings_updates["events_per_run"] = payload.events_per_run
    if payload.target_valid_events is not None:
        settings_updates["target_valid_events"] = payload.target_valid_events

    # Rejection settings
    for field in (
        "reject_no_organizer",
        "require_organizer_email",
        "require_organizer_phone",
        "require_organizer_website",
        "reject_past_events",
        "reject_unparseable_dates",
        "reject_missing_location",
        "reject_missing_ticket_url",
        "reject_unmatched_category",
        "fallback_to_other_sector",
        "min_title_length",
        "min_description_length",
        "min_confidence_score",
        "blacklisted_keywords",
        "excluded_domains",
    ):
        val = getattr(payload, field, None)
        if val is not None:
            settings_updates[field] = val

    if settings_updates:
        set_discovery_auto_settings(db, settings_updates)

    db.commit()
    auto_scope = get_discovery_auto_settings(db)
    return DiscoveryAutoStatusOut(
        enabled=is_discovery_auto_enabled(db),
        interval_minutes=settings.discovery_scan_interval_minutes,
        country=auto_scope.get("country"),
        countries=auto_scope.get("countries") or ([] if not auto_scope.get("country") else [auto_scope.get("country")]),
        cities=auto_scope.get("cities") or [],
        states=auto_scope.get("states") or [],
        categories=auto_scope.get("categories") or [],
        sources=auto_scope.get("sources") or ["web", "linkedin", "facebook", "instagram", "twitter", "telegram", "reddit", "event_platforms"],
        search_depth=auto_scope.get("search_depth"),
        daily_limit=auto_scope.get("daily_limit"),
        events_per_run=auto_scope.get("events_per_run", 50),
        target_valid_events=auto_scope.get("target_valid_events", 25),
        reject_no_organizer=auto_scope.get("reject_no_organizer", False),
        require_organizer_email=auto_scope.get("require_organizer_email", False),
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
        blacklisted_keywords=auto_scope.get("blacklisted_keywords", []),
        excluded_domains=auto_scope.get("excluded_domains", []),
    )


@router.get("/runs/active")
def get_active_discovery_run(
    db: Session = Depends(get_db),
    _user: User = _admin,
) -> dict[str, Any]:
    """Returns the currently active background discovery run, or active: false if none."""
    active_run = db.execute(
        select(AgentRun)
        .where(AgentRun.agent_type == "discovery", AgentRun.status == "running")
        .order_by(AgentRun.id.desc())
    ).scalars().first()

    if active_run is None:
        return {"active": False, "run": None}

    return {
        "active": True,
        "run": AgentRunOut.model_validate(active_run).model_dump(by_alias=True),
    }


@router.post("/runs/stop")
@router.post("/runs/{run_id}/stop")
def stop_discovery_run(
    run_id: int | None = None,
    db: Session = Depends(get_db),
    _user: User = _admin,
) -> dict[str, Any]:
    """Signals an active discovery run to stop immediately and preserves all progress."""
    from backend.services.discovery_agent.orchestrator import cancel_discovery_run

    if run_id is None:
        target_run = db.execute(
            select(AgentRun)
            .where(AgentRun.agent_type == "discovery", AgentRun.status == "running")
            .order_by(AgentRun.id.desc())
        ).scalars().first()
        if target_run is None:
            return {"stopped": False, "message": "No active discovery run found to stop."}
    else:
        target_run = db.get(AgentRun, run_id)
        if target_run is None or target_run.agent_type != "discovery":
            raise HTTPException(status_code=404, detail="Discovery run not found")

    cancel_discovery_run(target_run.id)
    target_run.status = "stopped"
    target_run.completed_at = datetime.now(timezone.utc)
    db.add(target_run)
    db.commit()

    return {
        "stopped": True,
        "runId": target_run.id,
        "status": "stopped",
        "message": f"Discovery run #{target_run.id} has been stopped.",
        "summary": target_run.summary,
    }


@router.get("/runs")
def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = _admin,
) -> list[AgentRunOut]:
    stmt = select(AgentRun).where(AgentRun.agent_type == "discovery").order_by(AgentRun.id.desc()).limit(limit)
    return [AgentRunOut.model_validate(run) for run in db.execute(stmt).scalars().all()]


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db), _user: User = _admin) -> AgentRunOut:
    run = db.get(AgentRun, run_id)
    if run is None or run.agent_type != "discovery":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discovery run not found")
    return AgentRunOut.model_validate(run)



@router.get("/runs/{run_id}/events")
def get_run_discovered_events(
    run_id: int,
    db: Session = Depends(get_db),
    _user: User = _admin,
) -> list[DiscoveredEventOut]:
    """Return all DiscoveredEvent records found during a specific discovery agent run."""
    run = db.get(AgentRun, run_id)
    if run is None or run.agent_type != "discovery":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discovery run not found")

    if run.summary and isinstance(run.summary, dict):
        event_ids = run.summary.get("event_ids") or run.summary.get("discovered_event_ids") or []
        if event_ids:
            events = db.execute(
                select(DiscoveredEvent)
                .options(selectinload(DiscoveredEvent.sources))
                .where(DiscoveredEvent.id.in_(event_ids))
                .order_by(DiscoveredEvent.id.desc())
            ).scalars().all()
            return [_serialize_event(e) for e in events]

    if run.started_at:
        start_bound = run.started_at - timedelta(seconds=60)
        end_bound = (run.completed_at or datetime.now(timezone.utc)) + timedelta(seconds=60)
        events = db.execute(
            select(DiscoveredEvent)
            .options(selectinload(DiscoveredEvent.sources))
            .where(
                DiscoveredEvent.discovered_at >= start_bound,
                DiscoveredEvent.discovered_at <= end_bound,
            )
            .order_by(DiscoveredEvent.id.desc())
        ).scalars().all()
        return [_serialize_event(e) for e in events]

    return []


@router.get("/events")
def list_discovered_events(
    country: str | None = None,
    city: str | None = None,
    category: str | None = None,
    verification_status: str | None = Query(default=None, alias="verificationStatus"),
    limit: int = Query(default=50, ge=1, le=5000),  # the console fetches the full list for its browsing/filtering tables — see `/stats` for cheap true counts
    db: Session = Depends(get_db),
    _user: User = _admin,
) -> list[DiscoveredEventOut]:
    stmt = select(DiscoveredEvent).options(selectinload(DiscoveredEvent.sources)).order_by(DiscoveredEvent.id.desc())
    if country and country.strip().lower() not in ("all", "all countries", "worldwide", ""):
        c_low = country.strip().lower()
        if c_low == "dubai":
            stmt = stmt.where(
                or_(
                    DiscoveredEvent.country.ilike("%dubai%"),
                    DiscoveredEvent.country.ilike("%united arab emirates%"),
                    DiscoveredEvent.city.ilike("%dubai%"),
                )
            )
        elif c_low in ("united arab emirates", "uae"):
            stmt = stmt.where(
                or_(
                    DiscoveredEvent.country.ilike("%united arab emirates%"),
                    DiscoveredEvent.country.ilike("%dubai%"),
                    DiscoveredEvent.city.ilike("%dubai%"),
                )
            )
        else:
            stmt = stmt.where(DiscoveredEvent.country.ilike(f"%{country.strip()}%"))
    if city:
        stmt = stmt.where(DiscoveredEvent.city.ilike(f"%{city}%"))
    if category:
        stmt = stmt.where(DiscoveredEvent.category.ilike(f"%{category}%"))
    if verification_status:
        stmt = stmt.where(DiscoveredEvent.verification_status == verification_status)
    stmt = stmt.limit(limit)
    return [_serialize_event(event) for event in db.execute(stmt).scalars().all()]


@router.get("/organizers")
def list_discovered_organizers(
    limit: int = Query(default=50, ge=1, le=5000),  # see `/events` above — the console fetches the full list
    db: Session = Depends(get_db),
    _user: User = _admin,
) -> list[DiscoveredOrganizerOut]:
    stmt = (
        select(DiscoveredOrganizer)
        .options(selectinload(DiscoveredOrganizer.contacts))
        .order_by(DiscoveredOrganizer.id.desc())
        .limit(limit)
    )
    return [_serialize_organizer(organizer) for organizer in db.execute(stmt).scalars().all()]


@router.get("/stats")
def get_discovery_stats(db: Session = Depends(get_db), _user: User = _admin) -> DiscoveryStatsOut:
    """Real database counts for the console's overview cards — computed
    with SQL COUNT, never by fetching a page of rows and taking `.length`,
    so these never silently stop growing once discovery passes the
    `/events`/`/organizers` list endpoints' 200-row cap."""
    venue_missing_filter = (
        DiscoveredEvent.event_format.in_(("offline", "hybrid")),
        (DiscoveredEvent.venue.is_(None)) | (DiscoveredEvent.venue == ""),
    )
    venue_missing_sample = db.execute(
        select(DiscoveredEvent.id, DiscoveredEvent.name, DiscoveredEvent.city)
        .where(*venue_missing_filter)
        .order_by(DiscoveredEvent.id.desc())
        .limit(5)
    ).all()

    def count(*where: Any) -> int:
        stmt = select(func.count()).select_from(DiscoveredEvent)
        if where:
            stmt = stmt.where(*where)
        return db.scalar(stmt) or 0

    rejected_total = count(DiscoveredEvent.verification_status == "REJECTED")
    accepted_total = count(DiscoveredEvent.verification_status == "VERIFIED")
    from sqlalchemy import String, cast
    missing_email_total = db.scalar(
        select(func.count())
        .select_from(DiscoveredEvent)
        .where(
            DiscoveredEvent.verification_status == "REJECTED",
            cast(DiscoveredEvent.verification_notes, String).ilike("%MISSING_ORGANIZER_EMAIL%"),
        )
    ) or 0

    return DiscoveryStatsOut(
        events_total=count(),
        organizers_total=db.scalar(select(func.count()).select_from(DiscoveredOrganizer)) or 0,
        contacts_total=db.scalar(select(func.count()).select_from(OrganizerContact)) or 0,
        organizers_with_email_total=db.scalar(
            select(func.count()).select_from(DiscoveredOrganizer).where(DiscoveredOrganizer.email.is_not(None), DiscoveredOrganizer.email != "")
        ) or 0,
        needs_review_total=count(DiscoveredEvent.verification_status == "NEEDS_REVIEW"),
        new_events_total=count(DiscoveredEvent.discovery_status == "NEW"),
        online_total=count(DiscoveredEvent.event_format == "online"),
        offline_total=count(DiscoveredEvent.event_format == "offline"),
        hybrid_total=count(DiscoveredEvent.event_format == "hybrid"),
        format_unknown_total=count(DiscoveredEvent.event_format.is_(None) | ~DiscoveredEvent.event_format.in_(("online", "offline", "hybrid"))),
        rejected_total=rejected_total,
        accepted_total=accepted_total,
        missing_organizer_email_total=missing_email_total,
        venue_missing_total=count(*venue_missing_filter),
        venue_missing_sample=[VenueMissingEventOut(id=row.id, name=row.name, city=row.city) for row in venue_missing_sample],
    )


@router.get("/export.xlsx")
def export_discovered_events(
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    _user: User = _admin,
) -> Response:
    """Excel download of discovered events (and their organizers) whose
    event date falls within [from, to]. Either bound may be left out; with
    no range at all every event is included, undated ones too."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'from' must be on or before 'to'.")

    stmt = select(DiscoveredEvent).options(selectinload(DiscoveredEvent.organizer))
    if date_from:
        stmt = stmt.where(DiscoveredEvent.event_date >= date_from)
    if date_to:
        stmt = stmt.where(DiscoveredEvent.event_date <= date_to)
    stmt = stmt.order_by(DiscoveredEvent.event_date.asc().nulls_last(), DiscoveredEvent.id.asc())
    events = list(db.execute(stmt).scalars().all())

    label = f"{date_from or 'start'}_to_{date_to or 'latest'}" if (date_from or date_to) else "all"
    return Response(
        content=build_events_workbook(events),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="discovered-events_{label}.xlsx"'},
    )
