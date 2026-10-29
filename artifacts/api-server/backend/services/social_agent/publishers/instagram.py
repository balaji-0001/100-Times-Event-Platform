"""Official Instagram publisher via Meta Graph API (Instagram Content Publishing API).

Publishes media posts to authorized Instagram Business / Creator accounts using
official Meta Graph API container creation and media publish endpoints (`/{ig_user_id}/media`).
Strictly adheres to dry-run and official verification requirements.
"""

import time
from typing import Any
import httpx

from backend.services.social_agent.connectors.base import _settings_credential
from backend.services.social_agent.publishers.base import PlatformPublisher
from backend.services.social_agent.types import PublishResult

_GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


class InstagramPublisher(PlatformPublisher):
    platform = "instagram"

    @property
    def access_token(self) -> str | None:
        return _settings_credential("instagram_access_token")

    @property
    def ig_user_id(self) -> str | None:
        return _settings_credential("instagram_business_account_id")

    @property
    def is_real(self) -> bool:
        return bool(self.access_token and self.ig_user_id)

    def validate_connection(self) -> dict[str, Any]:
        if not self.access_token:
            return {"connected": False, "message": "INSTAGRAM_ACCESS_TOKEN not configured."}
        if not self.ig_user_id:
            return {"connected": False, "message": "INSTAGRAM_BUSINESS_ACCOUNT_ID not configured."}

        try:
            url = f"{_GRAPH_API_BASE}/{self.ig_user_id}"
            params = {"fields": "id,username,name", "access_token": self.access_token}
            resp = httpx.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                username = data.get("username", self.ig_user_id)
                return {"connected": True, "message": f"Connected to Instagram Business account: @{username}"}
            err_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            err_msg = err_data.get("error", {}).get("message", f"HTTP {resp.status_code}")
            return {"connected": False, "message": f"Instagram Graph API validation failed: {err_msg}"}
        except httpx.HTTPError as exc:
            return {"connected": False, "message": f"Network error connecting to Instagram Graph API: {str(exc)}"}

    def validate_publish_permission(self, target_ref: str) -> dict[str, Any]:
        target = target_ref or self.ig_user_id
        if not target:
            return {"allowed": False, "message": "No Instagram Business Account ID specified."}
        conn = self.validate_connection()
        if not conn.get("connected"):
            return {"allowed": False, "message": conn.get("message")}
        return {"allowed": True, "message": f"Authorized to publish to Instagram Account {target}."}

    def permalink(self, media_id: str) -> str | None:
        """The post's public link, as Instagram gives it. A post's URL uses its
        shortcode (instagram.com/p/<shortcode>/), not the numeric media id the
        publish call returns, so the link can't be built from the id."""
        try:
            resp = httpx.get(f"{_GRAPH_API_BASE}/{media_id}", params={"fields": "permalink", "access_token": self.access_token}, timeout=10)
            if resp.status_code == 200:
                link = resp.json().get("permalink")
                return link if isinstance(link, str) and link.startswith("https://") else None
        except (httpx.HTTPError, ValueError):
            pass
        return None

    def publish_reply(self, text: str, target_ref: str) -> PublishResult:
        return PublishResult(success=False, platform=self.platform, published_url=None, message="Instagram comment replies not supported; media feed publishing supported.")

    def publish_post(self, text: str, target_ref: str, **kwargs: Any) -> PublishResult:
        """Publishes an image post to Instagram via official 2-step media container flow.
        
        Supports `is_dry_run=True` to simulate publication with zero external side effects.
        """
        is_dry_run = kwargs.get("is_dry_run", False)
        target = target_ref or self.ig_user_id or "instagram_business"
        image_url = kwargs.get("image_url") or (kwargs.get("media_urls", [None])[0] if kwargs.get("media_urls") else None)

        if is_dry_run:
            simulated_id = f"dry_run_ig_{int(time.time())}"
            return PublishResult(
                success=True,
                platform=self.platform,
                published_url=None,  # nothing was posted, so there is no Instagram page to link to
                message="[DRY-RUN] Instagram post simulated successfully. Media container not created.",
                post_id=simulated_id,
            )

        if not self.is_real:
            return PublishResult(
                success=False,
                platform=self.platform,
                published_url=None,
                message="INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_BUSINESS_ACCOUNT_ID must be configured for live publishing.",
            )

        if not image_url:
            return PublishResult(
                success=False,
                platform=self.platform,
                published_url=None,
                message="Instagram Content Publishing API requires a public image URL for feed posts.",
            )

        try:
            # Step 1: Create media container
            container_url = f"{_GRAPH_API_BASE}/{target}/media"
            container_payload = {
                "image_url": image_url,
                "caption": text,
                "access_token": self.access_token,
            }
            c_resp = httpx.post(container_url, data=container_payload, timeout=20)
            if c_resp.status_code not in (200, 201):
                err = c_resp.json().get("error", {}).get("message", f"HTTP {c_resp.status_code}")
                return PublishResult(success=False, platform=self.platform, published_url=None, message=f"Instagram media container creation failed: {err}")

            creation_id = c_resp.json().get("id")
            if not creation_id:
                return PublishResult(success=False, platform=self.platform, published_url=None, message="Instagram API returned empty container ID.")

            # Step 2: Publish media container
            publish_url = f"{_GRAPH_API_BASE}/{target}/media_publish"
            p_resp = httpx.post(publish_url, data={"creation_id": creation_id, "access_token": self.access_token}, timeout=20)
            if p_resp.status_code not in (200, 201):
                err = p_resp.json().get("error", {}).get("message", f"HTTP {p_resp.status_code}")
                return PublishResult(success=False, platform=self.platform, published_url=None, message=f"Instagram media publish failed: {err}")

            media_id = p_resp.json().get("id", creation_id)
            published_url = self.permalink(media_id)
            return PublishResult(
                success=True,
                platform=self.platform,
                published_url=published_url,
                message="Published successfully to Instagram via Meta Graph API."
                + ("" if published_url else " Instagram didn't return the post's link yet."),
                post_id=media_id,
            )
        except httpx.HTTPError as exc:
            return PublishResult(
                success=False,
                platform=self.platform,
                published_url=None,
                message=f"Network error calling Instagram Graph API: {str(exc)}",
            )

