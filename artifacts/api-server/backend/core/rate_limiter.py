"""Rate Limiting module for authentication endpoints and sensitive actions.

Protects against credential stuffing, brute force, and automated registration attacks
following OWASP ASVS v4.0.3 Chapter 2 & 13.
"""

from collections import defaultdict
import time
from threading import Lock
from fastapi import HTTPException, Request, status

from backend.core.config import get_settings


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window rate limiter keyed by client identifier."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """Check if request is allowed. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            # Purge timestamps outside the current window
            valid_timestamps = [t for t in self._history[key] if t > cutoff]
            self._history[key] = valid_timestamps

            if len(valid_timestamps) >= self.max_requests:
                oldest_in_window = valid_timestamps[0]
                retry_after = max(1, int(oldest_in_window + self.window_seconds - now))
                return False, retry_after

            self._history[key].append(now)
            return True, 0

    def reset(self, key: str | None = None) -> None:
        """Reset rate limiter state (useful for test isolation)."""
        with self._lock:
            if key is None:
                self._history.clear()
            else:
                self._history.pop(key, None)


# Default instance for auth endpoints (10 attempts per minute per IP)
auth_rate_limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)


def rate_limit_auth(request: Request) -> None:
    """FastAPI dependency to rate limit login/registration requests."""
    settings = get_settings()
    if settings.environment.lower() == "test":
        return

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    key = f"{client_ip}:{request.url.path}"
    allowed, retry_after = auth_rate_limiter.is_allowed(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many attempts. Please try again after {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

