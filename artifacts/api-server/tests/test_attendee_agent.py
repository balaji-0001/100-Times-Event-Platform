"""Attendee Agent: catalog eligibility, matching, query parsing, assistant,
tracking, notifications and role-based access — end to end over an
in-memory DB (same standalone-app pattern as the other route tests)."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import get_db
from backend.dependencies import get_current_user
from backend.models import (
    AttendeeEventActivity,
    AttendeeNotificationLog,
    AttendeePreference,
    Category,
    DiscoveredEvent,
    DiscoveredOrganizer,
    Event,
    EventReminder,
    EventSource,
    Notification,
    Organizer,
    Registration,
    User,
)
from backend.routes import attendee as attendee_routes
from backend.services.attendee_agent import assistant, catalog, notifier
from backend.services.attendee_agent.matching import Preferences, score_event
from backend.services.attendee_agent.query_parser import parse_rules
from backend.services.discovery_agent.categorizer import CATEGORIES, categorize

TODAY = date.today()


def _offers(price=None, currency="USD", valid_through=None, status=None, end=None, keywords=None):
    fields = {"@type": "Event", "name": "x"}
    offer = {}
    if price is not None:
        offer["price"] = price
        offer["priceCurrency"] = currency
    if valid_through:
        offer["validThrough"] = valid_through
    if offer:
        fields["offers"] = offer
    if status:
        fields["eventStatus"] = f"https://schema.org/{status}"
    if end:
        fields["endDate"] = end
    if keywords:
        fields["keywords"] = keywords
    return fields


def _discovered(db, name, *, days=10, country="India", city="Bengaluru", category="Technology", subcategory="Conference",
                fmt="offline", verification="VERIFIED", evidence=None, description="", first_seen=None):
    org = DiscoveredOrganizer(name=f"{name} Org", email="hello@org.test", website="https://org.test", source_url="https://org.test")
    db.add(org)
    db.flush()
    ev = DiscoveredEvent(
        name=name,
        event_description=description,
        category=category,
        subcategory=subcategory,
        event_date=TODAY + timedelta(days=days),
        city=city,
        country=country,
        event_format=fmt,
        url=f"https://events.test/{name.replace(' ', '-').lower()}",
        source_url="https://www.eventbrite.com/e/x",
        organizer_id=org.id,
        verification_status=verification,
        discovery_status="NEW",
        discovered_by="web_discovery_agent",
        confidence_score=80,
        discovered_at=first_seen or datetime.now(timezone.utc) - timedelta(days=30),
    )
    db.add(ev)
    db.flush()
    if evidence is not None:
        db.add(EventSource(discovered_event_id=ev.id, source_url=ev.url, source_type="event_listing", extracted_fields=evidence))
        db.flush()
    db.refresh(ev)
    return ev


def _platform_event(db, title, *, trust="APPROVED", days=20, price="0.00"):
    cat = db.query(Category).filter_by(slug="technology").first()
    if cat is None:
        cat = Category(name="Technology", slug="technology", description="Tech", icon="cpu")
        db.add(cat)
        db.flush()
    org = Organizer(name=f"{title} Org", slug=f"{title.lower().replace(' ', '-')}-org", description="d", website="https://p.test")
    db.add(org)
    db.flush()
    ev = Event(
        title=title, slug=title.lower().replace(" ", "-"), description="An AI conference for builders.", event_type="Conference",
        start_date=TODAY + timedelta(days=days), end_date=TODAY + timedelta(days=days), start_time="09:00 AM",
        price=Decimal(price), is_free=Decimal(price) == 0, status="published", format="in-person", city_name="Pune",
        country_name="India", category_id=cat.id, organizer_id=org.id, trust_status=trust,
    )
    db.add(ev)
    db.flush()
    return ev


def _user(db, role="USER", email="attendee@x.test"):
    u = User(name="Asha", email=email, password_hash="x", role=role)
    db.add(u)
    db.flush()
    return u


@pytest.fixture()
def world(db_session):
    db = db_session
    data = {
        "ai_india": _discovered(db, "Bengaluru AI Summit", description="Generative AI and machine learning for founders",
                                subcategory="Conference", evidence=_offers(price=0, currency="INR", valid_through=(TODAY + timedelta(days=2)).isoformat())),
        "fintech_us": _discovered(db, "NYC Fintech Forum", country="United States", city="New York", category="Finance",
                                  subcategory="Conference", evidence=_offers(price=250, currency="USD")),
        "health_us": _discovered(db, "Healthcare Expo USA", country="United States", city="Chicago", category="Healthcare",
                                 subcategory="Exhibition", evidence=_offers()),
        "online_ws": _discovered(db, "Cloud Workshop Online", country="Worldwide", city=None, fmt="online", subcategory="Workshop",
                                 description="Hands-on cloud and kubernetes workshop", evidence=_offers(price=0)),
        "unverified": _discovered(db, "Unverified AI Meetup", verification="NEEDS_REVIEW"),
        "past": _discovered(db, "Past AI Conference", days=-3),
        "cancelled": _discovered(db, "Cancelled AI Conference", evidence=_offers(status="EventCancelled")),
        "dubai": _discovered(db, "Dubai AI Week", country="Dubai", city="Dubai", description="AI week"),
        "approved_platform": _platform_event(db, "Pune AI Builders Conference"),
        "unapproved_platform": _platform_event(db, "Unreviewed Platform Event", trust=None),
    }
    # Same title + date as the platform event -> collapses to the platform listing.
    data["dup"] = _discovered(db, "Pune AI Builders Conference", days=20, city="Pune")
    db.commit()
    return data


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def test_catalog_only_contains_eligible_deduplicated_events(db_session, world):
    items = catalog.load_catalog(db_session)
    titles = {i.title for i in items}
    assert {"Bengaluru AI Summit", "NYC Fintech Forum", "Healthcare Expo USA", "Cloud Workshop Online", "Dubai AI Week",
            "Pune AI Builders Conference"} <= titles
    for excluded in ("Unverified AI Meetup", "Past AI Conference", "Cancelled AI Conference", "Unreviewed Platform Event"):
        assert excluded not in titles
    pune = [i for i in items if i.title == "Pune AI Builders Conference"]
    assert len(pune) == 1 and pune[0].kind == catalog.PLATFORM


def test_catalog_reads_price_deadline_and_country_from_evidence(db_session, world):
    by_title = {i.title: i for i in catalog.load_catalog(db_session)}
    ai = by_title["Bengaluru AI Summit"]
    assert ai.is_free is True and ai.currency == "INR"
    assert ai.registration_deadline == TODAY + timedelta(days=2)
    fin = by_title["NYC Fintech Forum"]
    assert fin.price_min == Decimal("250") and fin.currency == "USD" and fin.is_free is False
    assert by_title["Healthcare Expo USA"].is_free is None  # source published no price -> unknown, not guessed
    assert by_title["Dubai AI Week"].country == "United Arab Emirates"
    assert by_title["Cloud Workshop Online"].country is None


def test_ineligible_event_still_viewable_with_reason(db_session, world):
    item = catalog.get_event(db_session, catalog.DISCOVERED, world["cancelled"].id)
    assert item.eligible is False and "Cancelled" in item.ineligible_reason


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def test_no_preferences_means_no_score(db_session, world):
    item = catalog.get_event(db_session, catalog.DISCOVERED, world["ai_india"].id)
    assert score_event(item, Preferences()) is None


def test_full_match_and_unknown_data_is_not_checked(db_session, world):
    prefs = Preferences(interests=["ai"], industries=["Technology"], countries=["India"], event_types=["conference"],
                        attendance_mode="offline", free_only=True)
    ai = catalog.get_event(db_session, catalog.DISCOVERED, world["ai_india"].id)
    result = score_event(ai, prefs)
    assert result.percent == 100 and result.possible == 95  # no date window set -> dates not scored

    health = catalog.get_event(db_session, catalog.DISCOVERED, world["health_us"].id)
    h = score_event(health, prefs)
    budget = next(c for c in h.criteria if c.key == "budget")
    assert budget.status == "not_checked"
    assert h.possible == 90  # budget weight left out of the denominator
    assert h.percent < 50


def test_online_event_satisfies_country_preference(db_session, world):
    item = catalog.get_event(db_session, catalog.DISCOVERED, world["online_ws"].id)
    result = score_event(item, Preferences(countries=["India"]))
    assert result.percent == 100 and "Online" in result.reasons[0]


def test_partial_interest_overlap_is_proportional(db_session, world):
    item = catalog.get_event(db_session, catalog.DISCOVERED, world["ai_india"].id)
    result = score_event(item, Preferences(interests=["ai", "blockchain", "design"]))
    assert result.percent == 33


# ---------------------------------------------------------------------------
# Query parsing (the five example questions)
# ---------------------------------------------------------------------------


def test_parse_example_questions():
    today = date(2026, 10, 26)  # a Monday
    q = parse_rules("Find 10 AI conferences in India", today)
    assert (q.count, q.topics, q.event_types, q.countries) == (10, ["ai"], ["conference"], ["India"])

    q = parse_rules("Show free technology events worldwide next month", today)
    assert q.free_only and q.worldwide and q.sectors == ["Technology"] and q.countries == []
    assert (q.date_from, q.date_to) == (date(2026, 11, 1), date(2026, 11, 30))

    q = parse_rules("Find healthcare exhibitions in the USA", today)
    assert q.sectors == ["Healthcare"] and q.event_types == ["exhibition"] and q.countries == ["United States"]

    q = parse_rules("Recommend events matching my profile", today)
    assert q.use_profile and not q.count_requested

    q = parse_rules("Find online workshops this weekend", today)
    assert q.mode == "online" and q.event_types == ["workshop"]
    assert (q.date_from, q.date_to) == (date(2026, 10, 31), date(2026, 11, 1))


def test_price_and_year_are_not_read_as_count():
    q = parse_rules("conferences under $500 in 2027", date(2026, 10, 26))
    assert not q.count_requested and q.max_price == Decimal("500") and q.currency == "USD"


def test_trade_show_is_not_read_as_finance():
    q = parse_rules("trade shows in Germany", date(2026, 10, 26))
    assert q.event_types == ["exhibition"] and q.sectors == []


# ---------------------------------------------------------------------------
# Assistant
# ---------------------------------------------------------------------------


def test_assistant_respects_filters_and_count(db_session, world):
    user = _user(db_session)
    res = assistant.answer(db_session, user, "Find 10 AI conferences in India")
    titles = [r["title"] for r in res["results"]]
    assert set(titles) == {"Bengaluru AI Summit", "Pune AI Builders Conference"}
    assert res["requestedCount"] == 10 and res["totalMatching"] == 2
    assert "only 2" in res["reply"]

    one = assistant.answer(db_session, user, "Find 1 AI conference in India")
    assert len(one["results"]) == 1


def test_assistant_explains_empty_result(db_session, world):
    user = _user(db_session)
    res = assistant.answer(db_session, user, "Find healthcare exhibitions in Japan")
    assert res["results"] == []
    assert "Dropping" in res["reply"]


def test_assistant_logs_question_as_intent(db_session, world):
    from backend.models import AttendeeIntent

    user = _user(db_session)
    assistant.answer(db_session, user, "Show free technology events worldwide next month")
    row = db_session.query(AttendeeIntent).filter_by(source_platform="assistant").one()
    assert row.raw_text.startswith("Show free") and row.price_preference == "free"


# ---------------------------------------------------------------------------
# HTTP routes + role-based access
# ---------------------------------------------------------------------------


@pytest.fixture()
def api(db_session):
    holder = {"user": None}
    app = FastAPI()
    app.include_router(attendee_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session

    def current():
        if holder["user"] is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="Authentication required")
        return holder["user"]

    app.dependency_overrides[get_current_user] = current
    return TestClient(app), holder


def test_routes_require_login_and_admin(api, db_session, world):
    client, holder = api
    assert client.get("/api/attendee/dashboard").status_code == 401
    holder["user"] = _user(db_session)
    assert client.get("/api/attendee/dashboard").status_code == 200
    assert client.get("/api/attendee/admin/overview").status_code == 403
    assert client.post("/api/attendee/admin/notifications/run").status_code == 403
    holder["user"] = _user(db_session, role="ADMIN", email="admin@x.test")
    overview = client.get("/api/attendee/admin/overview").json()
    assert overview["catalog"]["total"] == 6


def test_preferences_validation_and_match(api, db_session, world):
    client, holder = api
    holder["user"] = _user(db_session)
    assert client.post("/api/attendee/match").json()["hasPreferences"] is False
    bad = client.put("/api/attendee/preferences", json={"countries": ["Atlantis"]})
    assert bad.status_code == 422
    ok = client.put("/api/attendee/preferences", json={
        "interests": ["AI"], "industries": ["technology"], "countries": ["india"], "eventTypes": ["conference"],
    })
    assert ok.status_code == 200 and ok.json()["industries"] == ["Technology"] and ok.json()["countries"] == ["India"]
    res = client.post("/api/attendee/match", json={"limit": 3}).json()
    assert res["hasPreferences"] and res["results"][0]["match"]["percent"] == 100
    assert all(r["match"]["reasons"] for r in res["results"][:2])


def test_save_view_and_external_registration_flow(api, db_session, world):
    client, holder = api
    holder["user"] = user = _user(db_session)
    ev = world["ai_india"]
    base = f"/api/attendee/events/discovered/{ev.id}"

    detail = client.get(base).json()
    assert detail["organizer"]["name"] == "Bengaluru AI Summit Org" and detail["officialUrl"].startswith("https://")
    assert client.post(f"{base}/save").json()["saved"] is True

    opened = client.post(f"{base}/registration-opened").json()
    assert opened["state"]["registrationStatus"] == "REGISTRATION_PAGE_OPENED"  # opening is NOT registering

    assert client.post(f"{base}/registration", json={"status": "REGISTERED"}).status_code == 400  # no confirmation
    confirmed = client.post(f"{base}/registration", json={"status": "REGISTERED", "confirm": True}).json()
    assert confirmed["registrationStatus"] == "REGISTERED" and confirmed["registrationSource"] == "self_reported"

    dash = client.get("/api/attendee/dashboard").json()
    assert [e["title"] for e in dash["saved"]] == ["Bengaluru AI Summit"]
    assert [e["title"] for e in dash["registered"]] == ["Bengaluru AI Summit"]
    assert dash["recentlyViewed"][0]["title"] == "Bengaluru AI Summit"

    platform = world["approved_platform"]
    resp = client.post(f"/api/attendee/events/platform/{platform.id}/registration", json={"status": "REGISTERED", "confirm": True})
    assert resp.status_code == 400  # platform events register through the real registration API only

    # Platform favourites go to the shared saved_events table.
    client.post(f"/api/attendee/events/platform/{platform.id}/save")
    from backend.models import SavedEvent

    assert db_session.query(SavedEvent).filter_by(user_id=user.id, event_id=platform.id).count() == 1


def test_cannot_touch_another_users_notification(api, db_session, world):
    client, holder = api
    other = _user(db_session, email="other@x.test")
    note = Notification(user_id=other.id, title="t", message="m")
    db_session.add(note)
    db_session.commit()
    holder["user"] = _user(db_session)
    assert client.post(f"/api/attendee/notifications/{note.id}/read").status_code == 404


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


def _prefs(db, user, **kw):
    row = AttendeePreference(user_id=user.id, interests=["ai"], industries=["Technology"], countries=[], event_types=[], **kw)
    db.add(row)
    db.flush()
    return row


def test_no_consent_means_no_notifications(db_session, world):
    user = _user(db_session)
    _prefs(db_session, user, notify_consent=False)
    db_session.add(AttendeeEventActivity(user_id=user.id, discovered_event_id=world["ai_india"].id, is_saved=True))
    db_session.commit()
    summary = notifier.run_attendee_notifications(db_session)
    assert summary["usersConsidered"] == 0
    assert db_session.query(Notification).count() == 0


@pytest.fixture()
def smtp_off(monkeypatch):
    from backend.services.social_agent.outreach import senders

    monkeypatch.setattr(senders, "provider_status", lambda: {"provider": "mock", "status": "NOT_CONFIGURED"})


@pytest.fixture()
def smtp_fake(monkeypatch):
    from types import SimpleNamespace

    from backend.services.social_agent.outreach import senders

    sent = []

    class FakeProvider:
        def send(self, recipient, subject, body):
            sent.append((recipient, subject))
            return SimpleNamespace(ok=True)

    monkeypatch.setattr(senders, "provider_status", lambda: {"provider": "smtp", "status": "REAL"})
    monkeypatch.setattr(senders, "get_email_provider", lambda: FakeProvider())
    return sent


def test_email_only_when_opted_in_and_smtp_real(db_session, world, smtp_fake):
    opted_in = _user(db_session)
    _prefs(db_session, opted_in, notify_consent=True, notify_by_email=True)
    in_app_only = _user(db_session, email="inapp@x.test")
    _prefs(db_session, in_app_only, notify_consent=True, notify_by_email=False)
    for u in (opted_in, in_app_only):
        db_session.add(AttendeeEventActivity(user_id=u.id, discovered_event_id=world["ai_india"].id, is_saved=True))
    db_session.commit()
    notifier.run_attendee_notifications(db_session)
    assert [r for r, _ in smtp_fake] == ["attendee@x.test"]
    statuses = {r.user_id: r.email_status for r in db_session.query(AttendeeNotificationLog).all()}
    assert statuses == {opted_in.id: "sent", in_app_only.id: "not_requested"}


def test_reminder_deadline_change_and_idempotency(db_session, world, smtp_off):
    user = _user(db_session)
    _prefs(db_session, user, notify_consent=True, notify_by_email=True)
    ev = world["ai_india"]  # starts in 10 days, deadline in 2 days
    soon = _discovered(db_session, "Tomorrow AI Day", days=1)
    item_soon = catalog.get_event(db_session, catalog.DISCOVERED, soon.id)
    item_ev = catalog.get_event(db_session, catalog.DISCOVERED, ev.id)
    db_session.add_all([
        AttendeeEventActivity(user_id=user.id, discovered_event_id=ev.id, is_saved=True, change_fingerprint=catalog.fingerprint(item_ev)),
        AttendeeEventActivity(user_id=user.id, discovered_event_id=soon.id, external_registration_status="REGISTERED",
                              change_fingerprint=catalog.fingerprint(item_soon)),
    ])
    db_session.commit()

    first = notifier.run_attendee_notifications(db_session)
    assert first["reminder"] == 1 and first["deadline"] == 1 and first["change"] == 0
    log = db_session.query(AttendeeNotificationLog).all()
    assert {r.kind for r in log} == {"reminder", "deadline"}
    assert all(r.email_status == "not_configured" for r in log)  # no SMTP -> never a pretend send

    again = notifier.run_attendee_notifications(db_session)
    assert again["reminder"] == 0 and again["deadline"] == 0

    ev.event_date = TODAY + timedelta(days=12)  # organizer moved the date
    db_session.commit()
    changed = notifier.run_attendee_notifications(db_session)
    assert changed["change"] == 1
    note = db_session.query(Notification).filter(Notification.template_key == "attendee_change").one()
    assert "start date" in note.message


def test_new_matches_first_run_sets_baseline_then_notifies(db_session, world):
    user = _user(db_session)
    _prefs(db_session, user, notify_consent=True)
    db_session.commit()
    t0 = datetime.now(timezone.utc)
    assert notifier.run_attendee_notifications(db_session, now=t0)["new_matches"] == 0  # baseline only

    _discovered(db_session, "Brand New AI Conference", description="ai", first_seen=t0 + timedelta(minutes=5))
    db_session.commit()
    res = notifier.run_attendee_notifications(db_session, now=t0 + timedelta(hours=1))
    assert res["new_matches"] == 1
    note = db_session.query(Notification).filter(Notification.template_key == "attendee_new_matches").one()
    assert "Brand New AI Conference" in note.message


def test_platform_reminders_respect_opt_out(db_session, world):
    from backend.services.registration_automation import dispatch_due_reminders

    user = _user(db_session)
    _prefs(db_session, user, notify_consent=False)
    ev = world["approved_platform"]
    reg = Registration(event_id=ev.id, user_id=user.id, ticket_type="Standard", status="confirmed")
    db_session.add(reg)
    db_session.flush()
    rem = EventReminder(event_id=ev.id, registration_id=reg.id, user_id=user.id, reminder_type="24_HOURS",
                        scheduled_for_utc=datetime.now(timezone.utc) - timedelta(minutes=1), idempotency_key="k1")
    db_session.add(rem)
    db_session.commit()
    assert dispatch_due_reminders(db_session) == {"sent": 0, "skipped": 1}
    assert rem.status == "SKIPPED"


# ---------------------------------------------------------------------------
# Categorizer regression (the "ev" keyword matched the word "event")
# ---------------------------------------------------------------------------


def test_event_word_no_longer_means_energy():
    assert categorize("The MI5 Archive: Official Secrets", "Join this online event", supported_categories=CATEGORIES)[0] == "Other"
    assert categorize("Design Week", "an evening networking event", supported_categories=CATEGORIES)[0] == "Other"
    assert categorize("EV Charging Expo", "", supported_categories=CATEGORIES)[0] == "Energy and Power Generation"
