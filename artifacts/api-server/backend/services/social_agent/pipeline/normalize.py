"""Stage: NORMALIZED — turns a raw signal into a canonical Discussion row.

Handles external_id generation, platform+external_id duplicate detection
(never process the same post twice unless explicitly reprocessed), and
get-or-create for the source Community.
"""

import hashlib
import re
import urllib.parse
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Community, Discussion


class NormalizeResult:
    __slots__ = ("discussion", "is_duplicate", "community")

    def __init__(self, discussion: Discussion, is_duplicate: bool, community: Community) -> None:
        self.discussion = discussion
        self.is_duplicate = is_duplicate
        self.community = community


def _build_external_id(platform: str, community_name: str, title: str, content: str) -> str:
    raw_hash = hashlib.md5(f"{platform}:{community_name}:{title}:{content}".encode()).hexdigest()
    return f"{platform}_{raw_hash[:16]}"


def _get_or_create_community(db: Session, platform: str, community_name: str) -> Community:
    community = db.scalar(select(Community).where(Community.name == community_name))
    if community:
        return community

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", community_name.lower()).strip("-")
    comm_url = (
        f"https://www.reddit.com/r/{community_name.replace('r/', '').strip('/')}"
        if platform == "reddit"
        else f"https://{platform}.com/{slug}"
    )
    community = Community(
        platform=platform,
        name=community_name,
        slug=slug,
        url=comm_url,
        rules_text=None,  # unverified — the policy-check stage treats this as REQUIRES_HUMAN_REVIEW
        promotion_allowed=False,
        external_links_allowed=True,
        automation_allowed=False,
        risk_level="medium",
        quality_score=75,
        last_checked=datetime.now(timezone.utc),
    )
    db.add(community)
    db.flush()
    return community


def normalize_signal(
    db: Session,
    platform: str,
    community_name: str,
    title: str,
    content: str,
    url: str = "",
    external_id: str | None = None,
    author: str | None = None,
) -> NormalizeResult:
    if not external_id:
        external_id = _build_external_id(platform, community_name, title, content)

    existing = db.scalar(select(Discussion).where(Discussion.external_id == external_id))
    community = _get_or_create_community(db, platform, community_name)
    if existing:
        return NormalizeResult(discussion=existing, is_duplicate=True, community=community)

    if not url:
        if platform == "reddit":
            clean_sub = community_name.replace("r/", "").strip("/")
            q = urllib.parse.quote_plus(title[:60])
            url = f"https://www.reddit.com/r/{clean_sub}/search/?q={q}"
        else:
            url = f"https://{platform}.com/{community.slug}"

    discussion = Discussion(
        community_id=community.id,
        platform=platform,
        external_id=external_id,
        url=url,
        title=title,
        content=content,
        author=author or "community_member",
        published_at=datetime.now(timezone.utc),
        intent_classification="PENDING",
        intent_confidence=0,
        extracted_intent=None,
        status="pending",
        pipeline_status="DISCOVERED",
    )
    db.add(discussion)
    db.flush()

    return NormalizeResult(discussion=discussion, is_duplicate=False, community=community)
