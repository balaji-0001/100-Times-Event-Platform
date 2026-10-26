"""FastAPI Routes for Global Event Discovery Source Registry.

Provides administrative APIs to:
- List & filter all 74+ candidate event discovery sources
- View aggregate source health and integration metrics
- Toggle source enabled/disabled state
- Update source configurations and API credentials
- Trigger live health probes with latency measurements
- Execute sample event extraction tests with real source data
- Synchronize registry definitions with the database
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.services.discovery_agent.adapters import adapter_manager
from backend.services.discovery_agent.source_registry import (
    get_registry_summary_stats,
    get_source,
    list_sources,
    seed_or_sync_source_registry,
    update_source,
)

logger = logging.getLogger("routes.discovery_sources")

router = APIRouter(prefix="/api/discovery/sources", tags=["discovery_sources"])


class UpdateSourcePayload(BaseModel):
    is_enabled: bool | None = None
    integration_status: str | None = None
    permission_status: str | None = None
    health_status: str | None = None
    config: dict[str, Any] | None = None
    api_auth_requirements: str | None = None


class TestSourcePayload(BaseModel):
    sample_query_or_url: str | None = None


@router.get("")
def get_sources(
    category: str | None = None,
    status: str | None = None,
    access_method: str | None = None,
    country: str | None = None,
    search: str | None = None,
    enabled_only: bool = False,
    db: Session = Depends(get_db),
):
    """Lists registered global discovery sources with optional filters."""
    # Ensure registry is initialized in DB
    seed_or_sync_source_registry(db)

    sources, total_count = list_sources(
        db,
        category=category,
        status=status,
        access_method=access_method,
        q=search,
        is_enabled=True if enabled_only else None,
    )

    return {
        "total": total_count,
        "sources": [
            {
                "id": s.id,
                "name": s.name,
                "website_url": s.website_url,
                "source_category": s.source_category,
                "supported_industries": s.supported_industries,
                "supported_countries": s.supported_countries,
                "supported_event_types": s.supported_event_types,
                "access_method": s.access_method,
                "api_docs_url": s.api_docs_url,
                "api_auth_requirements": s.api_auth_requirements,
                "permission_status": s.permission_status,
                "integration_status": s.integration_status,
                "last_successful_execution": s.last_successful_execution.isoformat() if s.last_successful_execution else None,
                "last_error": s.last_error,
                "events_discovered": s.events_discovered,
                "events_extracted": s.events_extracted,
                "unique_events_discovered": s.unique_events_discovered,
                "health_status": s.health_status,
                "is_enabled": s.is_enabled,
                "config": s.config,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in sources
        ],
    }


@router.get("/stats")
def get_sources_stats(db: Session = Depends(get_db)):
    """Computes comprehensive metrics and breakdown across all registered sources."""
    seed_or_sync_source_registry(db)
    return get_registry_summary_stats(db)


@router.get("/{source_id}")
def get_source_details(source_id: str, db: Session = Depends(get_db)):
    """Fetches full configuration and history for a single source."""
    seed_or_sync_source_registry(db)
    s = get_source(db, source_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found")

    return {
        "id": s.id,
        "name": s.name,
        "website_url": s.website_url,
        "source_category": s.source_category,
        "supported_industries": s.supported_industries,
        "supported_countries": s.supported_countries,
        "supported_event_types": s.supported_event_types,
        "access_method": s.access_method,
        "api_docs_url": s.api_docs_url,
        "api_auth_requirements": s.api_auth_requirements,
        "permission_status": s.permission_status,
        "integration_status": s.integration_status,
        "last_successful_execution": s.last_successful_execution.isoformat() if s.last_successful_execution else None,
        "last_error": s.last_error,
        "events_discovered": s.events_discovered,
        "events_extracted": s.events_extracted,
        "unique_events_discovered": s.unique_events_discovered,
        "health_status": s.health_status,
        "is_enabled": s.is_enabled,
        "config": s.config,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.patch("/{source_id}")
def update_source_config(
    source_id: str,
    payload: UpdateSourcePayload,
    db: Session = Depends(get_db),
):
    """Updates enabled state, integration status, or credentials for a source."""
    seed_or_sync_source_registry(db)
    fields = payload.model_dump(exclude_unset=True)
    updated = update_source(db, source_id, fields)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found")

    return {
        "success": True,
        "source": {
            "id": updated.id,
            "name": updated.name,
            "is_enabled": updated.is_enabled,
            "integration_status": updated.integration_status,
            "health_status": updated.health_status,
            "config": updated.config,
        },
    }


@router.post("/{source_id}/health")
def probe_source_health(source_id: str, db: Session = Depends(get_db)):
    """Runs a live health probe with network latency measurement."""
    seed_or_sync_source_registry(db)
    result = adapter_manager.check_health(source_id, db=db)
    return result


@router.post("/{source_id}/test")
def test_source_extraction(
    source_id: str,
    payload: TestSourcePayload | None = None,
    db: Session = Depends(get_db),
):
    """Executes a real test probe against the source to verify event extraction."""
    seed_or_sync_source_registry(db)
    sample = payload.sample_query_or_url if payload else None
    result = adapter_manager.test_extraction(source_id, sample=sample, db=db)
    return result


@router.post("/sync")
def sync_sources(db: Session = Depends(get_db)):
    """Synchronizes registry definitions with master catalog."""
    res = seed_or_sync_source_registry(db)
    return {"success": True, "result": res}
