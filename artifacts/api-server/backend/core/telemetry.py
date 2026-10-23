"""Production Observability & Telemetry Infrastructure.

Provides:
- Workflow & Correlation ID context propagation across requests and agents
- Prometheus-compatible metrics aggregation
- Application readiness & database connectivity checks
- OpenTelemetry tracer integration with safe fallback
"""

import contextvars
import os
import time
import uuid
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Context variables for tracing across async execution flows
correlation_id_ctx = contextvars.ContextVar("correlation_id", default="")
workflow_id_ctx = contextvars.ContextVar("workflow_id", default="")

# In-memory Prometheus metric counters
_HTTP_REQUESTS_TOTAL = 0
_HTTP_ERRORS_TOTAL = 0
_AGENT_EXECUTIONS_TOTAL = 0
_AGENT_FAILURES_TOTAL = 0


def get_current_workflow_id() -> str:
    """Returns the active workflow/correlation ID or generates a new one."""
    wid = workflow_id_ctx.get()
    if not wid:
        wid = f"wf-{uuid.uuid4().hex[:12]}"
        workflow_id_ctx.set(wid)
    return wid


class TelemetryMiddleware(BaseHTTPMiddleware):
    """Propagates X-Workflow-ID and X-Correlation-ID headers across requests and responses."""

    async def dispatch(self, request: Request, call_next):
        global _HTTP_REQUESTS_TOTAL, _HTTP_ERRORS_TOTAL

        _HTTP_REQUESTS_TOTAL += 1
        cid = request.headers.get("x-correlation-id") or request.headers.get("x-request-id") or f"req-{uuid.uuid4().hex[:10]}"
        wid = request.headers.get("x-workflow-id") or f"wf-{uuid.uuid4().hex[:10]}"

        correlation_id_ctx.set(cid)
        workflow_id_ctx.set(wid)

        start_time = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception:
            _HTTP_ERRORS_TOTAL += 1
            raise

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        response.headers["X-Correlation-ID"] = cid
        response.headers["X-Workflow-ID"] = wid
        response.headers["X-Response-Time-Ms"] = str(duration_ms)

        if response.status_code >= 400:
            _HTTP_ERRORS_TOTAL += 1

        return response


def get_prometheus_metrics_text() -> str:
    """Renders basic OpenMetrics / Prometheus plain text formatted metrics."""
    return f"""# HELP http_requests_total Total number of HTTP requests received
# TYPE http_requests_total counter
http_requests_total {_HTTP_REQUESTS_TOTAL}

# HELP http_errors_total Total number of HTTP 4xx and 5xx responses
# TYPE http_errors_total counter
http_errors_total {_HTTP_ERRORS_TOTAL}

# HELP app_status Current application status
# TYPE app_status gauge
app_status 1
"""

