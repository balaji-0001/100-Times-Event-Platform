"""Development/mock sender — used automatically whenever SMTP isn't
configured. Never claims a real email was delivered; logs the message so
it's visible during local development and testing."""

import logging
import uuid

from backend.services.social_agent.outreach.senders.base import EmailProvider
from backend.services.social_agent.outreach.types import SendResult

logger = logging.getLogger("outreach.mock_sender")


class MockEmailProvider(EmailProvider):
    is_real = False

    def send_message(self, recipient: str, subject: str, body: str) -> SendResult:
        message_id = f"mock-{uuid.uuid4().hex[:12]}"
        logger.info("MOCK outreach email (not actually sent) -> %s | subject=%r | id=%s", recipient, subject, message_id)
        return SendResult(
            success=True,
            message_id=message_id,
            message="MOCK provider — no real email was sent (SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD not configured).",
        )
