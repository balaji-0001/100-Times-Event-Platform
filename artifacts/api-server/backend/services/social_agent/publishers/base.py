"""Platform Publisher Layer.

Separate from the Connector layer (discovery/read) by design — a platform's
read and write APIs often have different auth scopes, different approval
gates, and different failure modes.

After human approval, the flow is always exactly these four steps (see
`routes/acquisition.py`'s `/publish` endpoint):
  validate_connection -> validate_publish_permission -> publish_reply -> verify_publication

`publish_post` is the same flow's standalone-post sibling, added for Agent
4's community-promotion extension: a proactive announcement into a
destination with no inbound discussion to reply to (`target_ref` is just
the chat/channel, no message id — see each platform's publisher for the
exact format). Same approval gate, same connection/permission checks, same
never-fabricate-success rule.

Nothing here is ever called without an explicit human click. Nothing here
is ever allowed to fabricate a success result.
"""

from abc import ABC, abstractmethod
from typing import Any

from backend.services.social_agent.types import PublishResult


class PlatformPublisher(ABC):
    platform: str = "base"

    @property
    def is_real(self) -> bool:
        """True only for a publisher with a genuine, working API
        implementation — used to decide whether a platform can skip Manual
        Publishing Mode."""
        return False

    def validate_connection(self) -> dict[str, Any]:
        """Confirms the publish credential itself is valid."""
        return {"connected": False, "message": f"{self.platform} has no real publish integration configured."}

    def validate_publish_permission(self, target_ref: str) -> dict[str, Any]:
        """Confirms the authenticated account can actually post to this
        specific destination (e.g. the bot is a member of the target
        chat/channel/server)."""
        return {"allowed": False, "message": "No publish integration to check permissions against."}

    @abstractmethod
    def publish_reply(self, text: str, target_ref: str) -> PublishResult:
        """Attempts the real publish, as a reply. Must never fabricate success."""

    def publish_post(self, text: str, target_ref: str, **kwargs: Any) -> PublishResult:
        """Attempts the real publish as a standalone post (no reply target).
        Base implementation reports an honest "not supported" failure, like
        every other not-yet-implemented capability here; platforms with a
        real integration override this."""
        return PublishResult(success=False, platform=self.platform, published_url=None, message=f"{self.platform} has no standalone-post publish integration configured.")

    def verify_publication(self, result: PublishResult) -> PublishResult:
        """Optional post-publish confirmation (e.g. re-checking the post
        wasn't silently removed by a spam filter). Base implementation
        trusts the platform API's own success response."""
        return result
