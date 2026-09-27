"""Honest stub publisher for any platform without a real, working publish
integration yet. Never returns success — always reports Manual Publishing
Mode, or an approval-required message when the platform itself (not just a
missing credential) is the blocker."""

from backend.services.social_agent.publishers.base import PlatformPublisher
from backend.services.social_agent.types import PublishResult


class StubPublisher(PlatformPublisher):
    def __init__(self, platform: str, requires_approval: bool = False) -> None:
        self.platform = platform
        self._requires_approval = requires_approval

    def publish_reply(self, text: str, target_ref: str) -> PublishResult:
        if self._requires_approval:
            message = (
                f"{self.platform} publishing requires the platform's own approval "
                "(commercial API access / app review) before this can go live — "
                "adding a credential alone would not be enough. Manual publishing required for now."
            )
        else:
            message = (
                f"{self.platform} has no configured publish integration yet. "
                "Manual publishing required: copy the approved content, post it yourself, "
                "then confirm with the published URL."
            )
        return PublishResult(success=False, platform=self.platform, published_url=None, message=message)
