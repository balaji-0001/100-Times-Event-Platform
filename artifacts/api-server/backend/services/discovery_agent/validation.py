"""Validation gate — decides whether a discovered event is trustworthy
enough to store as VERIFIED, needs a human to look at it (NEEDS_REVIEW), or
should be REJECTED outright, plus a 0-100 confidence score. Deliberately
narrow and honest: never invents a fact to make something pass, and an
unparseable/relative date is a review note, not an auto-reject — only a
*confidently parsed* past date is.
"""

from datetime import date, datetime

from email_validator import EmailNotValidError, validate_email

from backend.services.discovery_agent.types import ExtractedEventCandidate

_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y")


def try_parse_date(raw: str | None) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def validate_email_syntax(email: str | None) -> bool:
    if not email:
        return False
    try:
        validate_email(email, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


def validate_event(candidate: ExtractedEventCandidate, confidence_threshold: int) -> tuple[str, list[str], int, date | None]:
    """Returns (verification_status, notes, confidence_score, parsed_event_date)."""
    notes: list[str] = []

    if not candidate.name:
        return "REJECTED", ["No event name could be extracted from the source page."], 0, None

    parsed_date = try_parse_date(candidate.date)
    if parsed_date is not None and parsed_date < date.today():
        return "REJECTED", [f"Extracted event date ({candidate.date}) is in the past."], 0, parsed_date

    if parsed_date is None and candidate.date:
        notes.append(f"Could not confidently parse the event date ({candidate.date!r}) — verify manually.")
    elif parsed_date is None:
        notes.append("No event date was found on the source page — verify manually before publishing.")

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

    if confidence < confidence_threshold or parsed_date is None:
        status = "NEEDS_REVIEW"
    else:
        status = "VERIFIED"

    return status, notes, confidence, parsed_date
