"""Attendee and organiser accounts are separate.

- The account type is chosen at sign-up and decides everything; a raw `role`
  in the payload is ignored and nothing ever promotes an attendee.
- Attendee endpoints refuse organiser accounts, organiser endpoints refuse
  attendee accounts, admins pass both.
- Attendee personal details live in `attendee_profiles`, organiser details in
  `organizer_profiles` / `organizers` — never the other way round.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.core.security import create_access_token
from backend.db import get_db
from backend.main import app
from backend.models import AttendeeProfile, Organizer, OrganizerProfile, User


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


def _user(db, name: str, email: str, role: str = "USER") -> User:
    user = User(name=name, email=email, role=role, password_hash="x")
    db.add(user)
    db.commit()
    return user


def _register(client: TestClient, email: str, **extra):
    body = {"name": "Test Person", "email": email, "password": "SecurePassword123!", "country": "India", **extra}
    return client.post("/api/auth/register", json=body)


# ---------------------------------------------------------------------------
# Sign-up
# ---------------------------------------------------------------------------


def test_attendee_sign_up_creates_only_an_attendee_account(client, db_session):
    resp = _register(client, "asha@example.com", company="Asha Labs")
    assert resp.status_code == 201, resp.text
    user = resp.json()["user"]
    assert user["role"] == "USER" and user["accountType"] == "attendee"
    assert user["roles"] == ["attendee", "user"]

    row = db_session.get(User, user["id"])
    assert db_session.get(AttendeeProfile, row.id).company == "Asha Labs"
    assert row.company is None  # attendee details are not kept on the account row
    assert db_session.scalar(select(Organizer).where(Organizer.user_id == row.id)) is None
    assert db_session.scalar(select(OrganizerProfile).where(OrganizerProfile.user_id == row.id)) is None


def test_organiser_sign_up_creates_only_an_organiser_account(client, db_session):
    resp = _register(client, "host@example.com", accountType="organiser", company="Host Events Pvt")
    assert resp.status_code == 201, resp.text
    user = resp.json()["user"]
    assert user["role"] == "ORGANIZER" and user["accountType"] == "organiser"
    assert "attendee" not in user["roles"]

    profile = db_session.scalar(select(OrganizerProfile).where(OrganizerProfile.user_id == user["id"]))
    assert profile is not None and profile.organization_name == "Host Events Pvt"
    assert profile.identity_verified is False
    assert db_session.scalar(select(Organizer).where(Organizer.user_id == user["id"])).verified is False
    assert db_session.get(AttendeeProfile, user["id"]) is None


def test_organiser_sign_up_needs_an_organisation_name(client):
    assert _register(client, "noorg@example.com", accountType="organiser").status_code == 422


def test_raw_role_in_sign_up_is_ignored(client):
    resp = _register(client, "sneaky@example.com", role="ORGANIZER")
    assert resp.status_code == 201
    assert resp.json()["user"]["role"] == "USER"
    assert _register(client, "admin-wannabe@example.com", accountType="admin").status_code == 422


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

ORGANISER_ONLY = [
    ("get", "/api/organizer/profile", None),
    ("post", "/api/organizer/onboarding", {"organizerName": "X Org", "organizationName": "X Org Ltd", "contactEmail": "x@example.com"}),
    ("get", "/api/organizer/events/full", None),
    ("get", "/api/organizer", None),
    ("get", "/api/organizer/events", None),
    ("get", "/api/organizer/analytics", None),
]

ATTENDEE_ONLY = [
    ("get", "/api/attendee/profile", None),
    ("get", "/api/attendee/preferences", None),
    ("get", "/api/attendee/events", None),
    ("get", "/api/attendee/dashboard", None),
    ("post", "/api/attendee/match", {}),
    ("get", "/api/dashboard", None),
    ("get", "/api/dashboard/saved-events", None),
    ("get", "/api/dashboard/registrations", None),
    ("get", "/api/dashboard/schedule", None),
    ("get", "/api/connections", None),
    ("get", "/api/connections/attendees", None),
]


@pytest.mark.parametrize("method,path,body", ORGANISER_ONLY, ids=[p for _, p, _ in ORGANISER_ONLY])
def test_attendee_cannot_use_organiser_endpoints_or_get_promoted(client, db_session, method, path, body):
    attendee = _user(db_session, "Asha", "asha@example.com")
    resp = getattr(client, method)(path, headers=_auth(attendee), **({"json": body} if body is not None else {}))
    assert resp.status_code == 403
    db_session.expire_all()
    assert db_session.get(User, attendee.id).role == "USER"
    assert db_session.scalar(select(Organizer).where(Organizer.user_id == attendee.id)) is None


@pytest.mark.parametrize("method,path,body", ATTENDEE_ONLY, ids=[p for _, p, _ in ATTENDEE_ONLY])
def test_organiser_cannot_use_attendee_endpoints(client, db_session, method, path, body):
    organiser = _user(db_session, "Host", "host@example.com", role="ORGANIZER")
    resp = getattr(client, method)(path, headers=_auth(organiser), **({"json": body} if body is not None else {}))
    assert resp.status_code == 403


def test_organiser_cannot_save_or_register_for_events(client, db_session, seeded_catalog):
    organiser = _user(db_session, "Host", "host@example.com", role="ORGANIZER")
    event = seeded_catalog["event"]
    assert client.post(f"/api/events/{event.id}/save", headers=_auth(organiser)).status_code == 403
    resp = client.post(
        f"/api/events/{event.id}/register",
        headers=_auth(organiser),
        json={"firstName": "Host", "lastName": "Person", "email": "host@example.com", "ticketType": "Standard"},
    )
    assert resp.status_code == 403
    assert "attendee account" in resp.json()["detail"]


def test_admin_can_open_both_areas(client, db_session):
    admin = _user(db_session, "Admin", "admin@example.com", role="ADMIN")
    assert client.get("/api/attendee/profile", headers=_auth(admin)).status_code == 200
    assert client.get("/api/organizer/profile", headers=_auth(admin)).status_code == 200


def test_me_reports_the_account_type(client, db_session):
    attendee = _user(db_session, "Asha", "asha@example.com")
    organiser = _user(db_session, "Host", "host@example.com", role="ORGANIZER")
    assert client.get("/api/auth/me", headers=_auth(attendee)).json()["accountType"] == "attendee"
    assert client.get("/api/auth/me", headers=_auth(organiser)).json()["accountType"] == "organiser"


# ---------------------------------------------------------------------------
# Attendee profile
# ---------------------------------------------------------------------------


def test_attendee_profile_round_trip_is_stored_apart_from_organiser_data(client, db_session):
    attendee = _user(db_session, "Asha", "asha@example.com")
    first = client.get("/api/attendee/profile", headers=_auth(attendee)).json()
    assert first["accountType"] == "attendee" and first["email"] == "asha@example.com" and first["jobTitle"] is None

    body = {
        "name": "Asha Rao", "phone": "+91 98765 43210", "city": "Pune", "country": "india",
        "jobTitle": "Product Lead", "company": "Asha Labs", "bio": "Builds things.",
        "linkedinUrl": "https://www.linkedin.com/in/asha",
    }
    saved = client.put("/api/attendee/profile", headers=_auth(attendee), json=body)
    assert saved.status_code == 200, saved.text
    out = saved.json()
    assert out["name"] == "Asha Rao" and out["country"] == "India" and out["jobTitle"] == "Product Lead"

    row = db_session.get(AttendeeProfile, attendee.id)
    assert (row.phone, row.city, row.company, row.linkedin_url) == ("+91 98765 43210", "Pune", "Asha Labs", "https://www.linkedin.com/in/asha")
    assert db_session.scalar(select(OrganizerProfile).where(OrganizerProfile.user_id == attendee.id)) is None


@pytest.mark.parametrize(
    "field,value",
    [("country", "Atlantis"), ("linkedinUrl", "https://evil.example.com/in/x"), ("phone", "call me maybe"), ("name", "A")],
)
def test_attendee_profile_rejects_bad_values(client, db_session, field, value):
    attendee = _user(db_session, "Asha", "asha@example.com")
    resp = client.put("/api/attendee/profile", headers=_auth(attendee), json={"name": "Asha", field: value})
    assert resp.status_code == 422


def test_existing_account_details_seed_a_new_attendee_profile(client, db_session):
    attendee = User(name="Old", email="old@example.com", role="USER", password_hash="x", job_title="Analyst", company="OldCo", country="India")
    db_session.add(attendee)
    db_session.commit()
    out = client.get("/api/attendee/profile", headers=_auth(attendee)).json()
    assert (out["jobTitle"], out["company"], out["country"]) == ("Analyst", "OldCo", "India")


# ---------------------------------------------------------------------------
# Discover: search & filter
# ---------------------------------------------------------------------------


def test_attendee_event_search_filters_the_verified_catalog(client, db_session, seeded_catalog):
    event = seeded_catalog["event"]
    event.trust_status = "APPROVED"
    attendee = _user(db_session, "Asha", "asha@example.com")
    headers = _auth(attendee)

    everything = client.get("/api/attendee/events", headers=headers).json()
    assert everything["total"] == 1 and everything["results"][0]["title"] == event.title

    assert client.get("/api/attendee/events?q=pharma summit", headers=headers).json()["total"] == 1
    assert client.get("/api/attendee/events?q=blockchain", headers=headers).json()["total"] == 0
    assert client.get("/api/attendee/events?country=Germany", headers=headers).json()["total"] == 0
    assert client.get("/api/attendee/events?mode=online", headers=headers).json()["total"] == 0
    assert client.get("/api/attendee/events?pageSize=0", headers=headers).status_code == 422
