"""Agent 4 extension — Community Promotion: a second, proactive matching
path alongside the original discussion-reply pipeline (`orchestrator.py`,
`discovery_pipeline.py`). Instead of reacting to an inbound Discussion,
this matches eligible 100Times events directly against the Community
registry Agent 5 discovers and an admin approves, and drafts a standalone
announcement (not a reply) for each good match.

Same honesty rules as the rest of this codebase: deterministic scoring
(no AI required — matches the project-wide "no AI needed" discipline),
a short explanation for every match, and content generation that falls
back to a real template when AI isn't configured, same as
`pipeline/content_generation.py`.
"""

from datetime import date

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Community, DiscoveredCommunity, Event
from backend.services.social_agent.ai_client import AIClientError, get_ai_client

_CATEGORY_MATCH_SCORE = 50
_TOPIC_OVERLAP_SCORE = 20
_LOCATION_MATCH_SCORE = 20
_ONLINE_BASE_SCORE = 10  # an online event has no city to match, but isn't penalized for it


def _eligible_events(db: Session) -> list[Event]:
    """Published, upcoming events only — same filter `EventMatchingEngine`
    already uses for promotable events (`services/acquisition_agent.py`)."""
    stmt = select(Event).where(Event.status == "published", Event.start_date >= date.today())
    return list(db.execute(stmt).scalars().all())


def _approved_communities(db: Session) -> list[Community]:
    return list(db.execute(select(Community).where(Community.promotion_allowed.is_(True))).scalars().all())


def _community_topics(db: Session, community: Community) -> set[str]:
    """Topics come from the `DiscoveredCommunity` lead this `Community` was
    materialized from (Agent 5), when there is one — a manually-added
    Community (no `discovered_community_id`) simply has no topics beyond
    its name, which is still used for matching below."""
    if not community.discovered_community_id:
        return set()
    discovered = db.get(DiscoveredCommunity, community.discovered_community_id)
    if not discovered:
        return set()
    topics = set(discovered.topics or [])
    if discovered.category:
        topics.add(discovered.category)
    return {t.lower() for t in topics}


def find_event_community_matches(db: Session, *, match_threshold: int = 60) -> list[tuple[Event, Community, int, str]]:
    """Returns (event, community, score, explanation) for every pair that
    clears `match_threshold`. Deterministic, no AI required — category and
    topic overlap plus a location check, same spirit as
    `EventMatchingEngine`'s scoring but far simpler, since this only needs
    to decide "worth drafting a post for", not rank a large candidate pool."""
    events = _eligible_events(db)
    communities = _approved_communities(db)
    matches: list[tuple[Event, Community, int, str]] = []

    for community in communities:
        topics = _community_topics(db, community)
        for event in events:
            score = 0
            reasons: list[str] = []
            event_category = (event.category.name if event.category else None) or ""
            category_lower = event_category.lower()
            cat_words = [w.strip() for w in category_lower.replace("&", " ").replace("/", " ").split() if len(w.strip()) > 3]
            if category_lower and category_lower in community.name.lower():
                score += _CATEGORY_MATCH_SCORE
                reasons.append(f'Category "{event_category}" matches this community\'s name.')
            elif any(w in community.name.lower() for w in cat_words):
                score += _CATEGORY_MATCH_SCORE
                reasons.append(f'Category keyword in "{event_category}" matches this community\'s name.')
            elif category_lower and any(category_lower in t or t in category_lower for t in topics):
                score += _TOPIC_OVERLAP_SCORE
                reasons.append(f'Category "{event_category}" overlaps with the community\'s known topics.')

            if event.format == "online":
                score += _ONLINE_BASE_SCORE
                reasons.append("Event is online, so location isn't a constraint.")
            elif event.city_name and event.city_name.lower() in community.name.lower():
                score += _LOCATION_MATCH_SCORE
                reasons.append(f"Community name mentions {event.city_name}, matching the event's city.")
            elif "india" in community.name.lower() and (not getattr(event, "country_name", None) or (event.country_name or "").lower() in ("india", "in")):
                score += _LOCATION_MATCH_SCORE
                reasons.append("Community serves India, matching the event's host country.")

            if score >= match_threshold:
                explanation = " ".join(reasons) if reasons else "Matched on available signals."
                matches.append((event, community, min(score, 100), explanation))

    return matches


class PromotionPostAI(BaseModel):
    subject: str
    body: str


_TOOL_NAME = "write_community_promotion_post"
_TOOL_DESCRIPTION = "A standalone announcement post inviting a community to check out an event — not a reply to anything."


class PromotionContentResult:
    __slots__ = ("success", "subject", "body", "generated_by", "error")

    def __init__(self, success: bool, subject: str = "", body: str = "", generated_by: str = "deterministic_fallback", error: str | None = None) -> None:
        self.success = success
        self.subject = subject
        self.body = body
        self.generated_by = generated_by
        self.error = error


def _event_link(event: Event) -> str:
    return f"https://100times.in/events/{event.slug}"


def _deterministic_post(event: Event, community: Community) -> PromotionPostAI:
    when = event.start_date.strftime("%d %b %Y") if event.start_date else "soon"
    where = "online" if event.format == "online" else (event.city_name or "in person")
    subject = f"{event.title} — {when}"
    body = (
        f"Hey {community.name}! Thought this might interest folks here: {event.title}, happening {when} ({where}).\n\n"
        f"{(event.description or '').strip()[:280]}\n\n"
        f"Details and registration: {_event_link(event)}"
    )
    return PromotionPostAI(subject=subject, body=body)


def generate_promotion_content(event: Event, community: Community) -> PromotionContentResult:
    """AI-first with a real deterministic fallback, same `generated_by`
    honesty convention as `pipeline/content_generation.py` and Agent 2's
    `message_generator.py`. Never required — this agent works with zero AI
    configured, same as Agent 1 and Agent 2."""
    client = get_ai_client()
    if client.is_configured:
        try:
            raw = client.generate_structured(
                system=(
                    "You write ONE short, genuine, non-spammy standalone announcement post inviting a community "
                    "to check out a real event. This is NOT a reply to anyone — it's a fresh post. Only use facts "
                    "given to you; never invent details, attendance figures, or guaranteed outcomes. Match the "
                    "community's likely tone from its name. Call the `write_community_promotion_post` tool once."
                ),
                user=(
                    f"Community: {community.name}\n"
                    f"Event: {event.title}\n"
                    f"Category: {event.category.name if event.category else 'unknown'}\n"
                    f"Date: {event.start_date}\n"
                    f"Format: {event.format}\n"
                    f"Location: {event.city_name or 'online'}\n"
                    f"Description: {(event.description or '')[:600]}\n"
                    f"Link: {_event_link(event)}\n"
                ),
                tool_name=_TOOL_NAME,
                tool_description=_TOOL_DESCRIPTION,
                input_schema=PromotionPostAI.model_json_schema(),
            )
            parsed = PromotionPostAI.model_validate(raw)
            return PromotionContentResult(success=True, subject=parsed.subject, body=parsed.body, generated_by="ai")
        except (AIClientError, ValidationError):
            pass  # fall through to the deterministic template — never block on an AI failure

    draft = _deterministic_post(event, community)
    return PromotionContentResult(success=True, subject=draft.subject, body=draft.body, generated_by="deterministic_fallback")
