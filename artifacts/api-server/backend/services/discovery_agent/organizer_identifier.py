"""Organizer Identifier — generalizes Organizer Outreach's
`outreach/organizer_finder.py` 2-hop lookup to more hops, since the Event
Discovery Agent has a real web-search tool available (`organizer_finder.py`
is capped at 2 hops specifically because *it* has no search API).

Follows the priority chain from the spec: event page -> organizer/host link
-> organizer's own official site -> a contact page on that site. Every hop
that actually gets fetched is recorded as a `CandidateSource` so the final
`event_sources`/evidence trail shows exactly where each contact detail came
from — this never fabricates a contact "found" on a page that wasn't
actually read.
"""

import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from backend.services.discovery_agent.email_verifier import is_valid_organizer_email
from backend.services.discovery_agent.platforms import is_platform_url, same_host
from backend.services.discovery_agent.types import CandidateSource, ExtractedEventCandidate, OrganizerCandidate
from backend.services.social_agent.browser_fetch import browser_fetch_enabled
from backend.services.social_agent.web_fetch import (
    extract_contact,
    extract_social_links,
    fetch,
    find_emails,
    find_labelled_organizer,
    find_phone,
    json_ld_organizer_details,
    visible_text,
)

logger = logging.getLogger("discovery_agent.organizer_identifier")
_MAX_HOPS = 4  # pages read per lookup: the event page + 3 follow-ups
# Optional headless-browser reads per lookup, only after the plain reads found no e-mail.
_MAX_RENDERS = 2
_CONTACT_LINKS_PER_PAGE = 4
# Pages that carry an organizer's contact details, most useful first.
_CONTACT_LINK_HINTS = (
    ("contact", "kontakt", "contacto", "contatti", "reach-us", "get-in-touch", "enquir", "inquir"),
    ("impressum", "imprint", "legal-notice", "mentions-legales", "aviso-legal"),
    ("organiser", "organizer", "organisator", "veranstalter"),
    ("about", "ueber-uns", "uber-uns", "who-we-are", "our-team"),
)
_SKIP_LINK_HINTS = ("login", "log-in", "signin", "sign-in", "signup", "sign-up", "/user", "account", "cart", "checkout", "privacy", "cookie",
                    "terms", "share", "subscribe", "archive", "javascript:", ".pdf", ".jpg", ".png", ".zip")
# Hosts that are never an organizer's own site.
_NOT_ORGANIZER_HOSTS = ("google.", "goo.gl", "doubleclick.", "cloudflare.", "cookie", "trustpilot", "w3.org", "schema.org", "youtube.", "youtu.be",
                        "discord.", "t.me", "wa.me", "whatsapp.", "apple.com", "play.google", "bit.ly", "tiktok.", "vimeo.", "flickr.", "pinterest.")
_OFFICIAL_LINK_HINTS = ("official", "website", "homepage", "organizer", "organiser", "organised by", "organized by", "hosted by", "visit site")

_ORGANIZER_TYPE_BY_SOURCE_TYPE = {
    "college_page": "college",
    "government": "government",
    "trade_association": "association",
}


def _page_key(url: str) -> str:
    """One key per page however it's spelled: http/https, www or not, trailing slash."""
    parsed = urlparse(url)
    key = (parsed.netloc or "").lower().removeprefix("www.") + parsed.path.rstrip("/")
    return f"{key}?{parsed.query}" if parsed.query else key


def _site_root(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"


def _contact_page_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Same-site Contact / Imprint / Organizer / About pages, most useful first."""
    tiers: list[list[str]] = [[] for _ in _CONTACT_LINK_HINTS]
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        haystack = f"{href.lower()} {(anchor.get_text() or '').strip().lower()}"
        if any(skip in href.lower() for skip in _SKIP_LINK_HINTS):
            continue
        tier = next((i for i, hints in enumerate(_CONTACT_LINK_HINTS) if any(hint in haystack for hint in hints)), None)
        if tier is None:
            continue
        absolute = urljoin(base_url, href).split("#", 1)[0]
        if urlparse(absolute).scheme in ("http", "https") and same_host(absolute, base_url):
            tiers[tier].append(absolute)
    ordered = list(dict.fromkeys(link for tier in tiers for link in tier))
    return [link for link in ordered if _page_key(link) != _page_key(base_url)][:_CONTACT_LINKS_PER_PAGE]


def _find_official_website_links(soup: BeautifulSoup, current_url: str, organizer_name: str | None = None) -> list[str]:
    """Links to other sites that are labelled as the official / organizer site,
    or whose text or domain carries the organizer's name (as the page itself
    gave it). Other outbound links (app stores, news, sponsors, help pages)
    are not followed: e-mails read there belonged to someone else."""
    name_words = [w for w in _distinctive_words(organizer_name) if len(w) >= 4]
    labelled: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href.startswith(("http://", "https://")):
            continue
        host = (urlparse(href).netloc or "").lower()
        if not host or same_host(href, current_url) or is_platform_url(href) or any(bad in host for bad in _NOT_ORGANIZER_HOSTS):
            continue
        if any(skip in href.lower() for skip in _SKIP_LINK_HINTS):
            continue
        text = (anchor.get_text() or "").strip().lower()
        compact_host = re.sub(r"[^a-z0-9]", "", host)
        if any(hint in text or hint in href.lower() for hint in _OFFICIAL_LINK_HINTS) or any(
            w in compact_host or w in text.split() for w in name_words
        ):
            labelled.append(href.split("#", 1)[0])
    return list(dict.fromkeys(labelled))


def _next_hop(
    website: str | None,
    soup: BeautifulSoup,
    current_url: str,
    visited: set[str],
    platform_url: str | None,
    contact_only: bool = False,
    organizer_name: str | None = None,
) -> str | None:
    """The organizer's declared site first, then links labelled as the official
    site, then this site's Contact/Imprint/Organizer/About pages. Skips pages
    already read in any spelling, and (for platform-hosted events) anything
    on the platform itself, whose contact page is the platform's."""
    labelled = _find_official_website_links(soup, current_url, organizer_name) if not contact_only else []
    candidates = ([website] if website and not contact_only else []) + labelled + _contact_page_links(soup, current_url)
    for url in candidates:
        if _page_key(url) in visited:
            continue
        if platform_url and same_host(url, platform_url):
            continue
        return url
    return None


def _read_page(html: str, soup: BeautifulSoup, url: str) -> dict:
    """Everything a first-party page (the event's or organizer's own site)
    publishes about the organizer. `name_strong` is True when the page itself
    names the organizer, False for the site-name/title fallback."""
    details = json_ld_organizer_details(soup, include_site_owner=True)
    fallback_name, website, _, linkedin = extract_contact(html, soup)
    labelled = details["name"] or find_labelled_organizer(soup)
    emails = find_emails(html, soup, url, structured=details["emails"])
    socials = extract_social_links(soup)
    return {
        "name": labelled or fallback_name,
        "name_strong": bool(labelled),
        "website": details["website"] or website,
        "email": emails[0] if emails else None,
        "phone": find_phone(html, soup, structured=details["phones"]),
        "linkedin": linkedin or socials.get("linkedin"),
        "twitter": socials.get("twitter"),
        "instagram": socials.get("instagram"),
        "facebook": socials.get("facebook"),
    }


def _read_platform_page(soup: BeautifulSoup) -> dict:
    """On a ticketing/listing page only the organizer it explicitly declares
    counts; everything else (footer mailbox, helpline, socials, site name)
    belongs to the platform."""
    details = json_ld_organizer_details(soup, include_site_owner=False)
    nothing = BeautifulSoup("", "html.parser")
    emails = find_emails("", nothing, structured=details["emails"])
    return {"name": details["name"], "name_strong": bool(details["name"]), "website": details["website"],
            "email": emails[0] if emails else None, "phone": find_phone("", nothing, structured=details["phones"], india_fallback=False)}


_DIRECTORY_NAME_HINTS = ("eventbrite", "meetup", "10times", "allevents", "townscript", "luma", "ticketmaster", "skillboxes", "dev.events")
_CONTACT_FIELDS = ("email", "phone", "website", "linkedin", "twitter", "instagram", "facebook")


class _Lookup:
    """What one lookup has gathered so far and the page each detail was read
    from. A detail is filled once; later pages never overwrite or blank it."""

    def __init__(self, candidate: ExtractedEventCandidate, render_js: bool) -> None:
        self.candidate = candidate
        self.render_js = render_js
        self.values: dict[str, str | None] = dict.fromkeys(_CONTACT_FIELDS)
        self.name: str | None = None
        # 3 = named by a page or its structured data, 2 = an organizer site's
        # own name, 1 = the event page's site name/title (a last resort).
        self.name_rank = 0
        self.evidence: dict[str, str] = {}
        self.sources: list[CandidateSource] = []
        self.visited: set[str] = set()
        self.fetches = 0
        self.renders = 0

    def absorb(self, found: dict, url: str, name_rank: int) -> None:
        for key in _CONTACT_FIELDS:
            value = found.get(key)
            if value and not self.values[key]:
                self.values[key] = value
                self.evidence[key] = url
        name = (found.get("name") or "").strip()
        if not name:
            return
        if self.name and any(hint in self.name.lower() for hint in _DIRECTORY_NAME_HINTS):
            self.name_rank = 0  # a listing site's name is never the organizer's
        rank = 3 if found.get("name_strong") else name_rank
        if rank > self.name_rank:
            self.name, self.name_rank = name, rank
            self.evidence["name"] = url

    def read(self, url: str) -> str | None:
        """One plain read (the existing fetch, incl. its thin-page browser retry)."""
        self.visited.add(_page_key(url))
        self.fetches += 1
        try:
            return fetch(url, render_js=self.render_js)
        except Exception as exc:  # an unreachable site must never end the run
            logger.debug("Organizer page %s could not be read: %s", url, exc)
            return None


def _organizer_from_official_api(candidate: ExtractedEventCandidate) -> OrganizerCandidate | None:
    """Events from an official API (e.g. IEEE vTools) carry the organizer the
    API publishes — the hosting body and its contact address. That is the
    evidence; the event page isn't opened (vTools allows one request a minute)."""
    source = candidate.primary_source
    raw = candidate.raw_evidence if isinstance(candidate.raw_evidence, dict) else {}
    organizer = raw.get("organizer")
    if source is None or source.source_type != "official_api" or not isinstance(organizer, dict):
        return None
    name = (organizer.get("name") or "").strip() or candidate.organizer_name_hint
    email = None
    if organizer.get("email"):
        valid, normalized, _ = is_valid_organizer_email(organizer["email"])
        email = normalized if valid else None
    website = organizer.get("url") or None
    evidence = {k: candidate.url for k, v in (("name", name), ("website", website)) if v}
    return OrganizerCandidate(
        found=bool(email), name=name or None, email=email, website=website,
        confidence_score=70 if email else 30, sources=[source],
        email_source_url=candidate.url if email else None, field_sources=evidence,
    )


def identify_organizer(candidate: ExtractedEventCandidate) -> OrganizerCandidate:
    if not candidate.url:
        return OrganizerCandidate(found=False)
    from_api = _organizer_from_official_api(candidate)
    if from_api is not None:
        return from_api

    look = _Lookup(candidate, render_js=browser_fetch_enabled())
    event_html = look.read(candidate.url)
    if not event_html:
        return OrganizerCandidate(found=False)

    look.sources.append(candidate.primary_source or CandidateSource(url=candidate.url, source_type="event_listing"))
    soup = BeautifulSoup(event_html, "html.parser")
    on_platform = is_platform_url(candidate.url) or (
        candidate.primary_source is not None and candidate.primary_source.source_type in ("aggregator", "event_directory")
    )
    confidence = 0
    from backend.services.discovery_agent.adapters import eventseye

    if eventseye.is_detail_url(candidate.url):
        # An EventsEye show page lists the venue's contacts too: take only the
        # show's own contacts and its organizers' (see eventseye.parse_detail).
        detail = eventseye.parse_detail(event_html)
        organizers = detail["organizers"]
        first = organizers[0] if organizers else {}
        found = {"name": first.get("name"), "name_strong": True, "website": first.get("website") or detail["event_website"],
                 "phone": detail["event_phone"] or first.get("phone")}
        for raw_email in [detail["event_email"], *(o.get("email") for o in organizers)]:
            valid, norm_email, _ = is_valid_organizer_email(raw_email) if raw_email else (False, None, None)
            if valid:
                found["email"] = norm_email
                break
        look.absorb(found, candidate.url, 3)
        if detail["event_website"]:
            look.sources.append(CandidateSource(url=detail["event_website"], source_type="official_event_site"))
        on_platform = True  # nothing else on the page belongs to the organizer
    elif on_platform:
        found = _read_platform_page(soup)
        website = found["website"]
        if website and not website.startswith(("http://", "https://")) and "." in website:
            found["website"] = "https://" + website.lstrip("/")  # e.g. "www.informa.com" on TradeFairDates
        if found["website"] and same_host(found["website"], candidate.url):
            found["website"] = None
        look.absorb(found, candidate.url, 3)
    else:
        look.absorb(_read_page(event_html, soup, candidate.url), candidate.url, 1)

    # Check candidate raw structured evidence if available
    if candidate.raw_evidence and isinstance(candidate.raw_evidence, dict):
        raw_org = candidate.raw_evidence.get("organizer")
        if isinstance(raw_org, dict):
            found = {"name": raw_org.get("name"), "name_strong": True}
            if raw_org.get("url") and not same_host(raw_org.get("url"), candidate.url):
                found["website"] = raw_org.get("url")
            if raw_org.get("email"):
                valid, norm_email, _ = is_valid_organizer_email(raw_org.get("email"))
                found["email"] = norm_email if valid else None
            look.absorb(found, candidate.url, 3)

    if candidate.raw_evidence is not None:
        confidence += 30  # this hop came from structured JSON-LD, not free text

    # A page that declares the organizer's own site elsewhere (a venue's or a
    # directory's page) is not the organizer's: its contact pages aren't either.
    website = look.values["website"]
    hosted_elsewhere = on_platform or bool(website and not same_host(website, candidate.url))
    platform_url = candidate.url if hosted_elsewhere else None

    # 1. Plain reads: the organizer's site, official links, contact pages. Once
    # an e-mail is known, at most one more same-site contact page for a phone.
    pages: list[tuple[str, bool]] = [(candidate.url, on_platform)]
    current_url, current_soup = candidate.url, soup
    phone_hops = 0
    while look.fetches < _MAX_HOPS:
        need_email = not look.values["email"]
        if not need_email and (look.values["phone"] or phone_hops >= 1):
            break
        next_url = _next_hop(look.values["website"], current_soup, current_url, look.visited, platform_url, contact_only=not need_email,
                             organizer_name=look.name if look.name_rank >= 3 else None)
        if not next_url:
            break
        phone_hops += 0 if need_email else 1
        html = look.read(next_url)
        if not html:
            continue  # one unreachable page doesn't end the lookup; try the next link
        current_url, current_soup = next_url, _absorb_hop(look, next_url, html, candidate.url)
        pages.append((next_url, False))

    # 2. Optional browser fallback, only when the plain reads found no e-mail.
    if not look.values["email"] and look.render_js:
        try:
            _render_fallback(look, pages, platform_url)
        except Exception as exc:  # a browser failure must never end the lookup
            logger.debug("Browser fallback skipped for %s: %s", candidate.url, exc)

    # 3. Search fallback if direct links did not reveal a verified organizer email
    target_name = look.name if look.name_rank >= 2 else (look.name or candidate.organizer_name_hint)
    is_platform_name = bool(target_name and any(p in target_name.lower() for p in _DIRECTORY_NAME_HINTS))

    org_search_query = None
    if not look.values["email"] and target_name and not is_platform_name and len(target_name.strip()) > 3:
        loc = f" {candidate.city}" if candidate.city else ""
        org_search_query = f"{target_name.strip()}{loc} official website contact email"
    elif not look.values["email"] and not on_platform and candidate.name and len(candidate.name.strip()) > 5:
        loc = f" {candidate.city}" if candidate.city else ""
        org_search_query = f"{candidate.name.strip()}{loc} organizer official contact"

    if org_search_query:
        try:
            _search_fallback(look, org_search_query, target_name or candidate.name)
        except Exception as exc:
            logger.debug("Organizer search lookup skipped: %s", exc)

    name = look.name or candidate.organizer_name_hint
    email, phone = look.values["email"], look.values["phone"]
    linkedin, twitter, instagram, facebook = (look.values[k] for k in ("linkedin", "twitter", "instagram", "facebook"))
    website = look.values["website"]

    if email:
        confidence += 40
    if phone:
        confidence += 15
    if linkedin or twitter or instagram or facebook:
        confidence += 10
    if website and website != candidate.url:
        confidence += 15
    confidence = min(confidence, 100)

    organizer_type = None
    if candidate.primary_source is not None:
        organizer_type = _ORGANIZER_TYPE_BY_SOURCE_TYPE.get(candidate.primary_source.source_type)

    field_sources = {k: v for k, v in look.evidence.items() if k != "email"}
    if not website and not on_platform:
        field_sources["website"] = candidate.url
    return OrganizerCandidate(
        found=bool(email),
        name=name,
        email=email,
        phone=phone,
        website=website or (None if on_platform else candidate.url),
        linkedin=linkedin,
        twitter=twitter,
        instagram=instagram,
        facebook=facebook,
        organizer_type=organizer_type,
        confidence_score=confidence,
        sources=look.sources,
        email_source_url=look.evidence.get("email"),
        field_sources=field_sources,
    )


def _absorb_hop(look: _Lookup, url: str, html: str, event_url: str) -> BeautifulSoup:
    """Read one followed page (organizer site or contact page) into the lookup."""
    look.sources.append(CandidateSource(url=url, source_type="organizer_website"))
    soup = BeautifulSoup(html, "html.parser")
    found = _read_page(html, soup, url)
    external = not same_host(url, event_url)
    if not found["website"] and external:
        found["website"] = url  # the organizer's own site we followed
    look.absorb(found, url, 2 if external else 1)
    return soup


def _render_fallback(look: _Lookup, pages: list[tuple[str, bool]], platform_url: str | None) -> None:
    """The plain reads found no e-mail: re-read the pages in the headless
    browser (contact blocks filled in by JavaScript, lazily loaded footers),
    then follow contact links that only the rendered page shows. Bounded by
    _MAX_RENDERS, and skipped while the browser workers are saturated."""
    from backend.services.social_agent import browser_fetch, web_fetch

    event_url = look.candidate.url
    # The organizer's own pages first (likeliest to carry a contact), the event page last.
    for url, platform_page in pages[1:] + pages[:1]:
        if look.values["email"] or look.renders >= _MAX_RENDERS:
            return
        if platform_page and (look.name or look.values["website"]):
            continue  # it declared its organizer; rendering it again rarely adds more
        if web_fetch.was_rendered(url) or browser_fetch.busy():
            continue
        look.renders += 1
        html = browser_fetch.render(url, for_contacts=True)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        if platform_page:
            found = _read_platform_page(soup)
            if found["website"] and same_host(found["website"], url):
                found["website"] = None
            look.absorb(found, url, 3)
            continue
        look.absorb(_read_page(html, soup, url), url, 1 if same_host(url, event_url) else 2)
        # Contact pages that only the rendered navigation links to (one extra read).
        for link in _contact_page_links(soup, url):
            if look.values["email"] or look.fetches > _MAX_HOPS:
                break
            if _page_key(link) in look.visited or (platform_url and same_host(link, platform_url)):
                continue
            page = look.read(link)
            if page:
                _absorb_hop(look, link, page, event_url)


def _search_fallback(look: _Lookup, query: str, subject: str | None) -> None:
    """Web search for the organizer's own site. A result page's e-mail is only
    taken when that page actually names the organizer (or event) — a random
    result's mailbox belongs to whoever runs that site."""
    from backend.services.discovery_agent import web_search

    found_urls = web_search.search(query, max_results=3)
    for res_url in found_urls:
        if _page_key(res_url) in look.visited or is_platform_url(res_url):
            continue
        look.visited.add(_page_key(res_url))
        res_html = fetch(res_url, render_js=False)
        if not res_html:
            continue
        res_soup = BeautifulSoup(res_html, "html.parser")
        if not _mentions(visible_text(res_soup), subject):
            continue
        for url, html, soup in [(res_url, res_html, res_soup)] + [
            (link, None, None) for link in _contact_page_links(res_soup, res_url)[:2] if _page_key(link) not in look.visited
        ]:
            if html is None:
                look.visited.add(_page_key(url))
                html = fetch(url, render_js=False)
                if not html:
                    continue
                soup = BeautifulSoup(html, "html.parser")
            found = _read_page(html, soup, url)
            if found["email"] and _site_matches(subject, res_url, found["email"]):
                found["name"], found["name_strong"] = found["name"] if not look.name else None, False
                found["website"] = found["website"] or res_url
                look.absorb(found, url, 2)
                look.sources.append(CandidateSource(url=url, source_type="organizer_website"))
                return


_STOPWORDS = {"the", "and", "for", "of", "in", "on", "at", "to", "a", "an", "&", "-", "|", "event", "events", "conference", "expo", "summit", "official"}


def _distinctive_words(subject: str | None) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (subject or "").lower()) if len(w) > 2 and w not in _STOPWORDS and not w.isdigit()]


def _mentions(text: str, subject: str | None) -> bool:
    """True when most of the subject's distinctive words appear on the page."""
    words = _distinctive_words(subject)
    if not words:
        return True
    page = set(re.findall(r"[a-z0-9]+", text.lower()))
    return sum(w in page for w in words) >= max(1, round(len(words) * 0.6))


def _site_matches(subject: str | None, url: str, email: str) -> bool:
    """A search result is the organizer's own site only when its domain (or the
    e-mail's) carries the organizer's name — a news article or another
    directory that merely mentions them does not."""
    words = [w for w in _distinctive_words(subject) if len(w) >= 4]
    domains = re.sub(r"[^a-z0-9]", "", f"{urlparse(url).netloc.lower().removeprefix('www.')} {email.split('@', 1)[-1].lower()}")
    return bool(words) and any(w in domains for w in words)
