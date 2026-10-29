"""An Instagram post's link is the permalink Instagram returns (shortcode URL),
never one built from the numeric media id; a dry run has no link at all."""

from types import SimpleNamespace

from backend.services.social_agent.publishers import instagram
from backend.services.social_agent.publishers.instagram import InstagramPublisher


def _resp(status, body):
    return SimpleNamespace(status_code=status, json=lambda: body, headers={"content-type": "application/json"})


def _publisher(monkeypatch):
    monkeypatch.setattr(instagram, "_settings_credential", lambda name: {"instagram_access_token": "t", "instagram_business_account_id": "42"}[name])
    return InstagramPublisher()


def test_published_link_is_instagrams_permalink(monkeypatch):
    pub = _publisher(monkeypatch)
    posts = iter([_resp(200, {"id": "container-1"}), _resp(200, {"id": "17980055034133300"})])
    monkeypatch.setattr(instagram.httpx, "post", lambda *a, **k: next(posts))
    seen = {}

    def fake_get(url, params=None, timeout=None):
        seen["url"], seen["fields"] = url, params["fields"]
        return _resp(200, {"permalink": "https://www.instagram.com/p/DfBeUYNFDTr/"})

    monkeypatch.setattr(instagram.httpx, "get", fake_get)
    result = pub.publish_post("caption", "", image_url="https://example.com/a.jpg")
    assert result.success and result.post_id == "17980055034133300"
    assert result.published_url == "https://www.instagram.com/p/DfBeUYNFDTr/"
    assert seen == {"url": f"{instagram._GRAPH_API_BASE}/17980055034133300", "fields": "permalink"}


def test_no_link_when_instagram_gives_none_and_for_dry_runs(monkeypatch):
    pub = _publisher(monkeypatch)
    posts = iter([_resp(200, {"id": "c"}), _resp(200, {"id": "123"})])
    monkeypatch.setattr(instagram.httpx, "post", lambda *a, **k: next(posts))
    monkeypatch.setattr(instagram.httpx, "get", lambda *a, **k: _resp(400, {"error": {"message": "x"}}))
    result = pub.publish_post("caption", "", image_url="https://example.com/a.jpg")
    assert result.success and result.published_url is None  # not a guessed instagram.com/p/123 link

    dry = pub.publish_post("caption", "", is_dry_run=True)
    assert dry.success and dry.published_url is None
