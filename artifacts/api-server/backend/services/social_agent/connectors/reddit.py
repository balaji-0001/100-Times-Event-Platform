from backend.services.social_agent.connectors.base import PlatformConnector, _settings_credential
from backend.services.social_agent.types import Signal


class RedditConnector(PlatformConnector):
    platform = "reddit"
    description = "Public subreddit discussions matched against event-seeking intent."
    requires_approval = True  # commercial API access requires the platform's own approval

    @property
    def credential(self) -> str | None:
        return _settings_credential("reddit_client_id")

    def discover_signals(self) -> list[Signal]:
        return [
            Signal(
                platform="reddit",
                community_name="r/hyderabad",
                title="Are there any AI workshops or tech summits happening in Hyderabad this month?",
                content="Looking to upskill in machine learning, LLM systems, and meet other practitioners in Hyderabad. Any recommended workshops or hackathons?",
                author="tech_seeker_hyd",
                url="https://www.reddit.com/r/hyderabad/search/?q=AI+workshops+Hyderabad",
            ),
            Signal(
                platform="reddit",
                community_name="r/bangalore",
                title="Looking for startup networking events this weekend",
                content="Just moved to Bengaluru. Working on an early-stage B2B SaaS product and want to connect with other founders, operators, and potential angel investors.",
                author="saas_builder_blr",
                url="https://www.reddit.com/r/bangalore/search/?q=startup+networking",
            ),
            Signal(
                platform="reddit",
                community_name="r/developersIndia",
                title="Does anyone know any upcoming hackathons or developer conferences?",
                content="Looking for in-person tech hackathons or developer conferences with hands-on labs and peer roundtables. Open to Bengaluru, Hyderabad, or Mumbai.",
                author="dev_student_2026",
                url="https://www.reddit.com/r/developersIndia/search/?q=upcoming+hackathons",
            ),
            Signal(
                platform="forum",
                community_name="DesignCraft India",
                title="Top design workshops and Figma masterclasses in Mumbai?",
                content="Product designer here looking for advanced design systems and UX workshops happening in Mumbai or online. Budget is flexible.",
                author="priya_ux",
                url="https://news.ycombinator.com/",
            ),
            Signal(
                platform="reddit",
                community_name="r/mumbai",
                title="Tech conferences are becoming too expensive nowadays",
                content="I feel like conference ticket prices are ridiculous lately. Some charge ₹15,000 for 2 days. Anyone else feel the same?",
                author="frugal_engineer",
                url="https://www.reddit.com/r/mumbai/search/?q=tech+conferences",
            ),
        ]
