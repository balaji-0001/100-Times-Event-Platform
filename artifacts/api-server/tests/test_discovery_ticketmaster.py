"""Unit tests for Ticketmaster Discovery API integration."""

from backend.services.discovery_agent.ticketmaster import (
    parse_ticketmaster_event,
    test_ticketmaster_connection as check_tm_connection,
)


def test_parse_ticketmaster_event():
    sample_tm_event = {
        "id": "vvG1YZ99f4h0",
        "name": "Global AI & Cloud Expo 2026",
        "url": "https://www.ticketmaster.com/event/vvG1YZ99f4h0",
        "dates": {
            "start": {
                "localDate": "2026-12-15",
                "localTime": "09:30:00",
            }
        },
        "classifications": [
            {
                "segment": {"name": "Miscellaneous"},
                "genre": {"name": "Business"},
                "subGenre": {"name": "Conference"},
            }
        ],
        "info": "The world's leading artificial intelligence and cloud computing summit.",
        "promoter": {"name": "TechEx Global"},
        "_embedded": {
            "venues": [
                {
                    "name": "Santa Clara Convention Center",
                    "city": {"name": "San Francisco"},
                    "state": {"name": "California"},
                    "country": {"name": "United States"},
                }
            ]
        },
    }

    candidate = parse_ticketmaster_event(sample_tm_event)
    assert candidate is not None
    assert candidate.name == "Global AI & Cloud Expo 2026"
    assert candidate.date == "2026-12-15"
    assert candidate.start_time == "09:30:00"
    assert candidate.city == "San Francisco"
    assert candidate.state == "California"
    assert candidate.country == "United States"
    assert candidate.venue == "Santa Clara Convention Center"
    assert candidate.category == "Finance"
    assert candidate.organizer_name_hint == "TechEx Global"
    assert candidate.extraction_confidence >= 90
    assert candidate.primary_source.source_type == "ticketmaster_api"


def test_ticketmaster_connection_with_empty_key():
    res = check_tm_connection("")
    assert res["success"] is False
    assert "missing" in res["message"].lower()


def test_connection_error_never_echoes_the_api_key(monkeypatch):
    import requests

    from backend.services.discovery_agent import ticketmaster

    def boom(url, params=None, **kwargs):
        raise requests.exceptions.ConnectionError(f"HTTPSConnectionPool: Max retries exceeded with url: /discovery/v2/events.json?apikey={params['apikey']}")

    monkeypatch.setattr(ticketmaster.requests, "get", boom)
    result = check_tm_connection("SECRET-KEY-1234567890")

    assert result["success"] is False
    assert "SECRET-KEY" not in result["message"]
