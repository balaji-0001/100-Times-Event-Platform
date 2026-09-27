from backend.core.config import get_settings
from backend.services.social_agent.outreach.senders.base import EmailProvider
from backend.services.social_agent.outreach.senders.mock import MockEmailProvider
from backend.services.social_agent.outreach.senders.smtp import SMTPEmailProvider

__all__ = ["EmailProvider", "MockEmailProvider", "SMTPEmailProvider", "get_email_provider", "provider_status"]


def _smtp_configured() -> bool:
    settings = get_settings()
    return bool(settings.smtp_host and settings.smtp_username and settings.smtp_password and settings.smtp_from_email)


def get_email_provider() -> EmailProvider:
    if _smtp_configured():
        return SMTPEmailProvider()
    return MockEmailProvider()


def provider_status() -> dict[str, str]:
    """Same REAL/NOT_CONFIGURED honesty vocabulary used by
    `PlatformConnector.status` — surfaced on the outreach stats endpoint so
    the dashboard never silently pretends emails are really being sent."""
    if _smtp_configured():
        return {"provider": "smtp", "status": "REAL"}
    return {"provider": "mock", "status": "NOT_CONFIGURED"}
