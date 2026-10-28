"""Shared pytest fixtures: an isolated in-memory SQLite DB per test, seeded
with a minimal event catalog, plus a fake AI client so no test ever makes a
real network call to any AI provider."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models  # noqa: F401 - registers all model metadata
from backend.db import Base
from backend.models import Category, City, Community, Event, Organizer, Venue


@pytest.fixture(autouse=True)
def no_real_database(monkeypatch):
    """backend.db.SessionLocal is the app's REAL database (MySQL in dev). Any
    code a test reaches that opens it — the app's own get_db for requests
    without a db override, the background discovery worker, the scheduler —
    gets a throwaway in-memory database instead, so a test can never read or
    write real data. (A stray background run once wrote test events to MySQL.)"""
    import backend.db
    from backend.services.social_agent import scheduler

    state: dict = {}

    def throwaway_session(*args, **kwargs):
        if "factory" not in state:
            engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
            Base.metadata.create_all(engine)
            state["engine"], state["factory"] = engine, sessionmaker(bind=engine)
        return state["factory"](*args, **kwargs)

    monkeypatch.setattr(backend.db, "SessionLocal", throwaway_session)
    # Modules that imported the name keep their own reference.
    monkeypatch.setattr(scheduler, "SessionLocal", throwaway_session)
    yield
    if "engine" in state:
        state["engine"].dispose()


@pytest.fixture(autouse=True)
def no_live_listing_pages(monkeypatch):
    """The Discovery Agent reads real listing sites by default; tests that
    want listing pages pass them explicitly with fake pages instead."""
    from backend.core.config import get_settings

    monkeypatch.setattr(get_settings(), "discovery_listing_urls", "")


@pytest.fixture(autouse=True)
def no_live_source_adapters(monkeypatch):
    """A discovery run also reads the operational source adapters (dev.events,
    venue calendars, …) over the live web; unit tests run without them unless
    they opt in by patching `_select_adapter_ids` themselves."""
    from backend.services.discovery_agent import orchestrator

    # Tests of the selection rules themselves use the real function via this name.
    monkeypatch.setattr(orchestrator, "real_select_adapter_ids", orchestrator._select_adapter_ids, raising=False)
    monkeypatch.setattr(orchestrator, "_select_adapter_ids", lambda requested, countries=None: [])


@pytest.fixture(autouse=True)
def fresh_page_cache():
    """web_fetch caches pages process-wide; tests stub `_http_get` with
    different HTML for the same URLs, so each test starts with it empty."""
    from backend.services.social_agent import web_fetch

    web_fetch.clear_cache()
    yield
    web_fetch.clear_cache()


@pytest.fixture(autouse=True)
def no_live_web_search(monkeypatch):
    """Discovery web-searches through `search_providers` (keyless DuckDuckGo
    fallback when no API key is set); tests get no results unless they
    patch `web_search` themselves, and never share cached search results."""
    from backend.services.discovery_agent.search_providers import search_engine
    from backend.services.discovery_agent.search_providers.web_fallback import WebFallbackProvider

    # Every provider is stubbed — .env may hold real keys (Exa bills per call)
    # and a real SEARXNG_URL; no test may reach any of them.
    for provider in search_engine._providers.values():
        monkeypatch.setattr(type(provider), "search", lambda self, *args, **kwargs: [])
    monkeypatch.setattr(WebFallbackProvider, "_wait_turn", lambda self: None)
    with search_engine._cache_lock:
        search_engine._cache.clear()
    search_engine.reset_breakers()


@pytest.fixture(autouse=True)
def no_live_ai_calls(monkeypatch, request):
    """Ensure no test outside test_ai_client makes live network calls to AI vendors."""
    if "test_ai_client" in request.node.nodeid:
        return
    fake = FakeAIClient(configured=False)
    from backend.services.social_agent import ai_client
    monkeypatch.setattr(ai_client, "get_ai_client", lambda: fake)
    try:
        import backend.services.trust_agent.agent as ta
        monkeypatch.setattr(ta, "get_ai_client", lambda: fake)
    except (ImportError, AttributeError):
        pass




@pytest.fixture()
def db_session():
    # StaticPool shares one connection across all threads/checkouts — required
    # because FastAPI's TestClient runs sync route handlers in a worker thread
    # pool, and plain in-memory SQLite gives each new thread a fresh, empty
    # database otherwise (schema created on the main thread would vanish).
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def seeded_catalog(db_session):
    """One category/city/venue/organizer and one published, future event —
    enough for the event-matching stage to have something real to score."""
    category = Category(name="Pharmaceuticals", slug="pharmaceuticals", description="Pharma", icon="pill")
    city = City(name="Pune", slug="pune", country="India")
    organizer = Organizer(name="Orbit Collective", slug="orbit-collective", description="desc")
    db_session.add_all([category, city, organizer])
    db_session.flush()

    venue = Venue(name="Pune Convention Centre", slug="pune-cc", address="MG Road", city_id=city.id, country="India")
    db_session.add(venue)
    db_session.flush()

    event = Event(
        title="Global Pharma Innovations Summit",
        slug="global-pharma-innovations-summit",
        description="A hands-on pharma conference.",
        event_type="Hackathon",
        start_date=date.today() + timedelta(days=14),
        end_date=date.today() + timedelta(days=15),
        start_time="09:00 AM",
        price=Decimal("0.00"),
        status="published",
        format="in-person",
        category_id=category.id,
        organizer_id=organizer.id,
        venue_id=venue.id,
    )
    db_session.add(event)
    db_session.flush()

    community = Community(
        platform="reddit",
        name="r/pune",
        slug="r-pune",
        url="https://reddit.com/r/pune",
        rules_text="Be helpful.",
        promotion_allowed=False,
        external_links_allowed=True,
        automation_allowed=False,
        risk_level="low",
        quality_score=90,
    )
    db_session.add(community)
    db_session.flush()

    return {"category": category, "city": city, "event": event, "community": community}


class FakeAIClient:
    """Drop-in replacement for AIClient — configurable per test, never
    touches the network."""

    def __init__(
        self,
        structured_response=None,
        raise_error: Exception | None = None,
        configured: bool = True,
        web_search_response=None,
    ):
        self._response = structured_response
        self._raise_error = raise_error
        self.is_configured = configured
        self._web_search_response = web_search_response

    def generate_structured(self, **kwargs):
        if self._raise_error:
            raise self._raise_error
        if callable(self._response):
            return self._response(kwargs)
        return self._response

    def generate_with_web_search(self, **kwargs):
        if self._raise_error:
            raise self._raise_error
        if callable(self._web_search_response):
            return self._web_search_response(kwargs)
        return self._web_search_response or {"text": "", "citations": []}


class DeliveringEmailProvider:
    """A provider that really "delivers" (into `sent`) — for tests of the
    delivered path. The built-in MockEmailProvider reports "not sent"
    because without SMTP nothing reaches an inbox."""

    is_real = True

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send_message(self, recipient, subject, body, html=None):
        from backend.services.social_agent.outreach.types import SendResult

        self.sent.append((recipient, subject, body))
        return SendResult(success=True, message_id=f"test-{len(self.sent)}", message="delivered by test provider")

    send = send_message


@pytest.fixture()
def delivering_email_provider(monkeypatch):
    from backend.services.social_agent.outreach import orchestrator

    provider = DeliveringEmailProvider()
    monkeypatch.setattr(orchestrator, "get_email_provider", lambda: provider)
    return provider


class _NoRealSMTP:
    """Stands in for smtplib.SMTP / SMTP_SSL: tests must never reach a real
    mail server (a working SMTP account in a .env made suite runs send mail)."""

    def __init__(self, *args, **kwargs):
        raise ConnectionRefusedError("Real SMTP is disabled in tests; patch smtplib or use a fake provider")


@pytest.fixture(autouse=True)
def no_real_email(tmp_path, monkeypatch):
    """Every test: no real e-mail is sent and no real .env file is rewritten.
    SMTP settings saved by a test go to a temp file; SMTP_* environment
    variables are restored afterwards. A test that needs a delivering
    provider or a fake smtplib patches it itself (its patch wins)."""
    import os
    import smtplib

    from backend.services import smtp_config

    monkeypatch.setattr(smtp_config, "_get_env_paths", lambda: [tmp_path / ".env.test"])
    from backend.core.config import get_settings

    settings = get_settings()
    for field in ("smtp_host", "smtp_username", "smtp_password", "smtp_from_email"):
        monkeypatch.setattr(settings, field, None)  # no SMTP unless a test configures it
    monkeypatch.setattr(smtplib, "SMTP", _NoRealSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _NoRealSMTP)
    for key in ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL", "SMTP_USE_TLS"):
        if key in os.environ:
            monkeypatch.setenv(key, os.environ[key])  # restored after the test
        else:
            monkeypatch.delenv(key, raising=False)
    yield
