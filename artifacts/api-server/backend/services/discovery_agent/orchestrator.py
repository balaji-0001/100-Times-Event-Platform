"""Event Discovery automation orchestrator ("Agent 1") — fixed rules and a
headless browser, no AI.

Sources: operational source adapters, the Ticketmaster API, the configured
event-listing sites for each target city, and web-search queries (whatever
search providers are configured; keyless DuckDuckGo otherwise), whose
result pages are read too.

Concurrency model: all network work — adapter reads, listing/result page
reads, searches, organizer lookups — runs in bounded worker pools
(`config.max_parallel_*`); everything that touches the DB (categorize,
validate, dedup, persist) runs on the run's own thread, in the order work
completes, so verified events are stored (and visible to the UI's polling)
the moment they're ready. Per-candidate flow on that thread:

  screen (guardrails, categorize, cheap validation incl. date/country/sector,
  pre-lookup dedup) -> [worker] organizer lookup -> full validation -> persist

so the expensive organizer lookup never runs for a candidate the cheap rules
already reject. The run stops launching work once `target_valid_events`
VERIFIED events are stored (NEEDS_REVIEW never counts), the time budget
(`max_run_seconds`) is spent, or every source is exhausted; the stop reason
and any shortfall are recorded in the run summary along with per-stage
timings. Expanded queries run only when the first wave falls short.

Every stage that can fail per-item is caught and logged so one bad candidate
can't abort the run. Every DB write goes through `storage.py`, which
dedup-checks before inserting, so a resumed or re-run pass never creates
duplicate records.
"""

import logging
import re
import threading
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import Settings, get_settings
from backend.models import AgentExecutionMetric, AgentRun, DiscoveredEvent
from backend.services import guardrails
from backend.services.discovery_agent import catalog, categorizer, geo_scope, listing_sources, organizer_identifier, page_extractor, query_seeds, storage, validation, web_search
from backend.services.discovery_agent.adapters.base import SourceError
from backend.services.discovery_agent.discovery_dedup import DedupIndex
from backend.services.discovery_agent.search_providers import search_engine
from backend.services.discovery_agent.search_providers.engine import SearchRunStats
from backend.services.discovery_agent.source_report import RunSourceReport
from backend.services.discovery_agent.types import DiscoveryConfig, OrganizerCandidate, RunSummary
from backend.services.social_agent import web_fetch

logger = logging.getLogger("discovery_agent.orchestrator")

# Run-config fields never written to the run record or returned by the API.
_SECRET_CONFIG_FIELDS = ("ticketmaster_api_key",)


def redacted_config(config: DiscoveryConfig | dict | None) -> dict:
    """A run's config as stored/returned: credentials replaced by whether they were set."""
    data = asdict(config) if isinstance(config, DiscoveryConfig) else dict(config or {})
    for name in _SECRET_CONFIG_FIELDS:
        if name in data:
            data[name] = "(set)" if data[name] else None
    return data


def _build_summary_dict(summary: RunSummary) -> dict:
    return summary.as_dict()


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


def config_from_settings(settings: Settings, db: Session | None = None, include_auto_scope: bool = True) -> DiscoveryConfig:
    """Base config for a run. Automatic runs (`include_auto_scope=True`) use the
    admin's saved Automatic Discovery scope; a manual run passes False so it
    searches exactly what was selected on the Manual Research page, never
    silently inheriting saved states/sectors/websites it left empty."""
    # Dynamically retrieve categories from the website/database if available
    db_cats = categorizer.get_supported_categories(db) if db is not None else []
    target_categories = db_cats if db_cats else _split(settings.discovery_target_categories)

    # Check for admin-configured auto discovery scope settings in db
    auto_scope: dict = {}
    if db is not None and include_auto_scope:
        try:
            from backend.services.discovery_agent.auto_toggle import get_discovery_auto_settings
            auto_scope = get_discovery_auto_settings(db)
        except Exception:
            pass

    # Geography: the saved scope as a whole when anything geographic was saved
    # (never topped up with .env defaults - those listed e.g. "Tokyo Prefecture"
    # and leaked into country-specific runs); .env defaults only when nothing is.
    has_saved_geo = any(auto_scope.get(k) for k in ("countries", "country", "cities", "states", "locations"))
    if has_saved_geo:
        cities = list(auto_scope.get("cities") or [])
        states = list(auto_scope.get("states") or [])
        countries = list(auto_scope.get("countries") or [])
    else:
        cities = _split(settings.discovery_target_cities)
        states = _split(settings.discovery_target_states)
        countries = _split(getattr(settings, "discovery_target_countries", ""))
    if auto_scope.get("categories"):
        target_categories = auto_scope["categories"]
    country = auto_scope.get("country")
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
        locations=list(auto_scope.get("locations") or []),
        region_cities=dict(auto_scope.get("region_cities") or {}),
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
        keep_rejected_events=auto_scope.get("keep_rejected_events", True),
        min_title_length=auto_scope.get("min_title_length", 8),
        min_description_length=auto_scope.get("min_description_length", 20),
        min_confidence_score=auto_scope.get("min_confidence_score", 20),
        blacklisted_keywords=auto_scope.get("blacklisted_keywords") or [],
        excluded_domains=auto_scope.get("excluded_domains") or [],
        search_providers=auto_scope.get("search_providers"),
    )


def _todays_new_event_count(db: Session) -> int:
    today = datetime.now(timezone.utc).date()
    rows = db.execute(
        select(DiscoveredEvent.discovered_at).where(DiscoveredEvent.discovered_by == "web_discovery_agent")
    ).scalars().all()
    return sum(1 for ts in rows if ts and ts.date() == today)



# ---------------------------------------------------------------------------
# Per-candidate stages (DB thread)
# ---------------------------------------------------------------------------


def _validation_kwargs(config: DiscoveryConfig, supported_categories: list[str]) -> dict:
    return dict(
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
        target_countries=_target_countries(config),
        target_places=geo_scope.resolve(config).place_rules(),
    )


def _target_countries(config: DiscoveryConfig) -> list[str]:
    """Every selected country (not just the first), normalized - including the
    countries of selected cities when no country was picked."""
    return list(geo_scope.resolve(config).countries)


def _screen_candidate(
    db: Session,
    run: AgentRun,
    candidate,
    config: DiscoveryConfig,
    summary: RunSummary,
    supported_categories: list[str],
    index: DedupIndex | None = None,
) -> bool:
    """Everything that needs no network: guardrails, categorization, the
    category gate, every validation rule that doesn't depend on the organizer
    (title, dates, date window, country, location, blacklists), and a dedup
    check. Returns True only when the candidate is worth an organizer lookup.
    A rule rejection here is stored exactly as the full validation would
    have stored it (without the organizer lookup it no longer needs)."""
    summary.events_discovered += 1

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
        return False

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
    target_categories = set(config.categories) if config.categories else set(supported_categories)
    is_unmatched = candidate.category not in target_categories or candidate.category.lower() == "other"
    if is_unmatched:
        if getattr(config, "sector_scoped", False):
            # The admin picked sectors: anything outside them is not what the
            # run was asked for. The 'Other' fallback only applies to runs with
            # no sector chosen — it used to let concerts through as VERIFIED.
            return _reject_off_sector(db, run, candidate, config, summary, index)
        if getattr(config, "fallback_to_other_sector", True):
            candidate.category = "Other"
        elif getattr(config, "reject_unmatched_category", False):
            return _reject_off_sector(db, run, candidate, config, summary, index)

    # Organizer-independent rules only: the organizer requirements are
    # switched off here and enforced after the lookup.
    kwargs = _validation_kwargs(config, supported_categories)
    kwargs.update(require_organizer_email=False, reject_no_organizer=False, require_organizer_phone=False, require_organizer_website=False)
    pre = validation.validate_event(candidate, config.confidence_threshold, organizer=None, **kwargs)
    if pre.status == "REJECTED":
        if pre.rejection_reason == "OUT_OF_TARGET_COUNTRY":
            summary.out_of_target_country += 1
        elif pre.rejection_reason == "OUT_OF_TARGET_CITY":
            summary.out_of_target_city += 1
        _persist(db, run, candidate, None, pre, summary, index)
        return False

    # A copy rejected by an earlier run doesn't block a re-check under this run's rules.
    if index is not None and index.find_event_id(
        name=candidate.name, date=candidate.date, city=candidate.city, url=candidate.ticket_url or candidate.url, skip_rejected=True
    ) is not None:
        summary.duplicate_events += 1
        return False
    return True


def _reject_off_sector(db, run, candidate, config, summary, index) -> bool:
    """An event outside the run's sectors. Kept (REJECTED, with the reason)
    when it has a real sector of its own and the run keeps rejections;
    sector-less noise (concerts, parties) is only counted."""
    if getattr(config, "keep_rejected_events", True) and candidate.category and candidate.category.lower() != "other":
        result = validation.ValidationResult(
            "REJECTED",
            [f"Its sector ({candidate.category}) is not one of the selected sectors ({', '.join(config.categories or [])})."],
            0,
            validation.try_parse_date(candidate.date),
            rejection_reason="UNSUPPORTED_CATEGORY",
        )
        _persist(db, run, candidate, None, result, summary, index)
    else:
        summary.unsupported_category += 1
        summary.rejected_events += 1
    return False


def _finalize_candidate(
    db: Session,
    run: AgentRun,
    candidate,
    organizer_candidate: OrganizerCandidate | None,
    config: DiscoveryConfig,
    summary: RunSummary,
    supported_categories: list[str],
    index: DedupIndex | None = None,
) -> str | None:
    """Full validation (now with the organizer) and persistence. Returns the
    stored verification status, or None when nothing was stored."""
    organizer_candidate = organizer_candidate or OrganizerCandidate(found=False)
    if config.require_organizer_email and (not organizer_candidate.found or not organizer_candidate.email):
        if getattr(config, "keep_rejected_events", True):
            result = validation.ValidationResult(
                "REJECTED",
                ["No publicly listed organizer e-mail was found, and this run requires one."],
                0,
                validation.try_parse_date(candidate.date),
                rejection_reason="MISSING_ORGANIZER_EMAIL",
            )
            return _persist(db, run, candidate, organizer_candidate, result, summary, index)
        summary.missing_organizer_email += 1
        summary.rejected_events += 1
        return None
    result = validation.validate_event(
        candidate,
        config.confidence_threshold,
        organizer=organizer_candidate,
        **_validation_kwargs(config, supported_categories),
    )
    return _persist(db, run, candidate, organizer_candidate, result, summary, index)


def _persist(db, run, candidate, organizer_candidate, result, summary, index) -> str | None:
    status, notes, confidence, event_date = result
    try:
        stored = storage.persist_event(
            db,
            candidate=candidate,
            organizer=organizer_candidate,
            verification_status=status,
            verification_notes=notes,
            confidence_score=confidence,
            event_date=event_date,
            summary=summary,
            rejection_reason=getattr(result, "rejection_reason", None),
            index=index,
        )
    except Exception:
        db.rollback()
        logger.exception("Failed to persist candidate %r — skipping.", candidate.name)
        return None
    return status if stored is not None else None


def _process_candidate(
    db: Session,
    run: AgentRun,
    candidate,
    config: DiscoveryConfig,
    summary: RunSummary,
    supported_categories: list[str],
) -> None:
    """One candidate end to end, synchronously (kept for scripts/tests that
    process a single candidate; the run itself uses the concurrent pipeline)."""
    if not _screen_candidate(db, run, candidate, config, summary, supported_categories):
        return
    try:
        organizer_candidate = organizer_identifier.identify_organizer(candidate)
    except Exception:
        logger.exception("Organizer identification failed for %s — continuing without an organizer.", candidate.url)
        organizer_candidate = None
    _finalize_candidate(db, run, candidate, organizer_candidate, config, summary, supported_categories)
    run.summary = _build_summary_dict(summary)
    db.add(run)
    try:
        db.commit()
    except Exception:
        db.rollback()


def _target_reached(summary: RunSummary, config: DiscoveryConfig) -> bool:
    target = getattr(config, "target_valid_events", None)
    return bool(target and target > 0 and summary.verified_events >= target)


def _limit_reached(already_today: int, summary: RunSummary, config: DiscoveryConfig) -> bool:
    target_valid = getattr(config, "target_valid_events", None)
    if target_valid and target_valid > 0:
        # Only VERIFIED events count toward the requested number — a candidate
        # held for review is not a valid event.
        if _target_reached(summary, config):
            return True
        # Safety circuit-breaker ceiling only if the web is completely exhausted:
        return summary.events_discovered >= max(target_valid * 25, 2500)

    max_for_run = getattr(config, "events_per_run", None)
    if max_for_run and summary.events_discovered >= max_for_run:
        return True
    return summary.new_events >= config.daily_limit


# ---------------------------------------------------------------------------
# Work selection
# ---------------------------------------------------------------------------


_covers_countries = catalog.covers_countries


def _select_adapter_ids(requested: set[str], countries: list[str] | None = None) -> list[str]:
    """Directory adapters this selection schedules (see `catalog.plan_sources`:
    the "Global Directories & Adapters" toggle must be on; inside it, the
    individually ticked sources, else its defaults; only implemented sources
    covering the selected countries). Consumer aggregators run as listing
    pages, search engines as providers — never as adapters here."""
    return catalog.plan_sources(requested, countries).adapters


_DEFAULT_CITIES = ["London", "New York", "San Francisco", "Singapore", "Berlin", "Dubai", "Mumbai", "Bengaluru", "Tokyo", "Paris"]
_YEAR_IN_URL = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def _normalize_url(url: str) -> str:
    return url.split("#", 1)[0].strip()


def _is_stale_url(url: str) -> bool:
    """A result page whose URL path only names past years (".../2023/...")
    is an expired edition — skip it before fetching."""
    years = {int(y) for y in _YEAR_IN_URL.findall(urlparse(url).path)}
    return bool(years) and max(years) < date.today().year


# ---------------------------------------------------------------------------
# Concurrent pipeline
# ---------------------------------------------------------------------------


class _Stopped(Exception):
    pass


class _DiscoveryPipeline:
    """Owns one run's worker pools, work queues and bookkeeping. `execute()`
    runs on the caller's (DB) thread until a stop condition is met."""

    _SUMMARY_FLUSH_SECONDS = 2.0
    _CANCEL_CHECK_SECONDS = 1.5

    def __init__(self, db, run, config, summary, supported_categories, already_today):
        self.db, self.run, self.config, self.summary = db, run, config, summary
        self.categories = supported_categories
        self.already_today = already_today
        self.index = DedupIndex(db)
        self.geo = geo_scope.resolve(config)
        self.requested = set(config.sources or [])
        self.t0 = time.perf_counter()
        self.deadline = self.t0 + max(int(getattr(config, "max_run_seconds", 900) or 900), 10)
        self.pages_read: set[str] = set()
        self.queries_issued: set[str] = set()
        self.search_error: str | None = None
        self.stop_reason: str | None = None
        self.cache_before = web_fetch.cache_stats()

        self.search_pool = ThreadPoolExecutor(max_workers=max(1, config.max_parallel_searches), thread_name_prefix="disc-search")
        self.page_pool = ThreadPoolExecutor(max_workers=max(1, config.max_parallel_fetches), thread_name_prefix="disc-page")
        self.org_pool = ThreadPoolExecutor(max_workers=max(1, config.max_parallel_organizer_lookups), thread_name_prefix="disc-org")
        self.pending: dict[Future, tuple[str, object]] = {}
        self.inflight = {"search": 0, "page": 0, "org": 0}

        # Per-source execution record and this run's search accounting. Provider
        # selection: the admin's list, else every configured provider.
        self.report = RunSourceReport()
        selected_providers = getattr(config, "search_providers", None)
        self.allowed_providers: set[str] | None = set(selected_providers) if selected_providers is not None else None
        budget = getattr(config, "paid_search_budget", None)
        self.search_stats = SearchRunStats(
            allowed=self.allowed_providers,
            paid_budget=budget if budget is not None else get_settings().paid_search_calls_per_run,
        )
        self.disabled_sources = catalog.admin_disabled_ids(db)
        self.channels: dict[str, bool] = {}

        # (kind, origin, arg): ("adapter", id, id) | ("ticketmaster", "ticketmaster_api", places) | ("listing", origin, url)
        self.source_jobs: deque = deque()
        self.result_pages: deque[tuple[str, str]] = deque()  # (search provider id, url)
        self.query_waves: list[list[str]] = []
        self.queries: deque[str] = deque()
        self.organizer_jobs: deque = deque()

        self._stats_lock = threading.Lock()
        self.stage_ms = {"search": 0.0, "page_read": 0.0, "organizer": 0.0}
        # Real per-stage progress, persisted with the run (Plan → Collect → Read
        # pages → Screen → Find organizer → Decide & save) for the progress view.
        self.counts = {
            "planned_queries": 0, "planned_source_reads": 0,
            "searches": 0, "search_results": 0, "pages_read": 0, "result_urls_skipped": 0,
            "screened": 0, "passed_screening": 0,
            "organizer_lookups": 0,
        }
        self.db_ms = 0.0
        self.milestones: dict[str, float] = {}
        self.scope_stats: dict = {}
        self.source_jobs_planned: list = []
        self._last_flush = 0.0
        self._last_cancel_check = 0.0

    # -------------------------------------------------------------- planning
    def plan(self) -> None:
        self._plan()
        self.source_jobs = self._round_robin_by_source(self.source_jobs)
        self.source_jobs_planned = list(self.source_jobs)
        self.counts["planned_queries"] = len(self.queries) + sum(len(wave) for wave in self.query_waves)
        self.counts["planned_source_reads"] = len(self.source_jobs)

    @staticmethod
    def _round_robin_by_source(jobs) -> deque:
        """Take queued reads one per source in turn (each source keeps its own
        order), so a source with many city pages (Eventbrite) can't use up the
        run before the other selected sources are read at all."""
        queues: dict[str, deque] = {}
        for job in jobs:
            queues.setdefault(job[1], deque()).append(job)
        ordered: deque = deque()
        while queues:
            for origin in list(queues):
                ordered.append(queues[origin].popleft())
                if not queues[origin]:
                    del queues[origin]
        return ordered
        self.summary.scope = self.scope()  # visible to the UI from the first poll

    def scope(self) -> dict:
        """What this run covers, as planned from the admin's selection."""
        geo_sum = self.geo.summary()
        cities_list = list(geo_sum.get("cities_list") or [])
        for c in (getattr(self.config, "cities", None) or []):
            if c and c not in cities_list:
                cities_list.append(c)
        return {
            **geo_sum,
            "cities_list": cities_list,
            "sectors": list(self.config.categories or []),
            "adapters": sum(1 for job in self.source_jobs_planned if job[0] == "adapter"),
            "listing_pages": sum(1 for job in self.source_jobs_planned if job[0] == "listing"),
            "channels": self.channels,
            **self.scope_stats,
        }

    def _plan(self) -> None:
        config = self.config
        requested = self.requested
        report = self.report
        # Listing pages / Ticketmaster are expanded per city: the selected
        # cities with their own countries, plus major cities of selected
        # countries that have none, round-robin so every country is included.
        places = self.geo.anchor_places(12)
        cities = [city for city, _ in places] or list(_DEFAULT_CITIES)
        plan = catalog.plan_sources(requested, self.geo.countries, self.disabled_sources)
        self.channels = plan.channels
        names = {src["id"]: src["name"] for src in catalog.ALL_CANDIDATE_SOURCES}

        # --- General Web Search: the selected providers (all configured if none chosen).
        if plan.channels["web"]:
            for pid, provider in search_engine.providers.items():
                if self.allowed_providers is not None and pid not in self.allowed_providers:
                    continue
                reason = provider.unavailable_reason()
                cooling = search_engine._breaker_open(pid)
                record = report.add(pid, provider.display_name or provider.provider_name, "web", "search_provider",
                                    configured=reason is None, available=not cooling)
                if reason:
                    report.skip(pid, record.name, "web", "search_provider", reason, configured=False)

        # --- Global Directories & Adapters.
        for sid, reason in plan.skipped:
            channel = catalog.channel_of(next(s for s in catalog.ALL_CANDIDATE_SOURCES if s["id"] == sid))
            implemented = catalog.is_implemented(sid)
            report.skip(sid, names.get(sid, sid), channel, "adapter" if channel == "directories" else "aggregator", reason,
                        configured=implemented, available=implemented and sid not in self.disabled_sources)
        for sid in _select_adapter_ids(requested, self.geo.countries):
            if sid in self.disabled_sources:
                report.skip(sid, names.get(sid, sid), "directories", "adapter", "disabled on the Source Registry page", available=False)
                continue
            report.add(sid, names.get(sid, sid), "directories", "adapter")
            self.source_jobs.append(("adapter", sid, sid))

        # --- Ticketmaster (its own switch + key).
        tm_key = getattr(config, "ticketmaster_api_key", None)
        tm_enabled = getattr(config, "ticketmaster_enabled", False) or ("ticketmaster" in requested)
        if tm_enabled:
            report.add("ticketmaster_api", "Ticketmaster Discovery API", "apis", "api", configured=bool(tm_key))
            if tm_key:
                self.source_jobs.append(("ticketmaster", "ticketmaster_api", places or [(c, None) for c in cities]))
            else:
                report.skip("ticketmaster_api", "Ticketmaster Discovery API", "apis", "api", "not configured: no Ticketmaster API key", configured=False)

        # --- Consumer Aggregators: each selected aggregator's city pages (its
        # template from the website list, else its registry template). Other
        # sites the admin added run whenever listed, tracked per site.
        by_aggregator: dict[str, list[str]] = {}
        custom: list[str] = []
        for template in config.listing_urls or []:
            aid = catalog.aggregator_for_url(template)
            (by_aggregator.setdefault(aid, []) if aid else custom).append(template)
        from backend.services.discovery_agent.adapters import adapter_manager

        for aid in plan.aggregators:
            # Explicitly ticked: its registry city page if the website list has none.
            templates = by_aggregator.get(aid) or ([adapter_manager.get_adapter(aid).listing_template()] if aid in requested else [])
            if not templates:
                report.skip(aid, names.get(aid, aid), "aggregators", "aggregator", "no listing page for it in the website list")
                continue
            report.add(aid, names.get(aid, aid), "aggregators", "aggregator")
            for url in listing_sources.build_listing_urls(templates, cities, countries=self.geo.countries, places=places):
                self.source_jobs.append(("listing", aid, url))
        for template in custom:
            origin = f"custom:{urlparse(template).netloc.lower().removeprefix('www.') or template}"
            report.add(origin, origin.removeprefix("custom:"), "custom", "custom_website")
            for url in listing_sources.build_listing_urls([template], cities, countries=self.geo.countries, places=places):
                self.source_jobs.append(("listing", origin, url))

        if plan.channels["web"]:
            first_wave = query_seeds.build_search_queries(config)
            self.queries.extend(first_wave)
            self.scope_stats["first_wave_queries"] = len(first_wave)
            if getattr(config, "target_valid_events", None):
                # Expanded queries run only if the first wave falls short.
                self.query_waves.append(query_seeds.build_expanded_queries(config))

    # ------------------------------------------------------------ worker jobs
    def _timed(self, stage: str, fn, *args, **kwargs):
        start = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            with self._stats_lock:
                self.stage_ms[stage] += (time.perf_counter() - start) * 1000

    def _read_source(self, kind: str, arg):
        config = self.config
        if kind == "adapter":
            from backend.services.discovery_agent.adapters import adapter_manager

            adapter = adapter_manager.get_adapter(arg)
            if not adapter:
                raise SourceError("not_implemented", f"no adapter registered for {arg!r}")
            return self._timed("page_read", adapter.discover, config, limit=config.events_per_listing)
        if kind == "ticketmaster":
            from backend.services.discovery_agent import ticketmaster

            return self._timed(
                "page_read",
                ticketmaster.fetch_ticketmaster_events,
                api_key=config.ticketmaster_api_key,
                countries=self.geo.countries,
                categories=self.categories,
                max_events_per_city=config.events_per_listing,
                places=arg,
            )
        result = self._timed("page_read", page_extractor.extract_events_from_page, arg, config.events_per_listing, config.cities)
        if not result and kind == "listing":
            reason = web_fetch.failure_reason(arg)
            if reason:  # the page could not be read — not "no events"
                raise SourceError("unreachable", f"{arg}: {reason}")
        return result

    def _job_source(self, kind: str, origin: str, arg):
        """One source read in a worker thread, recorded in the run's source
        report (timing, candidates, or the failure reason)."""
        if kind == "page":  # a search-result page: counted under its provider in _handle
            return self._read_source(kind, arg)
        t0 = self.report.started(origin)
        try:
            result = self._read_source(kind, arg)
        except Exception as exc:
            self.report.finished(origin, t0, ok=False, error=str(exc) or type(exc).__name__)
            raise
        self.report.finished(origin, t0, ok=True, candidates=len(result or []))
        return result

    def _job_search(self, query: str) -> list[str]:
        config = self.config
        with web_search.run_context(self.allowed_providers, self.search_stats, "discovery"):
            return self._timed(
                "search",
                web_search.search,
                query,
                max_results=config.sources_per_query,
                country=self.geo.countries[0] if len(self.geo.countries) == 1 else None,
                date_range=(config.date_from, config.date_to),
                requested_sources=self.requested,
            )

    def _job_organizer(self, candidate):
        # Organizer lookups search too: same provider selection, same accounting.
        with web_search.run_context(self.allowed_providers, self.search_stats, "organizer_lookup"):
            return self._timed("organizer", organizer_identifier.identify_organizer, candidate)

    # ------------------------------------------------------------- submission
    def _submit(self, pool, slot: str, kind: str, payload, fn, *args):
        future = pool.submit(fn, *args)
        self.pending[future] = (kind, payload)
        self.inflight[slot] += 1

    def _organizer_backlog(self) -> int:
        return len(self.organizer_jobs) + self.inflight["org"]

    def _fill(self) -> None:
        cfg = self.config
        # Organizer lookups first: they turn screened candidates into verified events.
        while self.organizer_jobs and self.inflight["org"] < cfg.max_parallel_organizer_lookups:
            candidate = self.organizer_jobs.popleft()
            self._submit(self.org_pool, "org", "organizer", candidate, self._job_organizer, candidate)

        # Backpressure: don't discover far more candidates than can be verified.
        target = getattr(cfg, "target_valid_events", None) or 50
        if self._organizer_backlog() > max(24, 2 * target):
            return

        page_cap = cfg.max_parallel_fetches
        # Alternate source pages and search-result pages so neither starves.
        while self.inflight["page"] < page_cap and (self.source_jobs or self.result_pages):
            if self.result_pages and (not self.source_jobs or self.inflight["page"] % 2 == 1):
                origin, url = self.result_pages.popleft()
                self._submit(self.page_pool, "page", "page", (origin, url), self._job_source, "page", origin, url)
            else:
                kind, origin, arg = self.source_jobs.popleft()
                self._submit(self.page_pool, "page", "source", (kind, origin, arg), self._job_source, kind, origin, arg)

        while self.queries and self.inflight["search"] < cfg.max_parallel_searches and self.search_error is None:
            query = self.queries.popleft()
            if query in self.queries_issued:
                continue
            self.queries_issued.add(query)
            self._submit(self.search_pool, "search", "search", query, self._job_search, query)

    # --------------------------------------------------------------- results
    def _milestone(self, name: str) -> None:
        self.milestones.setdefault(name, round((time.perf_counter() - self.t0) * 1000))

    def _accept_candidates(self, candidates, origin: str | None = None) -> None:
        summary = self.summary
        for candidate in candidates or []:
            self._check_stop()
            self._milestone("first_candidate_ms")
            candidate.discovery_origin = origin
            before = (summary.duplicate_events, summary.unsupported_category)
            start = time.perf_counter()
            keep = _screen_candidate(self.db, self.run, candidate, self.config, self.summary, self.categories, self.index)
            self.db_ms += (time.perf_counter() - start) * 1000
            self.counts["screened"] += 1
            if keep:
                self.counts["passed_screening"] += 1
                self.organizer_jobs.append(candidate)
            elif summary.duplicate_events > before[0]:
                self.report.outcome(origin, "duplicates")
            elif summary.unsupported_category > before[1]:
                self.report.outcome(origin, "off_sector")
            else:
                self.report.outcome(origin, "rejected")

    def _accept_result_urls(self, urls) -> None:
        excluded = [d.strip().lower() for d in (getattr(self.config, "excluded_domains", None) or []) if d.strip()]
        for raw in urls or []:
            url = _normalize_url(raw)
            if (
                not url
                or url in self.pages_read
                or web_fetch.is_known_permanent_failure(url)
                or _is_stale_url(url)
                or any(d in url.lower() for d in excluded)
            ):
                self.counts["result_urls_skipped"] += 1
                continue
            self.pages_read.add(url)
            self.result_pages.append((self.search_stats.origin_of(raw) or self.search_stats.origin_of(url) or "web", url))

    def _handle(self, future: Future, kind: str, payload) -> None:
        slot = {"search": "search", "organizer": "org"}.get(kind, "page")
        self.inflight[slot] -= 1
        try:
            result = future.result()
        except web_search.SearchBlocked as exc:
            self.search_error = str(exc)
            self.queries.clear()
            logger.warning("Web search stopped: %s", exc)
            return
        except SourceError as exc:
            # Recorded in the source report by the worker; the run continues with the other sources.
            logger.warning("Discovery source %r failed (%s): %s", payload[1] if isinstance(payload, tuple) else payload, exc.kind, exc)
            return
        except Exception:
            if kind == "organizer":
                logger.exception("Organizer identification failed for %s — continuing without an organizer.", getattr(payload, "url", None))
                result = None
            else:
                logger.exception("Discovery %s job failed for %r — skipping it.", kind, payload)
                return

        if kind == "search":
            self.counts["searches"] += 1
            self.counts["search_results"] += len(result or [])
            self._accept_result_urls(result)
        elif kind in ("source", "page"):
            self.counts["pages_read"] += 1
            origin = payload[1] if kind == "source" else payload[0]
            if kind == "page":
                self.report.add_candidates(origin, len(result or []))
            self._accept_candidates(result, origin)
        elif kind == "organizer":
            self.counts["organizer_lookups"] += 1
            start = time.perf_counter()
            duplicates_before = self.summary.duplicate_events
            status = _finalize_candidate(self.db, self.run, payload, result, self.config, self.summary, self.categories, self.index)
            self.db_ms += (time.perf_counter() - start) * 1000
            origin = getattr(payload, "discovery_origin", None)
            if status == "VERIFIED":
                self.report.outcome(origin, "verified")
            elif status == "NEEDS_REVIEW":
                self.report.outcome(origin, "needs_review")
            elif status is None and self.summary.duplicate_events > duplicates_before:
                self.report.outcome(origin, "duplicates")
            else:
                self.report.outcome(origin, "rejected")
            if status == "VERIFIED":
                self._milestone("first_verified_ms")
                if _target_reached(self.summary, self.config):
                    self._milestone("target_reached_ms")
            self._flush(force=status is not None)

    # ------------------------------------------------------------ stop logic
    def _check_stop(self) -> None:
        now = time.perf_counter()
        if now - self._last_cancel_check >= self._CANCEL_CHECK_SECONDS:
            self._last_cancel_check = now
            if is_run_cancelled(self.run.id, self.db):
                self.stop_reason = "cancelled"
        elif self.run.id in _CANCELLED_RUN_IDS:
            self.stop_reason = "cancelled"
        if self.stop_reason is None:
            if _target_reached(self.summary, self.config):
                self.stop_reason = "target_reached"
            elif _limit_reached(self.already_today, self.summary, self.config):
                self.stop_reason = "candidate_ceiling"
            elif now >= self.deadline:
                self.stop_reason = "time_budget"
        if self.stop_reason:
            raise _Stopped()

    def _has_more_work(self) -> bool:
        searchable = bool(self.queries) and self.search_error is None
        return bool(self.pending or self.source_jobs or self.result_pages or searchable or self.organizer_jobs)

    def _flush(self, force: bool = False) -> None:
        now = time.perf_counter()
        if not force and now - self._last_flush < self._SUMMARY_FLUSH_SECONDS:
            return
        self._last_flush = now
        self.summary.timings = self.timings()
        self.report.merge_search_stats(self.search_stats.snapshot())
        self.summary.sources = self.report.summary()  # live progress for the UI
        self.run.summary = _build_summary_dict(self.summary)
        self.db.add(self.run)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()

    def timings(self) -> dict:
        cache_now = web_fetch.cache_stats()
        with self._stats_lock:
            stage = {f"{k}_ms": round(v) for k, v in self.stage_ms.items()}
        return {
            "elapsed_ms": round((time.perf_counter() - self.t0) * 1000),
            **self.milestones,
            "cumulative_worker_ms": stage,
            "db_thread_ms": round(self.db_ms),
            **self.counts,
            "page_cache_hits": cache_now["hits"] - self.cache_before["hits"],
            "permanent_failures_skipped": cache_now["permanent_failure_skips"] - self.cache_before["permanent_failure_skips"],
            "parallelism": {
                "searches": self.config.max_parallel_searches,
                "page_reads": self.config.max_parallel_fetches,
                "organizer_lookups": self.config.max_parallel_organizer_lookups,
            },
        }

    # ------------------------------------------------------------- main loop
    def execute(self) -> None:
        self.plan()
        try:
            while True:
                self._check_stop()
                self._fill()
                if not self.pending:
                    if self.query_waves and not self.queries and not self.organizer_jobs and self.search_error is None:
                        self.queries.extend(self.query_waves.pop(0))
                        continue
                    if not self._has_more_work():
                        self.stop_reason = "sources_exhausted"
                        break
                    continue
                done, _ = wait(list(self.pending), timeout=0.5, return_when=FIRST_COMPLETED)
                for future in done:
                    self._check_stop()  # never store past the target within one batch
                    kind, payload = self.pending.pop(future)
                    self._handle(future, kind, payload)
                self._flush()
        except _Stopped:
            pass
        finally:
            # Stop launching work; in-flight network calls finish in the
            # background and their results are discarded (no DB access there).
            for pool in (self.search_pool, self.page_pool, self.org_pool):
                pool.shutdown(wait=False, cancel_futures=True)

    def finish_summary(self) -> None:
        target = getattr(self.config, "target_valid_events", None)
        self.summary.stop_reason = self.stop_reason
        self.summary.scope = self.scope()
        self.summary.target_shortfall = max(0, target - self.summary.verified_events) if target else None
        self.summary.timings = self.timings()
        self.summary.timings["paid_search_calls"] = self.search_stats.paid_calls
        self.summary.timings["paid_search_budget"] = self.search_stats.paid_budget
        self._finish_report()

    def _finish_report(self) -> None:
        snapshot = self.search_stats.snapshot()
        for pid, row in snapshot.items():
            # With the web channel off, providers still ran for organizer lookups.
            if row["calls"] and pid not in self.report.records:
                provider = search_engine.providers.get(pid)
                self.report.add(pid, (provider.display_name or provider.provider_name) if provider else pid, "web", "search_provider")
        self.report.merge_search_stats(snapshot)
        self.report.close(self.stop_reason)
        self.summary.sources = self.report.summary()
        self.summary.search_log = list(self.search_stats.log)

    def persist_source_health(self) -> None:
        """Store each adapter/aggregator's real outcome in the registry table,
        so the settings page shows health from actual runs, not labels."""
        known = {src["id"] for src in catalog.ALL_CANDIDATE_SOURCES}
        executed = [r for r in self.report.records.values() if r.id in known and r.jobs]
        if not executed:
            return
        try:
            from backend.services.discovery_agent.source_registry import seed_or_sync_source_registry

            seed_or_sync_source_registry(self.db)  # rows must exist to hold the outcome
        except Exception:
            self.db.rollback()
            logger.warning("Could not sync the source registry before recording source health", exc_info=True)
            return
        for record in executed:
            try:
                catalog.record_outcome(self.db, record.id, ok=bool(record.jobs_ok), events=record.candidates,
                                       error="; ".join(record.errors) if not record.jobs_ok else None)
            except Exception:
                self.db.rollback()
                logger.warning("Could not record source health for %s", record.id, exc_info=True)


def run_discovery_agent(
    db: Session,
    config: DiscoveryConfig | None = None,
    run: AgentRun | None = None,
) -> RunSummary:
    config = config or config_from_settings(get_settings(), db=db)
    supported_categories = categorizer.get_supported_categories(db)
    # Categorize against EVERY known sector (incl. Technology, which the site's
    # category table may not list), so an off-sector event is recognised as such
    # and rejected by the sector gate, instead of landing in the nearest selected
    # sector ("Clean Architecture Masterclass" -> Construction).
    known_sectors = [c for c in categorizer.CATEGORIES if c != "Other"]
    effective_categories = list(dict.fromkeys(supported_categories + known_sectors + (config.categories or [])))
    config.sector_scoped = bool(config.categories) and not set(supported_categories) <= set(config.categories)
    if not config.categories:
        config.categories = supported_categories

    if run is None:
        run = AgentRun(
            agent_type="discovery",
            status="running",
            started_at=datetime.now(timezone.utc),
            config_snapshot=redacted_config(config),
            summary=RunSummary().as_dict(),
            created_at=datetime.now(timezone.utc),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
    else:
        run = db.get(AgentRun, run.id) or run
        run.status = "running"
        run.config_snapshot = redacted_config(config)
        db.add(run)
        db.commit()
        db.refresh(run)

    summary = RunSummary()
    pipeline: _DiscoveryPipeline | None = None
    try:
        pipeline = _DiscoveryPipeline(db, run, config, summary, effective_categories, _todays_new_event_count(db))
        pipeline.execute()
        pipeline.finish_summary()
        pipeline.persist_source_health()

        run.status = "stopped" if pipeline.stop_reason == "cancelled" else "completed"
        notes = []
        if pipeline.search_error:
            notes.append(f"Web search stopped early: {pipeline.search_error}")
        if summary.target_shortfall:
            why = {
                "time_budget": f"the {config.max_run_seconds}s time budget was used up",
                "sources_exhausted": "every configured source and query was exhausted",
                "candidate_ceiling": "the run's candidate or daily limit was reached",
                "cancelled": "the run was stopped",
            }.get(pipeline.stop_reason or "", pipeline.stop_reason or "")
            notes.append(
                f"Found {summary.verified_events} of {config.target_valid_events} requested verified events — {why}."
            )
        run.error = " ".join(notes) or None
        run.completed_at = datetime.now(timezone.utc)
        run.summary = _build_summary_dict(summary)
        db.add(run)
        db.commit()
        _CANCELLED_RUN_IDS.discard(run.id)

        # Real execution metric: measured wall time and the search cost the
        # providers reported (Exa returns its billed amount). Discovery itself
        # uses no AI model; Google-via-Gemini grounded searches are counted.
        try:
            provider_rows = (summary.sources or {}).get("sources", [])
            reported_cost = sum(r.get("cost_usd") or 0 for r in provider_rows if r.get("kind") == "search_provider")
            gemini_calls = sum(r.get("calls") or 0 for r in provider_rows if r.get("id") == "google_gemini")
            db.add(
                AgentExecutionMetric(
                    workflow_id=f"wf-disc-{run.id:04d}",
                    agent_name="DiscoveryAgent",
                    status="SUCCESS" if run.status in ("completed", "stopped") else "FAILED",
                    duration_ms=summary.timings.get("elapsed_ms", 0),
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    estimated_cost=Decimal(str(round(reported_cost, 4))),
                    model_name=f"none (rule-based); {gemini_calls} Gemini-grounded searches" if gemini_calls else "none (rule-based)",
                    error_message=run.error,
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
        except Exception as m_exc:
            db.rollback()
            logger.warning("Could not persist agent execution metric: %s", m_exc)

    except Exception as exc:
        db.rollback()
        if pipeline is not None:
            pipeline.finish_summary()
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error = str(exc)
        run.summary = _build_summary_dict(summary)
        db.add(run)
        db.commit()
        _CANCELLED_RUN_IDS.discard(run.id)
        logger.exception("Discovery Agent run #%s failed", run.id)

    return summary
