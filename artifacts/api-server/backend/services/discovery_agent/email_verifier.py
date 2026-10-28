"""Organizer email verification and sanitization for 100 TIMES Discovery Agent.

Strictly enforces:
- Valid email format and syntax.
- Removal of whitespace and malformed values.
- Rejection of dummy/placeholder domains (example.com, test.com, domain.com, etc.).
- Rejection of asset/image filenames mistakenly captured as emails (.png, .jpg, etc.).
- Rejection of automated non-organizer mailboxes (noreply, do-not-reply, mailer-daemon, etc.).
- No synthesized or guessed emails.
"""

from email_validator import EmailNotValidError, validate_email
import re

_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

_DUMMY_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "test.com",
    "domain.com",
    "yourcompany.com",
    "yoursite.com",
    "sample.com",
    "placeholder.com",
    "sentry.io",
    "wixpress.com",
    "wix.com",
    "mysite.com",
    "fake.com",
    "temp.com",
    "invalid.com",
    "localhost",
    "linkedin.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "meta.com",
}

_ASSET_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".css",
    ".js",
    ".ico",
    ".tiff",
    ".bmp",
    ".woff",
    ".woff2",
    ".ttf",
)

_GENERIC_SYSTEM_LOCALS = {
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "mailer-daemon",
    "mailerdaemon",
    "abuse",
    "root",
    "postmaster",
    "webmaster",
    "daemon",
}


_PLACEHOLDER_LOCALS = {"name", "yourname", "your.name", "you", "your", "user", "username", "email", "youremail", "firstname.lastname", "john.doe", "jane.doe", "someone"}
_PLACEHOLDER_DOMAIN_LABELS = {"email", "mail", "domain", "company", "yourdomain", "yourcompany", "website", "example", "gmail"}


def is_valid_organizer_email(
    email: str | None,
    allow_test_domains: bool = True,
) -> tuple[bool, str | None, str | None]:
    """Validates an organizer email address according to 100 TIMES Discovery Rules.

    Returns:
        (is_valid: bool, normalized_email: str | None, failure_reason: str | None)
    """
    if not email or not isinstance(email, str):
        return False, None, "Email address is missing or empty"

    clean = email.strip()
    if not clean:
        return False, None, "Email address is empty or whitespace"

    if len(clean) > 254:
        return False, None, "Email address exceeds maximum permitted length"

    # Quick structural regex
    if not _EMAIL_REGEX.match(clean):
        return False, None, f"Malformed email format: {clean!r}"

    # Syntax validation using email_validator
    try:
        valid_info = validate_email(clean, check_deliverability=False, test_environment=allow_test_domains)
        normalized = valid_info.normalized.lower()
    except EmailNotValidError as exc:
        return False, None, f"Email syntax error: {exc}"

    domain = normalized.split("@", 1)[1].lower()
    local = normalized.split("@", 1)[0].lower()

    # Reject asset/image filename false matches
    if normalized.lower().endswith(_ASSET_EXTENSIONS):
        return False, None, "Email matches a static asset or image filename"

    # Reject placeholder / dummy domains
    if domain in _DUMMY_DOMAINS or any(domain.endswith("." + dummy) for dummy in _DUMMY_DOMAINS):  # incl. "o123.ingest.sentry.io"
        return False, None, f"Domain {domain!r} is an unverified placeholder or dummy domain"

    if not allow_test_domains and (domain.endswith(".test") or domain.endswith(".example") or domain.endswith(".invalid")):
        return False, None, f"Domain {domain!r} is a test-only domain"

    # Reject generic automated system mailboxes
    if local in _GENERIC_SYSTEM_LOCALS:
        return False, None, f"Generic automated mailbox ({local}) does not belong to the organizer or event team"

    # Form placeholders ("name@email.com", "you@domain.com") are not anyone's address.
    if local in _PLACEHOLDER_LOCALS and domain.split(".", 1)[0] in _PLACEHOLDER_DOMAIN_LABELS:
        return False, None, f"Placeholder address ({normalized}) from a form field, not a real mailbox"

    return True, normalized, None
