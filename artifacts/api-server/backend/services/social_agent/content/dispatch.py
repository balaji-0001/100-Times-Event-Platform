"""Picks the right platform-flavored content generator.

Reddit keeps using the original `ResponseGenerationAgent` (helpful discussion
reply) that the pipeline already ships with. Every other discussion platform
gets its own tone/format. Instagram is handled separately via
`InstagramContentAgent.generate_theme_pack` since it's a content-distribution
flow, not a discussion-reply flow.
"""

from backend.services.acquisition_agent import ResponseGenerationAgent
from backend.services.social_agent.content.discord import DiscordContentGenerator
from backend.services.social_agent.content.linkedin import LinkedInContentGenerator
from backend.services.social_agent.content.telegram import TelegramContentGenerator
from backend.services.social_agent.content.x import XContentGenerator

_DISPATCH = {
    "discord": DiscordContentGenerator,
    "telegram": TelegramContentGenerator,
    "x": XContentGenerator,
    "linkedin": LinkedInContentGenerator,
}


def get_content_generator(platform: str):
    """Returns a class exposing `generate_variations(title, content, matched_events,
    rules_check, location) -> (primary, variations)`. Falls back to the Reddit-style
    generic generator for reddit/forum/meetup/unknown platforms."""
    return _DISPATCH.get(platform, ResponseGenerationAgent)
