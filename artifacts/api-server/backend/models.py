from datetime import date, datetime
from datetime import date as _Date  # alias for annotations inside classes that also have a field literally named `date`
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.types import JSON, TypeDecorator

from backend.db import Base


class StringList(TypeDecorator):
    """Use native PostgreSQL arrays while keeping SQLite-based tests portable."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(ARRAY(Text) if dialect.name == "postgresql" else JSON())


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, default="USER", nullable=False)
    country: Mapped[str | None] = mapped_column(Text)
    job_title: Mapped[str | None] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(Text)
    bio: Mapped[str | None] = mapped_column(Text)
    profile_image: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    registrations: Mapped[list["Registration"]] = relationship(back_populates="user")
    saved_events: Mapped[list["SavedEvent"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    reviews: Mapped[list["Review"]] = relationship(back_populates="user")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    schedule_items: Mapped[list["ScheduleItem"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str] = mapped_column(Text, nullable=False)
    image: Mapped[str | None] = mapped_column(Text)
    events: Mapped[list["Event"]] = relationship(back_populates="category")


class City(Base):
    __tablename__ = "cities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    country: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    image: Mapped[str | None] = mapped_column(Text)
    venues: Mapped[list["Venue"]] = relationship(back_populates="city")


class Organizer(Base):
    __tablename__ = "organizers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    logo: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    events: Mapped[list["Event"]] = relationship(back_populates="organizer")


class Venue(Base):
    __tablename__ = "venues"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id"))
    country: Mapped[str] = mapped_column(Text, nullable=False)
    capacity: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    image: Mapped[str | None] = mapped_column(Text)
    city: Mapped[City | None] = relationship(back_populates="venues")
    events: Mapped[list["Event"]] = relationship(back_populates="venue")


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[str] = mapped_column(Text, nullable=False)
    end_time: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    image: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="draft", nullable=False)
    format: Mapped[str] = mapped_column(Text, default="in-person", nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    organizer_id: Mapped[int | None] = mapped_column(ForeignKey("organizers.id"))
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    category: Mapped[Category | None] = relationship(back_populates="events")
    organizer: Mapped[Organizer | None] = relationship(back_populates="events")
    venue: Mapped[Venue | None] = relationship(back_populates="events")
    registrations: Mapped[list["Registration"]] = relationship(back_populates="event")
    saved_by: Mapped[list["SavedEvent"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    reviews: Mapped[list["Review"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class Speaker(Base):
    __tablename__ = "speakers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    biography: Mapped[str | None] = mapped_column(Text)
    image: Mapped[str | None] = mapped_column(Text)
    expertise: Mapped[list[str]] = mapped_column(StringList, default=list, nullable=False)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    event: Mapped[Event] = relationship(back_populates="reviews")
    user: Mapped[User] = relationship(back_populates="reviews")
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="reviews_event_user_idx"),)


class Registration(Base):
    __tablename__ = "registrations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    ticket_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="confirmed", nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    event: Mapped[Event] = relationship(back_populates="registrations")
    user: Mapped[User] = relationship(back_populates="registrations")
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="registrations_event_user_idx"),)


class SavedEvent(Base):
    __tablename__ = "saved_events"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    user: Mapped[User] = relationship(back_populates="saved_events")
    event: Mapped[Event] = relationship(back_populates="saved_by")


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    user: Mapped[User] = relationship(back_populates="notifications")


class Connection(Base):
    __tablename__ = "connections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    addressee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    requester: Mapped[User] = relationship("User", foreign_keys=[requester_id])
    addressee: Mapped[User] = relationship("User", foreign_keys=[addressee_id])
    __table_args__ = (UniqueConstraint("requester_id", "addressee_id", name="connections_requester_addressee_idx"),)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    sender: Mapped[User] = relationship("User", foreign_keys=[sender_id])
    recipient: Mapped[User] = relationship("User", foreign_keys=[recipient_id])


class ScheduleItem(Base):
    __tablename__ = "schedule_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    session_title: Mapped[str] = mapped_column(Text, nullable=False)
    session_time: Mapped[str] = mapped_column(Text, nullable=False)
    session_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    user: Mapped[User] = relationship("User", back_populates="schedule_items")
    event: Mapped["Event"] = relationship("Event")
    __table_args__ = (UniqueConstraint("user_id", "event_id", "session_title", name="schedule_items_user_event_session_idx"),)


class Community(Base):
    __tablename__ = "communities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    rules_text: Mapped[str | None] = mapped_column(Text)
    promotion_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    external_links_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    automation_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    quality_score: Mapped[int] = mapped_column(Integer, default=85, nullable=False)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    discussions: Mapped[list["Discussion"]] = relationship(back_populates="community", cascade="all, delete-orphan")


class Discussion(Base):
    __tablename__ = "discussions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    community_id: Mapped[int | None] = mapped_column(ForeignKey("communities.id"))
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    intent_classification: Mapped[str] = mapped_column(String(30), default="IRRELEVANT", nullable=False)
    intent_confidence: Mapped[float] = mapped_column(Numeric(4, 2), default=0.0, nullable=False)
    extracted_intent: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    # --- Pipeline architecture (state machine + real AI extraction) ---
    pipeline_status: Mapped[str] = mapped_column(String(40), default="DISCOVERED", nullable=False)
    ai_intent: Mapped[dict | None] = mapped_column(JSON)  # raw ExtractedIntentAI structured output
    qualification_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    qualification_breakdown: Mapped[dict | None] = mapped_column(JSON)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    ai_extraction_retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    community: Mapped[Community | None] = relationship(back_populates="discussions")
    opportunities: Mapped[list["AcquisitionOpportunity"]] = relationship(back_populates="discussion", cascade="all, delete-orphan")
    pipeline_executions: Mapped[list["PipelineExecution"]] = relationship(back_populates="discussion", cascade="all, delete-orphan")


class AcquisitionOpportunity(Base):
    __tablename__ = "acquisition_opportunities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discussion_id: Mapped[int] = mapped_column(ForeignKey("discussions.id"), nullable=False)
    matching_events: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    relevance_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generated_response: Mapped[str] = mapped_column(Text, nullable=False)
    response_variations: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    content_payload: Mapped[dict | None] = mapped_column(JSON)
    content_generated_by: Mapped[str | None] = mapped_column(String(30))  # "ai" | "deterministic_fallback"
    policy_notes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_url: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    discussion: Mapped[Discussion] = relationship(back_populates="opportunities")
    actions: Mapped[list["AgentAction"]] = relationship(back_populates="opportunity", cascade="all, delete-orphan")
    referral_events: Mapped[list["AcquisitionReferralEvent"]] = relationship(back_populates="opportunity", cascade="all, delete-orphan")
    click_events: Mapped[list["ClickEvent"]] = relationship(back_populates="opportunity", cascade="all, delete-orphan")


class AgentAction(Base):
    __tablename__ = "agent_actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("acquisition_opportunities.id"))
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    result: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    opportunity: Mapped[AcquisitionOpportunity | None] = relationship(back_populates="actions")


class AcquisitionReferralEvent(Base):
    __tablename__ = "acquisition_referral_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("acquisition_opportunities.id"), nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"))
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)  # "click", "visit", "registration"
    visitor_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    opportunity: Mapped[AcquisitionOpportunity] = relationship(back_populates="referral_events")
    event: Mapped[Event | None] = relationship("Event")


class PipelineExecution(Base):
    """One row per orchestrator run over a Discussion — the top of the
    Debug Pipeline View's timeline."""

    __tablename__ = "pipeline_executions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discussion_id: Mapped[int] = mapped_column(ForeignKey("discussions.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_status: Mapped[str | None] = mapped_column(String(40))
    discussion: Mapped[Discussion] = relationship(back_populates="pipeline_executions")
    stage_logs: Mapped[list["PipelineStageLog"]] = relationship(back_populates="execution", cascade="all, delete-orphan")


class PipelineStageLog(Base):
    """One row per pipeline stage attempt — powers the ✓/✗ timeline."""

    __tablename__ = "pipeline_stage_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipeline_execution_id: Mapped[int] = mapped_column(ForeignKey("pipeline_executions.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success | failed | skipped
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    execution: Mapped[PipelineExecution] = relationship(back_populates="stage_logs")


class ClickEvent(Base):
    """Real click tracking, written by the `/r/{opportunity_id}` backend
    redirect route — not a manually-POSTed simulation."""

    __tablename__ = "click_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("acquisition_opportunities.id"), nullable=False)
    anonymous_session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    destination_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    opportunity: Mapped[AcquisitionOpportunity] = relationship(back_populates="click_events")


class RegistrationAttribution(Base):
    """Links a real Registration back to the click (and therefore the
    opportunity) that drove it, within the configured attribution window."""

    __tablename__ = "registration_attributions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registrations.id"), nullable=False)
    click_id: Mapped[int] = mapped_column(ForeignKey("click_events.id"), nullable=False)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("acquisition_opportunities.id"), nullable=False)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    registration: Mapped[Registration] = relationship("Registration")
    click: Mapped[ClickEvent] = relationship("ClickEvent")
    opportunity: Mapped[AcquisitionOpportunity] = relationship("AcquisitionOpportunity")
    event: Mapped[Event] = relationship("Event")


class DiscoveredOrganizer(Base):
    """An external event organizer identified either by Organizer Outreach's
    public-page lookup (`discovered_by="social_pipeline"`) or by the Event
    Discovery Agent's broad web search (`discovered_by="web_discovery_agent"`)
    — NOT the same as `Organizer` (that table holds organizers already
    onboarded to 100.com with real, published `Event` rows). This is an
    unverified lead until a human explicitly promotes/contacts them."""

    __tablename__ = "discovered_organizers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text, index=True)
    website: Mapped[str | None] = mapped_column(Text)
    linkedin: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # individual | company | college | association | government | other — best-effort, null until classified.
    organizer_type: Mapped[str | None] = mapped_column(String(30))
    city: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    discovered_events: Mapped[list["DiscoveredEvent"]] = relationship(back_populates="organizer")
    contacts: Mapped[list["OrganizerContact"]] = relationship(back_populates="organizer", cascade="all, delete-orphan")


class DiscoveredEvent(Base):
    """An external, not-yet-onboarded event — either extracted from a
    discussion/candidate post by the social pipeline's Case B branch, or
    found directly on the open web by the Event Discovery Agent
    (`discovered_by="web_discovery_agent"`). The prospect record Organizer
    Outreach acts on. Deliberately separate from the platform's own `Event`
    table since this event isn't real 100.com inventory until an organizer
    actually lists it (or an admin explicitly promotes this record)."""

    __tablename__ = "discovered_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discussion_id: Mapped[int | None] = mapped_column(ForeignKey("discussions.id"))
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("acquisition_opportunities.id"))
    name: Mapped[str | None] = mapped_column(Text)
    event_description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    subcategory: Mapped[str | None] = mapped_column(Text)
    # Free-text as originally extracted (kept for backward compat with the social pipeline).
    date: Mapped[str | None] = mapped_column(Text)
    # Parsed real date, when validation.py could confidently parse `date` — never guessed.
    event_date: Mapped[_Date | None] = mapped_column(Date, nullable=True)
    start_time: Mapped[str | None] = mapped_column(Text)
    end_time: Mapped[str | None] = mapped_column(Text)
    venue: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text, default="India")
    url: Mapped[str | None] = mapped_column(Text)
    ticket_url: Mapped[str | None] = mapped_column(Text)
    source_website: Mapped[str | None] = mapped_column(Text)
    # online | offline | hybrid — null when the source didn't make this clear.
    event_format: Mapped[str | None] = mapped_column(String(20))
    organizer_id: Mapped[int | None] = mapped_column(ForeignKey("discovered_organizers.id"))
    source_url: Mapped[str | None] = mapped_column(Text)
    match_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # PENDING (not yet looked up) | FOUND (has a usable email) | NOT_FOUND
    organizer_status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    # UNVERIFIED | VERIFIED | NEEDS_REVIEW | REJECTED
    verification_status: Mapped[str] = mapped_column(String(20), default="UNVERIFIED", nullable=False)
    # NEW | DUPLICATE | PROMOTED
    discovery_status: Mapped[str] = mapped_column(String(20), default="NEW", nullable=False)
    # social_pipeline | web_discovery_agent — which producer created this row.
    discovered_by: Mapped[str] = mapped_column(String(30), default="social_pipeline", nullable=False)
    # Human-facing flags from event_verification.py/validation.py (e.g. unparseable date,
    # high-risk source) — never a hard reject, just review context.
    verification_notes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    last_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    organizer: Mapped[DiscoveredOrganizer | None] = relationship(back_populates="discovered_events")
    outreach_messages: Mapped[list["OutreachMessage"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    sources: Mapped[list["EventSource"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class EventSource(Base):
    """One row per source URL/evidence a `DiscoveredEvent`'s data came from —
    an event can (and often does) have more than one source (e.g. the
    listing page AND the organizer's own site); this is what lets the agent
    "preserve source URLs" and "preserve evidence" per record, not just one
    `source_url` string on the event itself."""

    __tablename__ = "event_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discovered_event_id: Mapped[int] = mapped_column(ForeignKey("discovered_events.id"), nullable=False)
    source_website: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    # event_listing | conference_site | college_page | government | trade_association |
    # corporate | organizer_website | aggregator | other
    source_type: Mapped[str] = mapped_column(String(30), default="other", nullable=False)
    # Raw evidence captured at fetch time (e.g. the JSON-LD block or extracted fields) —
    # kept so a human reviewer can see exactly what was read, not just a URL.
    extracted_fields: Mapped[dict | None] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    event: Mapped[DiscoveredEvent] = relationship(back_populates="sources")


class OrganizerContact(Base):
    """One row per contact channel for a `DiscoveredOrganizer` — an organizer
    can have several (a general email, a specific person's email, a phone
    number), each independently sourced and scored, rather than being
    squashed into single `email`/`phone` columns on the organizer itself."""

    __tablename__ = "organizer_contacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discovered_organizer_id: Mapped[int] = mapped_column(ForeignKey("discovered_organizers.id"), nullable=False)
    # email | phone | linkedin | website | other
    contact_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    organizer: Mapped[DiscoveredOrganizer] = relationship(back_populates="contacts")


class AgentRun(Base):
    """One row per whole pipeline execution of either agent — the top-level
    idempotent-resume/audit record. Distinct from `PipelineExecution`/
    `PipelineStageLog`, which log per-discussion social-pipeline detail;
    this is the higher-level "Agent 1/Agent 2 run" record the spec's
    structured output summary hangs off, and what a resumed/retried run
    checks to avoid redoing (or duplicating) completed work."""

    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # discovery | outreach
    agent_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # running | completed | failed
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The cities/states/categories/limits this run was configured with, for reproducibility.
    config_snapshot: Mapped[dict | None] = mapped_column(JSON)
    # events_discovered, new_events, duplicate_events, organizers_found, new_organizers,
    # contacts_found, events_needing_review — updated incrementally as the run progresses,
    # so a crash mid-run leaves an honest partial summary rather than nothing.
    summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class OutreachCampaign(Base):
    """A named, configured batch of organizer outreach (Phase 5+ — schema
    defined now for forward compatibility, not yet written to)."""

    __tablename__ = "outreach_campaigns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    agent_type: Mapped[str] = mapped_column(String(20), default="outreach", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    # Daily cap, follow-up interval, confidence threshold, etc. for this campaign.
    config: Mapped[dict | None] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class OutreachMessage(Base):
    """One outreach attempt (initial or follow-up) to a discovered
    organizer about a discovered event.

    Rows now persist starting at `NEW` — before an email is even drafted —
    so the full research→draft→approve→send lifecycle is auditable, not
    just the "already drafted" moment the old flow started recording at."""

    __tablename__ = "outreach_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("discovered_events.id"), nullable=False)
    organizer_id: Mapped[int | None] = mapped_column(ForeignKey("discovered_organizers.id"))
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("outreach_campaigns.id"))
    recipient: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)
    generated_by: Mapped[str] = mapped_column(String(30), default="ai", nullable=False)  # ai | deterministic_fallback
    # NEW | RESEARCHED | EMAIL_GENERATED | PENDING_APPROVAL | APPROVED | SENT | DELIVERED |
    # BOUNCED | REPLIED | OPTED_OUT | FOLLOW_UP_DUE | COMPLETED | REJECTED
    # (SENT exists for schema/future-ESP compatibility — with plain SMTP a successful send goes
    # straight to DELIVERED, since there is no separate async delivery confirmation to wait for.)
    status: Mapped[str] = mapped_column(String(30), default="NEW", nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    send_attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    follow_up_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    message_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    event: Mapped[DiscoveredEvent] = relationship(back_populates="outreach_messages")
    organizer: Mapped[DiscoveredOrganizer | None] = relationship("DiscoveredOrganizer")
    campaign: Mapped["OutreachCampaign | None"] = relationship("OutreachCampaign")


class SuppressedContact(Base):
    """A durable, email-keyed do-not-contact record — survives even if the
    `DiscoveredOrganizer` row that triggered it is superseded by a later
    discovery run. Checked before every outreach send, in addition to (not
    instead of) the cheaper per-row `DiscoveredOrganizer.blocked` flag."""

    __tablename__ = "suppressed_contacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    # admin_restricted | opted_out | bounced
    reason: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class PlatformRateLimit(Base):
    """Admin-editable daily signal-ingestion cap per platform, replacing the
    single flat env-var cap."""

    __tablename__ = "platform_rate_limits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    daily_limit: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class AgentSetting(Base):
    """Small persisted key/value store for admin-toggleable runtime switches
    that take effect immediately and survive a backend restart — e.g.
    whether Agent 1's discovery scan runs on a timer (see
    `services/discovery_agent/auto_toggle.py`). Distinct from
    `core/config.py`'s env-var settings, which need a restart to change."""

    __tablename__ = "agent_settings"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(200), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
