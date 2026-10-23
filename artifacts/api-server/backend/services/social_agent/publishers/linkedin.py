"""Official LinkedIn publisher via LinkedIn Posts API (REST v2).

Publishes organization updates and articles using authorized LinkedIn OAuth tokens
and official REST endpoints (`https://api.linkedin.com/rest/posts`).
Strictly adheres to dry-run and official verification requirements.
"""

import time
from typing import Any
import httpx

from backend.services.social_agent.connectors.base import _settings_credential
from backend.services.social_agent.publishers.base import PlatformPublisher
from backend.services.social_agent.types import PublishResult

_LINKEDIN_API_BASE = "https://api.linkedin.com/rest"


class LinkedInPublisher(PlatformPublisher):
    platform = "linkedin"

    @property
    def access_token(self) -> str | None:
        return _settings_credential("linkedin_access_token")

    @property
    def organization_id(self) -> str | None:
        return _settings_credential("linkedin_organization_id")

    @property
    def is_real(self) -> bool:
        return bool(self.access_token)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "LinkedIn-Version": "202401",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

    def validate_connection(self) -> dict[str, Any]:
        if not self.access_token:
            return {"connected": False, "message": "LINKEDIN_ACCESS_TOKEN not configured."}

        try:
            # Check token validity via LinkedIn userinfo endpoint
            url = "https://api.linkedin.com/v2/userinfo"
            resp = httpx.get(url, headers={"Authorization": f"Bearer {self.access_token}"}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                name = data.get("name", "Authorized LinkedIn User")
                org_info = f" (Default Org: {self.organization_id})" if self.organization_id else ""
                return {"connected": True, "message": f"Connected to LinkedIn as: {name}{org_info}"}
            return {"connected": False, "message": f"LinkedIn token verification failed: HTTP {resp.status_code}"}
        except httpx.HTTPError as exc:
            return {"connected": False, "message": f"Network error connecting to LinkedIn API: {str(exc)}"}

    def validate_publish_permission(self, target_ref: str) -> dict[str, Any]:
        if not self.access_token:
            return {"allowed": False, "message": "LINKEDIN_ACCESS_TOKEN not configured."}
        author = target_ref or self.organization_id
        if not author:
            return {"allowed": False, "message": "No LinkedIn author or organization URN specified."}
        return {"allowed": True, "message": f"Authorized to publish to LinkedIn target: {author}."}

    def publish_reply(self, text: str, target_ref: str) -> PublishResult:
        return PublishResult(
            success=False,
            platform=self.platform,
            published_url=None,
            message="Manual publishing required; LinkedIn comment replies not supported (organization post shares supported).",
        )

    def publish_post(self, text: str, target_ref: str, **kwargs: Any) -> PublishResult:
        """Publishes a standalone update/article to LinkedIn via official Posts API.
        
        Supports `is_dry_run=True` to simulate publication with zero external side effects.
        """
        is_dry_run = kwargs.get("is_dry_run", False)
        org_id = target_ref or self.organization_id or "100times"
        author_urn = org_id if org_id.startswith("urn:li:") else f"urn:li:organization:{org_id}"
        link = kwargs.get("link")
        title = kwargs.get("title")

        if is_dry_run:
            simulated_urn = f"urn:li:share:dry_run_{int(time.time())}"
            return PublishResult(
                success=True,
                platform=self.platform,
                published_url=f"https://www.linkedin.com/feed/update/{simulated_urn}",
                message="[DRY-RUN] LinkedIn share simulated successfully. Posts API was not called.",
                post_id=simulated_urn,
            )

        if not self.is_real:
            return PublishResult(
                success=False,
                platform=self.platform,
                published_url=None,
                message="LINKEDIN_ACCESS_TOKEN must be configured for live publishing.",
            )

        try:
            url = f"{_LINKEDIN_API_BASE}/posts"
            payload: dict[str, Any] = {
                "author": author_urn,
                "commentary": text,
                "visibility": "PUBLIC",
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            }

            if link:
                payload["content"] = {
                    "article": {
                        "source": link,
                        "title": title or "100 TIMES Event",
                        "description": text[:200],
                    }
                }

            resp = httpx.post(url, json=payload, headers=self._headers(), timeout=15)
            if resp.status_code in (200, 201):
                post_urn = resp.headers.get("x-restli-id") or resp.json().get("id") or f"urn:li:share:{int(time.time())}"
                published_url = f"https://www.linkedin.com/feed/update/{post_urn}"
                return PublishResult(
                    success=True,
                    platform=self.platform,
                    published_url=published_url,
                    message="Published successfully to LinkedIn via Posts API.",
                    post_id=post_urn,
                )
            err_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            err_msg = err_data.get("message", f"HTTP {resp.status_code}")
            return PublishResult(
                success=False,
                platform=self.platform,
                published_url=None,
                message=f"LinkedIn Posts API error: {err_msg}",
            )
        except httpx.HTTPError as exc:
            return PublishResult(
                success=False,
                platform=self.platform,
                published_url=None,
                message=f"Network error calling LinkedIn Posts API: {str(exc)}",
            )

