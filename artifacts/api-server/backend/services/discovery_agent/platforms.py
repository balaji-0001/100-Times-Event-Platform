"""Ticketing / event-listing platforms. An event page hosted on one of
these carries the *platform's* contact details (support mailbox, helpline,
social links, contact page), not the event organizer's — so the Organizer
Identifier must not attribute them, and the source finder classifies
these URLs as `aggregator`.
"""

from urllib.parse import urlparse

PLATFORM_HOST_HINTS = (
    "eventbrite",
    "meetup.com",
    "allevents.in",
    "10times.com",
    "bookmyshow",
    "townscript",
    "eventshigh",
    "skillboxes.com",
    "insider.in",
    "district.in",
    "konfhub.com",
    "lu.ma",
    "luma.com",
    "ticketnew.com",
    "zomato.com",
    "highape.com",
    "explara.com",
    "unstop.com",
    "linkedin.com",
    "facebook.com",
    "fb.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "threads.net",
)


def is_platform_url(url: str | None) -> bool:
    host = (urlparse(url or "").netloc or "").lower()
    return any(hint in host for hint in PLATFORM_HOST_HINTS)


def same_host(url_a: str | None, url_b: str | None) -> bool:
    def host(url: str | None) -> str:
        return (urlparse(url or "").netloc or "").lower().removeprefix("www.")

    return bool(host(url_a)) and host(url_a) == host(url_b)
