"""SMTP Configuration and Test Email Service.

Allows viewing, saving, and testing SMTP settings dynamically from the UI
and persists configuration to the project's .env file.
"""

import os
from pathlib import Path
from typing import Any

from backend.core.config import get_settings
from backend.services.social_agent.outreach.senders import (
    SMTPEmailProvider,
    _smtp_configured,
    get_email_provider,
    get_outbox,
    provider_status,
)


def _get_env_paths() -> list[Path]:
    api_server_dir = Path(__file__).resolve().parent.parent.parent
    root_dir = api_server_dir.parent
    paths = [
        api_server_dir / ".env",
        root_dir / ".env",
    ]
    return [p for p in paths if p.exists() or p.parent.exists()]


def get_smtp_info() -> dict[str, Any]:
    """Return public summary of SMTP configuration."""
    settings = get_settings()
    configured = _smtp_configured()
    status_dict = provider_status()

    return {
        "configured": configured,
        "status": status_dict["status"],
        "provider": status_dict["provider"],
        "host": settings.smtp_host or "",
        "port": settings.smtp_port or 587,
        "username": settings.smtp_username or "",
        "fromEmail": settings.smtp_from_email or "",
        "useTls": settings.smtp_use_tls,
        "hasPassword": bool(settings.smtp_password),
    }


def save_smtp_settings(
    host: str,
    port: int,
    username: str | None,
    password: str | None,
    from_email: str,
    use_tls: bool = True,
) -> dict[str, Any]:
    """Persist SMTP settings to .env and update the live runtime settings."""
    host = host.strip() if host else ""
    from_email = from_email.strip() if from_email else ""
    username = username.strip() if username else ""

    current_settings = get_settings()
    # Keep existing password if not supplied in update
    actual_password = password if (password is not None and password != "") else (current_settings.smtp_password or "")

    # 1. Update OS environment variables
    os.environ["SMTP_HOST"] = host
    os.environ["SMTP_PORT"] = str(port)
    os.environ["SMTP_USERNAME"] = username
    if actual_password:
        os.environ["SMTP_PASSWORD"] = actual_password
    elif "SMTP_PASSWORD" in os.environ and not actual_password:
        del os.environ["SMTP_PASSWORD"]
    os.environ["SMTP_FROM_EMAIL"] = from_email
    os.environ["SMTP_USE_TLS"] = "true" if use_tls else "false"

    # 2. Update .env files
    env_keys = {
        "SMTP_HOST": host,
        "SMTP_PORT": str(port),
        "SMTP_USERNAME": username,
        "SMTP_PASSWORD": actual_password,
        "SMTP_FROM_EMAIL": from_email,
        "SMTP_USE_TLS": "true" if use_tls else "false",
    }

    for env_path in _get_env_paths():
        try:
            lines: list[str] = []
            if env_path.exists():
                with open(env_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

            existing_keys_found = set()
            new_lines = []
            for line in lines:
                key_match = False
                for k, v in env_keys.items():
                    if line.startswith(f"{k}=") or line.startswith(f"# {k}="):
                        new_lines.append(f"{k}={v}\n")
                        existing_keys_found.add(k)
                        key_match = True
                        break
                if not key_match:
                    new_lines.append(line)

            # Append any keys that weren't already in .env
            remaining_keys = set(env_keys.keys()) - existing_keys_found
            if remaining_keys:
                if new_lines and not new_lines[-1].endswith("\n"):
                    new_lines.append("\n")
                new_lines.append("\n# SMTP Email Delivery Configuration\n")
                for k in sorted(remaining_keys):
                    new_lines.append(f"{k}={env_keys[k]}\n")

            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception:
            pass

    # 3. Clear settings cache so new requests load fresh config
    get_settings.cache_clear()

    return get_smtp_info()


def send_test_email(recipient: str, subject: str = "Test Email from 100 TIMES", body: str | None = None) -> dict[str, Any]:
    """Dispatch a test email using the currently configured provider."""
    recipient = recipient.strip()
    if not recipient:
        return {"success": False, "message": "Recipient email address is required."}

    settings = get_settings()
    test_body = body or (
        f"Hi,\n\n"
        f"This is a verified test email sent from the 100 TIMES Event Platform.\n"
        f"SMTP Server: {settings.smtp_host}:{settings.smtp_port}\n"
        f"From Address: {settings.smtp_from_email}\n"
        f"TLS Enabled: {settings.smtp_use_tls}\n\n"
        f"Your email delivery pipeline is working correctly."
    )

    provider = get_email_provider()
    result = provider.send_message(recipient, subject, test_body)

    return {
        "success": result.success,
        "message": result.message,
        "messageId": result.message_id,
        "provider": "smtp" if provider.is_real else "mock",
        "bounced": result.bounced,
    }

