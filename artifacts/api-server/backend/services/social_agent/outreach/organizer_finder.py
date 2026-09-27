"""Organizer Finder — identifies a real, publicly-contactable organizer for
a discovered event.

Priority order, matching the architecture spec (4.5): official event website
-> official organizer website -> public company/organization page -> other
public professional profile. Concretely, this does up to TWO real, public
HTTP GETs — never an unbounded crawl:

  1. `event.url` (the registration/event page the AI extraction found in
     the source post) — parsed for schema.org JSON-LD `Event`/`Organization`
     structured data, a `mailto:` link or email address in the page text,
     and a `linkedin.com/company/...` or `linkedin.com/in/...` link.
  2. If step 1 finds an organizer website but no email, ONE follow-up GET to
     that organizer's own site (the "official organizer website" priority),
     parsed the same way for whatever contact info it publishes.

The fetch/parse logic itself lives in `services/social_agent/web_fetch.py`,
shared with the Event Discovery Agent's `discovery_agent/organizer_identifier.
py` (which generalizes this to more than 2 hops now that web search is
available) so the two don't maintain separate copies of the same scraping code.

Honesty limit, stated up front: this project has no web-search API
credential configured, so it cannot search "public organizer contact
information" or "public LinkedIn/company information" more broadly (spec
priorities 3-4) beyond the two pages above — that would require a search
API this project doesn't have. If nothing verifiable is found in those two
fetches, the event is honestly marked `organizer_not_found` rather than
fabricating a contact.
"""

from backend.services.social_agent.outreach.types import EventDetails, OrganizerContactInfo
from backend.services.social_agent.web_fetch import extract_contact, fetch


def find_organizer(event: EventDetails) -> OrganizerContactInfo:
    """Priority 1: the event's own page. Priority 2 (only if step 1 found an
    organizer website but no email): one follow-up fetch of that organizer's
    own site — see module docstring for the full priority rationale."""
    if not event.url:
        return OrganizerContactInfo(found=False)

    html = fetch(event.url)
    if not html:
        return OrganizerContactInfo(found=False, source_url=event.url)

    name, website, email, linkedin = extract_contact(html)

    if not email and website and website != event.url:
        organizer_html = fetch(website)
        if organizer_html:
            org_name, org_website, org_email, org_linkedin = extract_contact(organizer_html)
            name = name or org_name
            email = email or org_email
            linkedin = linkedin or org_linkedin
            website = org_website or website

    if not name:
        name = event.organizer_name_hint

    return OrganizerContactInfo(
        found=bool(email),
        name=name,
        email=email,
        website=website or event.url,
        linkedin=linkedin,
        source_url=event.url,
    )
