"""Real email sender via SMTP (stdlib smtplib — works with any SMTP relay:
Gmail app passwords, SendGrid, Mailgun, Brevo, AWS SES, Resend, or local mail servers).
Credentials only ever come from environment variables or administrative settings.
"""

from email.message import EmailMessage
import logging
import smtplib
import socket
import ssl
import uuid

from backend.core.config import get_settings
from backend.services.social_agent.outreach.senders.base import EmailProvider
from backend.services.social_agent.outreach.senders.outbox import record_outbox
from backend.services.social_agent.outreach.types import SendResult

logger = logging.getLogger("outreach.smtp_sender")


class SMTPEmailProvider(EmailProvider):
    is_real = True

    @staticmethod
    def test_connection(
        host: str,
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        timeout: int = 10,
    ) -> tuple[bool, str]:
        """Test SMTP connection, TLS handshake, and credentials without sending an email."""
        if not host:
            return False, "SMTP Host is required."
        try:
            if port == 465:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(host, port, context=context, timeout=timeout) as server:
                    server.ehlo()
                    if username and password:
                        server.login(username, password)
                    return True, f"Connected to {host}:{port} via SSL successfully."
            else:
                with smtplib.SMTP(host, port, timeout=timeout) as server:
                    server.ehlo()
                    if use_tls and server.has_extn("STARTTLS"):
                        context = ssl.create_default_context()
                        server.starttls(context=context)
                        server.ehlo()
                    if username and password:
                        server.login(username, password)
                    return True, f"Connected to {host}:{port} via STARTTLS successfully."
        except smtplib.SMTPAuthenticationError as exc:
            err_msg = exc.smtp_error.decode() if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error)
            return False, f"Authentication failed: {err_msg}"
        except smtplib.SMTPConnectError as exc:
            return False, f"Could not connect to {host}:{port}: {exc}"
        except (socket.timeout, TimeoutError):
            return False, f"Connection to {host}:{port} timed out after {timeout}s."
        except Exception as exc:
            return False, f"SMTP error: {exc}"

    def send_message(self, recipient: str, subject: str, body: str, html: str | None = None) -> SendResult:
        settings = get_settings()
        if not (settings.smtp_host and settings.smtp_from_email):
            err = "SMTP is not fully configured (missing SMTP_HOST or SMTP_FROM_EMAIL)."
            record_outbox(recipient, subject, body, html, provider="smtp", status="FAILED", error=err)
            return SendResult(success=False, message=err)

        message = EmailMessage()
        message["From"] = settings.smtp_from_email
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        if html:
            message.add_alternative(html, subtype="html")

        message_id = f"<{uuid.uuid4().hex}@100times.in>"
        message["Message-ID"] = message_id

        port = settings.smtp_port or 587
        use_tls = settings.smtp_use_tls

        try:
            if port == 465:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(settings.smtp_host, port, context=context, timeout=15) as server:
                    server.ehlo()
                    if settings.smtp_username and settings.smtp_password:
                        server.login(settings.smtp_username, settings.smtp_password)
                    server.send_message(message)
            else:
                with smtplib.SMTP(settings.smtp_host, port, timeout=15) as server:
                    server.ehlo()
                    if use_tls and server.has_extn("STARTTLS"):
                        context = ssl.create_default_context()
                        server.starttls(context=context)
                        server.ehlo()
                    if settings.smtp_username and settings.smtp_password:
                        server.login(settings.smtp_username, settings.smtp_password)
                    server.send_message(message)

            record_outbox(recipient, subject, body, html, provider="smtp", status="DELIVERED", message_id=message_id)
            return SendResult(success=True, message_id=message_id, message="Delivered via SMTP.")

        except smtplib.SMTPRecipientsRefused as exc:
            err = f"Recipient refused (bounced): {exc}"
            record_outbox(recipient, subject, body, html, provider="smtp", status="BOUNCED", error=err)
            return SendResult(success=False, bounced=True, message=err)
        except smtplib.SMTPAuthenticationError as exc:
            err = f"SMTP Authentication failed: {exc}"
            record_outbox(recipient, subject, body, html, provider="smtp", status="FAILED", error=err)
            return SendResult(success=False, message=err)
        except (smtplib.SMTPException, OSError) as exc:
            err = f"SMTP send failed: {exc}"
            record_outbox(recipient, subject, body, html, provider="smtp", status="FAILED", error=err)
            return SendResult(success=False, message=err)
