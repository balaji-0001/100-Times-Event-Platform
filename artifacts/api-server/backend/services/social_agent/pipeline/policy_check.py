"""Stage: RULES_CHECKED — Community Policy Engine.

Thin wrapper over `CommunityRulesChecker` (the proven, existing logic) that
adds one explicit honesty rule the old version didn't surface: a community
with no verified `rules_text` is NOT assumed to allow promotion — it's
flagged `requires_human_review=True` so the dashboard can call that out
instead of silently treating "unknown" as "permitted".
"""

from typing import Any

from backend.models import Community


def check_policy(community: Community | None) -> dict[str, Any]:
    from backend.services.acquisition_agent import CommunityRulesChecker

    result = CommunityRulesChecker.check_rules(community)
    result["requires_human_review"] = community is None or not (community.rules_text or "").strip()
    return result
