# Trust Agent (Agent 3) Documentation

## Purpose
**Trust Agent** (`backend/services/trust_agent/agent.py`) evaluates every submitted event before public listing to ensure marketplace quality, safety, and authenticity.

## Inspection Signals
1. **Completeness Check:** Validates title, minimum description length, start date/time, venue/address (for offline/hybrid), and meeting URL (for online/hybrid).
2. **Organizer Identity & Velocity:** Verifies `OrganizerProfile` email/company verification and checks 24-hour submission frequency against `TRUST_AGENT_MAX_DAILY_SUBMISSIONS_PER_ORGANIZER`.
3. **Duplicate Detection:** Computes title similarity (`SequenceMatcher`) and date overlap against both published `Event` rows and `DiscoveredEvent` listings, saving matches in `duplicate_candidates`.
4. **Prohibited, Scam & Spam Filtering:** Flags illegal schemes, deceptive financial claims, invalid URLs, and spam patterns.
5. **AI Semantic Assessment:** Uses `ai_client.py` (`generate_structured`) with Gemini/Anthropic when configured, falling back safely to deterministic scoring if the AI key is absent.

## Output Schema (`TrustAgentResult`)
```json
{
  "status": "APPROVED | NEEDS_REVIEW | REJECTED | DUPLICATE",
  "score": 95,
  "confidence": "HIGH | MEDIUM | LOW",
  "reasons": ["All completeness, organizer identity, duplicate, and safety checks passed with high confidence."],
  "warnings": [],
  "duplicate_candidates": [],
  "missing_fields": [],
  "recommended_action": "AUTO_PUBLISH | HUMAN_REVIEW | REJECT | REQUEST_CHANGES"
}
```

## Decision Matrix
- **HIGH confidence + safe (`score >= 75` & zero warnings):** Auto-approves and transitions event to `PUBLISHED`.
- **MEDIUM or LOW confidence:** Transitions event to `NEEDS_REVIEW` and notifies the organizer (`"Your event is under review."`).
- **Prohibited or Duplicate:** Transitions to `REJECTED` or `DUPLICATE`.
- **Admin Moderation (`/admin/trust-review`):** Admins can **Approve**, **Reject**, or **Request Changes**, logging every action in `trust_decisions` and `audit_logs`.
