"""Description assistant on the create-event form (POST /api/organizer/events/describe).

- Organiser accounts only.
- With AI: the model sees only the form's details + the organiser's messages,
  under rules that forbid inventing facts; its text is returned as-is.
- Without AI: "Write it for me" (no instructions) gets a plain description
  built only from the form fields; instructions get an honest 503.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.security import create_access_token
from backend.db import get_db
from backend.models import User
from backend.routes import platform_ops
from backend.services.social_agent import ai_client
from backend.services.social_agent.ai_client import AIClientError

FIELDS = {
    "title": "Dell AI Summit",
    "eventType": "Conference",
    "sector": "Technology",
    "format": "in-person",
    "startDate": "2026-12-03",
    "endDate": "2026-12-04",
    "city": "Bengaluru",
    "country": "India",
    "organizationName": "Dell",
    "targetAudience": "IT leaders",
}


class TextAI:
    provider = "test"
    model = "test-model"

    def __init__(self, reply="", configured=True, error=None):
        self.is_configured = configured
        self.reply = reply
        self.error = error
        self.calls = []

    def generate_text(self, system, user, max_tokens=512):
        self.calls.append({"system": system, "user": user})
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture
def api(db_session):
    app = FastAPI()
    app.include_router(platform_ops.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    platform_ops._description_limiter._history.clear()
    return TestClient(app)


def _user(db, role):
    user = User(name="Host", email=f"{role.lower()}@example.com", role=role, password_hash="x")
    db.add(user)
    db.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id, role)}"}


def _use_ai(monkeypatch, fake):
    monkeypatch.setattr(ai_client, "get_ai_client", lambda: fake)
    return fake


def test_only_organisers_can_use_it(api, db_session):
    assert api.post("/api/organizer/events/describe", json={"fields": FIELDS}, headers=_user(db_session, "USER")).status_code == 403
    assert api.post("/api/organizer/events/describe", json={"fields": FIELDS}).status_code == 401


def test_ai_draft_uses_only_the_given_details_and_prompt(api, db_session, monkeypatch):
    draft = "Dell AI Summit brings IT leaders to Bengaluru on 3-4 December 2026 for two days of conference sessions on applied AI."
    fake = _use_ai(monkeypatch, TextAI(reply=draft))
    resp = api.post(
        "/api/organizer/events/describe",
        json={"fields": FIELDS, "prompt": "Make it sound formal and mention hands-on labs", "currentDescription": "old text"},
        headers=_user(db_session, "ORGANIZER"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"description": draft, "source": "ai", "provider": "test", "model": "test-model"}

    sent = fake.calls[0]
    assert "Never invent speakers" in sent["system"]
    for value in ("Dell AI Summit", "Bengaluru", "IT leaders", "hands-on labs", "old text"):
        assert value in sent["user"]


def test_follow_up_messages_carry_the_conversation(api, db_session, monkeypatch):
    fake = _use_ai(monkeypatch, TextAI(reply="A shorter description of the Dell AI Summit for IT leaders in Bengaluru."))
    history = [{"role": "user", "text": "Write it"}, {"role": "assistant", "text": "First draft text"}]
    resp = api.post(
        "/api/organizer/events/describe",
        json={"fields": FIELDS, "prompt": "Shorter please", "history": history},
        headers=_user(db_session, "ORGANIZER"),
    )
    assert resp.status_code == 200
    assert "First draft text" in fake.calls[0]["user"] and "Shorter please" in fake.calls[0]["user"]


def test_without_ai_write_it_for_me_builds_a_factual_description(api, db_session, monkeypatch):
    _use_ai(monkeypatch, TextAI(configured=False))
    resp = api.post("/api/organizer/events/describe", json={"fields": FIELDS}, headers=_user(db_session, "ORGANIZER"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "template"
    assert body["description"].startswith(
        "Dell AI Summit is a conference for the Technology sector in Bengaluru, India from 3 December 2026 to 4 December 2026."
    )
    assert "organised by Dell" in body["description"] and "aimed at IT leaders" in body["description"]


def test_without_ai_instructions_fail_honestly(api, db_session, monkeypatch):
    _use_ai(monkeypatch, TextAI(configured=False))
    resp = api.post(
        "/api/organizer/events/describe", json={"fields": FIELDS, "prompt": "Make it fun"}, headers=_user(db_session, "ORGANIZER")
    )
    assert resp.status_code == 503
    assert "isn't set up" in resp.json()["detail"]


def test_ai_error_with_instructions_is_reported(api, db_session, monkeypatch):
    _use_ai(monkeypatch, TextAI(error=AIClientError("timeout")))
    resp = api.post(
        "/api/organizer/events/describe", json={"fields": FIELDS, "prompt": "Make it fun"}, headers=_user(db_session, "ORGANIZER")
    )
    assert resp.status_code == 503 and "timeout" in resp.json()["detail"]


def test_online_event_template_does_not_claim_a_place(api, db_session, monkeypatch):
    _use_ai(monkeypatch, TextAI(configured=False))
    fields = {**FIELDS, "format": "online", "endDate": "2026-12-03"}
    text = api.post("/api/organizer/events/describe", json={"fields": fields}, headers=_user(db_session, "ORGANIZER")).json()["description"]
    assert "held online on 3 December 2026" in text and "Bengaluru" not in text


def test_needs_a_title_or_a_prompt(api, db_session):
    assert api.post("/api/organizer/events/describe", json={"fields": {}}, headers=_user(db_session, "ORGANIZER")).status_code == 422
