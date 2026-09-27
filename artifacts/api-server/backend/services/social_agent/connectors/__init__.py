from backend.services.social_agent.connectors.base import PlatformConnector
from backend.services.social_agent.connectors.discord import DiscordConnector
from backend.services.social_agent.connectors.instagram import InstagramConnector
from backend.services.social_agent.connectors.linkedin import LinkedInConnector
from backend.services.social_agent.connectors.reddit import RedditConnector
from backend.services.social_agent.connectors.telegram import TelegramConnector
from backend.services.social_agent.connectors.x import XConnector

CONNECTOR_REGISTRY: dict[str, type[PlatformConnector]] = {
    RedditConnector.platform: RedditConnector,
    DiscordConnector.platform: DiscordConnector,
    TelegramConnector.platform: TelegramConnector,
    XConnector.platform: XConnector,
    LinkedInConnector.platform: LinkedInConnector,
    InstagramConnector.platform: InstagramConnector,
}


def get_connector(platform: str) -> PlatformConnector:
    connector_cls = CONNECTOR_REGISTRY.get(platform)
    if not connector_cls:
        raise ValueError(f"No connector registered for platform '{platform}'")
    return connector_cls()


def all_connectors() -> list[PlatformConnector]:
    return [cls() for cls in CONNECTOR_REGISTRY.values()]
