from datetime import date, datetime
from datetime import date as _Date  # alias for use inside classes that also have a field literally named `date`
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class APIModel(BaseModel):
    # API responses use camelCase. `alias` (rather than serialization_alias)
    # also lets existing serializers construct these models with camelCase.
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class UserInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    country: str | None = Field(default="India", max_length=80)
    role: Literal["USER", "ORGANIZER"] | None = None
    company: str | None = Field(default=None, max_length=160)


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserOut(APIModel):
    id: int
    name: str
    email: EmailStr
    role: Literal["USER", "ORGANIZER", "ADMIN"]
    roles: list[str] = Field(default_factory=list)
    email_verified: bool = Field(default=True, alias="emailVerified")
    country: str | None = None
    company: str | None = None


class ForgotPasswordInput(BaseModel):
    email: EmailStr


class ResetPasswordInput(BaseModel):
    token: str = Field(min_length=16, max_length=128)
    new_password: str = Field(min_length=8, max_length=128, alias="newPassword")


class VerifyEmailInput(BaseModel):
    token: str = Field(min_length=16, max_length=128)


class DeleteAccountInput(BaseModel):
    confirmation: str = Field(min_length=1)
    password: str = Field(min_length=8, max_length=128)


class Session(APIModel):
    user: UserOut
    token: str


class ReviewInput(BaseModel):
    rating: int = Field(ge=1, le=5)
    title: str = Field(min_length=1, max_length=140)
    comment: str = Field(min_length=1, max_length=2000)


class ReviewOut(APIModel):
    id: int
    author: str
    rating: int
    title: str
    comment: str
    created_at: datetime = Field(alias="createdAt")


class CategoryOut(APIModel):
    id: int
    name: str
    slug: str
    description: str
    icon: str
    event_count: int = Field(alias="eventCount")


class CityOut(APIModel):
    id: int
    name: str
    slug: str
    country: str
    image: str = ""
    event_count: int = Field(alias="eventCount")


class CountryOut(APIModel):
    name: str
    code: str | None = None
    event_count: int = Field(default=0, alias="eventCount")


class OrganizerOut(APIModel):
    id: int
    name: str
    slug: str
    description: str
    logo: str = ""
    event_count: int = Field(alias="eventCount")
    rating: float


class VenueOut(APIModel):
    id: int
    name: str
    slug: str
    address: str
    city: str
    country: str
    capacity: int = 0
    image: str = ""


class SpeakerOut(APIModel):
    id: int
    name: str
    slug: str
    title: str
    company: str
    image: str = ""
    expertise: list[str]


class EventCard(APIModel):
    id: int
    title: str
    slug: str
    event_type: str = Field(alias="eventType")
    category: str
    category_slug: str = Field(alias="categorySlug")
    start_date: date = Field(alias="startDate")
    end_date: date = Field(alias="endDate")
    start_time: str = Field(alias="startTime")
    location: str
    venue: str
    organizer: str
    image: str = ""
    rating: float
    attendee_count: int = Field(alias="attendeeCount")
    price: Decimal
    format: Literal["online", "in-person"]
    is_saved: bool = Field(alias="isSaved")
    status: Literal["draft", "published", "pending"]


class AgendaItem(APIModel):
    time: str
    title: str
    detail: str


class EventDetail(EventCard):
    description: str
    organizer_id: int = Field(alias="organizerId")
    venue_id: int = Field(alias="venueId")
    agenda: list[AgendaItem]
    speakers: list[SpeakerOut]
    exhibitors: list[str]
    reviews: list[ReviewOut]
    related_events: list[EventCard] = Field(alias="relatedEvents")


class EventList(APIModel):
    items: list[EventCard]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")
    total_pages: int = Field(alias="totalPages")


class RegistrationInput(BaseModel):
    first_name: str = Field(min_length=1, max_length=80, alias="firstName")
    last_name: str = Field(min_length=1, max_length=80, alias="lastName")
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    company: str | None = Field(default=None, max_length=120)
    job_title: str | None = Field(default=None, max_length=120, alias="jobTitle")
    country: str | None = Field(default="India", max_length=80)
    ticket_type: Literal["Free", "Standard", "Premium", "VIP"] = Field(alias="ticketType")


class RegistrationOut(APIModel):
    id: int
    event_id: int = Field(alias="eventId")
    event_title: str = Field(alias="eventTitle")
    event_slug: str = Field(alias="eventSlug")
    ticket_type: str = Field(alias="ticketType")
    registered_at: datetime = Field(alias="registeredAt")
    status: Literal["confirmed", "pending", "cancelled"]
    user_name: str = Field(default="", alias="userName")
    company: str | None = None
    job_title: str | None = Field(default=None, alias="jobTitle")
    ticket_code: str = Field(default="", alias="ticketCode")
    qr_code: str = Field(default="", alias="qrCode")
    event_location: str = Field(default="", alias="eventLocation")
    event_venue: str = Field(default="", alias="eventVenue")
    event_start_date: str = Field(default="", alias="eventStartDate")
    event_end_date: str = Field(default="", alias="eventEndDate")
    event_start_time: str = Field(default="", alias="eventStartTime")


class NotificationOut(APIModel):
    id: int
    title: str
    message: str
    is_read: bool = Field(alias="isRead")
    created_at: datetime = Field(alias="createdAt")


class ActionResult(BaseModel):
    success: bool
    is_saved: bool = Field(alias="isSaved")
    message: str


class DirectoryDetail(BaseModel):
    name: str
    slug: str
    description: str
    events: list[EventCard]
    related: list[str]


class OrganizerDetail(BaseModel):
    organizer: OrganizerOut
    events: list[EventCard]
    reviews: list[ReviewOut]


class VenueDetail(BaseModel):
    venue: VenueOut
    description: str
    facilities: list[str]
    events: list[EventCard]


class SpeakerDetail(BaseModel):
    speaker: SpeakerOut
    biography: str
    events: list[EventCard]


class EventInput(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(min_length=10, max_length=5000)
    event_type: str = Field(min_length=2, max_length=80, alias="eventType")
    category: str = Field(min_length=2, max_length=120)
    start_date: date = Field(alias="startDate")
    end_date: date = Field(alias="endDate")
    start_time: str = Field(min_length=3, max_length=30, alias="startTime")
    location: str = Field(min_length=2, max_length=120)
    format: Literal["online", "in-person"]
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, value: date, info: Any) -> date:
        start = info.data.get("start_date")
        if start and value < start:
            raise ValueError("endDate must be on or after startDate")
        return value


class Dashboard(BaseModel):
    user_name: str = Field(alias="userName")
    saved_count: int = Field(alias="savedCount")
    registration_count: int = Field(alias="registrationCount")
    attended_count: int = Field(alias="attendedCount")
    upcoming: list[RegistrationOut]
    saved: list[EventCard]
    recommended: list[EventCard]
    notifications: list[NotificationOut]


class OrganizerDashboard(BaseModel):
    total_events: int = Field(alias="totalEvents")
    published_events: int = Field(alias="publishedEvents")
    registrations: int
    views: int
    conversion_rate: float = Field(alias="conversionRate")
    recent_events: list[EventCard] = Field(alias="recentEvents")


class Analytics(BaseModel):
    views: list[int]
    registrations: list[int]
    conversion: list[float]
    ticket_distribution: dict[str, int] = Field(alias="ticketDistribution")


class AdminDashboard(BaseModel):
    users: int
    events: int
    organizers: int
    registrations: int
    reviews: int
    user_growth: list[int] = Field(alias="userGrowth")
    event_growth: list[int] = Field(alias="eventGrowth")
    popular_categories: list[str] = Field(alias="popularCategories")


class HomePayload(BaseModel):
    featured: list[EventCard]
    trending: list[CategoryOut]
    cities: list[CityOut]
    event_types: list[str] = Field(alias="eventTypes")
    stats: dict[str, int]


class ConnectionCreate(BaseModel):
    addressee_id: int = Field(alias="addresseeId", gt=0)


class ConnectionOut(BaseModel):
    id: int
    requester_id: int = Field(alias="requesterId")
    addressee_id: int = Field(alias="addresseeId")
    status: Literal["pending", "accepted", "declined"]
    created_at: datetime = Field(alias="createdAt")
    peer_id: int = Field(default=0, alias="peerId")
    peer_name: str = Field(default="", alias="peerName")
    peer_company: str | None = Field(default=None, alias="peerCompany")
    peer_job_title: str | None = Field(default=None, alias="peerJobTitle")
    peer_bio: str | None = Field(default=None, alias="peerBio")
    is_requester: bool = Field(default=False, alias="isRequester")


class ConnectionUpdate(BaseModel):
    status: Literal["accepted", "declined"]


class AttendeeProfileOut(APIModel):
    id: int
    name: str
    job_title: str | None = Field(default=None, alias="jobTitle")
    company: str | None = None
    bio: str | None = None
    country: str | None = None
    role: str = "USER"
    registered_event_count: int = Field(default=0, alias="registeredEventCount")
    connection_status: Literal["none", "pending_sent", "pending_received", "connected"] = Field(
        default="none", alias="connectionStatus"
    )
    connection_id: int | None = Field(default=None, alias="connectionId")


class MessageCreate(BaseModel):
    recipient_id: int = Field(alias="recipientId", gt=0)
    content: str = Field(min_length=1, max_length=2000)


class MessageOut(APIModel):
    id: int
    sender_id: int = Field(alias="senderId")
    sender_name: str = Field(alias="senderName")
    recipient_id: int = Field(alias="recipientId")
    content: str
    is_read: bool = Field(alias="isRead")
    created_at: datetime = Field(alias="createdAt")


class ScheduleItemInput(BaseModel):
    event_id: int = Field(alias="eventId")
    session_title: str = Field(min_length=1, max_length=200, alias="sessionTitle")
    session_time: str = Field(min_length=1, max_length=50, alias="sessionTime")
    session_detail: str | None = Field(default=None, max_length=500, alias="sessionDetail")


class ScheduleItemOut(APIModel):
    id: int
    event_id: int = Field(alias="eventId")
    event_title: str = Field(alias="eventTitle")
    event_slug: str = Field(alias="eventSlug")
    event_date: str = Field(alias="eventDate")
    session_title: str = Field(alias="sessionTitle")
    session_time: str = Field(alias="sessionTime")
    session_detail: str | None = Field(default=None, alias="sessionDetail")
    created_at: datetime = Field(alias="createdAt")


class ProfileUpdateInput(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    job_title: str | None = Field(default=None, max_length=120, alias="jobTitle")
    company: str | None = Field(default=None, max_length=120)
    bio: str | None = Field(default=None, max_length=500)
    country: str | None = Field(default=None, max_length=80)


class AIEventMatch(APIModel):
    event: EventCard
    match_score: int = Field(alias="matchScore", ge=0, le=100)
    match_reason: str = Field(alias="matchReason")
    tags: list[str] = Field(default_factory=list)


class AIConciergeRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    context: dict[str, Any] | None = None


class AIConciergeResponse(APIModel):
    reply: str
    suggested_queries: list[str] = Field(alias="suggestedQueries", default_factory=list)
    matched_events: list[AIEventMatch] = Field(alias="matchedEvents", default_factory=list)


class AIPeerMatch(APIModel):
    attendee: AttendeeProfileOut
    match_score: int = Field(alias="matchScore", ge=0, le=100)
    match_reason: str = Field(alias="matchReason")
    mutual_interests: list[str] = Field(alias="mutualInterests", default_factory=list)


class AIEventBrief(APIModel):
    event_id: int = Field(alias="eventId")
    title: str
    summary: str
    key_takeaways: list[str] = Field(alias="keyTakeaways")
    target_audience: list[str] = Field(alias="targetAudience")
    recommended_role: str = Field(alias="recommendedRole")
    highlight_session: str | None = Field(default=None, alias="highlightSession")


class PersonalizedRecommendationsOut(APIModel):
    headline: str
    user_context: str = Field(alias="userContext")
    items: list[AIEventMatch]


# ---------------------------------------------------------------------------
# Community Attendee Acquisition Agent Schemas
# ---------------------------------------------------------------------------

class CommunityOut(APIModel):
    id: int
    platform: str
    name: str
    slug: str
    url: str
    rules_text: str | None = Field(default=None, alias="rulesText")
    promotion_allowed: bool = Field(alias="promotionAllowed")
    external_links_allowed: bool = Field(alias="externalLinksAllowed")
    automation_allowed: bool = Field(alias="automationAllowed")
    risk_level: str = Field(alias="riskLevel")
    quality_score: int = Field(alias="qualityScore")
    platform_ref: str | None = Field(default=None, alias="platformRef")
    discovered_community_id: int | None = Field(default=None, alias="discoveredCommunityId")
    last_checked: datetime | None = Field(default=None, alias="lastChecked")
    created_at: datetime = Field(alias="createdAt")


class CommunityUpdateInput(BaseModel):
    promotion_allowed: bool | None = Field(default=None, alias="promotionAllowed")
    external_links_allowed: bool | None = Field(default=None, alias="externalLinksAllowed")
    automation_allowed: bool | None = Field(default=None, alias="automationAllowed")
    risk_level: str | None = Field(default=None, alias="riskLevel")
    rules_text: str | None = Field(default=None, alias="rulesText")
    # Set once a human has connected the bot and looked up its real chat/channel id —
    # "telegram_<chat_id>" or "discord_<guild_id>_<channel_id>". Required before a
    # standalone community-promotion post can ever be published to this destination.
    platform_ref: str | None = Field(default=None, alias="platformRef")


class ExtractedIntent(APIModel):
    intent: str = "find_event"
    event_category: str | None = Field(default=None, alias="eventCategory")
    event_type: str | None = Field(default=None, alias="eventType")
    location: str | None = None
    date_range: str | None = Field(default=None, alias="dateRange")
    budget: str | None = None
    confidence: float = 0.85


class DiscussionOut(APIModel):
    id: int
    community_id: int | None = Field(default=None, alias="communityId")
    community_name: str = Field(default="", alias="communityName")
    platform: str
    external_id: str = Field(alias="externalId")
    url: str
    title: str
    content: str
    author: str | None = None
    published_at: datetime | None = Field(default=None, alias="publishedAt")
    intent_classification: str = Field(alias="intentClassification")
    intent_confidence: float = Field(alias="intentConfidence")
    extracted_intent: dict[str, Any] | None = Field(default=None, alias="extractedIntent")
    status: str
    pipeline_status: str = Field(default="DISCOVERED", alias="pipelineStatus")
    qualification_score: int = Field(default=0, alias="qualificationScore")
    qualification_breakdown: dict[str, int] | None = Field(default=None, alias="qualificationBreakdown")
    rejection_reason: str | None = Field(default=None, alias="rejectionReason")
    created_at: datetime = Field(alias="createdAt")


class MatchingEventSummary(APIModel):
    id: int
    title: str
    slug: str
    location: str
    start_date: str = Field(alias="startDate")
    price: float
    relevance_score: int = Field(alias="relevanceScore")
    category: str
    match_reasons: list[str] = Field(alias="matchReasons", default_factory=list)
    score_breakdown: dict[str, int] = Field(alias="scoreBreakdown", default_factory=dict)


class PromotedEventSummary(APIModel):
    id: int
    title: str
    slug: str


class TargetCommunitySummary(APIModel):
    id: int
    name: str
    platform: str
    connected: bool  # whether platform_ref is set — i.e. actually publishable, not just approved


class AcquisitionOpportunityOut(APIModel):
    id: int
    # discussion_reply | community_promotion
    source_kind: str = Field(default="discussion_reply", alias="sourceKind")
    discussion: DiscussionOut | None = None
    promoted_event: PromotedEventSummary | None = Field(default=None, alias="promotedEvent")
    target_community: TargetCommunitySummary | None = Field(default=None, alias="targetCommunity")
    match_explanation: str | None = Field(default=None, alias="matchExplanation")
    matching_events: list[MatchingEventSummary] = Field(alias="matchingEvents", default_factory=list)
    relevance_score: int = Field(alias="relevanceScore")
    generated_response: str = Field(alias="generatedResponse")
    response_variations: list[str] = Field(alias="responseVariations", default_factory=list)
    content_payload: dict[str, Any] | None = Field(default=None, alias="contentPayload")
    content_generated_by: str | None = Field(default=None, alias="contentGeneratedBy")
    policy_notes: list[str] = Field(default_factory=list, alias="policyNotes")
    approval_status: str = Field(alias="approvalStatus")
    community_risk: str = Field(default="low", alias="communityRisk")
    referral_url: str = Field(default="", alias="referralUrl")
    clicks_count: int = Field(default=0, alias="clicksCount")
    registrations_count: int = Field(default=0, alias="registrationsCount")
    scheduled_at: datetime | None = Field(default=None, alias="scheduledAt")
    published_at: datetime | None = Field(default=None, alias="publishedAt")
    published_url: str | None = Field(default=None, alias="publishedUrl")
    reviewed_at: datetime | None = Field(default=None, alias="reviewedAt")
    created_at: datetime = Field(alias="createdAt")


class OpportunityActionRequest(BaseModel):
    action: Literal["approve", "reject", "ignore", "schedule", "approve_and_publish"]
    response_text: str | None = Field(default=None, alias="responseText")
    scheduled_at: datetime | None = Field(default=None, alias="scheduledAt")
    notes: str | None = None


class MarkPublishedInput(BaseModel):
    published_url: str = Field(alias="publishedUrl", min_length=5)
    platform_post_id: str | None = Field(default=None, alias="platformPostId")


class OpportunityEditRequest(BaseModel):
    response_text: str = Field(min_length=5, alias="responseText")


class ScanTriggerRequest(BaseModel):
    community_id: int | None = Field(default=None, alias="communityId")
    platform: str | None = None
    platforms: list[str] | None = None


class InstagramContentRequest(BaseModel):
    theme: str = Field(min_length=3, max_length=200)


class TestDiscussionRequest(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    content: str = Field(min_length=5, max_length=2000)
    platform: str = "reddit"
    community_name: str = Field(default="r/hyderabad", alias="communityName")
    url: str = ""


class DiscoveryDiscussionRequest(BaseModel):
    """One incoming discussion (any topic) to run through the generic
    discovery agent: understand -> generate dynamic search queries -> search
    the selected platform -> extract candidate events -> match/stage."""

    platform: str
    community_name: str = Field(alias="communityName")
    title: str = Field(min_length=3, max_length=300)
    content: str = Field(min_length=5, max_length=2000)
    url: str = ""


class TrackEventRequest(BaseModel):
    opportunity_id: int = Field(alias="opportunityId")
    event_id: int | None = Field(default=None, alias="eventId")
    event_type: Literal["click", "visit", "registration"] = Field(default="click", alias="eventType")
    visitor_id: str | None = Field(default=None, alias="visitorId")


class ConversionSimulationRequest(BaseModel):
    opportunity_id: int = Field(alias="opportunityId")
    clicks: int = Field(default=3, ge=1, le=50)
    registrations: int = Field(default=1, ge=0, le=20)


class KeywordPerformanceOut(APIModel):
    keyword: str
    frequency: int
    high_intent_rate: float = Field(alias="highIntentRate")
    conversions: int


class AcquisitionAnalyticsOut(APIModel):
    total_opportunities: int = Field(alias="totalOpportunities")
    pending_approval: int = Field(alias="pendingApproval")
    approved_count: int = Field(alias="approvedCount")
    rejected_count: int = Field(alias="rejectedCount")
    high_intent_rate: float = Field(alias="highIntentRate")
    avg_relevance_score: float = Field(alias="avgRelevanceScore")
    total_clicks: int = Field(default=0, alias="totalClicks")
    total_registrations: int = Field(default=0, alias="totalRegistrations")
    overall_conversion_rate: float = Field(default=0.0, alias="overallConversionRate")
    funnel_steps: dict[str, int] = Field(alias="funnelSteps", default_factory=dict)
    source_quality_rankings: list[dict[str, Any]] = Field(alias="sourceQualityRankings", default_factory=list)
    platform_performance: list[dict[str, Any]] = Field(alias="platformPerformance", default_factory=list)
    top_keywords: list[KeywordPerformanceOut] = Field(alias="topKeywords", default_factory=list)
    recent_actions: list[dict[str, Any]] = Field(alias="recentActions", default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline Debug View + Platform Rate Limits
# ---------------------------------------------------------------------------

class PipelineStageLogOut(APIModel):
    id: int
    stage: str
    status: str
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(alias="createdAt")


class PipelineExecutionOut(APIModel):
    id: int
    discussion_id: int = Field(alias="discussionId")
    started_at: datetime = Field(alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    final_status: str | None = Field(default=None, alias="finalStatus")
    stages: list[PipelineStageLogOut] = Field(default_factory=list)


class PlatformRateLimitOut(APIModel):
    id: int
    platform: str
    daily_limit: int = Field(alias="dailyLimit")
    updated_at: datetime = Field(alias="updatedAt")


class PlatformRateLimitUpdateInput(BaseModel):
    daily_limit: int = Field(alias="dailyLimit", ge=1, le=1000)


# --- Organizer Outreach ---

class OrganizerContactOut(APIModel):
    id: int
    contact_type: str = Field(alias="contactType")
    value: str
    source_url: str | None = Field(default=None, alias="sourceUrl")
    confidence_score: int = Field(default=0, alias="confidenceScore")
    is_primary: bool = Field(default=False, alias="isPrimary")


class DiscoveredOrganizerOut(APIModel):
    id: int
    name: str
    email: str | None = None
    website: str | None = None
    linkedin: str | None = None
    source_url: str | None = Field(default=None, alias="sourceUrl")
    organizer_type: str | None = Field(default=None, alias="organizerType")
    city: str | None = None
    state: str | None = None
    phone: str | None = None
    confidence_score: int = Field(default=0, alias="confidenceScore")
    blocked: bool = False
    verified_at: datetime | None = Field(default=None, alias="verifiedAt")
    last_updated_at: datetime | None = Field(default=None, alias="lastUpdatedAt")
    contacts: list[OrganizerContactOut] = Field(default_factory=list)


class EventSourceOut(APIModel):
    id: int
    source_website: str | None = Field(default=None, alias="sourceWebsite")
    source_url: str = Field(alias="sourceUrl")
    source_type: str = Field(alias="sourceType")
    fetched_at: datetime = Field(alias="fetchedAt")


class DiscoveredEventOut(APIModel):
    id: int
    name: str | None = None
    date: str | None = None
    event_date: _Date | None = Field(default=None, alias="eventDate")
    location: str | None = None
    category: str | None = None
    subcategory: str | None = None
    event_description: str | None = Field(default=None, alias="eventDescription")
    venue: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    url: str | None = None
    ticket_url: str | None = Field(default=None, alias="ticketUrl")
    event_format: str | None = Field(default=None, alias="eventFormat")
    start_time: str | None = Field(default=None, alias="startTime")
    end_time: str | None = Field(default=None, alias="endTime")
    source_url: str | None = Field(default=None, alias="sourceUrl")
    source_website: str | None = Field(default=None, alias="sourceWebsite")
    match_score: int = Field(alias="matchScore")
    confidence_score: int = Field(default=0, alias="confidenceScore")
    organizer_id: int | None = Field(default=None, alias="organizerId")
    organizer_status: str = Field(alias="organizerStatus")
    verification_status: str = Field(default="UNVERIFIED", alias="verificationStatus")
    discovery_status: str = Field(default="NEW", alias="discoveryStatus")
    discovered_by: str = Field(default="social_pipeline", alias="discoveredBy")
    verification_notes: list[str] = Field(default_factory=list, alias="verificationNotes")
    discovered_at: datetime | None = Field(default=None, alias="discoveredAt")
    last_updated_at: datetime | None = Field(default=None, alias="lastUpdatedAt")
    sources: list[EventSourceOut] = Field(default_factory=list)


class OutreachMessageOut(APIModel):
    id: int
    event: DiscoveredEventOut
    organizer: DiscoveredOrganizerOut | None = None
    campaign_id: int | None = Field(default=None, alias="campaignId")
    recipient: str | None = None
    subject: str | None = None
    message: str | None = None
    generated_by: str = Field(alias="generatedBy")
    status: str
    failure_reason: str | None = Field(default=None, alias="failureReason")
    send_attempt_count: int = Field(default=0, alias="sendAttemptCount")
    sent_at: datetime | None = Field(default=None, alias="sentAt")
    last_contacted_at: datetime | None = Field(default=None, alias="lastContactedAt")
    response_at: datetime | None = Field(default=None, alias="responseAt")
    follow_up_sent_at: datetime | None = Field(default=None, alias="followUpSentAt")
    message_id: str | None = Field(default=None, alias="messageId")
    created_at: datetime = Field(alias="createdAt")


class OutreachActionRequest(BaseModel):
    action: Literal["approve", "reject", "send", "retry", "opt_out", "ignore", "restrict_organizer", "mark_replied"]
    reason: str | None = Field(default=None, max_length=500)


class OutreachEditRequest(BaseModel):
    subject: str = Field(min_length=2, max_length=200)
    message: str = Field(min_length=5)


class OutreachRunRequest(BaseModel):
    """Manual trigger for testing — mirrors `TestDiscussionRequest`, but runs
    a single candidate post straight through event extraction + outreach
    without needing a full discovery scan first."""

    platform: str = Field(default="manual")
    community_name: str = Field(default="manual-test", alias="communityName")
    topic_summary: str = Field(alias="topicSummary")
    title: str
    content: str
    url: str = ""


class OutreachBatchRunRequest(BaseModel):
    """Optional override for Agent 2's batch research+draft run — mirrors
    `DiscoveryRunRequest`. Left unset falls back to `outreach_max_candidates_per_run`."""

    max_candidates: int | None = Field(default=None, alias="maxCandidates", ge=1, le=200)


class OutreachStatsOut(APIModel):
    events_found: int = Field(alias="eventsFound")
    qualified_events: int = Field(alias="qualifiedEvents")
    organizers_found: int = Field(alias="organizersFound")
    messages_sent: int = Field(alias="messagesSent")
    follow_ups_sent: int = Field(alias="followUpsSent")
    responses: int = Field(alias="responses")
    failed_messages: int = Field(alias="failedMessages")
    email_provider_status: str = Field(alias="emailProviderStatus")


# --- Event Discovery Agent ---

class DiscoveryRunRequest(BaseModel):
    """Optional per-run overrides for a manually-triggered discovery scan —
    any field left unset falls back to the configured `discovery_*` settings."""

    cities: list[str] | None = None
    states: list[str] | None = None
    countries: list[str] | None = None
    country: str | None = None
    categories: list[str] | None = None
    search_depth: int | None = Field(default=None, alias="searchDepth", ge=1, le=200)
    sources_per_query: int | None = Field(default=None, alias="sourcesPerQuery", ge=1, le=20)
    daily_limit: int | None = Field(default=None, alias="dailyLimit", ge=1)
    confidence_threshold: int | None = Field(default=None, alias="confidenceThreshold", ge=0, le=100)
    require_organizer_email: bool | None = Field(default=None, alias="requireOrganizerEmail")
    date_from: str | None = Field(default=None, alias="dateFrom")
    date_to: str | None = Field(default=None, alias="dateTo")


# --- Community Discovery Agent ("Agent 5") ---

class CommunitySourceOut(APIModel):
    id: int
    source_url: str = Field(alias="sourceUrl")
    source_type: str = Field(alias="sourceType")
    fetched_at: datetime = Field(alias="fetchedAt")


class DiscoveredCommunityOut(APIModel):
    id: int
    platform: str
    name: str
    canonical_url: str = Field(alias="canonicalUrl")
    invite_url: str | None = Field(default=None, alias="inviteUrl")
    description: str | None = None
    category: str | None = None
    subcategory: str | None = None
    topics: list[str] = Field(default_factory=list)
    language: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    member_count: int | None = Field(default=None, alias="memberCount")
    rules_text: str | None = Field(default=None, alias="rulesText")
    promotion_allowed: bool | None = Field(default=None, alias="promotionAllowed")
    automation_allowed: bool = Field(default=False, alias="automationAllowed")
    risk_level: str = Field(default="unknown", alias="riskLevel")
    confidence_score: int = Field(default=0, alias="confidenceScore")
    discovery_status: str = Field(default="NEW", alias="discoveryStatus")
    verification_notes: list[str] = Field(default_factory=list, alias="verificationNotes")
    approval_status: str = Field(default="DISCOVERED", alias="approvalStatus")
    rejection_reason: str | None = Field(default=None, alias="rejectionReason")
    connection_status: str = Field(default="NOT_CONNECTED", alias="connectionStatus")
    community_id: int | None = Field(default=None, alias="communityId")
    discovered_at: datetime = Field(alias="discoveredAt")
    last_checked_at: datetime | None = Field(default=None, alias="lastCheckedAt")
    sources: list[CommunitySourceOut] = Field(default_factory=list)


class CommunityDiscoveryRunRequest(BaseModel):
    """Optional per-run overrides for a manually-triggered community scan —
    any field left unset falls back to the configured settings. Mirrors
    `DiscoveryRunRequest`."""

    cities: list[str] | None = None
    states: list[str] | None = None
    countries: list[str] | None = None
    country: str | None = None
    categories: list[str] | None = None
    search_depth: int | None = Field(default=None, alias="searchDepth", ge=1, le=200)
    sources_per_query: int | None = Field(default=None, alias="sourcesPerQuery", ge=1, le=20)
    daily_limit: int | None = Field(default=None, alias="dailyLimit", ge=1)
    confidence_threshold: int | None = Field(default=None, alias="confidenceThreshold", ge=0, le=100)
    require_organizer_email: bool | None = Field(default=None, alias="requireOrganizerEmail")
    date_from: str | None = Field(default=None, alias="dateFrom")
    date_to: str | None = Field(default=None, alias="dateTo")
    seed_urls: list[str] | None = Field(default=None, alias="seedUrls")


class CommunityDiscoveryAutoStatusOut(APIModel):
    enabled: bool
    interval_minutes: int = Field(alias="intervalMinutes")


class CommunityDiscoveryAutoToggleRequest(BaseModel):
    enabled: bool


class CommunityActionRequest(BaseModel):
    action: Literal["approve", "reject", "mark_connection_required", "mark_connected", "mark_permission_missing", "mark_promotion_restricted"]
    reason: str | None = Field(default=None, max_length=500)


class CommunityDiscoveryStatsOut(APIModel):
    communities_total: int = Field(alias="communitiesTotal")
    needs_review_total: int = Field(alias="needsReviewTotal")
    approved_total: int = Field(alias="approvedTotal")
    connected_total: int = Field(alias="connectedTotal")
    telegram_total: int = Field(alias="telegramTotal")
    discord_total: int = Field(alias="discordTotal")


# --- Agent 4 extension: Community Promotion ---

class CommunityPromotionAutoStatusOut(APIModel):
    enabled: bool
    interval_minutes: int = Field(alias="intervalMinutes")


class CommunityPromotionAutoToggleRequest(BaseModel):
    enabled: bool


class CommunityPromotionRunRequest(BaseModel):
    max_candidates: int | None = Field(default=None, alias="maxCandidates", ge=1, le=200)


class VenueMissingEventOut(APIModel):
    id: int
    name: str | None = None
    city: str | None = None


class DiscoveryStatsOut(APIModel):
    """True database counts — never derived by counting a capped list
    client-side. The `/events` and `/organizers` list endpoints cap at 200
    rows for the browsing table; once discovery finds more than that, any
    stat computed from `.length` on that list silently stops growing even
    though more keeps being found. These numbers always reflect the real
    total, at any scale."""

    events_total: int = Field(alias="eventsTotal")
    organizers_total: int = Field(alias="organizersTotal")
    contacts_total: int = Field(alias="contactsTotal")
    organizers_with_email_total: int = Field(alias="organizersWithEmailTotal")
    needs_review_total: int = Field(alias="needsReviewTotal")
    new_events_total: int = Field(alias="newEventsTotal")
    online_total: int = Field(alias="onlineTotal")
    offline_total: int = Field(alias="offlineTotal")
    hybrid_total: int = Field(alias="hybridTotal")
    format_unknown_total: int = Field(alias="formatUnknownTotal")
    rejected_total: int = Field(default=0, alias="rejectedTotal")
    accepted_total: int = Field(default=0, alias="acceptedTotal")
    missing_organizer_email_total: int = Field(default=0, alias="missingOrganizerEmailTotal")
    venue_missing_total: int = Field(alias="venueMissingTotal")
    venue_missing_sample: list[VenueMissingEventOut] = Field(default_factory=list, alias="venueMissingSample")


class DiscoveryAutoStatusOut(APIModel):
    """Live state of the discovery-scan on/off switch and scope settings — see
    `services/discovery_agent/auto_toggle.py`."""

    enabled: bool
    interval_minutes: int = Field(alias="intervalMinutes")
    country: str | None = None
    countries: list[str] = Field(default_factory=list)
    cities: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    search_depth: int | None = Field(default=None, alias="searchDepth")
    daily_limit: int | None = Field(default=None, alias="dailyLimit")


class DiscoveryAutoToggleRequest(BaseModel):
    enabled: bool | None = None
    country: str | None = None
    countries: list[str] | None = None
    cities: list[str] | None = None
    states: list[str] | None = None
    categories: list[str] | None = None
    search_depth: int | None = Field(default=None, alias="searchDepth")
    daily_limit: int | None = Field(default=None, alias="dailyLimit")


class OutreachAutoStatusOut(APIModel):
    """Live state of Agent 2's on/off switch (drafting + follow-up sweep) and
    scope/cadence settings — see `services/social_agent/outreach/auto_toggle.py`."""

    enabled: bool
    draft_interval_minutes: int = Field(alias="draftIntervalMinutes")
    followup_interval_minutes: int = Field(alias="followupIntervalMinutes")
    country: str | None = None
    countries: list[str] = Field(default_factory=list)
    cities: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    max_candidates: int = Field(default=20, alias="maxCandidates")
    daily_limit: int = Field(default=100, alias="dailyLimit")
    followup_wait_days: int = Field(default=2, alias="followupWaitDays")
    max_followup_attempts: int = Field(default=3, alias="maxFollowupAttempts")
    sender_name: str | None = Field(default="100 TIMES Partnerships", alias="senderName")
    template_style: str | None = Field(default="invitational", alias="templateStyle")


class OutreachAutoToggleRequest(BaseModel):
    enabled: bool | None = None
    country: str | None = None
    countries: list[str] | None = None
    cities: list[str] | None = None
    states: list[str] | None = None
    categories: list[str] | None = None
    max_candidates: int | None = Field(default=None, alias="maxCandidates")
    daily_limit: int | None = Field(default=None, alias="dailyLimit")
    followup_wait_days: int | None = Field(default=None, alias="followupWaitDays")
    max_followup_attempts: int | None = Field(default=None, alias="maxFollowupAttempts")
    sender_name: str | None = Field(default=None, alias="senderName")
    template_style: str | None = Field(default=None, alias="templateStyle")
    draft_interval_minutes: int | None = Field(default=None, alias="draftIntervalMinutes")
    followup_interval_minutes: int | None = Field(default=None, alias="followupIntervalMinutes")


class AutomationRequestOut(APIModel):
    id: int
    description: str
    status: str
    requested_by: str | None = Field(default=None, alias="requestedBy")
    note: str | None = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class AutomationRequestCreate(BaseModel):
    description: str = Field(min_length=10, max_length=2000)


class AgentRunOut(APIModel):
    id: int
    agent_type: str = Field(alias="agentType")
    status: str
    started_at: datetime = Field(alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    config_snapshot: dict[str, Any] | None = Field(default=None, alias="configSnapshot")
    summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


# --- SMTP Email Configuration & Outbox ---

class SmtpConfigOut(APIModel):
    configured: bool
    status: str
    provider: str
    host: str
    port: int
    username: str
    from_email: str = Field(alias="fromEmail")
    use_tls: bool = Field(alias="useTls")
    has_password: bool = Field(alias="hasPassword")


class SmtpConfigRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    host: str
    port: int = 587
    username: str | None = None
    password: str | None = None
    from_email: str = Field(alias="fromEmail")
    use_tls: bool = Field(default=True, alias="useTls")


class SmtpTestRequest(BaseModel):
    recipient: str
    subject: str | None = None
    body: str | None = None


class SmtpTestOut(APIModel):
    success: bool
    message: str
    message_id: str | None = Field(default=None, alias="messageId")
    provider: str
    bounced: bool = False


class OutboxItemOut(APIModel):
    id: str
    timestamp: str
    recipient: str
    subject: str
    body: str
    html: str | None = None
    provider: str
    status: str
    message_id: str | None = Field(default=None, alias="messageId")
    error: str | None = None





class AgentExecutionMetricOut(APIModel):
    id: int
    workflow_id: str = Field(alias="workflowId")
    agent_name: str = Field(alias="agentName")
    status: str
    duration_ms: int = Field(alias="durationMs")
    prompt_tokens: int = Field(alias="promptTokens")
    completion_tokens: int = Field(alias="completionTokens")
    total_tokens: int = Field(alias="totalTokens")
    estimated_cost: float = Field(alias="estimatedCost")
    model_name: str | None = Field(default=None, alias="modelName")
    error_message: str | None = Field(default=None, alias="errorMessage")
    created_at: datetime = Field(alias="createdAt")


class GuardrailLogOut(APIModel):
    id: int
    workflow_id: str | None = Field(default=None, alias="workflowId")
    agent_name: str = Field(alias="agentName")
    decision: str
    reason: str
    rule_name: str = Field(alias="ruleName")
    input_snippet: str | None = Field(default=None, alias="inputSnippet")
    created_at: datetime = Field(alias="createdAt")
