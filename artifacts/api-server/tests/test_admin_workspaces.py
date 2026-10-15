"""Integration tests for Admin Platform Workspaces:
- Events administration (list, status changes)
- Users administration (list, role changes)
- Reviews moderation (list, delete)
- RBAC validation: Non-admins rejected with 401/403
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import get_db
from backend.dependencies import get_current_user
from backend.models import Review, User
from backend.routes import dashboard as dashboard_routes


def _admin_user() -> User:
    return User(id=99, name="Super Admin", email="admin@100times.io", role="ADMIN", password_hash="hash")


def _normal_user() -> User:
    return User(id=2, name="Regular User", email="user@100times.io", role="USER", password_hash="hash")


@pytest.fixture()
def admin_app(db_session):
    app = FastAPI()
    app.include_router(dashboard_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    return app


def test_admin_events_rbac_and_status(admin_app, db_session, seeded_catalog):
    # Ordinary user gets 403
    admin_app.dependency_overrides[get_current_user] = _normal_user
    client = TestClient(admin_app)
    resp = client.get("/api/admin/events")
    assert resp.status_code == 403

    # Admin user succeeds
    admin_app.dependency_overrides[get_current_user] = _admin_user
    resp = client.get("/api/admin/events")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) >= 1

    event_id = seeded_catalog["event"].id
    # PATCH status to draft
    patch_resp = client.patch(f"/api/admin/events/{event_id}/status", json={"status": "draft"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "draft"


def test_admin_users_list_and_role(admin_app, db_session):
    normal = _normal_user()
    db_session.add(normal)
    db_session.commit()

    admin_app.dependency_overrides[get_current_user] = _admin_user
    client = TestClient(admin_app)

    resp = client.get("/api/admin/users")
    assert resp.status_code == 200
    users = resp.json()
    assert len(users) >= 1

    # Update role to ORGANIZER
    patch_resp = client.patch(f"/api/admin/users/{normal.id}/role", json={"role": "ORGANIZER"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["role"] == "ORGANIZER"


def test_admin_reviews_moderation(admin_app, db_session, seeded_catalog):
    normal = _normal_user()
    db_session.add(normal)
    db_session.commit()

    admin_app.dependency_overrides[get_current_user] = _admin_user
    client = TestClient(admin_app)

    # Create a review
    review = Review(
        event_id=seeded_catalog["event"].id,
        user_id=normal.id,
        rating=5,
        title="Phenomenal Event",
        comment="Incredible speakers and networking.",
    )
    db_session.add(review)
    db_session.commit()

    resp = client.get("/api/admin/reviews")
    assert resp.status_code == 200
    reviews = resp.json()
    assert any(r["id"] == review.id for r in reviews)

    # Delete review
    del_resp = client.delete(f"/api/admin/reviews/{review.id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "ok"

