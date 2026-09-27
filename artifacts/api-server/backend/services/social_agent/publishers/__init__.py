from backend.services.social_agent.publishers.base import PlatformPublisher
from backend.services.social_agent.publishers.discord import DiscordPublisher
from backend.services.social_agent.publishers.stub import StubPublisher
from backend.services.social_agent.publishers.telegram import TelegramPublisher

# Platforms where going live needs the *platform's* own approval (app
# review, commercial API access) rather than just a credential — mirrors
# `PlatformConnector.requires_approval` for each platform.
_APPROVAL_REQUIRED_PLATFORMS = {"reddit", "x", "linkedin", "instagram"}

_REAL_PUBLISHERS: dict[str, type[PlatformPublisher]] = {
    "telegram": TelegramPublisher,
    "discord": DiscordPublisher,
}


def get_publisher(platform: str) -> PlatformPublisher:
    if platform in _REAL_PUBLISHERS:
        return _REAL_PUBLISHERS[platform]()
    return StubPublisher(platform, requires_approval=platform in _APPROVAL_REQUIRED_PLATFORMS)
