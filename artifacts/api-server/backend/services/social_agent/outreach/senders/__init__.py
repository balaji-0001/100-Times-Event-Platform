from backend.core.config import get_settings
from backend.services.social_agent.outreach.senders.base import EmailProvider
from backend.services.social_agent.outreach.senders.mock import MockEmailProvider
from backend.services.social_agent.outreach.senders.outbox import clear_outbox, get_outbox, record_outbox
from backend.services.social_agent.outreach.senders.smtp import SMTPEmailProvider

__all__ = [
    "EmailProvider",
    "MockEmailProvider",
    "SMTPEmailProvider",
    "get_email_provider",
    "provider_status",
    "record_outbox",
    "get_outbox",
    "clear_outbox",
]


def _smtp_configured() -> bool:
    settings = get_settings()
    has_host = bool(settings.smtp_host and settings.smtp_host.strip())
    has_from = bool(settings.smtp_from_email and settings.smtp_from_email.strip())
    is_local = (settings.smtp_host in ("localhost", "127.0.0.1")) or (settings.smtp_port in (1025, 8025))
    has_creds = bool(settings.smtp_username and settings.smtp_password)
    return has_host and has_from and (has_creds or is_local)


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
