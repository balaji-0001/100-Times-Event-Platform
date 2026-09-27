from backend.services.social_agent.connectors.base import PlatformConnector, _settings_credential
from backend.services.social_agent.types import Signal


class LinkedInConnector(PlatformConnector):
    platform = "linkedin"
    description = "Professional networking, startup, and conference discussions in permitted groups."
    requires_approval = True  # commercial API access requires the platform's own approval

    @property
    def credential(self) -> str | None:
        return _settings_credential("linkedin_access_token")

    def discover_signals(self) -> list[Signal]:
        return [
            Signal(
                platform="linkedin",
                community_name="LinkedIn Group: Startup Founders India",
                title="Recommend any conferences for founders and operators in Bengaluru?",
                content="Building a seed-stage startup and looking to attend business conferences or networking events in Bengaluru this quarter to meet investors and peers.",
                author="Rhea Kapoor",
                url="https://www.linkedin.com/groups/startup-founders-india/",
            ),
            Signal(
                platform="linkedin",
                community_name="LinkedIn: Women in Tech India",
                title="What tech conferences are happening in Chennai this year?",
                content="Looking for tech conferences, hackathons, or networking events in Chennai for women in engineering leadership roles.",
                author="Sandhya Iyer",
                url="https://www.linkedin.com/groups/women-in-tech-india/",
            ),
        ]
