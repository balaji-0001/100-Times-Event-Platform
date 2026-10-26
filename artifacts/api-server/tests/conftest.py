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
def no_live_listing_pages(monkeypatch):
    """The Discovery Agent reads real listing sites by default; tests that
    want listing pages pass them explicitly with fake pages instead."""
    from backend.core.config import get_settings

    monkeypatch.setattr(get_settings(), "discovery_listing_urls", "")


@pytest.fixture(autouse=True)
def no_live_web_search(monkeypatch):
    """Discovery web-searches DuckDuckGo; tests get an empty results page
    unless they patch `web_search` themselves."""
    from types import SimpleNamespace

    from backend.services.discovery_agent import web_search

    monkeypatch.setattr(web_search, "_post", lambda query, *args, **kwargs: SimpleNamespace(status_code=200, text="<html></html>"))
    monkeypatch.setattr(web_search, "_wait_turn", lambda: None)


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
