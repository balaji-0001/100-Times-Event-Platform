"""Explore page date filter: GET /api/events?dateFrom=&dateTo=.

An event matches when it runs on any day inside the range, so multi-day
events that started before `dateFrom` but are still on are included."""

from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import get_db
from backend.routes import events


@pytest.fixture
def api(db_session, seeded_catalog):
    app = FastAPI()
    app.include_router(events.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app), seeded_catalog["event"]  # runs today+14 .. today+15


def _titles(client, **params):
    resp = client.get("/api/events", params=params)
    assert resp.status_code == 200, resp.text
    return [e["title"] for e in resp.json()["items"]]


def _d(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def test_range_containing_the_event(api):
    client, event = api
    assert _titles(client, dateFrom=_d(10), dateTo=_d(20)) == [event.title]


def test_range_overlapping_only_the_last_day(api):
    client, event = api
    assert _titles(client, dateFrom=_d(15), dateTo=_d(30)) == [event.title]


def test_range_before_or_after_the_event(api):
    client, _ = api
    assert _titles(client, dateFrom=_d(0), dateTo=_d(13)) == []
    assert _titles(client, dateFrom=_d(16), dateTo=_d(40)) == []


def test_open_ended_ranges(api):
    client, event = api
    assert _titles(client, dateFrom=_d(15)) == [event.title]
    assert _titles(client, dateTo=_d(14)) == [event.title]
    assert _titles(client, dateTo=_d(13)) == []


@pytest.mark.parametrize("params", [{"dateFrom": "next week"}, {"dateTo": "2026-13-40"}, {"dateFrom": _d(10), "dateTo": _d(5)}])
def test_bad_dates_are_rejected(api, params):
    client, _ = api
    assert client.get("/api/events", params=params).status_code == 422
