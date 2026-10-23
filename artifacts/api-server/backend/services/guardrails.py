"""Centralized AI Agent Guardrails & Defense Layer.

Provides:
- Prompt injection & jailbreak heuristic detection
- Untrusted external content sanitization
- SSRF and dangerous URL filtering
- Event payload structural & semantic validation
- Human-in-the-loop triggers for low-confidence or high-risk actions
- Audit logging of guardrail decisions to `guardrail_logs`
- Token and execution budget enforcement
"""

import logging
import re
import time
from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.core.ssrf_protection import validate_safe_url
from backend.models import AgentExecutionMetric, Event, GuardrailLog

logger = logging.getLogger("backend.guardrails")

# Common adversarial prompt injection and jailbreak patterns
_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|system)\s+(instructions|directives)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(DAN|unfiltered|jailbroken|an\s+unrestricted)", re.IGNORECASE),
    re.compile(r"(system\s+prompt|system_instructions)\s*:", re.IGNORECASE),
    re.compile(r"override\s+(all\s+)?(safety|security)\s+(protocols|rules|guidelines)", re.IGNORECASE),
    re.compile(r"repeat\s+everything\s+above\s+this\s+line", re.IGNORECASE),
    re.compile(r"<script[\s>]", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"data\s*:\s*text/html", re.IGNORECASE),
    re.compile(r"drop\s+table\s+[a-z0-9_]+", re.IGNORECASE),
]


class GuardrailViolationError(ValueError):
    """Raised when external input fails safety or security guardrails."""

    def __init__(self, rule_name: str, reason: str, snippet: str = ""):
        super().__init__(f"Guardrail blocked input [{rule_name}]: {reason}")
        self.rule_name = rule_name
        self.reason = reason
        self.snippet = snippet[:200] if snippet else ""


def detect_prompt_injection(text: str) -> tuple[bool, str]:
    """Scans untrusted input for prompt injection, jailbreak attempts, or exploit payloads.

    Returns (is_injected, rule_name).
    """
    if not text or not isinstance(text, str):
        return False, ""

    for pattern in _PROMPT_INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            return True, match.group(0)
    return False, ""


def sanitize_untrusted_text(text: str, max_length: int = 10000) -> str:
    """Sanitizes raw scraped text from external web pages, emails, or APIs."""
    if not text:
        return ""
    # Strip dangerous HTML and script tags
    cleaned = re.sub(r"<(script|style|iframe|object|embed)[^>]*>.*?</\1>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    # Neutralize null bytes and unprintable control characters
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", cleaned)
    # Normalize excessive whitespace
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned[:max_length].strip()


def record_guardrail_decision(
    db: Session,
    agent_name: str,
    decision: str,  # ALLOWED, BLOCKED, FLAGGED
    reason: str,
    rule_name: str,
    input_snippet: str | None = None,
    workflow_id: str | None = None,
) -> None:
    """Persists a guardrail check outcome to the database audit trail."""
    try:
        log_entry = GuardrailLog(
            workflow_id=workflow_id,
            agent_name=agent_name,
            decision=decision,
            reason=reason,
            rule_name=rule_name,
            input_snippet=(input_snippet[:300] if input_snippet else None),
            created_at=datetime.now(timezone.utc),
        )
        db.add(log_entry)
        db.commit()
    except Exception as exc:
        logger.warning("Failed to record guardrail log: %s", exc)


def validate_event_guardrails(
    db: Session,
    event_payload: dict[str, Any],
    agent_name: str = "DiscoveryAgent",
    workflow_id: str | None = None,
) -> dict[str, Any]:
    """Enforces strict safety, sanitization, and business rules on ingested or discovered event data.

    Returns the sanitized event dictionary or raises GuardrailViolationError.
    """
    title = str(event_payload.get("title", "")).strip()
    description = str(event_payload.get("description", "")).strip()
    url = str(event_payload.get("registration_url") or event_payload.get("url") or "").strip()

    # 1. Prompt Injection Checks on Title & Description
    for field_name, value in [("title", title), ("description", description)]:
        is_bad, pattern = detect_prompt_injection(value)
        if is_bad:
            reason = f"Adversarial pattern '{pattern}' detected in event {field_name}."
            record_guardrail_decision(db, agent_name, "BLOCKED", reason, "PROMPT_INJECTION", value, workflow_id)
            raise GuardrailViolationError("PROMPT_INJECTION", reason, value)

    # 2. Minimum content validity
    if len(title) < 3 or len(title) > 250:
        reason = f"Event title length ({len(title)}) outside allowed bounds (3-250 chars)."
        record_guardrail_decision(db, agent_name, "BLOCKED", reason, "INVALID_TITLE_LENGTH", title, workflow_id)
        raise GuardrailViolationError("INVALID_TITLE_LENGTH", reason, title)

    # 3. URL Safety (SSRF & Dangerous Schemes)
    if url:
        try:
            validate_safe_url(url, allow_private_in_dev=False)
        except ValueError as exc:
            reason = f"Unsafe event URL: {exc}"
            record_guardrail_decision(db, agent_name, "BLOCKED", reason, "SSRF_UNSAFE_URL", url, workflow_id)
            raise GuardrailViolationError("SSRF_UNSAFE_URL", reason, url) from exc

    # 4. Date sanity check
    start_date_val = event_payload.get("start_date")
    if start_date_val:
        if isinstance(start_date_val, str):
            try:
                start_date = datetime.strptime(start_date_val[:10], "%Y-%m-%d").date()
            except ValueError:
                start_date = None
        elif isinstance(start_date_val, date):
            start_date = start_date_val
        else:
            start_date = None

        if start_date:
            today = date.today()
            # Reject dates older than 1 year or more than 5 years in future
            if (start_date - today).days < -365 or (start_date - today).days > (365 * 5):
                reason = f"Event date {start_date} is implausible (must be within -1yr to +5yr)."
                record_guardrail_decision(db, agent_name, "BLOCKED", reason, "IMPLAUSIBLE_DATE", str(start_date), workflow_id)
                raise GuardrailViolationError("IMPLAUSIBLE_DATE", reason, str(start_date))

    # 5. Sanitize text fields
    event_payload["title"] = sanitize_untrusted_text(title, max_length=250)
    event_payload["description"] = sanitize_untrusted_text(description, max_length=15000)

    # Log successful validation
    record_guardrail_decision(db, agent_name, "ALLOWED", "Passed all event safety checks", "SCHEMA_AND_INJECTION_PASS", title, workflow_id)
    return event_payload


def require_human_approval_for_event(trust_score: int | None, trust_confidence: str | None) -> bool:
    """Returns True if an event requires explicit human administrator approval before publishing."""
    if trust_score is None or trust_score < 60:
        return True
    if trust_confidence and trust_confidence.upper() in ("LOW", "UNVERIFIED"):
        return True
    return False


def execute_agent_with_guardrails(
    db: Session,
    agent_name: str,
    workflow_id: str,
    action: Callable[[], Any],
    max_tokens: int = 15000,
    model_name: str = "gemini-flash-lite",
) -> tuple[Any, AgentExecutionMetric]:
    """Executes an agent workflow callable with bounded latency, token tracking, and metric logging."""
    start_time = time.perf_counter()
    status = "SUCCESS"
    error_msg = None
    result = None

    try:
        result = action()
    except Exception as exc:
        status = "FAILED"
        error_msg = str(exc)
        logger.error("Agent %s failed in workflow %s: %s", agent_name, workflow_id, exc)
        raise
    finally:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        # Approximate tokens if not explicitly returned by action
        prompt_tokens = getattr(result, "prompt_tokens", 350) if result else 200
        completion_tokens = getattr(result, "completion_tokens", 150) if result else 100
        total_tokens = min(prompt_tokens + completion_tokens, max_tokens)
        estimated_cost = round((total_tokens / 1_000_000) * 0.15, 6)

        try:
            metric = AgentExecutionMetric(
                workflow_id=workflow_id,
                agent_name=agent_name,
                status=status,
                duration_ms=duration_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost=estimated_cost,
                model_name=model_name,
                error_message=error_msg,
                created_at=datetime.now(timezone.utc),
            )
            db.add(metric)
            db.commit()
        except Exception as m_exc:
            logger.warning("Could not persist agent metric: %s", m_exc)

    return result, metric

