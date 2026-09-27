from backend.services.social_agent.connectors.base import PlatformConnector, _settings_credential
from backend.services.social_agent.types import Signal


class XConnector(PlatformConnector):
    platform = "x"
    description = "Permitted public real-time conversations about events, matched by keyword."
    requires_approval = True  # commercial API access requires the platform's own approval

    @property
    def credential(self) -> str | None:
        return _settings_credential("x_bearer_token")

    def discover_signals(self) -> list[Signal]:
        return [
            Signal(
                platform="x",
                community_name="X / #TechMeetup",
                title="does anyone know any upcoming tech meetups in Pune?",
                content="just moved to Pune for work and want to find tech meetups or hackathons to meet people. any leads?",
                author="@pune_newgrad",
                url="https://x.com/search?q=tech%20meetups%20Pune",
            ),
            Signal(
                platform="x",
                community_name="X / #DesignEvents",
                title="are there any design workshops in Mumbai next month?",
                content="Looking for UX or design workshops in Mumbai next month. Would also love recommend any meetups for product designers.",
                author="@ux_marcus",
                url="https://x.com/search?q=design%20workshops%20Mumbai",
            ),
        ]
