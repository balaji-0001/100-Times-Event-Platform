"""Rate Limiting module for authentication endpoints and sensitive actions.

Protects against credential stuffing, brute force, and automated registration attacks
following OWASP ASVS v4.0.3 Chapter 2 & 13.

The client is identified by the socket peer address. `X-Forwarded-For` is a
client-controlled header, so it is only consulted when the direct peer is one
of the reverse proxies listed in the TRUSTED_PROXY_IPS setting.
"""

from collections import OrderedDict
from collections.abc import Callable
import time
from threading import Lock
from fastapi import HTTPException, Request, status

from backend.core.config import get_settings


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window rate limiter keyed by client identifier.

    Memory is bounded: keys whose timestamps have all left the window are
    pruned, and at most `max_keys` keys are tracked (least recently used keys
    are evicted first)."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60, max_keys: int = 10_000, clock: Callable[[], float] = time.monotonic):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._history: "OrderedDict[str, list[float]]" = OrderedDict()
        self._lock = Lock()
        self._clock = clock
        self._last_prune = clock()

    def _prune(self, now: float) -> None:
        """Drop keys with no timestamps inside the window (caller holds the lock)."""
        cutoff = now - self.window_seconds
        stale = [key for key, stamps in self._history.items() if not stamps or stamps[-1] <= cutoff]
        for key in stale:
            del self._history[key]
        self._last_prune = now

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """Check if request is allowed. Returns (allowed, retry_after_seconds)."""
        now = self._clock()
        cutoff = now - self.window_seconds

        with self._lock:
            # Periodic sweep of idle keys; the max_keys LRU cap below bounds
            # memory between sweeps even under a flood of distinct addresses.
            if now - self._last_prune >= self.window_seconds:
                self._prune(now)

            # Purge timestamps outside the current window
            valid_timestamps = [t for t in self._history.get(key, ()) if t > cutoff]

            if len(valid_timestamps) >= self.max_requests:
                self._history[key] = valid_timestamps
                self._history.move_to_end(key)
                oldest_in_window = valid_timestamps[0]
                retry_after = max(1, int(oldest_in_window + self.window_seconds - now))
                return False, retry_after

            valid_timestamps.append(now)
            self._history[key] = valid_timestamps
            self._history.move_to_end(key)
            while len(self._history) > self.max_keys:
                self._history.popitem(last=False)
            return True, 0

    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._history)

    def reset(self, key: str | None = None) -> None:
        """Reset rate limiter state (useful for test isolation)."""
        with self._lock:
            if key is None:
                self._history.clear()
            else:
                self._history.pop(key, None)


# Default instance for auth endpoints (10 attempts per minute per IP)
auth_rate_limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)


def _trusted_proxies() -> set[str]:
    raw = get_settings().trusted_proxy_ips or ""
    return {item.strip() for item in raw.split(",") if item.strip()}


def client_ip_for(request: Request) -> str:
    """The address to rate-limit on.

    Uses the socket peer (`request.client.host`). Only when that peer is a
    configured trusted proxy is `X-Forwarded-For` read — right to left,
    skipping the trusted proxies themselves — so a client cannot pick its own
    rate-limit bucket by sending a forged header."""
    peer = request.client.host if request.client else "unknown"
    trusted = _trusted_proxies()
    if not trusted or peer not in trusted:
        return peer
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return peer
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    for hop in reversed(hops):
        if hop not in trusted:
            return hop
    return peer


def rate_limit_auth(request: Request) -> None:
    """FastAPI dependency to rate limit login/registration requests."""
    settings = get_settings()
    if settings.environment.lower() == "test":
        return

    key = f"{client_ip_for(request)}:{request.url.path}"
    allowed, retry_after = auth_rate_limiter.is_allowed(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many attempts. Please try again after {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
