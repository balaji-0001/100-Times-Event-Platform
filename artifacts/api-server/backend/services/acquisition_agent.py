import hashlib
import re
import urllib.parse
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from backend.models import (
    AcquisitionOpportunity,
    AgentAction,
    Category,
    City,
    Community,
    Discussion,
    Event,
    Venue,
)


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z]{3,}", text.lower()))


class IntentDetectionAgent:
    """Regex-based intent classifier.

    Used ONLY by the Instagram content-distribution flow (which parses an
    operator-supplied theme string, not a discovered discussion — there's no
    "AI understanding an ambiguous post" need there). The Demand Capture
    pipeline (Reddit/Discord/Telegram/X/LinkedIn) uses real AI extraction
    instead — see `backend/services/social_agent/pipeline/intent_extraction.py`.
    """

    HIGH_INTENT_PATTERNS = [
        r"looking for events?",
        r"any events? happening",
        r"events? this weekend",
        r"workshops? (?:in|near|around|for)",
        r"tech meetups?",
        r"startup networking",
        r"conference recommendations?",
        r"hackathons?",
        r"things to do",
        r"developer events?",
        r"business events?",
        r"free workshops?",
        r"events? near me",
        r"where can i find (?:ai|tech|startup|design|developer)",
        r"does anyone know (?:any|of any)? upcoming",
        r"what tech conferences",
        r"recommend any (?:meetups?|events?|workshops?|conferences?)",
        r"are there any (?:ai|tech|design|startup)",
    ]

    MEDIUM_INTENT_PATTERNS = [
        r"recently moved",
        r"want to meet (?:people|founders|developers|designers)",
        r"connect with (?:peers|entrepreneurs|folks)",
        r"communities (?:in|around)",
        r"groups for (?:developers|designers|founders)",
        r"interested in networking",
    ]

    LOW_INTENT_PATTERNS = [
        r"attended (?:an?|the)",
        r"went to (?:an?|the)",
        r"last year",
        r"recap of",
        r"photos from",
    ]

    IRRELEVANT_PATTERNS = [
        r"too expensive",
        r"waste of money",
        r"hate conferences",
        r"ticket prices? (?:are|is) ridiculous",
        r"spam",
        r"job vacancy",
        r"hiring for",
    ]

    @classmethod
    def classify_and_extract(cls, title: str, content: str, known_cities: list[str]) -> tuple[str, float, dict[str, Any]]:
        combined = f"{title} {content}".lower()
        tokens = tokenize(combined)

        # Check Irrelevant
        for pat in cls.IRRELEVANT_PATTERNS:
            if re.search(pat, combined):
                return "IRRELEVANT", 0.90, {"intent": "irrelevant_opinion", "confidence": 0.90}

        # Check High Intent
        high_score = 0.0
        for pat in cls.HIGH_INTENT_PATTERNS:
            if re.search(pat, combined):
                high_score += 0.45

        # Check Medium Intent
        med_score = 0.0
        for pat in cls.MEDIUM_INTENT_PATTERNS:
            if re.search(pat, combined):
                med_score += 0.35

        # Check Low Intent
        for pat in cls.LOW_INTENT_PATTERNS:
            if re.search(pat, combined):
                return "LOW_INTENT", 0.75, {"intent": "past_event_mention", "confidence": 0.75}

        # Determine Classification
        if high_score >= 0.4:
            confidence = min(0.85 + (high_score * 0.1), 0.98)
            classification = "HIGH_INTENT"
        elif med_score >= 0.3:
            confidence = min(0.70 + (med_score * 0.1), 0.88)
            classification = "MEDIUM_INTENT"
        elif any(w in tokens for w in ["event", "events", "meetup", "meetups", "workshop", "conference", "hackathon"]):
            confidence = 0.65
            classification = "LOW_INTENT"
        else:
            return "IRRELEVANT", 0.85, {"intent": "none", "confidence": 0.85}

        # Extract structured parameters
        # 1. Location
        detected_location = None
        for c in known_cities:
            if c.lower() in combined:
                detected_location = c
                break

        # 2. Category
        detected_category = "Technology"
        if any(w in tokens for w in ["ai", "artificial", "intelligence", "llm", "gpt", "deepseek", "machine", "learning", "data"]):
            detected_category = "Artificial Intelligence"
        elif any(w in tokens for w in ["design", "ui", "ux", "creative", "product", "figma"]):
            detected_category = "Design"
        elif any(w in tokens for w in ["startup", "business", "founder", "operators", "strategy", "venture", "investor", "pitch"]):
            detected_category = "Business & Strategy"
        elif any(w in tokens for w in ["art", "culture", "exhibition", "gallery", "music"]):
            detected_category = "Art & Culture"

        # 3. Event Type
        detected_type = "Conference"
        if any(w in tokens for w in ["workshop", "hands-on", "masterclass", "bootcamp"]):
            detected_type = "Workshop"
        elif any(w in tokens for w in ["hackathon", "buildathon", "hack"]):
            detected_type = "Hackathon"
        elif any(w in tokens for w in ["meetup", "gathering", "mixer"]):
            detected_type = "Meetup"
        elif any(w in tokens for w in ["summit", "conference", "symposium"]):
            detected_type = "Conference"

        # 4. Date Range
        detected_date = "upcoming"
        if "this weekend" in combined:
            detected_date = "this_weekend"
        elif "this month" in combined:
            detected_date = "this_month"
        elif "next month" in combined:
            detected_date = "next_month"

        # 5. Budget
        detected_budget = "free_or_paid"
        if any(w in tokens for w in ["free", "complimentary", "zero"]):
            detected_budget = "free"
        elif price_match := re.search(r"(?:under|below|<|up to)\s*(?:rs\.?|inr|₹)?\s*(\d+)", combined):
            detected_budget = f"under_{price_match.group(1)}"

        extracted = {
            "intent": "find_event",
            "event_category": detected_category,
            "event_type": detected_type,
            "location": detected_location,
            "date_range": detected_date,
            "budget": detected_budget,
            "confidence": round(confidence, 2),
        }

        return classification, round(confidence, 2), extracted


class EventMatchingEngine:
    """Two-stage deterministic event matching against the 100.com catalog.

    Stage A: a real SQL filter down to published, not-yet-started events —
    not "score everything in the database".
    Stage B: weighted scoring (category 30% / location 25% / date 20% /
    event type 15% / budget 10%, per spec) with every dimension's score
    visible in the response.
    """

    @classmethod
    def match_events(cls, db: Session, intent_data: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
        category_hint = (intent_data.get("event_category") or "").lower()
        location_hint = (intent_data.get("location") or "").lower()
        event_type_hint = (intent_data.get("event_type") or "").lower()
        budget_hint = intent_data.get("budget") or "free_or_paid"

        # Stage A: candidate filter — published and not already over.
        events = db.scalars(
            select(Event)
            .options(
                selectinload(Event.category),
                selectinload(Event.venue).selectinload(Venue.city),
                selectinload(Event.organizer),
            )
            .where(Event.status == "published", Event.start_date >= date.today())
        ).all()

        scored_list: list[tuple[Event, int, list[str], dict[str, int]]] = []

        for ev in events:
            # 1. Category Score (0 - 30) [30% weight]
            cat_score = 18
            reasons = []
            ev_cat_name = ev.category.name.lower() if ev.category else ""
            if category_hint and category_hint in ev_cat_name:
                cat_score = 30
                reasons.append(f"Direct match in {ev.category.name if ev.category else 'domain'}")
            elif any(w in ev.title.lower() for w in category_hint.split()):
                cat_score = 26
                reasons.append("Subject keyword overlap")

            # 2. Location Score (0 - 25) [25% weight]
            loc_score = 8
            ev_city = ev.venue.city.name.lower() if (ev.venue and ev.venue.city) else ""
            if location_hint:
                if location_hint in ev_city:
                    loc_score = 25
                    reasons.append(f"Hosted in {ev.venue.city.name if ev.venue and ev.venue.city else 'target city'}")
                elif ev.format == "online":
                    loc_score = 17
                    reasons.append("Virtual online access")
            else:
                loc_score = 25

            # 3. Date / Freshness Score (0 - 20) [20% weight]
            date_score = 18

            # 4. Event Type Match (0 - 15) [15% weight]
            type_score = 10
            if event_type_hint and event_type_hint in ev.event_type.lower():
                type_score = 15
                reasons.append(f"Exact format match: {ev.event_type}")

            # 5. Budget Match (0 - 10) [10% weight]
            budget_score = 8
            if budget_hint == "free":
                if ev.price == Decimal("0.00"):
                    budget_score = 10
                    reasons.append("Complimentary admission")
                else:
                    budget_score = 0
            elif budget_hint.startswith("under_"):
                max_p = int(budget_hint.split("_")[1])
                if ev.price <= max_p:
                    budget_score = 10
                    reasons.append(f"Under ₹{max_p}")
            else:
                budget_score = 10

            final_event_score = min(cat_score + loc_score + date_score + type_score + budget_score, 99)

            breakdown = {
                "categoryMatch": int(cat_score * 3.33),
                "locationMatch": int(loc_score * 4),
                "dateMatch": int(date_score * 5),
                "eventTypeMatch": int(type_score * 6.66),
                "budgetMatch": int(budget_score * 10),
            }

            scored_list.append((ev, final_event_score, reasons, breakdown))

        scored_list.sort(key=lambda x: x[1], reverse=True)

        # Take top 3 matching events
        top_matches = scored_list[:3]
        if not top_matches:
            return 0, []

        overall_relevance = top_matches[0][1]

        formatted_summaries = []
        for ev, score, reasons, breakdown in top_matches:
            formatted_summaries.append({
                "id": ev.id,
                "title": ev.title,
                "slug": ev.slug,
                "location": ev.venue.city.name if (ev.venue and ev.venue.city) else (ev.venue.address if ev.venue else "Online"),
                "startDate": str(ev.start_date),
                "price": float(ev.price),
                "relevanceScore": score,
                "category": ev.category.name if ev.category else "Technology",
                "matchReasons": reasons[:3] or ["Curated community match"],
                "scoreBreakdown": breakdown,
            })

        return overall_relevance, formatted_summaries


class CommunityRulesChecker:
    """Analyzes community policies to ensure safe, compliant engagement."""

    @classmethod
    def check_rules(cls, community: Community | None) -> dict[str, Any]:
        if not community:
            return {
                "external_links_allowed": True,
                "self_promotion_allowed": False,
                "automation_allowed": False,
                "risk_level": "medium",
                "can_generate_opportunity": True,
            }

        rules_lower = (community.rules_text or "").lower()

        links_allowed = community.external_links_allowed
        if "no links" in rules_lower or "links prohibited" in rules_lower:
            links_allowed = False

        promo_allowed = community.promotion_allowed
        if "no self promotion" in rules_lower or "zero tolerance for promotion" in rules_lower:
            promo_allowed = False

        risk = community.risk_level
        if not links_allowed and not promo_allowed:
            risk = "high"

        return {
            "external_links_allowed": links_allowed,
            "self_promotion_allowed": promo_allowed,
            "automation_allowed": False,  # Always require human approval
            "risk_level": risk,
            "can_generate_opportunity": risk != "high" or links_allowed,
        }


class ResponseGenerationAgent:
    """Deterministic, template-based response generator.

    This is the Reddit-flavored default and the deterministic fallback the
    new pipeline's content-generation stage uses when Claude isn't
    configured — it is never presented as AI-generated (see
    `backend/services/social_agent/pipeline/content_generation.py`,
    `generated_by: "deterministic_fallback"`).
    """

    @classmethod
    def generate_variations(
        cls,
        title: str,
        content: str,
        matched_events: list[dict[str, Any]],
        rules_check: dict[str, Any],
        location: str | None = None,
    ) -> tuple[str, list[str]]:
        if not matched_events:
            return "", []

        ev1 = matched_events[0]
        ev2 = matched_events[1] if len(matched_events) > 1 else None

        loc_str = f" in {location}" if location else ""
        link_allowed = rules_check.get("external_links_allowed", True)

        price_str = "Free admission" if ev1.get("price", 0) == 0 else f"₹{int(ev1['price'])}"

        # Variation 1: Direct, informative & helpful
        if link_allowed:
            v1 = (
                f"There are a few upcoming sessions{loc_str} that align with what you're looking for. "
                f"Specifically, '{ev1['title']}' is happening on {ev1['startDate']} ({price_str}). "
                f"You can check out the agenda and details here: https://100times.in/events/{ev1['slug']}"
            )
        else:
            v1 = (
                f"There are a few upcoming sessions{loc_str} matching your query. "
                f"'{ev1['title']}' is scheduled for {ev1['startDate']} in {ev1['location']}. "
                f"You can search for the organizer on 100 TIMES for the full schedule."
            )

        # Variation 2: Multi-event curated perspective
        if ev2:
            v2 = (
                f"A couple of upcoming gatherings{loc_str} worth checking out: "
                f"'{ev1['title']}' on {ev1['startDate']} focuses on {ev1['category'].lower()}, while '{ev2['title']}' on {ev2['startDate']} also has dedicated networking roundtables. "
                f"Both have active community registrations on 100.com."
            )
        else:
            v2 = (
                f"If you're exploring {ev1['category'].lower()} events{loc_str}, '{ev1['title']}' on {ev1['startDate']} is one of the top rated ones on 100.com this month. "
                f"It includes structured peer sessions and speaker deep-dives."
            )

        # Variation 3: Concise recommendation
        v3 = (
            f"Check out '{ev1['title']}' on {ev1['startDate']}{loc_str}. "
            f"It matches your focus on {ev1['category'].lower()} and is {price_str}."
        )

        return v1, [v1, v2, v3]


class AgentOrchestrator:
    """Backward-compatible entry point for the Demand Capture pipeline.

    This is now a thin wrapper over `backend.services.social_agent.pipeline
    .orchestrator.run_pipeline` (state machine + real AI intent extraction +
    deterministic qualification/matching/policy + AI content generation).
    Kept as a classmethod with this exact signature so existing callers
    (routes, seed.py) don't need to change.
    """

    @classmethod
    def process_discussion(
        cls,
        db: Session,
        platform: str,
        community_name: str,
        title: str,
        content: str,
        url: str = "",
        external_id: str | None = None,
        author: str | None = None,
    ) -> AcquisitionOpportunity | None:
        from backend.services.social_agent.pipeline.orchestrator import run_pipeline

        return run_pipeline(
            db=db,
            platform=platform,
            community_name=community_name,
            title=title,
            content=content,
            url=url,
            external_id=external_id,
            author=author,
        )
