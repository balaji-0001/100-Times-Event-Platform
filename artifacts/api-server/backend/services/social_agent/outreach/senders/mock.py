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
        logger.info("MOCK email logged (NOT sent) -> %s | subject=%r | id=%s", recipient, subject, message_id)
        msg = "Not sent: SMTP is not configured. The message was only logged to the Outbox."
        record_outbox(recipient, subject, body, html, provider="mock", status="NOT_SENT", message_id=message_id)
        # Nothing reached an inbox, so this is not a success: callers must not
        # mark the message delivered (and block a real send later as a duplicate).
        return SendResult(
            success=False,
            message_id=None,
            message=msg,
        )
