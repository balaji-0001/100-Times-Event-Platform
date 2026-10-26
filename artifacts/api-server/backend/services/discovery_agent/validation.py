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
    # Configurable rejection & quality filter rules
    reject_no_organizer: bool = False,
    require_organizer_phone: bool = False,
    require_organizer_website: bool = False,
    reject_past_events: bool = True,
    reject_unparseable_dates: bool = False,
    reject_missing_location: bool = False,
    reject_missing_ticket_url: bool = False,
    reject_unmatched_category: bool = False,
    fallback_to_other_sector: bool = False,
    min_title_length: int = 3,
    min_description_length: int = 0,
    min_confidence_score: int = 0,
    blacklisted_keywords: list[str] | None = None,
    excluded_domains: list[str] | None = None,
) -> ValidationResult:
    """Validates an event candidate against 100 TIMES event discovery rules.

    Configurable rejection rules:
    - Minimum title & description lengths.
    - Blacklisted keywords & excluded domain blocklists.
    - Category matching against supported 100 TIMES sectors.
    - Past/unparseable dates and custom date windows.
    - Missing location & missing ticket URLs.
    - Organizer requirements (identity, email, phone, website).
    - Minimum confidence threshold.
    """
    notes: list[str] = []

    # 0. Reject non-business consumer / social club activities
    NON_BUSINESS_NOISE = (
        "english class", "conversation club", "english conversation", "crazygames",
        "nightlife tour", "pub crawl", "pool party", "adhd meetup", "yoga retreat",
        "yogalates", "spiritual energy", "dating event", "speed dating", "bachelor party"
    )
    t_low = (candidate.name or "").lower()
    for nb_kw in NON_BUSINESS_NOISE:
        if nb_kw in t_low:
            return ValidationResult(
                "REJECTED",
                [f"Non-business consumer activity rejected: {nb_kw}"],
                0,
                None,
                rejection_reason="NON_BUSINESS_ACTIVITY",
            )

    # 1. Blacklisted keywords check (anti-spam / scam)
    if blacklisted_keywords:
        haystack = f"{candidate.name or ''} {candidate.event_description or ''}".lower()
        for kw in blacklisted_keywords:
            cleaned_kw = kw.strip().lower()
            if cleaned_kw and cleaned_kw in haystack:
                return ValidationResult(
                    "REJECTED",
                    [f"Event content matches blacklisted keyword {kw!r}."],
                    0,
                    None,
                    rejection_reason="BLACKLISTED_KEYWORD",
                )

    # 2. Excluded domains check
    if excluded_domains:
        urls_to_check: list[str] = []
        if candidate.url:
            urls_to_check.append(candidate.url)
        if candidate.ticket_url:
            urls_to_check.append(candidate.ticket_url)
        if candidate.primary_source and candidate.primary_source.url:
            urls_to_check.append(candidate.primary_source.url)
        for s in candidate.sources:
            if s.url:
                urls_to_check.append(s.url)

        for raw_url in urls_to_check:
            url_lower = raw_url.lower()
            for domain in excluded_domains:
                clean_domain = domain.strip().lower()
                if clean_domain and clean_domain in url_lower:
                    return ValidationResult(
                        "REJECTED",
                        [f"Event source or link matches excluded domain {domain!r}."],
                        0,
                        None,
                        rejection_reason="EXCLUDED_DOMAIN",
                    )

    # 3. Event title & min length
    if not candidate.name or not candidate.name.strip():
        return ValidationResult(
            "REJECTED",
            ["No event name could be extracted from the source page."],
            0,
            None,
            rejection_reason="MISSING_TITLE",
        )
    if min_title_length > 0 and len(candidate.name.strip()) < min_title_length:
        return ValidationResult(
            "REJECTED",
            [f"Event title {candidate.name!r} is shorter than minimum {min_title_length} characters."],
            0,
            None,
            rejection_reason="TITLE_TOO_SHORT",
        )

    # 4. Description min length (if present or required)
    if min_description_length > 0 and candidate.event_description:
        if len(candidate.event_description.strip()) < min_description_length:
            return ValidationResult(
                "REJECTED",
                [f"Event description is shorter than minimum {min_description_length} characters."],
                0,
                None,
                rejection_reason="DESCRIPTION_TOO_SHORT",
            )

    # 5. Upcoming date sanity & date parsing
    parsed_date = try_parse_date(candidate.date)
    if reject_unparseable_dates and parsed_date is None:
        return ValidationResult(
            "REJECTED",
            [f"Event date could not be parsed confidently from {candidate.date!r}."],
            0,
            None,
            rejection_reason="UNPARSEABLE_DATE",
        )

    if reject_past_events and parsed_date is not None and parsed_date < date.today():
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

    # 6. Category matching against supported categories
    category_unsupported = False
    if candidate.category:
        cat_clean = candidate.category.strip()
        if cat_clean.lower() in ("other", "none", "unknown"):
            if fallback_to_other_sector:
                candidate.category = "Other"
                notes.append("Event categorized under 'Other' sector.")
                category_unsupported = False
            else:
                category_unsupported = True
                notes.append(f"Event category {cat_clean!r} does not match any category listed on 100 TIMES — manual review required.")
        elif supported_categories and cat_clean not in supported_categories:
            if fallback_to_other_sector:
                candidate.category = "Other"
                notes.append(f"Event category {cat_clean!r} outside target sectors — assigned to 'Other' sector.")
                category_unsupported = False
            else:
                category_unsupported = True
                notes.append(f"Event category {cat_clean!r} is not among the supported categories on 100 TIMES — manual review required.")
    else:
        if fallback_to_other_sector:
            candidate.category = "Other"
            notes.append("No matching category identified — assigned to 'Other' sector.")
            category_unsupported = False
        else:
            category_unsupported = True
            notes.append("No matching category identified on 100 TIMES — manual review required.")

    if reject_unmatched_category and category_unsupported:
        return ValidationResult(
            "REJECTED",
            [f"Event category {candidate.category!r} is not among supported categories on 100 TIMES."],
            0,
            parsed_date,
            rejection_reason="UNMATCHED_CATEGORY",
        )

    # 7. Location verification
    if reject_missing_location:
        fmt = (candidate.event_format or "").strip().lower()
        if fmt not in ("online", "virtual") and not candidate.venue and not candidate.city:
            return ValidationResult(
                "REJECTED",
                ["In-person or hybrid event is missing both venue and city."],
                0,
                parsed_date,
                rejection_reason="MISSING_LOCATION",
            )

    # 8. Ticket URL verification
    if reject_missing_ticket_url and not candidate.ticket_url and not candidate.url:
        return ValidationResult(
            "REJECTED",
            ["Event is missing registration, ticket, or source URL."],
            0,
            parsed_date,
            rejection_reason="MISSING_TICKET_URL",
        )

    # 9. Organiser Details & Email/Phone/Website Validation
    if reject_no_organizer and (organizer is None or not organizer.found):
        return ValidationResult(
            "REJECTED",
            ["No identifiable organizer details found on the source page."],
            0,
            parsed_date,
            rejection_reason="MISSING_ORGANIZER",
        )

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

    if require_organizer_phone and organizer is not None and not organizer.phone:
        return ValidationResult(
            "REJECTED",
            ["Organizer phone number was not found."],
            0,
            parsed_date,
            rejection_reason="MISSING_ORGANIZER_PHONE",
        )

    if require_organizer_website and organizer is not None and not organizer.website:
        return ValidationResult(
            "REJECTED",
            ["Organizer official website was not found."],
            0,
            parsed_date,
            rejection_reason="MISSING_ORGANIZER_WEBSITE",
        )

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

    if min_confidence_score > 0 and confidence < min_confidence_score:
        return ValidationResult(
            "REJECTED",
            [f"Event confidence score ({confidence}) is below configured minimum threshold ({min_confidence_score})."],
            confidence,
            parsed_date,
            rejection_reason="LOW_CONFIDENCE",
        )

    if confidence < confidence_threshold or parsed_date is None or candidate.best_effort or category_unsupported or no_organizer_contact:
        status = "NEEDS_REVIEW"
    else:
        status = "VERIFIED"

    return ValidationResult(status, notes, confidence, parsed_date, rejection_reason=None)
