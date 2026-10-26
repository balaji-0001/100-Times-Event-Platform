from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_API_SERVER_DIR = Path(__file__).resolve().parent.parent.parent
_ENV_PATHS = (
    ".env",
    str(_API_SERVER_DIR / ".env"),
    str(_API_SERVER_DIR.parent / ".env"),
    str(_API_SERVER_DIR.parent.parent / ".env"),
    str(_API_SERVER_DIR.parent.parent.parent / ".env"),
    str(Path(__file__).resolve().parent.parent / ".env"),
)


class Settings(BaseSettings):
    app_name: str = "100 TIMES API"
    environment: str = "development"
    database_url: str = "sqlite:///./100times-dev.db"
    jwt_secret: str = "dev-insecure-secret-key-100times-development"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    cors_origins: str = "*"
    auto_create_schema: bool = True
    seed_demo_data: bool = True

    # Social Media Attendee Acquisition Agent — platform credentials.
    # Every connector runs in mock mode until its credential below is set;
    # no code changes are needed to "go live" once a real credential exists.
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_redirect_uri: str | None = None  # used only for the one-time refresh-token setup script, not a live callback route
    discord_bot_token: str | None = None
    discord_user_token: str | None = None  # User account token for automated posting into joined Discord communities
    telegram_bot_token: str | None = None
    telegram_api_id: int | None = None  # Telegram MTProto User Client API ID (from my.telegram.org)
    telegram_api_hash: str | None = None  # Telegram MTProto User Client API Hash
    telegram_session_string: str | None = None  # Telethon string session for user account automation
    telegram_phone: str | None = None
    x_bearer_token: str | None = None  # app-only bearer — read/discovery side only
    x_api_key: str | None = None  # OAuth2 client id — needed for the publish-side user-context flow, once X approves commercial access
    x_api_secret: str | None = None
    linkedin_access_token: str | None = None
    linkedin_client_id: str | None = None  # needed for the Community Management API OAuth flow, once LinkedIn approves the API product
    linkedin_client_secret: str | None = None
    linkedin_organization_id: str | None = None
    instagram_access_token: str | None = None
    instagram_business_account_id: str | None = None
    facebook_page_access_token: str | None = None
    facebook_page_id: str | None = None
    discord_promotion_webhook_url: str | None = None
    telegram_promotion_channel_id: str | None = None
    auto_promotion_enabled: bool = True
    auto_promotion_dry_run_default: bool = True
    auto_promotion_require_approval: bool = True
    auto_promotion_platforms: str = "instagram,facebook,linkedin,telegram,discord"
    social_agent_daily_cap_per_platform: int = 25

    # n8n orchestration layer (see infra/n8n/README.md). Not read by FastAPI
    # itself today — n8n calls FastAPI, not the other way around — kept here
    # so it's documented alongside every other external-service credential.
    n8n_url: str = "http://localhost:5678"
    n8n_encryption_key: str | None = None

    # AI provider for every LLM-backed stage (discovery web research, page
    # extraction, outreach drafting, social intent/content generation). Only
    # services/social_agent/ai_client.py touches a vendor SDK; the rest of the
    # app is provider-agnostic. "gemini" (Google, default) or "anthropic"
    # (Claude). Whichever is selected, a missing key makes AI-dependent stages
    # fail honestly (FAILED_AI_EXTRACTION / failed AgentRun) — never a silent
    # regex fallback pretending to be AI. Keys are never logged or returned.
    ai_provider: str = "gemini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-lite-latest"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"

    # Attribution window for tying a registration back to the click that drove it.
    click_attribution_window_days: int = 30

    # Base URL this backend is actually reachable at — used to build the real
    # /r/{opportunity_id} click-tracking redirect links.
    app_base_url: str = "http://127.0.0.1:8000"

    # Organizer Outreach — automated supply-side acquisition (inviting the
    # organizer of an externally-discovered event to list it on 100.com).
    # Gate on match_score (see pipeline/event_extraction.py's confidence/
    # relevance scores) and keep outreach volume configurable per the same
    # honesty rules as the rest of the agent: no sending below threshold, no
    # sending without a verified public contact, no duplicate initial sends.
    outreach_match_threshold: int = 80
    outreach_daily_cap: int = 10
    outreach_followup_days: int = 7
    organizer_discovery_max_seeds_per_cycle: int = 3
    # Public URL organizers use to list an event on 100Times — included in every outreach email.
    platform_listing_url: str = "https://100times.in"
    outreach_max_candidates_per_run: int = 20
    # How often Agent 2's scheduled draft tick runs when its own live toggle
    # (`services/social_agent/outreach/auto_toggle.py`, admin-flipped, no
    # restart needed — same pattern as discovery_scan_interval_minutes
    # below) is on. Each tick only drafts candidates to PENDING_APPROVAL;
    # nothing is ever auto-sent.
    outreach_scan_interval_minutes: int = 60

    # Event Discovery & Organizer Research Agent ("Agent 1") — broad web
    # search (the configured provider's web-search tool, via ai_client.py) for
    # events worldwide across all countries, regions, and major cities.
    # Comma-separated lists, same style as `cors_origins`.
    discovery_target_countries: str = (
        "United States,United Kingdom,Germany,India,Canada,Australia,France,"
        "Singapore,Japan,United Arab Emirates,Brazil,Netherlands,Switzerland,Spain,Italy"
    )
    discovery_target_cities: str = (
        "London,New York,San Francisco,Singapore,Tokyo,Dubai,Sydney,Toronto,"
        "Berlin,Paris,Bengaluru,Mumbai,Delhi,Amsterdam,Chicago,Frankfurt"
    )
    discovery_target_states: str = (
        "California,New York,England,Maharashtra,Karnataka,Bavaria,Ontario,"
        "New South Wales,Tokyo Prefecture,Dubai Emirate,Île-de-France"
    )
    discovery_target_categories: str = (
        "Pharmaceuticals,Healthcare,Energy and Power Generation,"
        "Telecommunications,Construction,Mining,Finance,Packaging,Transport and Logistics,"
        "Oil and Gas,Textiles,Manufacturing"
    )
    discovery_search_depth: int = 40  # max search queries issued per run
    discovery_sources_per_query: int = 5  # max candidate URLs pulled from each query
    discovery_daily_limit: int = 200  # max new DiscoveredEvent rows created per day
    discovery_confidence_threshold: int = 60  # below this -> verification_status=NEEDS_REVIEW
    discovery_scan_interval_minutes: int = 60
    discovery_require_organizer_email: bool = False
    # Re-open pages that come back empty/thin (JavaScript-rendered sites) in
    # headless Chromium via Playwright. Needs `playwright install chromium`;
    # without it discovery silently keeps the plain HTTP result.
    discovery_browser_fetch: bool = True
    # Public listing pages read directly from their schema.org data — this
    # is how discovery finds events with no AI key. `{city}` expands once per
    # DISCOVERY_TARGET_CITIES entry. Empty = AI web search only.
    discovery_listing_urls: str = (
        "https://dev.events/,"
        "https://allevents.in/{city},"
        "https://www.eventbrite.com/d/{country}--{city}/events/,"
        "https://www.eventbrite.com/d/{city}/events/,"
        "https://www.meetup.com/find/?location={city}&source=EVENTS,"
        "https://10times.com/{city},"
        "https://www.skillboxes.com/events"
    )
    discovery_events_per_listing: int = 25
    ticketmaster_api_key: str | None = None
    ticketmaster_enabled: bool = False

    # Community Discovery Agent ("Agent 5") — public web search (same DuckDuckGo
    # approach as Agent 1, no AI key required) for Telegram groups/channels and
    # Discord servers relevant to 100Times' event categories. Reuses
    # discovery_target_cities/states/categories above as its default scope.
    community_discovery_search_depth: int = 30  # max search queries issued per run
    community_discovery_sources_per_query: int = 5  # max candidate URLs pulled from each query
    community_discovery_daily_limit: int = 100  # max new DiscoveredCommunity rows created per day
    community_discovery_confidence_threshold: int = 60  # below this -> approval_status=NEEDS_REVIEW
    community_discovery_scan_interval_minutes: int = 60

    # Agent 4 extension — Community Promotion (event x approved-community matching,
    # drafting standalone posts; publishing stays human-approval-gated, same as
    # outreach). Reuses outreach_scan_interval_minutes-style cadence.
    community_promotion_max_candidates_per_run: int = 20
    community_promotion_scan_interval_minutes: int = 60
    community_promotion_match_threshold: int = 60  # min score to draft a post

    # Background scheduler — makes both agents run continuously without any
    # manual dashboard trigger (n8n's Schedule Trigger workflows remain a
    # valid alternative/parity option; this in-process loop is what makes
    # "automatic" true out of the box, with no Docker/n8n required). Set
    # ENABLE_BACKGROUND_SCHEDULER=false to rely on n8n (or manual triggers)
    # instead, so the two don't double-fire.
    # Off by default: agents run only when an admin triggers them from the console. Set true to
    # restore the timed loops (discovery, both social scans, follow-up sweep) — each spends API credits.
    enable_background_scheduler: bool = False
    attendee_scan_interval_minutes: int = 15
    organizer_scan_interval_minutes: int = 30
    outreach_followup_interval_minutes: int = 1440
    # Attendee notification sweep (reminders, deadlines, changes, new matches).
    # The loop always runs; each tick is a no-op unless the admin toggle is on.
    attendee_notifications_interval_minutes: int = 60

    # Email sending for Organizer Outreach. No SMTP credential -> the
    # provider factory in services/social_agent/outreach/senders falls back
    # to MockEmailProvider (logs only, never claims a fake send succeeded
    # against a real inbox).
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_tls: bool = True

    # n8n Webhook & Automation security
    n8n_webhook_secret: str = "dev-n8n-webhook-secret-100times"
    n8n_webhooks_enabled: bool = False
    calendar_provider: str = "ics"  # ics | google | outlook

    # Trust Agent (Agent 3) thresholds
    trust_agent_auto_approve_score: int = 75
    trust_agent_min_description_length: int = 25
    trust_agent_max_daily_submissions_per_organizer: int = 10

    # Organizer & Attendee follow-up settings
    organizer_followup_max_attempts: int = 3
    organizer_followup_first_wait_days: int = 1
    organizer_followup_second_wait_days: int = 2

    model_config = SettingsConfigDict(env_file=_ENV_PATHS, extra="ignore")

    @field_validator("ai_provider")
    @classmethod
    def validate_ai_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ("gemini", "anthropic"):
            raise ValueError("AI_PROVIDER must be 'gemini' or 'anthropic'")
        return normalized

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        """Accept the SQLAlchemy URLs supported by this application."""
        supported_prefixes = (
            "mysql://",
            "mysql+pymysql://",
            "sqlite://",
        )
        if not value.startswith(supported_prefixes):
            raise ValueError(
                "DATABASE_URL must use MySQL (mysql:// or mysql+pymysql://) or SQLite (sqlite:///...)"
            )
        return value

    @model_validator(mode="after")
    def validate_production_hardening(self) -> "Settings":
        if self.environment.lower() == "production":
            insecure_jwt_defaults = {
                "dev-insecure-secret-key-100times-development",
                "insecure-dev-jwt-secret-change-in-prod-please-use-strong-secret-key",
                "secret",
                "changeme",
                "test-secret",
            }
            if not self.jwt_secret or self.jwt_secret in insecure_jwt_defaults or len(self.jwt_secret) < 32:
                raise ValueError(
                    "In production, JWT_SECRET must be set to a strong, high-entropy secret with at least 32 characters."
                )

            insecure_webhook_defaults = {
                "dev-n8n-webhook-secret-100times",
                "dev-webhook-secret-change-in-production",
                "secret",
                "changeme",
            }
            if self.n8n_webhooks_enabled and (
                not self.n8n_webhook_secret or self.n8n_webhook_secret in insecure_webhook_defaults or len(self.n8n_webhook_secret) < 16
            ):
                raise ValueError(
                    "In production when N8N_WEBHOOKS_ENABLED is true, N8N_WEBHOOK_SECRET must be set to a strong secret key."
                )

            if self.cors_origins.strip() == "*":
                raise ValueError(
                    "In production, CORS_ORIGINS cannot be '*' (wildcard). Set explicit trusted domains."
                )

            if self.seed_demo_data:
                raise ValueError(
                    "In production, SEED_DEMO_DATA must be false to prevent demo user credentials from being seeded."
                )

        return self

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def cors_origin_regex(self) -> str | None:
        """Allow any local Vite port when the development wildcard is enabled."""
        if self.environment == "development" and self.cors_origins.strip() == "*":
            return r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
