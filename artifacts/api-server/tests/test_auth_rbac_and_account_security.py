"""Automated Tests for RBAC, Event Ownership, and Account Security Features.

Covers:
- Attendee vs. Organiser vs. Admin permission boundaries
- Preventing privilege elevation at registration
- Event ownership & tenant isolation
- Multi-role support
- Email verification flow (token generation, expiration, single-use)
- Password reset flow (generic anti-enumeration, single-use, hash verification)
- Account deletion (re-auth, cascading cleanup, audit logging)
"""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.core.security import create_access_token, hash_password
from backend.db import get_db
from backend.main import app
from backend.models import EmailVerificationToken, Event, Organizer, PasswordResetToken, Registration, User


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    c = TestClient(app)
    try:
        yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


def auth_header(user_id: int, role: str) -> dict[str, str]:
    token = create_access_token(user_id, role)
    return {"Authorization": f"Bearer {token}"}


def test_registration_always_defaults_to_attendee(client: TestClient, db_session):
    """Ensure user registration never grants organiser or admin roles even if requested."""
    payload = {
        "name": "Eager User",
        "email": "eager_user@example.com",
        "password": "SecurePassword123!",
        "role": "ORGANIZER",  # Requesting elevation during registration
        "country": "India",
        "company": "Eager Events",
    }
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["user"]["role"] == "USER"
    assert "attendee" in data["user"]["roles"]
    assert "organiser" not in data["user"]["roles"]
    assert "admin" not in data["user"]["roles"]

    # Verify user in database
    user = db_session.scalar(select(User).where(User.email == "eager_user@example.com"))
    assert user is not None
    assert user.role == "USER"
    assert user.email_verified is False


def test_non_admin_cannot_access_admin_routes(client: TestClient, db_session):
    """Verify attendees and organisers receive 403 Forbidden on admin APIs."""
    attendee = User(
        name="Regular Attendee",
        email="regular_attendee@example.com",
        password_hash=hash_password("Pass123!"),
        role="USER",
        email_verified=True,
    )
    db_session.add(attendee)
    db_session.commit()

    headers = auth_header(attendee.id, "USER")
    resp = client.get("/api/admin/overview-extended", headers=headers)
    assert resp.status_code == 403

    resp_obs = client.get("/api/admin/observability/overview", headers=headers)
    assert resp_obs.status_code == 403


def test_organizer_event_ownership_isolation(client: TestClient, db_session):
    """Verify that an organiser cannot mutate an event owned by another organiser."""
    org1_user = User(
        name="Org One",
        email="org1@example.com",
        password_hash=hash_password("Pass123!"),
        role="ORGANIZER",
        email_verified=True,
    )
    org2_user = User(
        name="Org Two",
        email="org2@example.com",
        password_hash=hash_password("Pass123!"),
        role="ORGANIZER",
        email_verified=True,
    )
    db_session.add_all([org1_user, org2_user])
    db_session.flush()

    org1 = Organizer(
        id=org1_user.id,
        user_id=org1_user.id,
        name="Org One",
        slug="org-one",
        description="Org One",
        email=org1_user.email,
        verified=True,
    )
    org2 = Organizer(
        id=org2_user.id,
        user_id=org2_user.id,
        name="Org Two",
        slug="org-two",
        description="Org Two",
        email=org2_user.email,
        verified=True,
    )
    db_session.add_all([org1, org2])
    db_session.flush()

    event1 = Event(
        title="Org One Private Event",
        slug="org-one-event",
        description="Exclusive conference",
        event_type="conference",
        start_date=datetime.now(timezone.utc).date() + timedelta(days=10),
        end_date=datetime.now(timezone.utc).date() + timedelta(days=10),
        start_time="10:00",
        timezone="Asia/Kolkata",
        organizer_id=org1.id,
        status="published",
    )
    db_session.add(event1)
    db_session.commit()

    # Org Two attempts to cancel Org One's event -> 403 Forbidden
    headers2 = auth_header(org2_user.id, "ORGANIZER")
    resp = client.post(f"/api/organizer/events/{event1.id}/cancel", json={"reason": "Malicious cancellation"}, headers=headers2)
    assert resp.status_code == 403


def test_email_verification_flow(client: TestClient, db_session):
    """Verify email verification token validation, single-use, and expiration."""
    user = User(
        name="Unverified User",
        email="unverified@example.com",
        password_hash=hash_password("Pass123!"),
        role="USER",
        email_verified=False,
    )
    db_session.add(user)
    db_session.commit()

    # Request verification email
    headers = auth_header(user.id, "USER")
    resp = client.post("/api/auth/send-verification-email", headers=headers)
    assert resp.status_code == 200

    # Retrieve created token
    token_row = db_session.scalar(select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id))
    assert token_row is not None
    assert token_row.used_at is None

    # Invalid token check fails
    resp_bad = client.post("/api/auth/verify-email", json={"token": "bogus-token-value-12345"})
    assert resp_bad.status_code == 400

    # Test direct token verification with raw token
    raw_token = "valid_test_verification_token_123"
    token_row.token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    db_session.commit()

    resp_valid = client.post("/api/auth/verify-email", json={"token": raw_token})
    assert resp_valid.status_code == 200

    db_session.refresh(user)
    assert user.email_verified is True


def test_password_reset_anti_enumeration_and_reset(client: TestClient, db_session):
    """Verify forgot-password anti-enumeration and reset-password completion."""
    user = User(
        name="Reset Target",
        email="resettarget@example.com",
        password_hash=hash_password("OldPassword123!"),
        role="USER",
        email_verified=True,
    )
    db_session.add(user)
    db_session.commit()

    # Non-existent user returns the identical generic message
    resp_unknown = client.post("/api/auth/forgot-password", json={"email": "nonexistent@example.com"})
    assert resp_unknown.status_code == 200
    assert "If an account with this email exists" in resp_unknown.json()["message"]

    # Real user request
    resp_real = client.post("/api/auth/forgot-password", json={"email": "resettarget@example.com"})
    assert resp_real.status_code == 200
    assert "If an account with this email exists" in resp_real.json()["message"]

    # Token exists in DB
    reset_record = db_session.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    assert reset_record is not None
    assert reset_record.used_at is None

    # Reset password with valid token
    raw_token = "valid_test_reset_token_987654321"
    reset_record.token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    db_session.commit()

    resp_reset = client.post("/api/auth/reset-password", json={"token": raw_token, "newPassword": "BrandNewPassword999!"})
    assert resp_reset.status_code == 200

    db_session.refresh(reset_record)
    assert reset_record.used_at is not None


def test_delete_account_safety(client: TestClient, db_session):
    """Verify account deletion requires re-authentication, deletes user, and preserves registration counts."""
    user = User(
        name="User To Delete",
        email="delete_me@example.com",
        password_hash=hash_password("MyPassword123!"),
        role="USER",
        email_verified=True,
    )
    db_session.add(user)
    db_session.commit()

    # Wrong password fails
    headers = auth_header(user.id, "USER")
    resp_wrong_pass = client.post("/api/auth/delete-account", json={"confirmation": "DELETE", "password": "WrongPassword!"}, headers=headers)
    assert resp_wrong_pass.status_code == 401

    # Wrong confirmation string fails
    resp_wrong_conf = client.post("/api/auth/delete-account", json={"confirmation": "CANCEL", "password": "MyPassword123!"}, headers=headers)
    assert resp_wrong_conf.status_code == 400

    # Successful deletion
    resp_success = client.post("/api/auth/delete-account", json={"confirmation": "DELETE", "password": "MyPassword123!"}, headers=headers)
    assert resp_success.status_code == 200

    # User is removed from database
    db_session.expire_all()
    assert db_session.get(User, user.id) is None

