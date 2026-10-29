"""Regression tests for the audited security / data-integrity fixes:

1  organizer ownership only via Organizer.user_id (no user-id == organizer-id takeover)
2  n8n webhooks: off unless enabled, built-in secret refused, constant-time compare
3  public registration cannot hijack/modify an existing account; published events only
4  reschedule keeps the event's own status
5  login rate limiter ignores forged X-Forwarded-For, bounded memory
6  attendee event detail hides drafts / rejected discovered events from non-admins
7  dashboards / event detail return only real numbers
8  honest payment/calendar flags, no follow-up to a stand-in organizer, webhook 422s
9  onboarding does not self-verify; discoveredOrganizerId validated
10 login does not reveal account existence; email links use PUBLIC_APP_URL
11 SMTP settings cannot inject .env lines; write failures are errors
12 attendee directory scoped to shared events, no role/email

Every test runs on the in-memory SQLite `db_session` (never the real DB).
"""

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from starlette.requests import Request


from backend.core.config import get_settings
from backend.core.rate_limiter import SlidingWindowRateLimiter, auth_rate_limiter, client_ip_for, rate_limit_auth
from backend.core.security import create_access_token, hash_password
from backend.db import get_db
from backend.dependencies import get_current_user
from backend.models import (
    AttendeeEventActivity,
    DiscoveredEvent,
    DiscoveredOrganizer,
    Event,
    Notification,
    Organization,
    Organizer,
    OrganizerFollowup,
    OrganizerProfile,
    Registration,
    User,
)
from backend.routes import attendee as attendee_routes
from backend.routes import auth as auth_routes
from backend.routes import dashboard as dashboard_routes
from backend.routes import events as events_routes
from backend.routes import networking as networking_routes
from backend.routes import platform_ops as platform_ops_routes
from backend.routes import webhooks_n8n as webhooks_routes
from backend.services import registration_automation, smtp_config
from backend.services.registration_automation import (
    automate_registration,
    initiate_or_advance_organizer_followup,
    reschedule_event_workflow,
)

TODAY = date.today()


def _client(db_session, *routers) -> TestClient:
    app = FastAPI()
    for router in routers:
        app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


def _user(db, name, email, role="USER", **extra) -> User:
    user = User(name=name, email=email, role=role, password_hash=extra.pop("password_hash", "x"), **extra)
    db.add(user)
    db.flush()
    return user


def _event(db, title, organizer_id, *, status="published", lifecycle="PUBLISHED", price="0.00", category_id=None, **extra) -> Event:
    ev = Event(
        title=title,
        slug=title.lower().replace(" ", "-"),
        description="A real event description for tests.",
        event_type="Conference",
        start_date=TODAY + timedelta(days=20),
        end_date=TODAY + timedelta(days=20),
        start_time="10:00 AM",
        price=Decimal(price),
        is_free=Decimal(price) == 0,
        status=status,
        lifecycle_state=lifecycle,
        format="in-person",
        organizer_id=organizer_id,
        category_id=category_id,
        **extra,
    )
    db.add(ev)
    db.flush()
    return ev


@pytest.fixture(autouse=True)
def no_real_email(monkeypatch):
    """A real SMTP account is configured in an .env file config.py reads, and
    conftest does not stub email: force the mock provider so nothing in this
    file can send a real message."""
    from backend.services.social_agent.outreach import senders

    monkeypatch.setattr(senders, "_smtp_configured", lambda: False)
    monkeypatch.setattr(smtp_config, "_smtp_configured", lambda: False)
    assert type(senders.get_email_provider()).__name__ == "MockEmailProvider"


@pytest.fixture(autouse=True)
def fresh_auth_rate_limiter():
    auth_rate_limiter.reset()
    yield
    auth_rate_limiter.reset()


# ---------------------------------------------------------------------------
# 1. Organizer ownership (CRITICAL takeover)
# ---------------------------------------------------------------------------


@pytest.fixture()
def takeover_world(db_session):
    db = db_session
    attacker = _user(db, "Mallory", "mallory@attacker.example.com")  # users.id == 1
    victim = _user(db, "Victor", "victor@victim.example.com", role="ORGANIZER")
    victim_org = Organizer(
        name="Victim Events", slug="victim-events", description="d", email="contact@victim.example.com",
        phone="+91 99999 00000", user_id=victim.id, verified=True,
    )
    db.add(victim_org)
    db.flush()
    assert attacker.id == victim_org.id  # the precondition the old OR-lookup abused
    victim_event = _event(db, "Victim Summit", victim_org.id)
    db.add(Registration(event_id=victim_event.id, user_id=victim.id, ticket_type="Standard", status="confirmed"))
    db.commit()
    return {"attacker": attacker, "victim": victim, "victim_org": victim_org, "victim_event": victim_event}


RICH_EVENT = {
    "title": "Hijacked Title",
    "description": "Trying to edit an event I do not own.",
    "category": "Pharmaceuticals",
    "eventType": "Conference",
    "startDate": str(TODAY + timedelta(days=30)),
    "startTime": "10:00",
    "city": "Pune",
    "format": "online",
    "price": 0,
    "isFree": True,
    "saveAsDraft": True,
}


def test_user_with_id_equal_to_an_organizer_id_cannot_take_it_over(db_session, takeover_world):
    w = takeover_world
    client = _client(db_session, platform_ops_routes.router, dashboard_routes.router)
    headers = _auth(w["attacker"])

    # As an attendee account the attacker can't reach organiser endpoints at all...
    assert client.get("/api/organizer/profile", headers=headers).status_code == 403
    # ...so the takeover attempt needs an organiser account of their own.
    w["attacker"].role = "ORGANIZER"
    db_session.commit()

    profile = client.get("/api/organizer/profile", headers=headers)
    assert profile.status_code == 200
    body = profile.json()
    assert body["organizerId"] != w["victim_org"].id
    assert body["contactEmail"] == "mallory@attacker.example.com"
    assert body["contactPhone"] == ""  # victim's phone not leaked

    assert client.put(f"/api/organizer/events/{w['victim_event'].id}", json=RICH_EVENT, headers=headers).status_code == 403

    onboard = client.post("/api/organizer/onboarding", headers=headers, json={
        "organizerName": "Pwned Org", "organizationName": "Pwned Org Ltd", "contactEmail": "mallory@attacker.example.com",
    })
    assert onboard.status_code == 200
    db_session.refresh(w["victim_org"])
    assert w["victim_org"].name == "Victim Events"
    assert w["victim_org"].email == "contact@victim.example.com"

    dash = client.get("/api/organizer", headers=headers).json()
    assert dash["totalEvents"] == 0 and dash["registrations"] == 0 and dash["recentEvents"] == []
    assert client.get("/api/organizer/events", headers=headers).json() == []
    assert client.get("/api/organizer/events/full", headers=headers).json() == []
    analytics = client.get("/api/organizer/analytics", headers=headers).json()
    assert sum(analytics["registrations"]) == 0 and analytics["ticketDistribution"] == {}

    attacker_org = db_session.scalar(select(Organizer).where(Organizer.user_id == w["attacker"].id))
    assert attacker_org is not None and attacker_org.id != w["victim_org"].id and attacker_org.name == "Pwned Org"


def test_real_owner_still_sees_and_manages_own_events(db_session, takeover_world):
    w = takeover_world
    client = _client(db_session, platform_ops_routes.router, dashboard_routes.router)
    headers = _auth(w["victim"])
    dash = client.get("/api/organizer", headers=headers).json()
    assert dash["totalEvents"] == 1 and dash["registrations"] == 1
    assert [e["id"] for e in client.get("/api/organizer/events", headers=headers).json()] == [w["victim_event"].id]
    assert client.put(f"/api/organizer/events/{w['victim_event'].id}", json=RICH_EVENT, headers=headers).status_code == 200
    profile = client.get("/api/organizer/profile", headers=headers).json()
    assert profile["organizerId"] == w["victim_org"].id


def test_failed_ownership_check_creates_nothing_and_promotes_nobody(db_session, takeover_world):
    w = takeover_world
    client = _client(db_session, platform_ops_routes.router)
    resp = client.post(f"/api/organizer/events/{w['victim_event'].id}/attendance", json={"attendedRegistrationIds": []}, headers=_auth(w["attacker"]))
    assert resp.status_code == 403
    db_session.expire_all()
    assert db_session.get(User, w["attacker"].id).role == "USER"
    assert db_session.scalar(select(Organizer).where(Organizer.user_id == w["attacker"].id)) is None


def test_dashboard_event_creation_uses_db_assigned_id_and_unique_slug(db_session):
    db = db_session
    db.add_all([Organizer(name="New Host", slug="new-host", description="d"), Organizer(name="Other", slug="other", description="d")])
    user = User(id=50, name="New Host", email="newhost@example.com", role="ORGANIZER", password_hash="x")
    db.add(user)
    db.commit()
    client = _client(db, dashboard_routes.router)
    resp = client.post("/api/organizer/events", headers=_auth(user), json={
        "title": "Host Summit", "description": "A real conference for hosts.", "eventType": "Conference",
        "category": "Pharmaceuticals", "startDate": str(TODAY + timedelta(days=9)), "endDate": str(TODAY + timedelta(days=9)),
        "startTime": "10:00 AM", "location": "Pune", "format": "in-person", "price": 0,
    })
    assert resp.status_code == 201, resp.text
    owned = db.scalars(select(Organizer).where(Organizer.user_id == 50)).all()
    assert len(owned) == 1
    assert owned[0].id != 50  # DB-assigned, not copied from the user id
    assert owned[0].slug == "new-host-1"
    assert owned[0].verified is False
    assert db.scalar(select(Event).where(Event.slug.like("host-summit%"))).organizer_id == owned[0].id


# ---------------------------------------------------------------------------
# 9. Onboarding: no self-verification, discoveredOrganizerId validated
# ---------------------------------------------------------------------------


def _onboard(client, user, **extra):
    body = {"organizerName": "Asha Events", "organizationName": "Asha Events Pvt", "contactEmail": user.email, **extra}
    return client.post("/api/organizer/onboarding", headers=_auth(user), json=body)


def test_onboarding_does_not_mark_anything_verified(db_session):
    user = _user(db_session, "Asha", "asha@example.com", role="ORGANIZER", email_verified=False)
    db_session.commit()
    client = _client(db_session, platform_ops_routes.router)
    body = _onboard(client, user).json()
    assert body["emailVerified"] is False and body["identityVerified"] is False
    organizer = db_session.scalar(select(Organizer).where(Organizer.user_id == user.id))
    assert organizer.verified is False
    assert db_session.scalar(select(Organization).where(Organization.slug == "asha-events-pvt")).verified is False


def test_onboarding_email_verified_only_for_the_verified_account_email(db_session):
    user = _user(db_session, "Ravi", "ravi@example.com", role="ORGANIZER", email_verified=True)
    db_session.commit()
    client = _client(db_session, platform_ops_routes.router)
    assert _onboard(client, user).json()["emailVerified"] is True
    other = _onboard(client, user, contactEmail="someone-else@example.com").json()
    assert other["emailVerified"] is False and other["identityVerified"] is False


def test_onboarding_validates_discovered_organizer_link(db_session):
    db = db_session
    user = _user(db, "Asha", "asha@example.com", role="ORGANIZER")
    claimed = DiscoveredOrganizer(name="Claimed Org", email="c@org.test", website="https://c.test", source_url="https://c.test")
    free = DiscoveredOrganizer(name="Free Org", email="f@org.test", website="https://f.test", source_url="https://f.test")
    db.add_all([claimed, free])
    db.flush()
    db.add(Organizer(name="Someone Else", slug="someone-else", description="d", discovered_organizer_id=claimed.id))
    db.commit()
    client = _client(db, platform_ops_routes.router)

    assert _onboard(client, user, discoveredOrganizerId=987654).status_code == 422
    assert _onboard(client, user, discoveredOrganizerId=claimed.id).status_code == 409
    assert _onboard(client, user, discoveredOrganizerId=free.id).status_code == 200
    organizer = db.scalar(select(Organizer).where(Organizer.user_id == user.id))
    profile = db.scalar(select(OrganizerProfile).where(OrganizerProfile.user_id == user.id))
    assert organizer.discovered_organizer_id == free.id and profile.discovered_organizer_id == free.id


# ---------------------------------------------------------------------------
# 2 + 8. n8n webhooks
# ---------------------------------------------------------------------------

STRONG_SECRET = "test-only-strong-n8n-secret-0123456789"


@pytest.fixture()
def n8n(db_session, seeded_catalog, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "n8n_webhooks_enabled", False)
    monkeypatch.setattr(settings, "n8n_webhook_secret", STRONG_SECRET)
    attendee = _user(db_session, "Jane", "jane@example.com")
    admin = _user(db_session, "Admin", "admin@example.com", role="ADMIN")
    db_session.commit()
    return {
        "client": _client(db_session, webhooks_routes.router), "settings": settings, "event": seeded_catalog["event"],
        "attendee": attendee, "admin": admin, "monkeypatch": monkeypatch,
    }


def _reg_payload(n, **over):
    return {"idempotencyKey": f"k-{n['event'].id}-{over.pop('key', 'a')}", "eventId": n["event"].id, "userId": n["attendee"].id, **over}


def test_n8n_routes_are_404_when_disabled(n8n):
    client = n8n["client"]
    good = {"X-Webhook-Secret": STRONG_SECRET}
    assert client.post("/api/webhooks/n8n/registration", json=_reg_payload(n8n), headers=good).status_code == 404
    assert client.post("/api/webhooks/n8n/reminders-dispatch", json={"idempotencyKey": "abc"}, headers=good).status_code == 404
    # The admin-only, read-only workflow catalog stays visible (it lists what exists, it receives nothing).
    assert client.get("/api/webhooks/n8n/workflows", headers=_auth(n8n["admin"])).status_code == 200


def test_n8n_builtin_default_secret_is_refused(n8n):
    mp, settings = n8n["monkeypatch"], n8n["settings"]
    mp.setattr(settings, "n8n_webhooks_enabled", True)
    default_secret = type(settings).model_fields["n8n_webhook_secret"].default
    mp.setattr(settings, "n8n_webhook_secret", default_secret)
    resp = n8n["client"].post("/api/webhooks/n8n/registration", json=_reg_payload(n8n), headers={"X-Webhook-Secret": default_secret})
    assert resp.status_code == 403


def test_n8n_enabled_with_strong_secret(n8n):
    n8n["monkeypatch"].setattr(n8n["settings"], "n8n_webhooks_enabled", True)
    client = n8n["client"]
    good = {"X-Webhook-Secret": STRONG_SECRET}

    assert client.post("/api/webhooks/n8n/registration", json=_reg_payload(n8n), headers={"X-Webhook-Secret": "wrong-secret-value-123456"}).status_code == 401
    assert client.post("/api/webhooks/n8n/registration", json=_reg_payload(n8n)).status_code == 401

    # Missing ids are 422 — never "the first event/user in the table".
    no_event = {"idempotencyKey": "k-no-event", "userId": n8n["attendee"].id}
    assert client.post("/api/webhooks/n8n/registration", json=no_event, headers=good).status_code == 422
    no_user = {"idempotencyKey": "k-no-user", "eventId": n8n["event"].id}
    assert client.post("/api/webhooks/n8n/registration", json=no_user, headers=good).status_code == 422
    for path in ("event-published", "event-cancelled", "event-rescheduled", "attendee-followup", "organizer-followup", "attendance"):
        assert client.post(f"/api/webhooks/n8n/{path}", json={"idempotencyKey": f"k-{path}"}, headers=good).status_code == 422, path

    bad_date = {"idempotencyKey": "k-bad-date", "eventId": n8n["event"].id, "data": {"newStartDate": "next tuesday"}}
    assert client.post("/api/webhooks/n8n/event-rescheduled", json=bad_date, headers=good).status_code == 422

    ok = client.post("/api/webhooks/n8n/registration", json=_reg_payload(n8n), headers=good)
    assert ok.status_code == 200 and ok.json()["status"] == "COMPLETED"

    assert client.get("/api/webhooks/n8n/workflows", headers=_auth(n8n["attendee"])).status_code == 403
    assert client.get("/api/webhooks/n8n/workflows", headers=_auth(n8n["admin"])).status_code == 200


def test_n8n_organizer_followup_without_organizer_is_422(n8n, db_session):
    n8n["monkeypatch"].setattr(n8n["settings"], "n8n_webhooks_enabled", True)
    orphan = _event(db_session, "Orphan Event", None)
    db_session.commit()
    resp = n8n["client"].post(
        "/api/webhooks/n8n/organizer-followup", json={"idempotencyKey": "k-orphan", "eventId": orphan.id},
        headers={"X-Webhook-Secret": STRONG_SECRET},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 3. Public registration
# ---------------------------------------------------------------------------


def _registration(email, **over):
    return {"firstName": "Eve", "lastName": "Doe", "email": email, "ticketType": "Standard", "company": "EvilCo", "jobTitle": "Intruder", **over}


def test_anonymous_registration_cannot_touch_an_existing_account(db_session, seeded_catalog):
    owner = _user(db_session, "Owner", "owner@example.com", company="RealCo", job_title="CTO", country="India")
    db_session.commit()
    client = _client(db_session, events_routes.router)
    event = seeded_catalog["event"]

    for email in ("owner@example.com", "OWNER@example.com"):
        resp = client.post(f"/api/events/{event.id}/register", json=_registration(email, country="Nowhere"))
        assert resp.status_code == 401
        assert "sign in" in resp.json()["detail"].lower()
    db_session.refresh(owner)
    assert (owner.company, owner.job_title, owner.country) == ("RealCo", "CTO", "India")
    assert db_session.scalar(select(func.count(Registration.id)).where(Registration.user_id == owner.id)) == 0

    new = client.post(f"/api/events/{event.id}/register", json=_registration("brand-new@example.com"))
    assert new.status_code == 201
    created = db_session.scalar(select(User).where(User.email == "brand-new@example.com"))
    assert created is not None and created.password_hash.startswith("!unusable_")


def test_signed_in_proxy_registration_cannot_attach_to_another_account(db_session, seeded_catalog):
    host = _user(db_session, "Host", "host@example.com")
    other = _user(db_session, "Other", "other@example.com", company="OtherCo")
    db_session.commit()
    client = _client(db_session, events_routes.router)
    event = seeded_catalog["event"]
    assert client.post(f"/api/events/{event.id}/register", json=_registration("host@example.com"), headers=_auth(host)).status_code == 201
    resp = client.post(f"/api/events/{event.id}/register", json=_registration("other@example.com"), headers=_auth(host))
    assert resp.status_code == 409
    db_session.refresh(other)
    assert other.company == "OtherCo"
    assert db_session.scalar(select(func.count(Registration.id)).where(Registration.user_id == other.id)) == 0


def test_only_published_non_cancelled_events_take_registrations(db_session, seeded_catalog):
    org_id = seeded_catalog["event"].organizer_id
    draft = _event(db_session, "Draft Event", org_id, status="draft", lifecycle="DRAFT")
    pending = _event(db_session, "Pending Event", org_id, status="pending", lifecycle="SUBMITTED")
    cancelled = _event(db_session, "Cancelled Event", org_id, status="draft", lifecycle="CANCELLED")
    closed = _event(db_session, "Closed Event", org_id, status="published", lifecycle="REGISTRATION_CLOSED")
    db_session.commit()
    client = _client(db_session, events_routes.router)
    assert client.post(f"/api/events/{draft.id}/register", json=_registration("a@example.com")).status_code == 404
    assert client.post(f"/api/events/{pending.id}/register", json=_registration("b@example.com")).status_code == 404
    assert client.post(f"/api/events/{cancelled.id}/register", json=_registration("c@example.com")).status_code == 400
    assert client.post(f"/api/events/{closed.id}/register", json=_registration("d@example.com")).status_code == 400
    assert db_session.scalar(select(func.count(Registration.id))) == 0


# ---------------------------------------------------------------------------
# 4. Reschedule keeps status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status,lifecycle", [("draft", "DRAFT"), ("pending", "SUBMITTED"), ("published", "PUBLISHED"), ("draft", "CANCELLED")])
def test_reschedule_keeps_existing_status(db_session, seeded_catalog, status, lifecycle):
    event = _event(db_session, f"Resched {lifecycle}", seeded_catalog["event"].organizer_id, status=status, lifecycle=lifecycle)
    new_date = TODAY + timedelta(days=60)
    reschedule_event_workflow(db_session, event, new_start_date=new_date, new_start_time="11:00 AM", actor_id=1)
    db_session.commit()
    assert (event.status, event.lifecycle_state) == (status, lifecycle)
    assert event.start_date == new_date and event.start_time == "11:00 AM"


# ---------------------------------------------------------------------------
# 5. Login rate limiter
# ---------------------------------------------------------------------------


def _request(peer: str, xff: str | None = None, path: str = "/api/auth/login") -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({
        "type": "http", "method": "POST", "path": path, "raw_path": path.encode(), "headers": headers,
        "client": (peer, 5555), "query_string": b"", "server": ("testserver", 80), "scheme": "http",
    })


def test_forwarded_for_ignored_unless_peer_is_trusted_proxy(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "trusted_proxy_ips", "")
    assert client_ip_for(_request("203.0.113.9", "1.2.3.4")) == "203.0.113.9"

    monkeypatch.setattr(settings, "trusted_proxy_ips", "10.0.0.1, 10.0.0.2")
    assert client_ip_for(_request("203.0.113.9", "1.2.3.4")) == "203.0.113.9"  # peer is not a proxy
    # Right-most hop that is not one of our proxies (left-most is client-controlled).
    assert client_ip_for(_request("10.0.0.1", "1.2.3.4, 198.51.100.7, 10.0.0.2")) == "198.51.100.7"
    assert client_ip_for(_request("10.0.0.1")) == "10.0.0.1"


def test_rotating_forged_forwarded_for_does_not_bypass_limit(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "trusted_proxy_ips", "")
    for i in range(auth_rate_limiter.max_requests):
        rate_limit_auth(_request("203.0.113.50", f"10.9.{i}.1"))
    with pytest.raises(HTTPException) as exc:
        rate_limit_auth(_request("203.0.113.50", "10.9.250.1"))
    assert exc.value.status_code == 429


def test_rate_limiter_prunes_idle_keys_and_caps_memory():
    clock = {"t": 1000.0}
    limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60, max_keys=50, clock=lambda: clock["t"])
    for i in range(40):
        limiter.is_allowed(f"198.51.100.{i}:/login")
    assert limiter.tracked_keys() == 40
    clock["t"] += 61
    assert limiter.is_allowed("192.0.2.1:/login")[0] is True
    assert limiter.tracked_keys() == 1  # idle keys swept

    for i in range(200):
        limiter.is_allowed(f"203.0.113.{i}:/login")
    assert limiter.tracked_keys() == 50  # LRU cap


# ---------------------------------------------------------------------------
# 6. Attendee event detail visibility
# ---------------------------------------------------------------------------


@pytest.fixture()
def attendee_api(db_session):
    holder: dict = {"user": None}
    app = FastAPI()
    app.include_router(attendee_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: holder["user"]
    return TestClient(app), holder


def _discovered(db, name, *, discovery_status="NEW", verification="VERIFIED") -> DiscoveredEvent:
    org = DiscoveredOrganizer(name=f"{name} Org", email="private@org.test", phone="+1 555 0100", website="https://org.test", source_url="https://org.test")
    db.add(org)
    db.flush()
    ev = DiscoveredEvent(
        name=name, event_description="desc", category="Technology", subcategory="Conference",
        event_date=TODAY + timedelta(days=10), city="Pune", country="India", event_format="offline",
        url=f"https://events.test/{name.replace(' ', '-').lower()}", source_url="https://events.test",
        organizer_id=org.id, verification_status=verification, discovery_status=discovery_status,
        discovered_by="web_discovery_agent", confidence_score=80, discovered_at=datetime.now(timezone.utc),
    )
    db.add(ev)
    db.flush()
    return ev


def test_non_admin_cannot_fetch_drafts_or_rejected_events(db_session, attendee_api):
    client, holder = attendee_api
    db = db_session
    owner = _user(db, "Owner", "owner@example.com", role="ORGANIZER")
    org = Organizer(name="Draft Org", slug="draft-org", description="d", email="secret@draft.test", phone="+91 1", user_id=owner.id)
    db.add(org)
    db.flush()
    draft = _event(db, "Secret Draft", org.id, status="draft", lifecycle="DRAFT")
    published = _event(db, "Public Event", org.id, trust_status="APPROVED")
    rejected = _discovered(db, "Rejected Meetup", discovery_status="REJECTED")
    rejected_by_verification = _discovered(db, "Fake Expo", verification="REJECTED")
    fine = _discovered(db, "Fine Meetup")
    user = _user(db, "Asha", "asha@example.com")
    admin = _user(db, "Admin", "admin@example.com", role="ADMIN")
    db.commit()

    holder["user"] = user
    assert client.get(f"/api/attendee/events/platform/{draft.id}").status_code == 404
    assert client.post(f"/api/attendee/events/platform/{draft.id}/save").status_code == 404
    assert client.get(f"/api/attendee/events/discovered/{rejected.id}").status_code == 404
    assert client.get(f"/api/attendee/events/discovered/{rejected_by_verification.id}").status_code == 404
    assert client.get(f"/api/attendee/events/platform/{published.id}").status_code == 200
    assert client.get(f"/api/attendee/events/discovered/{fine.id}").status_code == 200

    # The owning organiser manages drafts in the organiser studio; the attendee
    # API is closed to organiser accounts altogether.
    holder["user"] = owner
    assert client.get(f"/api/attendee/events/platform/{draft.id}").status_code == 403

    holder["user"] = admin
    assert client.get(f"/api/attendee/events/platform/{draft.id}").status_code == 200
    assert client.get(f"/api/attendee/events/discovered/{rejected.id}").status_code == 200


def test_saved_event_stays_viewable_after_rejection(db_session, attendee_api):
    client, holder = attendee_api
    ev = _discovered(db_session, "Later Rejected")
    user = _user(db_session, "Asha", "asha@example.com")
    db_session.commit()
    holder["user"] = user
    assert client.post(f"/api/attendee/events/discovered/{ev.id}/save").status_code == 200
    ev.discovery_status = "REJECTED"
    db_session.commit()
    assert client.get(f"/api/attendee/events/discovered/{ev.id}").status_code == 200
    assert db_session.scalar(select(AttendeeEventActivity).where(AttendeeEventActivity.user_id == user.id)).is_saved


# ---------------------------------------------------------------------------
# 7. Only real numbers
# ---------------------------------------------------------------------------


def test_organizer_dashboard_and_analytics_report_only_real_numbers(db_session, seeded_catalog):
    db = db_session
    host = _user(db, "Host", "host@example.com", role="ORGANIZER")
    org = Organizer(name="Host Org", slug="host-org", description="d", user_id=host.id)
    db.add(org)
    db.flush()
    ev = _event(db, "Host Expo", org.id)
    now = datetime.now(timezone.utc)
    attendees = [_user(db, f"A{i}", f"a{i}@example.com") for i in range(4)]
    db.add_all([
        Registration(event_id=ev.id, user_id=attendees[0].id, ticket_type="Standard", status="confirmed", registered_at=now - timedelta(hours=1)),
        Registration(event_id=ev.id, user_id=attendees[1].id, ticket_type="VIP", status="confirmed", registered_at=now - timedelta(days=8)),
        Registration(event_id=ev.id, user_id=attendees[2].id, ticket_type="Standard", status="cancelled", registered_at=now - timedelta(days=9)),
        Registration(event_id=ev.id, user_id=attendees[3].id, ticket_type="Standard", status="confirmed", registered_at=now - timedelta(days=200)),
    ])
    db.commit()
    client = _client(db, dashboard_routes.router)
    headers = _auth(host)

    dash = client.get("/api/organizer", headers=headers).json()
    assert dash["registrations"] == 4 and dash["views"] is None and dash["conversionRate"] is None

    analytics = client.get("/api/organizer/analytics", headers=headers).json()
    assert analytics["views"] == [] and analytics["conversion"] == []
    assert analytics["registrations"] == [0, 0, 0, 0, 0, 2, 1]  # oldest week first; 200-day-old row is outside the window
    assert analytics["ticketDistribution"] == {"Standard": 2, "VIP": 1}  # cancelled excluded


def test_admin_growth_series_counts_real_creations(db_session):
    db = db_session
    now = datetime.now(timezone.utc)
    admin = _user(db, "Admin", "admin@example.com", role="ADMIN")
    admin.created_at = now
    old = _user(db, "Old", "old@example.com")
    old.created_at = now - timedelta(days=40)
    mid = _user(db, "Mid", "mid@example.com")
    mid.created_at = now - timedelta(days=3)
    db.commit()
    body = _client(db, dashboard_routes.router).get("/api/admin", headers=_auth(admin)).json()
    assert len(body["userGrowth"]) == 7 and sum(body["userGrowth"]) == 2
    assert body["userGrowth"][-1] == 1 and body["userGrowth"][3] == 1
    assert body["eventGrowth"] == [0] * 7


def test_event_detail_has_no_invented_agenda_or_exhibitors(db_session, seeded_catalog):
    resp = _client(db_session, events_routes.router).get(f"/api/events/{seeded_catalog['event'].slug}")
    assert resp.status_code == 200
    assert resp.json()["agenda"] == [] and resp.json()["exhibitors"] == []


# ---------------------------------------------------------------------------
# 8. Honest registration flags, no stand-in organizer
# ---------------------------------------------------------------------------


def test_registration_payment_and_calendar_flags_are_honest(db_session, seeded_catalog):
    free_event = seeded_catalog["event"]
    paid_event = _event(db_session, "Paid Event", free_event.organizer_id, price="499.00")
    user = _user(db_session, "Jane", "jane@example.com")
    free_reg = automate_registration(db_session, event=free_event, user=user)["registration"]
    paid_reg = automate_registration(db_session, event=paid_event, user=user)["registration"]
    assert free_reg.payment_status == "not_required" and free_reg.calendar_added is False
    assert paid_reg.payment_status == "pending" and paid_reg.calendar_added is False


def test_followup_without_organizer_contacts_nobody(db_session, seeded_catalog, monkeypatch):
    sent: list = []
    monkeypatch.setattr(registration_automation, "send_templated_notification", lambda *a, **k: sent.append(k))
    orphan = _event(db_session, "Orphan", None)
    assert initiate_or_advance_organizer_followup(db_session, event=orphan) is None
    assert sent == []
    assert db_session.scalar(select(func.count(OrganizerFollowup.id))) == 0


# ---------------------------------------------------------------------------
# 10. Login enumeration + email links
# ---------------------------------------------------------------------------


def test_login_error_does_not_reveal_whether_account_exists(db_session):
    _user(db_session, "Real", "real@example.com", password_hash=hash_password("CorrectPass123!"))
    db_session.commit()
    client = _client(db_session, auth_routes.router)
    unknown = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "WhateverPass1!"})
    wrong = client.post("/api/auth/login", json={"email": "real@example.com", "password": "WrongPass123!"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"] == "Incorrect email or password"
    assert client.post("/api/auth/login", json={"email": "real@example.com", "password": "CorrectPass123!"}).status_code == 200


def test_email_links_use_public_app_url(db_session, monkeypatch):
    import backend.services.notifications as notifications

    monkeypatch.setattr(get_settings(), "public_app_url", "https://app.example.test/")
    captured: list[dict] = []
    monkeypatch.setattr(notifications, "send_templated_notification", lambda db, **k: captured.append(k))
    _user(db_session, "Real", "real@example.com")
    db_session.commit()
    client = _client(db_session, auth_routes.router)

    assert client.post("/api/auth/forgot-password", json={"email": "real@example.com"}).status_code == 200
    reset = next(c for c in captured if c["template_key"] == "password_reset")["context"]["reset_link"]
    assert reset.startswith("https://app.example.test/reset-password?token=") and "localhost" not in reset

    assert client.post("/api/auth/register", json={"name": "New Person", "email": "new@example.com", "password": "SecurePass123!"}).status_code == 201
    verify = next(c for c in captured if c["template_key"] == "email_verification")["context"]["verification_link"]
    assert verify.startswith("https://app.example.test/verify-email?token=")


# ---------------------------------------------------------------------------
# 11. SMTP settings writer
# ---------------------------------------------------------------------------

_SMTP_ENV = ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL", "SMTP_USE_TLS")


@pytest.fixture()
def isolated_env_file(tmp_path, monkeypatch):
    """Point the writer at a temp .env and restore process env + settings cache."""
    env_file = tmp_path / ".env"
    env_file.write_text("JWT_SECRET=keep-me\nSMTP_HOST=old.example.test\n", encoding="utf-8")
    monkeypatch.setattr(smtp_config, "_get_env_paths", lambda: [env_file])
    saved = {k: os.environ.get(k) for k in _SMTP_ENV}
    yield env_file
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    get_settings.cache_clear()


@pytest.mark.parametrize("field", ["host", "username", "password", "from_email"])
def test_smtp_values_with_line_breaks_are_rejected(isolated_env_file, field):
    args = {"host": "smtp.example.test", "port": 587, "username": "u", "password": "p", "from_email": "from@example.test"}
    args[field] = args[field] + "\nJWT_SECRET=attacker"
    before = isolated_env_file.read_text(encoding="utf-8")
    env_before = {k: os.environ.get(k) for k in _SMTP_ENV}
    with pytest.raises(smtp_config.SmtpConfigError):
        smtp_config.save_smtp_settings(**args)
    assert isolated_env_file.read_text(encoding="utf-8") == before
    assert {k: os.environ.get(k) for k in _SMTP_ENV} == env_before


def test_smtp_write_failure_is_an_error(tmp_path, isolated_env_file, monkeypatch):
    unwritable = tmp_path / "is-a-directory"
    unwritable.mkdir()
    monkeypatch.setattr(smtp_config, "_get_env_paths", lambda: [unwritable])
    with pytest.raises(smtp_config.SmtpConfigError):
        smtp_config.save_smtp_settings("smtp.example.test", 587, "u", "p", "from@example.test")


def test_smtp_valid_save_writes_single_lines(isolated_env_file):
    smtp_config.save_smtp_settings("smtp.example.test", 2525, "user", "pass=word", "from@example.test", use_tls=False)
    text = isolated_env_file.read_text(encoding="utf-8")
    assert "JWT_SECRET=keep-me\n" in text
    assert "SMTP_HOST=smtp.example.test\n" in text and "SMTP_PORT=2525\n" in text and "SMTP_PASSWORD=pass=word\n" in text
    assert text.count("JWT_SECRET=") == 1


# ---------------------------------------------------------------------------
# 12. Attendee directory
# ---------------------------------------------------------------------------


def test_attendee_directory_is_scoped_and_hides_role(db_session, seeded_catalog):
    db = db_session
    shared = seeded_catalog["event"]
    other_event = _event(db, "Other Event", shared.organizer_id)
    me = _user(db, "Me", "me@example.com")
    peer = _user(db, "Peer", "peer@example.com", company="PeerCo")
    organiser = _user(db, "Host", "host@example.com", role="ORGANIZER")
    stranger = _user(db, "Stranger", "stranger@example.com")
    cancelled_peer = _user(db, "Gone", "gone@example.com")
    admin = _user(db, "Admin", "admin@example.com", role="ADMIN")
    db.add_all([
        Registration(event_id=shared.id, user_id=me.id, ticket_type="Standard", status="confirmed"),
        Registration(event_id=shared.id, user_id=peer.id, ticket_type="Standard", status="confirmed"),
        Registration(event_id=shared.id, user_id=organiser.id, ticket_type="Standard", status="confirmed"),
        Registration(event_id=shared.id, user_id=cancelled_peer.id, ticket_type="Standard", status="cancelled"),
        Registration(event_id=other_event.id, user_id=stranger.id, ticket_type="Standard", status="confirmed"),
    ])
    db.commit()
    client = _client(db, networking_routes.router)

    rows = client.get("/api/connections/attendees", headers=_auth(me)).json()
    assert [r["name"] for r in rows] == ["Peer"]
    assert "role" not in rows[0] and "email" not in rows[0]
    assert client.get(f"/api/connections/attendees?eventId={shared.id}", headers=_auth(me)).status_code == 200
    assert client.get(f"/api/connections/attendees?eventId={other_event.id}", headers=_auth(me)).status_code == 403

    admin_rows = client.get(f"/api/connections/attendees?eventId={other_event.id}", headers=_auth(admin)).json()
    assert [r["name"] for r in admin_rows] == ["Stranger"]
    assert client.get("/api/connections/attendees", headers=_auth(stranger)).json() == []
    # Organiser accounts are neither listed (above: only "Peer") nor allowed in.
    assert client.get("/api/connections/attendees", headers=_auth(organiser)).status_code == 403


def test_admin_workflow_catalog_stays_visible_while_webhooks_are_off(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.core.config import get_settings
    from backend.dependencies import get_current_user
    from backend.models import User
    from backend.routes import webhooks_n8n

    monkeypatch.setattr(get_settings(), "n8n_webhooks_enabled", False)
    app = FastAPI()
    app.include_router(webhooks_n8n.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: User(id=1, name="A", email="a@x.test", password_hash="x", role="ADMIN")
    client = TestClient(app)

    catalog = client.get("/api/webhooks/n8n/workflows")
    assert catalog.status_code == 200 and all(w["webhooksEnabled"] is False for w in catalog.json())
    assert client.post("/api/webhooks/n8n/registration", json={}).status_code == 404  # receivers stay off
