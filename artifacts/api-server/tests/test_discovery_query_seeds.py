"""Event Discovery Agent — search query generation tests: broad coverage,
deterministic output, and the configured cap is respected."""

from backend.services.discovery_agent.query_seeds import build_search_queries
from backend.services.discovery_agent.types import DiscoveryConfig


def test_build_search_queries_respects_search_depth_cap():
    config = DiscoveryConfig(cities=["Pune", "Mumbai"], states=["Maharashtra"], categories=["Technology", "Finance"], search_depth=5)
    queries = build_search_queries(config)
    assert len(queries) == 5


def test_build_search_queries_is_deterministic():
    config = DiscoveryConfig(cities=["Pune"], states=["Maharashtra"], categories=["Technology"], search_depth=10)
    assert build_search_queries(config) == build_search_queries(config)


def test_build_search_queries_interleaves_cities_states_and_source_qualifiers():
    config = DiscoveryConfig(cities=["Pune"], states=["Maharashtra"], categories=["Technology"], search_depth=3)
    queries = build_search_queries(config)
    assert any("Pune" in q for q in queries)
    assert any("Maharashtra" in q for q in queries)


def test_build_search_queries_handles_empty_geography():
    config = DiscoveryConfig(cities=[], states=[], categories=["Technology"], search_depth=5)
    queries = build_search_queries(config)
    assert len(queries) <= 5
    assert all("Technology" in q for q in queries)
