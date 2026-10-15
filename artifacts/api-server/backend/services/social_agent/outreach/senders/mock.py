"""Development/mock sender — used automatically whenever SMTP isn't
configured. Logs the message and registers it in the Outbox inspector so
it's visible and verifiable during local testing.
"""

import logging
import uuid

from backend.services.social_agent.outreach.senders.base import EmailProvider
from backend.services.social_agent.outreach.senders.outbox import record_outbox
from backend.services.social_agent.outreach.types import SendResult

logger = logging.getLogger("outreach.mock_sender")


class MockEmailProvider(EmailProvider):
    is_real = False

    def send_message(self, recipient: str, subject: str, body: str, html: str | None = None) -> SendResult:
        message_id = f"mock-{uuid.uuid4().hex[:12]}"
        logger.info("MOCK email logged -> %s | subject=%r | id=%s", recipient, subject, message_id)
        msg = "MOCK provider — logged to console & Outbox (SMTP not configured)."
        record_outbox(recipient, subject, body, html, provider="mock", status="MOCK_LOGGED", message_id=message_id)
        return SendResult(
            success=True,
            message_id=message_id,
            message=msg,
        )
