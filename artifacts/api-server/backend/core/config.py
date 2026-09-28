from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_API_SERVER_DIR = Path(__file__).resolve().parent.parent.parent
_ENV_PATHS = (
    ".env",
    str(_API_SERVER_DIR / ".env"),
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
    telegram_bot_token: str | None = None
    x_bearer_token: str | None = None  # app-only bearer — read/discovery side only
    x_api_key: str | None = None  # OAuth2 client id — needed for the publish-side user-context flow, once X approves commercial access
    x_api_secret: str | None = None
    linkedin_access_token: str | None = None
    linkedin_client_id: str | None = None  # needed for the Community Management API OAuth flow, once LinkedIn approves the API product
    linkedin_client_secret: str | None = None
    instagram_access_token: str | None = None
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

    # Event Discovery & Organizer Research Agent ("Agent 1") — broad web
    # search (the configured provider's web-search tool, via ai_client.py) for
    # events across India, independent of the social-listening pipeline.
    # Comma-separated lists, same style as `cors_origins`.
    discovery_target_cities: str = (
        "Mumbai,Delhi,Bengaluru,Hyderabad,Chennai,Kolkata,Pune,Ahmedabad,"
        "Jaipur,Chandigarh,Kochi,Indore,Lucknow,Surat,Nagpur"
    )
    discovery_target_states: str = (
        "Maharashtra,Delhi,Karnataka,Telangana,Tamil Nadu,West Bengal,Gujarat,"
        "Rajasthan,Punjab,Kerala,Madhya Pradesh,Uttar Pradesh"
    )
    discovery_target_categories: str = (
        "Technology,Business,Startup,Healthcare,Finance,Education,Career,"
        "Arts & Culture,Music,Sports"
    )
    discovery_search_depth: int = 40  # max search queries issued per run
    discovery_sources_per_query: int = 5  # max candidate URLs pulled from each query
    discovery_daily_limit: int = 200  # max new DiscoveredEvent rows created per day
    discovery_confidence_threshold: int = 60  # below this -> verification_status=NEEDS_REVIEW
    discovery_scan_interval_minutes: int = 60

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
            "postgres://",
            "postgresql://",
            "postgresql+psycopg://",
            "sqlite://",
        )
        if not value.startswith(supported_prefixes):
            raise ValueError(
                "DATABASE_URL must use PostgreSQL (postgresql:// or "
                "postgresql+psycopg://) or SQLite (sqlite:///...)"
            )
        return value

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
