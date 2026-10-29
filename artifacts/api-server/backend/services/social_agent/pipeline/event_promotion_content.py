"""Platform-specific content generation and UTM tracking pipeline for Event Promotion.

Crafts tailored promotional copy for Instagram, Facebook Pages, LinkedIn,
Telegram, and Discord with UTM attribution tracking.
Maintains the project-wide "no AI required" rule with high-quality deterministic
templates and AI-first enhancement when configured.
"""

from datetime import date
from typing import Any
from urllib.parse import urlencode

from pydantic import BaseModel, Field
from backend.core.config import get_settings
from backend.models import Event
from backend.services.social_agent.ai_client import AIClientError, get_ai_client


def build_utm_tracking_url(event: Event, platform: str, app_base_url: str | None = None) -> tuple[str, dict[str, str]]:
    """Builds an event destination URL with normalized UTM tracking parameters."""
    settings = get_settings()
    base = (app_base_url or settings.platform_listing_url or "https://100times.in").rstrip("/")
    slug = event.slug or str(event.id)
    
    utm_params = {
        "utm_source": platform.lower().strip(),
        "utm_medium": "social",
        "utm_campaign": f"event_{event.id}",
        "utm_content": "event_promo",
    }
    query_string = urlencode(utm_params)
    tracking_url = f"{base}/events/{slug}?{query_string}"
    return tracking_url, utm_params


def public_media(event: Event) -> list[str]:
    """The event picture as a full web address a social platform can fetch.
    Pictures stored on this site (`/event-images/...`, `/uploads/...`) are
    served from the same public site the promotion links point to."""
    image = (event.image or "").strip()
    if image.startswith(("https://", "http://")):
        return [image]
    if image.startswith("/"):
        settings = get_settings()
        base = (settings.public_base_url or settings.platform_listing_url or "").rstrip("/")
        return [f"{base}{image}"] if base.startswith(("https://", "http://")) else []
    return []


def _format_event_details(event: Event) -> tuple[str, str, str, str]:
    when = event.start_date.strftime("%A, %d %B %Y") if event.start_date else "Coming Soon"
    start_time = getattr(event, "start_time", "09:30 AM") or "09:30 AM"
    
    if event.format == "online":
        where = "Online / Virtual Conference"
    else:
        city = event.city_name or (event.venue.city.name if event.venue and event.venue.city else "In-Person")
        venue_name = event.venue.name if event.venue else (event.full_address or "")
        where = f"{venue_name}, {city}".strip(", ") if venue_name else city
        
    price_str = "Free Admission" if (event.is_free or float(event.price or 0) == 0) else f"₹{float(event.price):,.2f}"
    return when, start_time, where, price_str


def _clean_category_tag(cat_name: str | None) -> str:
    if not cat_name:
        return "Events"
    return "".join(c for c in cat_name.title() if c.isalnum())


def _deterministic_instagram_post(event: Event, tracking_url: str) -> dict[str, Any]:
    when, start_time, where, price = _format_event_details(event)
    cat_tag = _clean_category_tag(event.category.name if event.category else "Events")
    city_tag = _clean_category_tag(event.city_name or "India")
    desc = (event.description or "").strip()[:240]

    content = (
        f"✨ UPCOMING EVENT: {event.title} ✨\n\n"
        f"📅 Date: {when}\n"
        f"⏰ Time: {start_time}\n"
        f"📍 Location: {where}\n"
        f"🎟️ Tickets: {price}\n\n"
        f"{desc}...\n\n"
        f"👉 Tap the link in bio or register directly at 100times.in\n"
        f"🔗 {tracking_url}\n\n"
        f"#100Times #{cat_tag} #{city_tag}Events #IndiaEvents #Networking"
    )
    media = public_media(event)
    return {"title": f"Instagram Promo: {event.title}", "content": content, "media_urls": media}


def _deterministic_facebook_post(event: Event, tracking_url: str) -> dict[str, Any]:
    when, start_time, where, price = _format_event_details(event)
    desc = (event.description or "").strip()[:350]

    content = (
        f"📣 Announcement: {event.title}\n\n"
        f"{desc}\n\n"
        f"📌 Event Details:\n"
        f"• When: {when} at {start_time}\n"
        f"• Where: {where}\n"
        f"• Category: {event.category.name if event.category else 'General'}\n"
        f"• Access: {price}\n\n"
        f"Reserve your spot today: {tracking_url}\n\n"
        f"Will you be joining us? Tag colleagues or friends who would benefit from attending!"
    )
    media = public_media(event)
    return {"title": f"Facebook Post: {event.title}", "content": content, "media_urls": media}


def _deterministic_linkedin_post(event: Event, tracking_url: str) -> dict[str, Any]:
    when, start_time, where, price = _format_event_details(event)
    category = event.category.name if event.category else "Industry Leaders"
    cat_tag = _clean_category_tag(category)
    desc = (event.description or "").strip()[:380]

    content = (
        f"Excited to highlight an impactful upcoming opportunity for professionals in {category}: {event.title}.\n\n"
        f"{desc}\n\n"
        f"Key Event Takeaways & Logistics:\n"
        f"• Schedule: {when} | {start_time}\n"
        f"• Format & Venue: {where}\n"
        f"• Admission: {price}\n"
        f"• Organizer: {event.organizer.name if event.organizer else '100 TIMES Host'}\n\n"
        f"Learn more and secure your registration here: {tracking_url}\n\n"
        f"#ProfessionalDevelopment #{cat_tag} #Leadership #Networking #100Times"
    )
    media = public_media(event)
    return {"title": f"LinkedIn Update: {event.title}", "content": content, "media_urls": media}


def _deterministic_telegram_post(event: Event, tracking_url: str) -> dict[str, Any]:
    when, start_time, where, price = _format_event_details(event)
    desc = (event.description or "").strip()[:280]

    content = (
        f"🚀 *{event.title}*\n\n"
        f"📅 *Date:* {when}\n"
        f"⏰ *Time:* {start_time}\n"
        f"📍 *Venue:* {where}\n"
        f"🏷️ *Category:* {event.category.name if event.category else 'General'}\n"
        f"🎟️ *Passes:* {price}\n\n"
        f"{desc}\n\n"
        f"🔗 [Register & View Full Schedule]({tracking_url})"
    )
    media = public_media(event)
    return {"title": f"Telegram Broadcast: {event.title}", "content": content, "media_urls": media}


def _deterministic_discord_post(event: Event, tracking_url: str) -> dict[str, Any]:
    when, start_time, where, price = _format_event_details(event)
    desc = (event.description or "").strip()[:300]

    content = (
        f"📢 **NEW EVENT ANNOUNCEMENT: {event.title}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 **Date & Time:** {when} at {start_time}\n"
        f"📍 **Format / Venue:** {where}\n"
        f"🏷️ **Category:** {event.category.name if event.category else 'General'}\n"
        f"🎟️ **Admission:** {price}\n\n"
        f"{desc}\n\n"
        f"👉 **RSVP & Event Details:** <{tracking_url}>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    media = public_media(event)
    return {"title": f"Discord Announcement: {event.title}", "content": content, "media_urls": media}


class PromotionAICopy(BaseModel):
    title: str = Field(description="Catchy headline for the post")
    content: str = Field(description="Full platform-tailored promotional copy including tracking link and hashtags")


def generate_platform_promotion_content(event: Event, platform: str, tracking_url: str) -> dict[str, Any]:
    """Generates tailored copy for the given social platform.
    
    Attempts AI generation if AIClient is configured; otherwise immediately
    uses the platform's deterministic template.
    """
    platform_key = platform.lower().strip()
    client = get_ai_client()

    if client.is_configured:
        try:
            platform_guidelines = {
                "instagram": "Visual, emojis, hook, clear key details, link in bio CTA, curated hashtags including #100Times.",
                "facebook": "Engaging community tone, highlights, call to action, question for discussion.",
                "linkedin": "Executive, professional tone, value proposition, industry focus, professional hashtags including #100Times.",
                "telegram": "Telegram Markdown format with bold labels, emojis, clean bullet points, inline link.",
                "discord": "Discord markdown formatting, bold headers, divider line, clean RSVP link.",
            }.get(platform_key, "Engaging and informative promotional announcement.")

            system_prompt = (
                f"You are a professional social media marketing agent writing an event promotion post for {platform_key.upper()}.\n"
                f"Guidelines: {platform_guidelines}\n"
                f"CRITICAL: Always include the tracking link: {tracking_url}\n"
                f"CRITICAL: Always include the brand hashtag #100Times in the hashtags.\n"
                f"Never fabricate false details. Use only the event facts provided."
            )
            user_prompt = (
                f"<untrusted_post>\n"
                f"Title: {event.title}\n"
                f"Description: {event.description or ''}\n"
                f"Date: {event.start_date}\n"
                f"Time: {event.start_time or '09:30 AM'}\n"
                f"Format: {event.format}\n"
                f"City: {event.city_name or 'Online'}\n"
                f"Category: {event.category.name if event.category else 'General'}\n"
                f"Price: {'Free' if event.is_free else event.price}\n"
                f"Tracking Link: {tracking_url}\n"
                f"</untrusted_post>"
            )

            raw = client.generate_structured(
                system=system_prompt,
                user=user_prompt,
                tool_name="generate_social_promotion_post",
                tool_description=f"Generate tailored event promotion copy for {platform_key}",
                input_schema=PromotionAICopy.model_json_schema(),
            )
            parsed = PromotionAICopy.model_validate(raw)
            content_text = parsed.content
            if platform_key in ("instagram", "linkedin") and "#100Times" not in content_text:
                content_text = f"{content_text.rstrip()}\n\n#100Times"

            media = public_media(event)
            return {
                "title": parsed.title,
                "content": content_text,
                "media_urls": media,
                "generated_by": "ai",
            }
        except (AIClientError, Exception):
            pass  # Fall through to deterministic template

    dispatchers = {
        "instagram": _deterministic_instagram_post,
        "facebook": _deterministic_facebook_post,
        "linkedin": _deterministic_linkedin_post,
        "telegram": _deterministic_telegram_post,
        "discord": _deterministic_discord_post,
    }
    dispatcher = dispatchers.get(platform_key, _deterministic_facebook_post)
    result = dispatcher(event, tracking_url)
    result["generated_by"] = "deterministic"
    return result

