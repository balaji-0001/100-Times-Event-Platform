"""Validation gate — decides whether a discovered event is trustworthy
enough to store as VERIFIED, needs a human to look at it (NEEDS_REVIEW), or
should be REJECTED outright, plus a 0-100 confidence score. Deliberately
narrow and honest: never invents a fact to make something pass, and an
unparseable/relative date is a review note, not an auto-reject — only a
*confidently parsed* past date is.
"""

from datetime import date, datetime

from email_validator import EmailNotValidError, validate_email

from backend.services.discovery_agent.email_verifier import is_valid_organizer_email
from backend.services.discovery_agent.text_extractor import parse_written_date
from backend.services.discovery_agent.types import ExtractedEventCandidate, OrganizerCandidate

_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y")


class ValidationResult(tuple):
    """Tuple subclass returning (status, notes, confidence, parsed_date)
    for seamless unpacking across all existing callers, while exposing
    .status, .notes, .confidence, .parsed_date, and .rejection_reason."""

    def __new__(
        cls,
        status: str,
        notes: list[str],
        confidence: int,
        parsed_date: date | None,
        rejection_reason: str | None = None,
    ):
        return super().__new__(cls, (status, notes, confidence, parsed_date))

    def __init__(
        self,
        status: str,
        notes: list[str],
        confidence: int,
        parsed_date: date | None,
        rejection_reason: str | None = None,
    ):
        self.status = status
        self.notes = notes
        self.confidence = confidence
        self.parsed_date = parsed_date
        self.rejection_reason = rejection_reason


def try_parse_date(raw: str | None) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    # ISO datetimes ("2026-11-17T09:00:00+05:30") and written ranges ("22nd - 24th Dec 2026").
    return parse_written_date(raw)


def validate_email_syntax(email: str | None) -> bool:
    if not email:
        return False
    try:
        validate_email(email, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


def validate_event(
    candidate: ExtractedEventCandidate,
    confidence_threshold: int,
    organizer: OrganizerCandidate | None = None,
    require_organizer_email: bool = True,
    supported_categories: list[str] | tuple[str, ...] | None = None,
    date_from: date | str | None = None,
    date_to: date | str | None = None,
) -> ValidationResult:
    """Validates an event candidate against 100 TIMES event discovery rules.

    Mandatory Rules:
    - Non-empty event title.
    - Category matching an active category listed on 100 TIMES.
    - Upcoming event date (past events rejected).
    - Mandatory organizer email address (if require_organizer_email=True):
      IF organizer_email is missing OR invalid OR unverified -> REJECT.
      A contact form, phone number, social profile, or website URL alone
      does not satisfy this requirement.
    """
    notes: list[str] = []

    # 1. Event title
    if not candidate.name or not candidate.name.strip():
        return ValidationResult(
            "REJECTED",
            ["No event name could be extracted from the source page."],
            0,
            None,
            rejection_reason="MISSING_TITLE",
        )

    # 2. Upcoming date sanity & optional date window
    parsed_date = try_parse_date(candidate.date)
    if parsed_date is not None and parsed_date < date.today():
        return ValidationResult(
            "REJECTED",
            [f"Extracted event date ({candidate.date}) is in the past."],
            0,
            parsed_date,
            rejection_reason="PAST_OR_EXPIRED",
        )

    if parsed_date is not None:
        if date_from:
            parsed_df = try_parse_date(date_from) if isinstance(date_from, str) else date_from
            if parsed_df and parsed_date < parsed_df:
                return ValidationResult(
                    "REJECTED",
                    [f"Event date ({candidate.date}) is before the target start date ({date_from})."],
                    0,
                    parsed_date,
                    rejection_reason="OUT_OF_DATE_RANGE",
                )
        if date_to:
            parsed_dt = try_parse_date(date_to) if isinstance(date_to, str) else date_to
            if parsed_dt and parsed_date > parsed_dt:
                return ValidationResult(
                    "REJECTED",
                    [f"Event date ({candidate.date}) is after the target end date ({date_to})."],
                    0,
                    parsed_date,
                    rejection_reason="OUT_OF_DATE_RANGE",
                )

    # 3. Category matching against supported categories
    category_unsupported = False
    if candidate.category:
        cat_clean = candidate.category.strip()
        if cat_clean.lower() in ("other", "none", "unknown"):
            category_unsupported = True
            notes.append(f"Event category {cat_clean!r} does not match any category listed on 100 TIMES — manual review required.")
        elif supported_categories and cat_clean not in supported_categories:
            category_unsupported = True
            notes.append(f"Event category {cat_clean!r} is not among the supported categories on 100 TIMES — manual review required.")
    else:
        category_unsupported = True
        notes.append("No matching category identified on 100 TIMES — manual review required.")

    # 4. Mandatory Organiser Details & Email Validation
    if require_organizer_email and organizer is not None:
        if not organizer.found or not organizer.email:
            email_notes = ["Missing valid public organizer email address — public organizer email is mandatory."]
            if organizer.phone and not organizer.email:
                email_notes.append("Phone number was found, but a phone number alone does not satisfy the mandatory organizer email requirement.")
            return ValidationResult(
                "REJECTED",
                email_notes,
                0,
                parsed_date,
                rejection_reason="MISSING_ORGANIZER_EMAIL",
            )

        is_valid, norm_email, err = is_valid_organizer_email(organizer.email)
        if not is_valid:
            return ValidationResult(
                "REJECTED",
                [f"Invalid or unverified organizer email ({organizer.email}): {err}."],
                0,
                parsed_date,
                rejection_reason="INVALID_ORGANIZER_EMAIL",
            )
        organizer.email = norm_email

    # Date parse guidance for non-rejected events
    if parsed_date is None and candidate.date:
        notes.append(f"Could not confidently parse the event date ({candidate.date!r}) — verify manually.")
    elif parsed_date is None:
        notes.append("No event date was found on the source page — verify manually before publishing.")

    # Confidence scoring
    confidence = candidate.extraction_confidence
    if candidate.venue:
        confidence += 5
    if candidate.city:
        confidence += 5
    if candidate.ticket_url:
        confidence += 5
    if not candidate.city and not candidate.venue:
        notes.append("No venue or city found — location could not be confirmed.")
    confidence = max(0, min(confidence, 100))

    if candidate.best_effort:
        notes.append("Read from the page text by fixed rules (the page has no structured event data) — check every field.")

    # Legacy contact check when require_organizer_email is False
    no_organizer_contact = False
    if not require_organizer_email:
        no_organizer_contact = organizer is not None and not (organizer.found and (organizer.email or organizer.phone))
        if no_organizer_contact:
            confidence = max(0, confidence - 15)
            notes.append("No organizer contact (email or phone) was found — this event can't be used for outreach until one is.")

    if confidence < confidence_threshold or parsed_date is None or candidate.best_effort or category_unsupported or no_organizer_contact:
        status = "NEEDS_REVIEW"
    else:
        status = "VERIFIED"

    return ValidationResult(status, notes, confidence, parsed_date, rejection_reason=None)
