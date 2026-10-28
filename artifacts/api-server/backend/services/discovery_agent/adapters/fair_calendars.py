"""Site-specific readers for trade-fair calendars whose pages publish events
as plain markup (no schema.org data), checked 2026-10-27:

- Expolya (expolya.com/expos, robots.txt allows all): every upcoming fair on
  one page as `a.salon-card` cards — start date, sectors and country code as
  data attributes, "City, Country · Venue" text. Each fair's own page carries
  a schema.org Event with its official website and organizer.
- Messe Düsseldorf (national + international lists): `li.dim-list-item`
  rows with title, dates and city attributes, the fair's website and its
  organizer. The international list covers its fairs in India, the UAE, Asia.
- CMT Events (cmtevents.com/main.aspx, robots.txt allows it): conference
  cards with "27-28 Oct, 2026 - Mexico City, MEXICO" and the event page link.
- Koelnmesse (/current-dates/all-trade-fairs/): `.exh_holder .item` cards
  with a begin-date attribute, "27.10. - 30.10.2026, Cologne" and the fair's
  website. Its robots.txt allows general visitors to this page but blocks
  named AI crawlers (GPTBot, ClaudeBot …); this rule-based reader is not one of
  them, and the source stays unticked by default — enabling it is the admin's call.

Each keeps upcoming fairs in the run's countries (all when none selected).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from backend.services.discovery_agent.adapters.base import BaseSourceAdapter, SourceError
from backend.services.discovery_agent.types import CandidateSource, DiscoveryConfig, ExtractedEventCandidate

logger = logging.getLogger("discovery_agent.adapters.fair_calendars")


def _day(value: str | None) -> date | None:
    try:
        return date.fromisoformat((value or "")[:10])
    except ValueError:
        return None


def _canonical(country: str | None) -> str | None:
    from backend.services.discovery_agent import geo_scope

    return geo_scope.canonical_country(country) or (country or None)


def _country_of_city(city: str | None) -> str | None:
    from backend.services.discovery_agent.country_utils import infer_country

    country = infer_country(None, city=city, default=None) if city else None
    return _canonical(country) if country else None


def _interleave(per_country: dict[str | None, list[ExtractedEventCandidate]], limit: int) -> list[ExtractedEventCandidate]:
    ordered: list[ExtractedEventCandidate] = []
    queues = [sorted(v, key=lambda c: c.date or "") for v in per_country.values()]
    while queues and len(ordered) < limit:
        for queue in list(queues):
            if queue:
                ordered.append(queue.pop(0))
            if not queue:
                queues.remove(queue)
    return ordered[:limit]


class _CalendarAdapter(BaseSourceAdapter):
    """Shared plumbing: read the calendar page(s), parse rows, filter, report."""

    access_method = "html_listing"
    PAGES: tuple[str, ...] = ()

    def __init__(self, source_id: str, name: str, website_url: str, category: str = "International Exhibition Organizer", config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        self.source_id, self.name, self.website_url, self.category = source_id, name, website_url, category

    def listing_template(self) -> str:
        return self.PAGES[0]

    def target_urls(self, config: DiscoveryConfig | None, max_urls: int = 5) -> list[str]:
        return list(self.PAGES)[:max_urls]

    def parse(self, html: str, page_url: str) -> list[dict[str, Any]]:  # pragma: no cover - overridden
        raise NotImplementedError

    def _read(self, url: str) -> list[dict[str, Any]] | None:
        from backend.services.social_agent.web_fetch import fetch

        self._respect_rate_limit()
        html = fetch(url)
        rows = self.parse(html, url) if html else []
        if html and not rows:  # some calendars only fill in after scripts run
            rendered = fetch(url, render_js=True)
            rows = self.parse(rendered, url) if rendered else []
        return rows if (html or rows) else None

    def discover(self, config: DiscoveryConfig, limit: int = 25) -> list[ExtractedEventCandidate]:
        from backend.services.discovery_agent import geo_scope
        from backend.services.social_agent.web_fetch import failure_reason

        wanted = {c.lower() for c in geo_scope.resolve(config).countries}
        until = _day(str(getattr(config, "date_to", "") or "")) if getattr(config, "date_to", None) else None
        today = date.today()
        per_country: dict[str | None, list[ExtractedEventCandidate]] = {}
        failures, read_any, seen = [], False, set()
        for url in self.PAGES:
            rows = self._read(url)
            if rows is None:
                failures.append(f"{url}: {failure_reason(url) or 'no response'}")
                continue
            read_any = True
            for row in rows:
                start = row.get("start")
                if not row.get("name") or start is None or start < today or (until and start > until):
                    continue
                key = (row["name"].strip().lower(), start)
                if key in seen:  # listed on more than one of the site's pages
                    continue
                seen.add(key)
                if wanted and (row.get("country") or "").lower() not in wanted:
                    continue
                per_country.setdefault(row.get("country"), []).append(self._candidate(row))
        if not read_any:
            raise SourceError("unreachable", "; ".join(failures[:2]) or "no page read")
        return _interleave(per_country, max(limit, 80))

    def _candidate(self, row: dict[str, Any]) -> ExtractedEventCandidate:
        url = row.get("url") or self.PAGES[0]
        primary = CandidateSource(url=url, source_type=row.get("source_type", "event_directory"), source_website=self.name)
        listing = CandidateSource(url=row.get("listing_url") or self.PAGES[0], source_type="organizer_portfolio", source_website=self.name)
        evidence: dict[str, Any] = {"source_id": self.source_id, "end_date": row.get("end").isoformat() if row.get("end") else None}
        if row.get("organizer"):
            evidence["organizer"] = {"name": row["organizer"], **({"url": row["organizer_url"]} if row.get("organizer_url") else {})}
        return ExtractedEventCandidate(
            name=row["name"],
            event_description=row.get("description"),
            date=row["start"].isoformat(),
            venue=row.get("venue"),
            city=row.get("city"),
            country=row.get("country"),
            url=url,
            event_format="offline",
            organizer_name_hint=row.get("organizer"),
            extraction_confidence=85,
            primary_source=primary,
            sources=[primary, listing] if listing.url != primary.url else [primary],
            raw_evidence=evidence,
        )

    def check_health(self) -> dict[str, Any]:
        start = time.time()
        rows = self._read(self.PAGES[0])
        latency = round((time.time() - start) * 1000, 1)
        if rows is None:
            from backend.services.social_agent.web_fetch import failure_reason

            return {"status": "unreachable", "latency_ms": latency, "error": failure_reason(self.PAGES[0]) or "no response", "details": {}}
        return {"status": "healthy", "latency_ms": latency, "error": None, "details": {"rows": len(rows)}}

    def test_extraction(self, sample_query_or_url: str | None = None) -> dict[str, Any]:
        start = time.time()
        try:
            events = self.discover(DiscoveryConfig(), limit=10)
        except SourceError as exc:
            return {"success": False, "events_found": 0, "sample_events": [], "duration_ms": round((time.time() - start) * 1000, 1), "error": str(exc)}
        samples = [{"name": e.name, "date": e.date, "city": e.city, "country": e.country, "url": e.url} for e in events[:5]]
        return {"success": True, "events_found": len(events), "sample_events": samples, "duration_ms": round((time.time() - start) * 1000, 1), "error": None,
                "note": None if events else "Calendar read, but it lists no upcoming fairs"}


class ExpolyaAdapter(_CalendarAdapter):
    PAGES = ("https://expolya.com/expos",)

    def __init__(self, source_id: str = "expolya", name: str = "Expolya", website_url: str = "https://expolya.com/", category: str = "Global Event Discovery", config: dict[str, Any] | None = None) -> None:
        super().__init__(source_id, name, website_url, category, config)

    def parse(self, html: str, page_url: str) -> list[dict[str, Any]]:
        rows = []
        for card in BeautifulSoup(html, "html.parser").select("a.salon-card[href]"):
            name = card.select_one(".salon-card-name")
            place = card.select_one(".salon-card-lieu")
            place_text = place.get_text(" ", strip=True) if place else ""
            where, _, venue = place_text.partition("·")
            city, _, country = where.rpartition(",")
            description = card.select_one(".salon-card-desc")
            sectors = [s for s in (card.get("data-secteurs") or "").split("|") if s]
            rows.append({
                "name": name.get_text(" ", strip=True) if name else None,
                "start": _day(card.get("data-date")),
                "city": city.strip() or None,
                "country": _canonical(country.strip()) if country.strip() else None,
                "venue": venue.strip() or None,
                "url": urljoin(page_url, card["href"]),
                "description": " ".join(filter(None, [description.get_text(" ", strip=True) if description else None,
                                                     f"(Expolya sectors: {', '.join(sectors)})" if sectors else None])) or None,
            })
        return rows


class MesseDuesseldorfAdapter(_CalendarAdapter):
    _BASE = "https://www.messe-duesseldorf.com/en/Trade_Fairs_Events/Trade_fairs_national_international"
    PAGES = (_BASE, _BASE + "?utd_national=international")
    _ORGANIZER = re.compile(r"Organizer:\s*(.+?)\s*(?:Location:|Cycle:|Opening|$)")

    def __init__(self, source_id: str = "messe_duesseldorf", name: str = "Messe Düsseldorf", website_url: str = "https://www.messe-duesseldorf.com/", category: str = "International Exhibition Organizer", config: dict[str, Any] | None = None) -> None:
        super().__init__(source_id, name, website_url, category, config)

    def parse(self, html: str, page_url: str) -> list[dict[str, Any]]:
        rows = []
        for item in BeautifulSoup(html, "html.parser").select("li.dim-list-item"):
            city = (item.get("data-location") or "").strip() or None
            website = next((a["href"] for a in item.select("a[href]") if a.get_text(" ", strip=True).lower() == "website" and a["href"].startswith("http")), None)
            subtitle = item.select_one(".dim-chapter_subtitle")
            organizer = self._ORGANIZER.search(" ".join(item.get_text(" ", strip=True).split()))
            rows.append({
                "name": (item.get("data-title") or "").strip() or None,
                "start": _day(item.get("data-date-from")),
                "end": _day(item.get("data-date-to")),
                "city": city,
                "country": "Germany" if city in ("Düsseldorf", "Dusseldorf") else _country_of_city(city),
                "url": website or f"{page_url}#{item.get('id', '')}",
                "source_type": "official_event_site" if website else "event_directory",
                "listing_url": page_url,
                "description": subtitle.get_text(" ", strip=True) if subtitle else None,
                "organizer": organizer.group(1).strip() if organizer else "Messe Düsseldorf",
            })
        return rows


class KoelnmesseAdapter(_CalendarAdapter):
    PAGES = ("https://www.koelnmesse.com/current-dates/all-trade-fairs/",)

    def __init__(self, source_id: str = "koelnmesse", name: str = "Koelnmesse", website_url: str = "https://www.koelnmesse.com/", category: str = "International Exhibition Organizer", config: dict[str, Any] | None = None) -> None:
        super().__init__(source_id, name, website_url, category, config)

    def parse(self, html: str, page_url: str) -> list[dict[str, Any]]:
        rows = []
        for item in BeautifulSoup(html, "html.parser").select(".exh_holder .item"):
            name = item.select_one(".sort_fairname")
            when = item.select_one(".date")
            when_text = when.get_text(" ", strip=True) if when else ""
            city = when_text.rpartition(",")[2].strip() if "," in when_text else None
            link = next((a["href"] for a in item.select("a[href]") if a["href"].startswith("http") and "ical" not in a["href"].lower()), None)
            paragraphs = [p.get_text(" ", strip=True) for p in item.find_all("p") if not p.get("class")]
            labels = [el.get_text(" ", strip=True) for el in item.select(".inner_category, .inner_branche")]
            description = next((p for p in paragraphs if p and p != (name.get_text(" ", strip=True) if name else "") and when_text not in p), None)
            rows.append({
                "name": name.get_text(" ", strip=True) if name else None,
                "start": _day(item.get("data-begin-date")),
                "city": city,
                "country": "Germany" if (city or "").lower() in ("cologne", "köln") else _country_of_city(city),
                "url": link,
                "source_type": "official_event_site" if link else "event_directory",
                "description": " ".join(filter(None, [description, f"(Koelnmesse sectors: {', '.join(labels)})" if labels else None])) or None,
                "organizer": "Koelnmesse",
                "organizer_url": "https://www.koelnmesse.com/",
            })
        return rows


_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
# "27-28 Oct, 2026", "01-03 Dec, 2026", "30 Nov - 02 Dec, 2026", "5 Mar, 2027"
_CMT_DATES = re.compile(r"(\d{1,2})(?:\s+([A-Za-z]{3,9}))?(?:\s*[-–]\s*(\d{1,2})(?:\s+([A-Za-z]{3,9}))?)?,?\s+(\d{4})")


def _cmt_dates(text: str) -> tuple[date | None, date | None]:
    found = _CMT_DATES.search(text)
    if not found:
        return None, None
    d1, m1, d2, m2, year = found.groups()
    end_month = _MONTHS.get((m2 or m1 or "")[:3].lower())
    start_month = _MONTHS.get((m1 or "")[:3].lower()) or end_month
    if not start_month:
        return None, None
    try:
        end = date(int(year), end_month, int(d2)) if d2 and end_month else None
        start = date(int(year) - (1 if end and start_month > end_month else 0), start_month, int(d1))
    except ValueError:
        return None, None
    return start, end


class CmtEventsAdapter(_CalendarAdapter):
    """CMT (Centre for Management Technology) — cmtevents.com, the new home of
    cmtsp.com (robots.txt allows main.aspx and aboutevent.aspx). Its upcoming
    conferences are cards on the home page: an `a.eventtitle` link to the
    event page, a subtitle, and "27-28 Oct, 2026 - Mexico City, MEXICO".
    The page names the company that runs them (no schema.org events)."""

    PAGES = ("https://www.cmtevents.com/main.aspx",)
    _ORGANIZER = "Centre for Management Technology Pte. Ltd"

    def __init__(self, source_id: str = "cmt_events", name: str = "CMT Events", website_url: str = "https://www.cmtevents.com/", category: str = "Industry Association", config: dict[str, Any] | None = None) -> None:
        super().__init__(source_id, name, website_url, category, config)

    def parse(self, html: str, page_url: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        runs_them = self._ORGANIZER.lower() in soup.get_text(" ", strip=True).lower()
        rows = []
        for title in soup.select("a.eventtitle[href]"):
            card = title.find_parent("div")
            when = card.select_one("p.h5") if card else None
            when_text = " ".join(when.get_text(" ", strip=True).split()) if when else ""
            start, end = _cmt_dates(when_text)
            place = when_text.split(" - ", 1)[1] if " - " in when_text else ""
            city, _, country = place.rpartition(",")
            subtitle = card.select_one("p strong") if card else None
            rows.append({
                "name": title.get_text(" ", strip=True) or None,
                "start": start,
                "end": end,
                "city": city.strip() or None,
                "country": _canonical(country.strip()) if country.strip() else None,
                "url": urljoin(page_url, title["href"]).rstrip("&"),
                "source_type": "official_event_site",
                "description": subtitle.get_text(" ", strip=True) if subtitle else None,
                "organizer": self._ORGANIZER if runs_them else None,
                "organizer_url": self.website_url if runs_them else None,
            })
        return rows
