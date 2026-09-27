"""Platform Connector Layer — discovery/read side only.

Publishing lives in a separate `PlatformPublisher` hierarchy
(`backend/services/social_agent/publishers/`) — a connector's job is
strictly discovery/read, never posting. This mirrors the real-world split:
a platform's read API and write API often have different auth scopes,
different approval requirements, and different failure modes.

Status vocabulary (see `status` property), used everywhere a connector's
state is surfaced (dashboard, API):
  REAL              - a real credential is configured and working
  MOCK              - no credential yet, but this connector can still
                      demonstrate the pipeline with curated sample data,
                      and going live needs no external platform approval
                      (just a credential you can obtain yourself)
  NOT_CONFIGURED    - no credential, no sample fallback, nothing to show
  APPROVAL_REQUIRED - going live needs the *platform's* sign-off first
                      (app review, commercial API approval, etc.) — adding
                      a credential alone would not be enough
  ERROR             - a credential is configured but the last connectivity
                      check failed (revoked/invalid token, etc.)
"""

from abc import ABC, abstractmethod
from typing import Any

from backend.core.config import get_settings
from backend.services.social_agent.types import Signal

STATUS_REAL = "REAL"
STATUS_MOCK = "MOCK"
STATUS_NOT_CONFIGURED = "NOT_CONFIGURED"
STATUS_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
STATUS_ERROR = "ERROR"


class PlatformConnector(ABC):
    platform: str = "base"
    description: str = ""

    # Set True on connectors whose real access requires the *platform's* own
    # manual review/approval (Reddit's Responsible Builder Policy, X's paid
    # API tiers, LinkedIn's Community Management API review, Meta's App
    # Review for Instagram) rather than just obtaining a credential.
    requires_approval: bool = False

    # Whether this connector has curated sample data to fall back on when no
    # credential is configured (lets the pipeline be demoed/tested without
    # requiring every platform to be live). Instagram is discovery-N/A by
    # design (content distribution only, see InstagramConnector), so it has
    # no mock discovery fallback either.
    has_mock_fallback: bool = True

    # Whether this platform even has a "discover public discussions" concept
    # for this connector. False only for Instagram.
    supports_discovery: bool = True

    @property
    def credential(self) -> str | None:
        """The credential env var configured for this platform, if any."""
        return None

    @property
    def is_live(self) -> bool:
        return bool(self.credential)

    @property
    def status(self) -> str:
        if self.is_live:
            check = self.validate_connection()
            return STATUS_REAL if check.get("connected", True) else STATUS_ERROR
        if self.requires_approval:
            return STATUS_APPROVAL_REQUIRED
        if self.has_mock_fallback:
            return STATUS_MOCK
        return STATUS_NOT_CONFIGURED

    def validate_connection(self) -> dict[str, Any]:
        """Best-effort live check of whether the configured credential
        actually works. Base implementation only reports credential
        presence — connectors with a cheap real API ping (e.g. Telegram's
        `getMe`) should override this with a real check."""
        if not self.is_live:
            return {"connected": False, "checked": False, "message": "No credential configured."}
        return {"connected": True, "checked": False, "message": "Credential present; no live connectivity check implemented for this connector."}

    def get_capabilities(self) -> dict[str, bool]:
        """Single source of truth for what this connector can actually do —
        never claims a capability the platform doesn't really support."""
        from backend.services.social_agent.publishers import get_publisher

        return {
            "discovery": self.supports_discovery,
            "read": self.supports_discovery,
            "search": self.supports_discovery,
            "publish": get_publisher(self.platform).is_real,
        }

    def get_community_rules(self, community) -> dict[str, Any]:
        """Community policy is DB-backed (verified/curated by us), not
        fetched live per-platform — every connector shares this."""
        from backend.services.acquisition_agent import CommunityRulesChecker

        return CommunityRulesChecker.check_rules(community)

    def get_post(self, external_id: str) -> dict[str, Any] | None:
        """Best-effort fetch of a single post by ID. Returns None when the
        platform doesn't support this (e.g. Telegram bots cannot fetch
        arbitrary historical messages outside of `getUpdates`) — never
        fabricates a result."""
        return None

    @abstractmethod
    def discover_signals(self) -> list[Signal]:
        """Return permitted, public signals for this platform.

        Mock connectors return curated sample data. A live connector calls
        the platform's official read API (public content only) and
        normalizes the results into `Signal` objects.
        """


def _settings_credential(attr: str) -> str | None:
    return getattr(get_settings(), attr, None) or None
