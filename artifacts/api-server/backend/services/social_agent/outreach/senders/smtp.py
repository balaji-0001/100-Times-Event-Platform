"""Real email sender via SMTP (stdlib `smtplib` — no new third-party
dependency, works with any SMTP relay: Gmail app passwords, SendGrid/
Mailgun/Resend's own SMTP relays, a self-hosted mail server, etc.).
Credentials only ever come from environment variables (`.env`), never
hardcoded.

Honesty limit, stated up front: plain SMTP gives exactly ONE synchronous
signal — whether the receiving server accepted the message at handshake
time. There is no webhook/async channel here for real delivery
confirmation, bounce notifications that arrive later, or open tracking —
those require a transactional ESP (SendGrid/Postmark/Resend/SES) with a
webhook, which this project deliberately doesn't integrate. The one real
signal this CAN observe is `SMTPRecipientsRefused` — the server rejecting
the recipient address outright — treated as a bounce (`SendResult.bounced
= True`); every other SMTP/network error is a generic, retryable failure.
"""

import smtplib
import uuid
from email.message import EmailMessage

from backend.core.config import get_settings
from backend.services.social_agent.outreach.senders.base import EmailProvider
from backend.services.social_agent.outreach.types import SendResult


class SMTPEmailProvider(EmailProvider):
    is_real = True

    def send_message(self, recipient: str, subject: str, body: str) -> SendResult:
        settings = get_settings()
        if not (settings.smtp_host and settings.smtp_username and settings.smtp_password and settings.smtp_from_email):
            return SendResult(success=False, message="SMTP is not fully configured.")

        message = EmailMessage()
        message["From"] = settings.smtp_from_email
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        message_id = f"<{uuid.uuid4().hex}@100times.in>"
        message["Message-ID"] = message_id

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(message)
        except smtplib.SMTPRecipientsRefused as exc:
            return SendResult(success=False, bounced=True, message=f"Recipient refused (bounced): {exc}")
        except (smtplib.SMTPException, OSError) as exc:
            return SendResult(success=False, message=f"SMTP send failed: {exc}")

        return SendResult(success=True, message_id=message_id, message="Sent via SMTP.")
