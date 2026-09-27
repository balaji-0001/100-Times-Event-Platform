"""Discovery Pipeline — the generic, topic-agnostic acquisition agent.

Chains: normalize (original discussion) -> intent extraction (AI, now also
produces dynamic search queries/keywords/synonyms) -> qualification
(deterministic) -> PLATFORM SEARCH (generic relevance ranking over whatever
the selected connector can legitimately return) -> per-candidate event
extraction (AI) -> 100.com duplicate check (deterministic, existing
EventMatchingEngine) -> branch:

  Case A (matches an existing 100.com event): generate a reply for the
  ORIGINAL discussion pointing at it, queued for human approval/publish.

  Case B (no existing match — a genuinely new event): stage the extracted
  event as an acquisition opportunity for human approval; approving it
  creates the real Event (see `routes/acquisition.py::update_opportunity_
  action`, which calls `backend.services.event_creation`).

Nothing here is specific to any topic or category — "biking" is just
whatever the AI-generated `search_queries` happen to contain for a given
discussion; a different discussion produces entirely different queries and
therefore entirely different search results and candidates.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.models import (
    AcquisitionOpportunity,
    AgentAction,
    Discussion,
    PipelineExecution,
    PipelineStageLog,
)
from backend.services.social_agent.connectors import get_connector
from backend.services.social_agent.pipeline import (
    content_generation,
    event_extraction,
    intent_extraction,
    normalize,
    platform_search,
    policy_check,
    qualification,
)
from backend.services.social_agent.pipeline.event_matching import QUALIFIED_MATCH_THRESHOLD
from backend.services.acquisition_agent import EventMatchingEngine
from backend.services.social_agent.outreach.orchestrator import run_organizer_outreach

MAX_CANDIDATES_TO_EXTRACT = 5
MIN_EVENT_CONFIDENCE = 40


def _log(db: Session, execution: PipelineExecution, stage: str, status: str, detail: dict[str, Any] | None = None) -> None:
    db.add(
        PipelineStageLog(
            pipeline_execution_id=execution.id,
            stage=stage,
            status=status,
            detail=detail or {},
            created_at=datetime.now(timezone.utc),
        )
    )


def _finish(db: Session, execution: PipelineExecution, discussion: Discussion, final_status: str) -> None:
    # Deliberately bypasses `transition_discussion()`: that guard models the
    # single-discussion-direct-match FSM in `pipeline/orchestrator.py`. This
    # pipeline fans one discussion out into N candidate-derived opportunities,
    # which doesn't fit a strict linear per-discussion state machine.
    discussion.pipeline_status = final_status
    execution.completed_at = datetime.now(timezone.utc)
    execution.final_status = final_status
    db.commit()


def _guess_start_date(raw: str) -> tuple[date, bool]:
    """Best-effort parse of the AI's free-text date into a real `date`.
    Never invents a *specific* date the model didn't imply — falls back to
    two weeks out and flags `approximate=True` so a human reviewer knows to
    verify it before the event goes live."""
    raw = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(raw, fmt).date(), False
        except ValueError:
            continue
    return date.today() + timedelta(days=14), True


def _build_topic_summary(ai_intent: intent_extraction.ExtractedIntentAI) -> str:
    parts = [ai_intent.topic] if ai_intent.topic else []
    if ai_intent.keywords:
        parts.append("keywords: " + ", ".join(ai_intent.keywords))
    if ai_intent.location.city or ai_intent.location.state or ai_intent.location.country:
        loc = ai_intent.location.city or ai_intent.location.state or ai_intent.location.country
        parts.append(f"location: {loc}")
    return "; ".join(parts) or "general event search"


def run_discovery_pipeline(
    db: Session,
    platform: str,
    community_name: str,
    title: str,
    content: str,
    url: str = "",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "platform": platform,
        "communityName": community_name,
        "title": title,
        "topic": None,
        "searchQueries": [],
        "candidatesFound": 0,
        "candidates": [],
        "opportunitiesCreated": [],
        "message": "",
    }

    # --- Stage: NORMALIZED (+ dedup of the original discussion) ---
    norm = normalize.normalize_signal(db, platform=platform, community_name=community_name, title=title, content=content, url=url)
    discussion = norm.discussion
    community = norm.community

    if norm.is_duplicate:
        # Same guard `pipeline/orchestrator.py::run_pipeline` applies for the
        # direct-match flow — without it, a scheduled/automatic caller would
        # re-run this AI-heavy search+extraction on every tick for whatever
        # fixed signal a mock connector keeps returning, burning AI calls and
        # creating duplicate "new event candidate" review cards each time.
        result["message"] = "This discussion was already processed in a previous cycle — nothing new to search for."
        return result

    execution = PipelineExecution(discussion_id=discussion.id, started_at=datetime.now(timezone.utc))
    db.add(execution)
    db.flush()
    _log(db, execution, "NORMALIZE", "success", {"communityId": community.id, "platform": platform, "wasDuplicate": norm.is_duplicate})

    # --- Stage: INTENT_EXTRACTED (AI) — also produces the dynamic search queries ---
    extraction = intent_extraction.extract_intent(title, content)
    if not extraction.success:
        _log(db, execution, "INTENT_EXTRACTION", "failed", {"reason": extraction.error})
        _finish(db, execution, discussion, "FAILED_AI_EXTRACTION")
        result["message"] = extraction.error or "AI intent extraction failed"
        return result

    ai_intent = extraction.data
    discussion.ai_intent = ai_intent.model_dump()
    discussion.ai_extraction_retry_count = extraction.retry_count
    result["topic"] = {
        "topic": ai_intent.topic,
        "eventCategory": ai_intent.event_category,
        "keywords": ai_intent.keywords,
        "synonyms": ai_intent.synonyms,
        "entities": ai_intent.entities,
        "location": ai_intent.location.model_dump(),
    }
    result["searchQueries"] = ai_intent.search_queries
    _log(db, execution, "INTENT_EXTRACTION", "success", {"intentType": ai_intent.intent_type, "searchQueries": ai_intent.search_queries})

    # --- Stage: QUALIFIED (deterministic) — gate obvious spam/irrelevance only ---
    qual = qualification.qualify(ai_intent)
    discussion.qualification_score = qual.score
    discussion.qualification_breakdown = qual.breakdown
    discussion.intent_classification = qual.level
    _log(db, execution, "QUALIFICATION", "success", {"score": qual.score, "level": qual.level})

    if qual.level == "IRRELEVANT" or not ai_intent.search_queries:
        discussion.rejection_reason = "Not event-related, or no search queries were generated"
        discussion.status = "ignored"
        _log(db, execution, "PLATFORM_SEARCH", "skipped", {"reason": discussion.rejection_reason})
        _finish(db, execution, discussion, "REJECTED_LOW_INTENT")
        result["message"] = discussion.rejection_reason
        return result

    # --- Stage: PLATFORM_SEARCH (generic relevance search, any platform/topic) ---
    try:
        connector = get_connector(platform)
    except ValueError as exc:
        _log(db, execution, "PLATFORM_SEARCH", "failed", {"reason": str(exc)})
        _finish(db, execution, discussion, "FAILED_PROCESSING")
        result["message"] = str(exc)
        return result

    queries = [*ai_intent.search_queries, *ai_intent.keywords, *ai_intent.synonyms]
    scored_candidates = platform_search.search_platform(
        connector, queries, exclude_external_ids={discussion.external_id}, limit=15
    )
    result["candidatesFound"] = len(scored_candidates)
    _log(
        db, execution, "PLATFORM_SEARCH", "success",
        {"connectorStatus": connector.status, "queriesUsed": queries, "candidatesFound": len(scored_candidates)},
    )

    if not scored_candidates:
        discussion.status = "processed"
        _finish(db, execution, discussion, "REJECTED_NO_MATCH")
        result["message"] = (
            f"Understood the topic and searched {platform} with {len(ai_intent.search_queries)} dynamic "
            f"quer{'y' if len(ai_intent.search_queries) == 1 else 'ies'}, but found no relevant candidate posts "
            f"({connector.status} connector)."
        )
        return result

    rules_check = policy_check.check_policy(community)
    topic_summary = _build_topic_summary(ai_intent)
    location_hint = ai_intent.location.city or ai_intent.location.state or ai_intent.location.country or None

    # --- Stage: EVENT_EXTRACTION + MATCH + CASE A/B, per candidate ---
    for scored in scored_candidates[:MAX_CANDIDATES_TO_EXTRACT]:
        sig = scored.signal
        candidate_out: dict[str, Any] = platform_search.scored_signal_to_dict(scored)
        result["candidates"].append(candidate_out)

        # Dedup: has this exact candidate post already been processed by a previous run?
        candidate_norm = normalize.normalize_signal(
            db, platform=sig.platform, community_name=sig.community_name, title=sig.title,
            content=sig.content, url=sig.url, external_id=sig.external_id, author=sig.author,
        )
        if candidate_norm.is_duplicate:
            candidate_out["outcome"] = "SKIPPED_ALREADY_PROCESSED"
            continue

        extracted = event_extraction.extract_event(topic_summary, sig.title, sig.content)
        if not extracted.success:
            candidate_out["outcome"] = "SKIPPED_EXTRACTION_FAILED"
            candidate_out["reason"] = extracted.error
            continue

        ev = extracted.data
        if not ev.is_genuine_event or ev.confidence_score < MIN_EVENT_CONFIDENCE:
            candidate_out["outcome"] = "SKIPPED_NOT_A_GENUINE_EVENT"
            candidate_out["reason"] = ev.reason
            continue

        candidate_out["extractedEvent"] = ev.model_dump()

        hint = event_extraction.flatten_extracted_event(ev)
        relevance_score, matched_events = EventMatchingEngine.match_events(db, hint)

        candidate_source = {
            "platform": sig.platform, "community": sig.community_name, "title": sig.title,
            "url": sig.url, "externalId": sig.external_id, "relevance": scored.relevance,
            "matchedQueries": scored.matched_queries,
        }

        if matched_events and relevance_score >= QUALIFIED_MATCH_THRESHOLD:
            # --- CASE A: this event already exists on 100.com ---
            gen = content_generation.generate_content(platform, title, content, matched_events, rules_check, location_hint)
            response_text = gen.data.content if gen.success else (
                f"Good news — we found an existing 100Times listing that matches: {matched_events[0]['title']} "
                f"on {matched_events[0]['startDate']}. https://100times.in/events/{matched_events[0]['slug']}"
            )
            opportunity = AcquisitionOpportunity(
                discussion_id=discussion.id,
                matching_events=matched_events,
                relevance_score=relevance_score,
                generated_response=response_text,
                response_variations=[response_text],
                content_payload={"discoveryKind": "existing_event_match", "candidateSource": candidate_source, "extractedEvent": ev.model_dump()},
                content_generated_by=gen.generated_by if gen.success else "deterministic_fallback",
                approval_status="pending",
                created_at=datetime.now(timezone.utc),
            )
            db.add(opportunity)
            db.add(AgentAction(
                opportunity=opportunity, action_type="opportunity_created",
                result=f"Existing-event match found via platform search (relevance {relevance_score}/100) from {sig.platform}:{sig.community_name}",
                created_at=datetime.now(timezone.utc),
            ))
            candidate_out["outcome"] = "EXISTING_EVENT_MATCH"
            candidate_out["relevanceScore"] = relevance_score
        else:
            # --- CASE B: genuinely new event, not yet on 100.com ---
            guessed_date, is_approximate = _guess_start_date(ev.date)
            price_str = "Free" if ev.is_free else (f"₹{ev.price:.0f}" if ev.price is not None else "price TBC")
            draft = (
                f"New event candidate discovered: \"{ev.event_name or sig.title}\"\n"
                f"Category: {ev.category or 'Uncategorized'} | Type: {ev.event_type or 'Event'}\n"
                f"Date: {ev.date or '(unspecified — defaulted to ' + guessed_date.isoformat() + ', please verify)'} "
                f"{ev.time}\nLocation: {ev.location or 'Unspecified'} | {price_str}\n"
                f"Organizer: {ev.organizer or 'Unknown'}\n"
                f"{ev.description}\n\nSource: {sig.url or sig.community_name} ({sig.platform})"
            )
            opportunity = AcquisitionOpportunity(
                discussion_id=discussion.id,
                matching_events=[],
                relevance_score=ev.relevance_score,
                generated_response=draft,
                response_variations=[draft],
                content_payload={
                    "discoveryKind": "new_event_candidate",
                    "candidateSource": candidate_source,
                    "extractedEvent": ev.model_dump(),
                    "guessedStartDate": guessed_date.isoformat(),
                    "dateIsApproximate": is_approximate,
                },
                content_generated_by="ai",
                policy_notes=["New event — approving this will create a real 100Times listing."],
                approval_status="pending",
                created_at=datetime.now(timezone.utc),
            )
            db.add(opportunity)
            db.add(AgentAction(
                opportunity=opportunity, action_type="opportunity_created",
                result=f"New event candidate discovered via platform search (confidence {ev.confidence_score}/100) from {sig.platform}:{sig.community_name}",
                created_at=datetime.now(timezone.utc),
            ))
            candidate_out["outcome"] = "NEW_EVENT_CANDIDATE"
            candidate_out["confidenceScore"] = ev.confidence_score

        db.flush()
        result["opportunitiesCreated"].append({"opportunityId": opportunity.id, "kind": candidate_out["outcome"]})

        if candidate_out["outcome"] == "NEW_EVENT_CANDIDATE":
            # --- Organizer Outreach: automated, additive step. A genuinely new
            # event (not yet on 100.com) is exactly the case worth inviting its
            # organizer to list — see services/social_agent/outreach/. Wrapped
            # so a failure here can never break event discovery itself. ---
            try:
                candidate_out["organizerOutreach"] = run_organizer_outreach(
                    db,
                    discussion_id=discussion.id,
                    opportunity_id=opportunity.id,
                    extracted_event=ev,
                    source_url=sig.url or "",
                    community=candidate_norm.community,
                )
            except Exception as exc:  # noqa: BLE001 - outreach must never break discovery
                candidate_out["organizerOutreach"] = {"outcome": "ERROR", "reason": str(exc)}

    discussion.status = "processed"
    final_status = "PENDING_APPROVAL" if result["opportunitiesCreated"] else "REJECTED_NO_MATCH"
    _log(db, execution, "APPROVAL_QUEUE", "success", {"opportunitiesCreated": len(result["opportunitiesCreated"])})
    _finish(db, execution, discussion, final_status)

    if result["opportunitiesCreated"]:
        result["message"] = (
            f"Searched {platform} with {len(ai_intent.search_queries)} dynamic queries, found "
            f"{len(scored_candidates)} relevant candidate(s), and created {len(result['opportunitiesCreated'])} "
            f"opportunity(ies) for human approval."
        )
    else:
        result["message"] = (
            f"Searched {platform} and found {len(scored_candidates)} relevant candidate(s), but none described "
            f"a genuine, specific event worth queuing for approval."
        )

    return result
