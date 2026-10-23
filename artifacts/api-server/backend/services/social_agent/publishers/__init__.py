from backend.services.social_agent.publishers.base import PlatformPublisher
from backend.services.social_agent.publishers.discord import DiscordPublisher
from backend.services.social_agent.publishers.discord_user import DiscordUserPublisher
from backend.services.social_agent.publishers.facebook import FacebookPublisher
from backend.services.social_agent.publishers.instagram import InstagramPublisher
from backend.services.social_agent.publishers.linkedin import LinkedInPublisher
from backend.services.social_agent.publishers.stub import StubPublisher
from backend.services.social_agent.publishers.telegram import TelegramPublisher
from backend.services.social_agent.publishers.telegram_user import TelegramUserPublisher

# Platforms where going live needs the *platform's* own approval (app
# review, commercial API access) rather than just a credential — mirrors
# `PlatformConnector.requires_approval` for each platform.
_APPROVAL_REQUIRED_PLATFORMS = {"reddit", "x"}

_REAL_PUBLISHERS: dict[str, type[PlatformPublisher]] = {
    "telegram": TelegramPublisher,
    "discord": DiscordPublisher,
    "discord_user": DiscordUserPublisher,
    "telegram_user": TelegramUserPublisher,
    "facebook": FacebookPublisher,
    "instagram": InstagramPublisher,
    "linkedin": LinkedInPublisher,
}


def get_publisher(platform: str) -> PlatformPublisher:
    if platform in _REAL_PUBLISHERS:
        return _REAL_PUBLISHERS[platform]()
    return StubPublisher(platform, requires_approval=platform in _APPROVAL_REQUIRED_PLATFORMS)
