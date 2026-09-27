"""EmailProvider — the sending interface Organizer Outreach depends on,
kept separate from the outreach orchestration logic so the sending
mechanism (SMTP today, anything else later) is never hardcoded into the
agent. Mirrors the existing `PlatformPublisher` split in
`services/social_agent/publishers/base.py`.
"""

from abc import ABC, abstractmethod

from backend.services.social_agent.outreach.types import SendResult


class EmailProvider(ABC):
    is_real: bool = False

    @abstractmethod
    def send_message(self, recipient: str, subject: str, body: str) -> SendResult: ...
