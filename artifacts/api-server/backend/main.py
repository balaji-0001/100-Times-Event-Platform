import os
import sys
from pathlib import Path

# Ensure api-server directory is in sys.path regardless of where uvicorn is launched
_parent_dir = str(Path(__file__).resolve().parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.config import get_settings
from backend.db import Base, engine
from backend.routes import acquisition, ai, auth, dashboard, directories, discovery, events, networking, outreach, redirect, workflow
from backend.services.social_agent.scheduler import start_background_scheduler, stop_background_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Production deployments should run `alembic upgrade head`.  Local
    # development can opt in through .env so a fresh checkout is runnable.
    if settings.auto_create_schema:
        from backend import models  # noqa: F401 - registers all model metadata

        Base.metadata.create_all(bind=engine, checkfirst=True)
    if settings.seed_demo_data:
        from backend.seed import seed

        seed()

    scheduler_tasks = start_background_scheduler()

    print("\n" + "=" * 60)
    print("  [100 TIMES] Backend API Server is Live!")
    print("  " + "-" * 56)
    print("  * API Base:         http://127.0.0.1:8000")
    print("  * Interactive Docs: http://127.0.0.1:8000/docs")
    print("  * ReDoc:            http://127.0.0.1:8000/redoc")
    print("  * Health Check:     http://127.0.0.1:8000/api/healthz")
    print("  * OpenAPI Spec:     http://127.0.0.1:8000/openapi.json")
    print(f"  * Event discovery loop: running (every {settings.discovery_scan_interval_minutes}m, actual scans gated by the")
    print("    console's Dashboard toggle — off until an admin turns it on)")
    if settings.enable_background_scheduler:
        print(f"  * Legacy scheduler: ON  (attendee scan every {settings.attendee_scan_interval_minutes}m,")
        print(f"    organizer scan every {settings.organizer_scan_interval_minutes}m, follow-ups every {settings.outreach_followup_interval_minutes}m)")
    else:
        print("  * Legacy scheduler: OFF (ENABLE_BACKGROUND_SCHEDULER=false)")
    print("=" * 60 + "\n")

    yield
    await stop_background_scheduler(scheduler_tasks)
    engine.dispose()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description="Production API for the 100 TIMES event discovery, networking, and management platform.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=settings.cors_origins.strip() != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception(_: Request, exc: Exception):
    if settings.environment == "development":
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/api/healthz", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(directories.router, prefix="/api")
app.include_router(networking.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(acquisition.router, prefix="/api")
app.include_router(outreach.router, prefix="/api")
app.include_router(discovery.router, prefix="/api")
app.include_router(workflow.router, prefix="/api")
app.include_router(redirect.router)  # no /api prefix: short /r/{id} tracking links


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

