"""Unit tests for `services/discovery_agent/format_normalize.py` — the
free-text -> online|offline|hybrid classifier extracted event pages'
`event_format` field gets normalized through."""

import pytest

from backend.services.discovery_agent.format_normalize import normalize_event_format


@pytest.mark.parametrize("raw", [None, "", "   ", "TBD", "check website", "Free entry"])
def test_missing_or_unrecognized_returns_none(raw):
    assert normalize_event_format(raw) is None


@pytest.mark.parametrize(
    "raw",
    ["online", "Online", "ONLINE", "Virtual", "This is a webinar", "join our livestream", "fully remote event"],
)
def test_online_variants(raw):
    assert normalize_event_format(raw) == "online"


@pytest.mark.parametrize(
    "raw",
    ["offline", "In-person", "in person", "In-person exhibition and conference", "physical venue only", "on-site at the campus"],
)
def test_offline_variants(raw):
    assert normalize_event_format(raw) == "offline"


@pytest.mark.parametrize(
    "raw",
    [
        "hybrid",
        "Hybrid Event",
        "In-person (with YouTube live streaming)",
        "https://schema.org/MixedEventAttendanceMode",
        "attend in person or join online",
    ],
)
def test_hybrid_variants(raw):
    assert normalize_event_format(raw) == "hybrid"


def test_schema_org_attendance_mode_urls():
    assert normalize_event_format("https://schema.org/OfflineEventAttendanceMode") == "offline"
    assert normalize_event_format("https://schema.org/OnlineEventAttendanceMode") == "online"
    assert normalize_event_format("https://schema.org/MixedEventAttendanceMode") == "hybrid"
