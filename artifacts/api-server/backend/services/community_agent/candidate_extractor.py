"""Turns one candidate URL (a search result pointing at a Telegram or
Discord invite) into an `ExtractedCommunityCandidate` by reading the
platform's own public page/API — never a bot, never a joined-member-only
endpoint, and never a guessed fact.

Telegram: the public `t.me/<name>` preview page (same page anyone sees
without logging in) — read with `services.social_agent.web_fetch.fetch`,
parsed for `og:title`/`og:description` and a "N subscribers"/"N members"
line when the page shows one.

Discord: the public, keyless invite-info endpoint
`GET https://discord.com/api/v10/invites/{code}?with_counts=true` — no bot
token, no server membership required, returns the guild's name,
description and `approximate_member_count` for any invite that is still
valid. A revoked/expired/invalid invite returns 404/410 and yields no
candidate — never a fabricated one.
"""

import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from backend.services.community_agent.types import CandidateSource, ExtractedCommunityCandidate
from backend.services.social_agent.web_fetch import USER_AGENT, fetch

_DISCORD_INVITE_API = "https://discord.com/api/v10/invites/{code}"
_SUBSCRIBER_RE = re.compile(r"([\d,.]+\s*[KM]?)\s*(subscribers|members|online)", re.IGNORECASE)
_HTTP_TIMEOUT_SECONDS = 8


def classify_platform(url: str) -> str | None:
    host = (urlparse(url).netloc or "").lower()
    if host.endswith("t.me") or host.endswith("telegram.me"):
        return "telegram"
    if host.endswith("discord.gg") or host in ("discord.com", "www.discord.com", "discordapp.com"):
        return "discord"
    return None


def _telegram_channel_name(url: str) -> str | None:
    path = urlparse(url).path.strip("/")
    if not path or path.startswith(("joinchat/", "+")):
        return None  # a private invite hash, or something unreadable without a client
    parts = [p for p in path.split("/") if p]
    if parts and parts[0] == "s":
        return parts[1] if len(parts) > 1 else None
    return parts[0] if parts else None


def _discord_invite_code(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc.endswith("discord.gg"):
        code = parsed.path.strip("/")
    else:
        # discord.com/invite/<code>
        parts = [p for p in parsed.path.split("/") if p]
        code = parts[-1] if parts and "invite" in parts else None
    return code or None


def _parse_member_count(text: str) -> int | None:
    match = _SUBSCRIBER_RE.search(text)
    if not match:
        return None
    raw = match.group(1).strip().upper().replace(",", "")
    try:
        if raw.endswith("K"):
            return int(float(raw[:-1]) * 1_000)
        if raw.endswith("M"):
            return int(float(raw[:-1]) * 1_000_000)
        return int(float(raw))
    except ValueError:
        return None


def _extract_telegram(source: CandidateSource) -> ExtractedCommunityCandidate | None:
    name = _telegram_channel_name(source.url)
    if not name:
        return None
    canonical_url = f"https://t.me/{name}"
    html = fetch(canonical_url)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("meta", property="og:title")
    desc_tag = soup.find("meta", property="og:description")
    raw_title = (title_tag.get("content") if title_tag else None) or name
    title = raw_title
    for prefix in ("Telegram: Contact @", "Telegram: View @", "Telegram: Join @"):
        if title.startswith(prefix):
            clean_name = title[len(prefix):].strip()
            title = clean_name.replace("_", " ").title()
            break
    description = desc_tag.get("content") if desc_tag else None
    page_text = soup.get_text(" ", strip=True)
    member_count = _parse_member_count(page_text)

    if not description or member_count is None:
        s_html = fetch(f"https://t.me/s/{name}")
        if s_html:
            s_soup = BeautifulSoup(s_html, "html.parser")
            if not description:
                s_desc = s_soup.find("meta", property="og:description")
                if s_desc and s_desc.get("content"):
                    description = s_desc.get("content")
            if member_count is None:
                member_count = _parse_member_count(s_soup.get_text(" ", strip=True))

    invite_source = CandidateSource(url=canonical_url, source_type="invite_page")
    return ExtractedCommunityCandidate(
        platform="telegram", name=title, canonical_url=canonical_url, invite_url=canonical_url,
        description=description, member_count=member_count, extraction_confidence=70,
        primary_source=invite_source, sources=[source, invite_source],
        raw_evidence={"ogTitle": title, "ogDescription": description, "memberCountText": page_text[:300]},
    )


def _extract_discord(source: CandidateSource) -> ExtractedCommunityCandidate | None:
    code = _discord_invite_code(source.url)
    if not code:
        return None
    api_url = _DISCORD_INVITE_API.format(code=code)
    try:
        response = httpx.get(api_url, params={"with_counts": "true"}, timeout=_HTTP_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None  # expired/invalid/revoked invite — never fabricate a guild for it
    try:
        data = response.json()
    except ValueError:
        return None
    guild = data.get("guild") or {}
    name = guild.get("name")
    if not name:
        return None
    canonical_url = f"https://discord.gg/{code}"

    api_source = CandidateSource(url=api_url, source_type="platform_api")
    return ExtractedCommunityCandidate(
        platform="discord", name=name, canonical_url=canonical_url, invite_url=canonical_url,
        description=guild.get("description"), member_count=data.get("approximate_member_count"),
        extraction_confidence=80,  # the platform's own structured API, higher trust than a scraped preview page
        primary_source=api_source, sources=[source, api_source],
        raw_evidence={"guildName": name, "description": guild.get("description"),
                      "approximateMemberCount": data.get("approximate_member_count"),
                      "approximatePresenceCount": data.get("approximate_presence_count")},
    )


def extract_community(source: CandidateSource) -> ExtractedCommunityCandidate | None:
    platform = classify_platform(source.url)
    if platform == "telegram":
        return _extract_telegram(source)
    if platform == "discord":
        return _extract_discord(source)
    return None
