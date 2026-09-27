from backend.services.social_agent.connectors.base import PlatformConnector, _settings_credential
from backend.services.social_agent.types import Signal


class InstagramConnector(PlatformConnector):
    """Instagram is a Content Distribution Agent, not a discussion-discovery platform.

    It never scans other people's posts for intent — instead it turns 100.com's
    own event catalog into proactive content (captions, carousels, reels)
    that a human reviews and (once approved) publishes through the official
    Instagram Graph API.
    """

    platform = "instagram"
    description = "Content distribution only — generates posts from 100.com's own event catalog."
    requires_approval = True  # Meta App Review required for instagram_content_publish
    has_mock_fallback = False
    supports_discovery = False

    @property
    def credential(self) -> str | None:
        return _settings_credential("instagram_access_token")

    def discover_signals(self) -> list[Signal]:
        return []
