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
from backend.db import Base, engine, sync_schema_columns
from backend.routes import (
    acquisition,
    ai,
    auth,
    automations,
    community_discovery,
    community_promotion,
    dashboard,
    directories,
    discovery,
    discovery_sources,
    event_promotions,
    events,
    networking,
    observability,
    outreach,
    platform_ops,
    redirect,
    webhooks_n8n,
    workflow,
)
from backend.services.social_agent.scheduler import start_background_scheduler, stop_background_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Production deployments should run `alembic upgrade head`.  Local
    # development can opt in through .env so a fresh checkout is runnable.
    if settings.auto_create_schema:
        from backend import models  # noqa: F401 - registers all model metadata

        Base.metadata.create_all(bind=engine, checkfirst=True)
        sync_schema_columns(engine)
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
    print(f"  * Agent 1 discovery loop: running (every {settings.discovery_scan_interval_minutes}m, actual scans gated by the")
    print("    console's Dashboard toggle — off until an admin turns it on)")
    print(f"  * Agent 2 outreach loops: running (draft every {settings.outreach_scan_interval_minutes}m, follow-up")
    print("    sweep every {}m, both gated by the same Dashboard toggle — off until an admin turns it on)".format(settings.outreach_followup_interval_minutes))
    if settings.enable_background_scheduler:
        print(f"  * Legacy scheduler: ON  (attendee scan every {settings.attendee_scan_interval_minutes}m,")
        print(f"    organizer scan every {settings.organizer_scan_interval_minutes}m)")
    else:
        print("  * Legacy scheduler: OFF (ENABLE_BACKGROUND_SCHEDULER=false) — attendee/organizer scan stay off")
    print("=" * 60 + "\n")

    yield
    await stop_background_scheduler(scheduler_tasks)
    engine.dispose()


from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_FAVICON_PNG = _STATIC_DIR / "favicon.png"
_FAVICON_SVG = _STATIC_DIR / "favicon.svg"

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description="Production API for the 100 TIMES event discovery, networking, and management platform.",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json",
    lifespan=lifespan,
)
from backend.core.telemetry import TelemetryMiddleware
app.add_middleware(TelemetryMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=settings.cors_origins.strip() != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_REQUEST_BODY_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


@app.middleware("http")
async def security_headers_and_limits_middleware(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BODY_SIZE_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request entity too large. Maximum allowed size is 10MB."},
                )
        except ValueError:
            pass

    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: https:; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "connect-src 'self' https:; "
            "frame-ancestors 'none';"
        )

    return response



@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.png", include_in_schema=False)
def get_favicon_png():
    return FileResponse(_FAVICON_PNG, media_type="image/png")


@app.get("/favicon.svg", include_in_schema=False)
def get_favicon_svg():
    return FileResponse(_FAVICON_SVG, media_type="image/svg+xml")


@app.get("/docs", include_in_schema=False)
def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} — Swagger UI",
        swagger_favicon_url="/favicon.png?v=2",
    )


@app.get("/redoc", include_in_schema=False)
def custom_redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} — ReDoc",
        redoc_favicon_url="/favicon.png?v=2",
    )


@app.get("/", include_in_schema=False, response_class=HTMLResponse)
def backend_root():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>100 TIMES API Server</title>
  <link rel="icon" type="image/png" href="/favicon.png?v=2" />
  <link rel="icon" type="image/svg+xml" href="/favicon.svg?v=2" />
  <style>body{font-family:system-ui,sans-serif;background:#090d16;color:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}a{color:#38bdf8;text-decoration:none;margin:0 10px;font-weight:600}</style>
</head>
<body>
  <div style="text-align:center">
    <img src="/favicon.png?v=2" width="72" height="72" style="border-radius:50%" alt="100 TIMES" />
    <h1>100 TIMES API Server is Live</h1>
    <p><a href="/docs">Swagger Docs (/docs)</a> &bull; <a href="/redoc">ReDoc (/redoc)</a> &bull; <a href="/api/healthz">Health (/api/healthz)</a></p>
  </div>
</body>
</html>"""


@app.exception_handler(Exception)
async def unhandled_exception(_: Request, exc: Exception):
    from backend.core.telemetry import correlation_id_ctx
    cid = correlation_id_ctx.get()
    if settings.environment == "development":
        return JSONResponse(status_code=500, content={"error": str(exc), "correlationId": cid})
    return JSONResponse(status_code=500, content={"error": "Internal server error", "correlationId": cid})


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
app.include_router(discovery_sources.router)
app.include_router(workflow.router, prefix="/api")
app.include_router(automations.router, prefix="/api")
app.include_router(community_discovery.router, prefix="/api")
app.include_router(community_promotion.router, prefix="/api")
app.include_router(event_promotions.router, prefix="/api")
app.include_router(platform_ops.router, prefix="/api")
app.include_router(webhooks_n8n.router, prefix="/api")
app.include_router(observability.router, prefix="/api")
app.include_router(observability.public_metrics_router, prefix="/api")
app.include_router(observability.public_metrics_router)  # both /metrics and /api/metrics for Prometheus
app.include_router(redirect.router)  # no /api prefix: short /r/{id} tracking links


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

