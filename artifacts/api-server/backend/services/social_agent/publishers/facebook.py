"""Official Facebook Pages publisher via Meta Graph API.

Publishes announcements and event updates to authorized Facebook Pages using
Page Access Tokens and official Graph API endpoints (`/{page_id}/feed`).
Strictly adheres to dry-run and official verification requirements.
"""

import time
from typing import Any
import httpx

from backend.services.social_agent.connectors.base import _settings_credential
from backend.services.social_agent.publishers.base import PlatformPublisher
from backend.services.social_agent.types import PublishResult

_GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


class FacebookPublisher(PlatformPublisher):
    platform = "facebook"

    @property
    def page_token(self) -> str | None:
        return _settings_credential("facebook_page_access_token")

    @property
    def page_id(self) -> str | None:
        return _settings_credential("facebook_page_id")

    @property
    def is_real(self) -> bool:
        return bool(self.page_token and self.page_id)

    def validate_connection(self) -> dict[str, Any]:
        if not self.page_token:
            return {"connected": False, "message": "FACEBOOK_PAGE_ACCESS_TOKEN not configured."}
        if not self.page_id:
            return {"connected": False, "message": "FACEBOOK_PAGE_ID not configured."}

        try:
            url = f"{_GRAPH_API_BASE}/{self.page_id}"
            params = {"fields": "id,name,category", "access_token": self.page_token}
            resp = httpx.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                page_name = data.get("name", self.page_id)
                return {"connected": True, "message": f"Connected to Facebook Page: '{page_name}' (ID: {self.page_id})"}
            err_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            err_msg = err_data.get("error", {}).get("message", f"HTTP {resp.status_code}")
            return {"connected": False, "message": f"Facebook Graph API validation failed: {err_msg}"}
        except httpx.HTTPError as exc:
            return {"connected": False, "message": f"Network error connecting to Facebook Graph API: {str(exc)}"}

    def validate_publish_permission(self, target_ref: str) -> dict[str, Any]:
        """Validates that the target destination is valid for this Facebook page."""
        target = target_ref or self.page_id
        if not target:
            return {"allowed": False, "message": "No Facebook Page ID specified for publication."}
        conn = self.validate_connection()
        if not conn.get("connected"):
            return {"allowed": False, "message": conn.get("message")}
        return {"allowed": True, "message": f"Authorized to publish to Facebook Page {target}."}

    def publish_reply(self, text: str, target_ref: str) -> PublishResult:
        """Reply to an existing Facebook post comment."""
        return PublishResult(success=False, platform=self.platform, published_url=None, message="Facebook comment replies not supported; standalone page posts supported.")

    def publish_post(self, text: str, target_ref: str, **kwargs: Any) -> PublishResult:
        """Publishes a standalone post to the Facebook Page feed.
        
        Supports `is_dry_run=True` to simulate publication with zero external side effects.
        """
        is_dry_run = kwargs.get("is_dry_run", False)
        target = target_ref or self.page_id or "facebook_page"
        link = kwargs.get("link")

        if is_dry_run:
            simulated_id = f"{target}_{int(time.time())}"
            return PublishResult(
                success=True,
                platform=self.platform,
                published_url=f"https://facebook.com/{target}/posts/{simulated_id}",
                message="[DRY-RUN] Facebook Page post simulated successfully. Graph API was not called.",
                post_id=simulated_id,
            )

        if not self.is_real:
            return PublishResult(
                success=False,
                platform=self.platform,
                published_url=None,
                message="FACEBOOK_PAGE_ACCESS_TOKEN and FACEBOOK_PAGE_ID must be configured for live publishing.",
            )

        try:
            url = f"{_GRAPH_API_BASE}/{target}/feed"
            payload: dict[str, Any] = {
                "message": text,
                "access_token": self.page_token,
            }
            if link:
                payload["link"] = link

            resp = httpx.post(url, data=payload, timeout=15)
            if resp.status_code in (200, 201):
                data = resp.json()
                post_id = data.get("id", f"{target}_{int(time.time())}")
                # Post ID format in FB Graph API is usually {page_id}_{post_fbid}
                parts = post_id.split("_")
                post_fbid = parts[1] if len(parts) > 1 else parts[0]
                published_url = f"https://facebook.com/{target}/posts/{post_fbid}"
                return PublishResult(
                    success=True,
                    platform=self.platform,
                    published_url=published_url,
                    message="Published successfully to Facebook Page via Meta Graph API.",
                    post_id=post_id,
                )
            err_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            err_msg = err_data.get("error", {}).get("message", f"HTTP {resp.status_code}")
            return PublishResult(
                success=False,
                platform=self.platform,
                published_url=None,
                message=f"Facebook Graph API error: {err_msg}",
            )
        except httpx.HTTPError as exc:
            return PublishResult(
                success=False,
                platform=self.platform,
                published_url=None,
                message=f"Network error calling Facebook Graph API: {str(exc)}",
            )

